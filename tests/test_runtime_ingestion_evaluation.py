"""Protect the frozen Phase 7.4 runtime-ingestion evaluation slice."""

import hashlib
import os
from pathlib import Path

import psycopg
import pytest

from evals import evaluate_runtime_ingestion as evaluation
from evals.evaluate_runtime_ingestion import (
    CASES_PATH,
    LEGACY_ARTIFACT_SHA256,
    RUNTIME_INGESTION_CASES_SHA256,
    ReasoningOutcome,
    RuntimeReasoningResult,
    _completed_reasoning_outcome,
    calculate_reasoning_metrics,
    evaluate_deterministic_layer,
    evaluate_malformed_bundles,
    evaluate_runtime_reasoning,
    load_dataset,
    verify_frozen_artifact_hashes,
)
from resolve_ai.investigation import verify_hypothesis
from resolve_ai.models import (
    Hypothesis,
    InvestigationStatus,
    ReasonerMetadata,
)
from resolve_ai.retrieval import populate_runbook_embeddings

PROJECT_ROOT = Path(__file__).parents[1]


def test_runtime_ingestion_dataset_is_frozen_and_covers_planned_pressures() -> None:
    dataset = load_dataset()

    assert hashlib.sha256(CASES_PATH.read_bytes()).hexdigest() == (
        RUNTIME_INGESTION_CASES_SHA256
    )
    assert len(dataset.valid_cases) == 5
    assert len(dataset.malformed_cases) == 5
    assert {case.ground_truth.expected_status for case in dataset.valid_cases} == {
        InvestigationStatus.DIAGNOSED,
        InvestigationStatus.INCONCLUSIVE,
    }
    assert any(
        not case.ground_truth.required_knowledge_documents
        for case in dataset.valid_cases
    )
    assert any(
        case.ground_truth.expected_inconclusive_reason for case in dataset.valid_cases
    )


def test_legacy_evaluation_artifacts_remain_byte_for_byte_frozen() -> None:
    verify_frozen_artifact_hashes()

    for filename, expected_digest in LEGACY_ARTIFACT_SHA256.items():
        artifact = PROJECT_ROOT / "evals" / filename
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == expected_digest


def test_malformed_bundles_are_rejected_without_storage_or_inference() -> None:
    results = evaluate_malformed_bundles(load_dataset())

    assert len(results) == 5
    assert all(result.rejected for result in results)
    assert all(result.expected_error_found for result in results)


def test_reasoning_metrics_keep_denominators_and_citation_boundaries_visible() -> None:
    dataset = load_dataset()
    diagnosed_case = dataset.case_by_id("runtime-ingestion-direct-retrieval")
    inconclusive_case = dataset.case_by_id("runtime-ingestion-insufficient-evidence")
    diagnosed_citations = list(
        diagnosed_case.ground_truth.required_supporting_evidence_ids
    )
    results = [
        RuntimeReasoningResult(
            case=diagnosed_case,
            repeat=1,
            provider="test",
            model="test-model",
            actual_status=InvestigationStatus.DIAGNOSED,
            predicted_root_cause_label=(
                diagnosed_case.ground_truth.expected_root_cause_label
            ),
            attempted_citation_ids=diagnosed_citations,
            accepted_citation_ids=diagnosed_citations,
            retrieved_document_ids=["RUNTIME-DOC-741-A"],
            outcome=ReasoningOutcome.CORRECT_ANSWER,
            retained_scope_rows=0,
        ),
        RuntimeReasoningResult(
            case=inconclusive_case,
            repeat=1,
            provider="test",
            model="test-model",
            actual_status=InvestigationStatus.INCONCLUSIVE,
            predicted_root_cause_label=None,
            attempted_citation_ids=[],
            accepted_citation_ids=[],
            retrieved_document_ids=["RUNTIME-DOC-744-A"],
            outcome=ReasoningOutcome.CORRECT_INCONCLUSIVE,
            retained_scope_rows=0,
        ),
    ]

    metrics = calculate_reasoning_metrics(results)

    assert metrics.status_accuracy == evaluation.MetricScore(2, 2)
    assert metrics.root_cause_accuracy == evaluation.MetricScore(1, 1)
    assert metrics.evidence_citation_precision == evaluation.MetricScore(2, 2)
    assert metrics.evidence_citation_recall == evaluation.MetricScore(2, 2)
    assert metrics.correct_abstention_rate == evaluation.MetricScore(1, 1)
    assert metrics.repeat_agreement == evaluation.MetricScore(2, 2)
    assert metrics.accepted_unsupported_citation_count == 0


def test_completed_reasoning_classification_requires_the_frozen_label_and_support() -> (
    None
):
    case = load_dataset().case_by_id("runtime-ingestion-direct-retrieval")
    _, evidence, _ = case.bundle.to_domain()
    required_citations = case.ground_truth.required_supporting_evidence_ids
    hypothesis = Hypothesis(
        root_cause_label=case.ground_truth.expected_root_cause_label,
        probable_root_cause="The rollout selected an undersized database profile.",
        cited_evidence_ids=required_citations,
        confidence=0.9,
        recommended_remediation="Restore the previous profile after approval.",
    )
    result = verify_hypothesis(
        incident_id=case.bundle.incident.id,
        hypothesis=hypothesis,
        evidence=evidence,
        retrieved_runbooks=[],
    )

    assert _completed_reasoning_outcome(case, result) == (
        ReasoningOutcome.CORRECT_ANSWER
    )

    incomplete_result = result.model_copy(deep=True)
    incomplete_result.diagnosis.supporting_evidence_ids = required_citations[:1]
    assert _completed_reasoning_outcome(case, incomplete_result) == (
        ReasoningOutcome.INCORRECT_ANSWER
    )


def _replace_database_boundaries(monkeypatch) -> list:
    """Keep live-layer unit tests deterministic and provider/database free."""
    deleted_scopes = []
    monkeypatch.setattr(
        evaluation,
        "store_runtime_knowledge_documents",
        lambda **kwargs: len(kwargs["documents"]),
    )
    monkeypatch.setattr(
        evaluation,
        "delete_runtime_knowledge_scope",
        lambda database_url, scope_id: deleted_scopes.append(scope_id) or 3,
    )
    monkeypatch.setattr(evaluation, "_count_runtime_scope_rows", lambda *args: 0)
    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runbooks",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runtime_knowledge_documents",
        lambda **kwargs: [],
    )
    return deleted_scopes


def test_live_layer_retains_reasoner_failures_and_cleans_every_scope(
    monkeypatch,
) -> None:
    deleted_scopes = _replace_database_boundaries(monkeypatch)

    def fail_reasoning(incident, evidence, retrieved_knowledge):
        raise RuntimeError("synthetic provider failure")

    results = evaluate_runtime_reasoning(
        database_url="postgresql://not-used",
        dataset=load_dataset(),
        hypothesis_generator=fail_reasoning,
        reasoner=ReasonerMetadata(provider="test", model="test-model"),
        repeats=1,
    )

    assert len(results) == 5
    assert len(deleted_scopes) == 5
    assert all(result.outcome == ReasoningOutcome.SYSTEM_FAILURE for result in results)
    assert all(result.retained_scope_rows == 0 for result in results)
    assert all("synthetic provider failure" in result.error for result in results)


def test_live_layer_records_document_citation_attempts_but_accepts_none(
    monkeypatch,
) -> None:
    deleted_scopes = _replace_database_boundaries(monkeypatch)

    def cite_untrusted_document(incident, evidence, retrieved_knowledge):
        case = next(
            case
            for case in load_dataset().valid_cases
            if case.bundle.incident.id == incident.id
        )
        return Hypothesis(
            root_cause_label="untrusted_document_claim",
            probable_root_cause="An untrusted document supplied the claim.",
            cited_evidence_ids=[case.bundle.knowledge_documents[0].id],
            confidence=0.5,
            recommended_remediation="Collect real operational Evidence.",
        )

    results = evaluate_runtime_reasoning(
        database_url="postgresql://not-used",
        dataset=load_dataset(),
        hypothesis_generator=cite_untrusted_document,
        reasoner=ReasonerMetadata(provider="test", model="test-model"),
        repeats=1,
    )
    metrics = calculate_reasoning_metrics(results)

    assert len(deleted_scopes) == 5
    assert all(
        result.outcome == ReasoningOutcome.UNSUPPORTED_ANSWER for result in results
    )
    assert metrics.unsupported_citation_count == 5
    assert metrics.attempted_knowledge_document_citation_count == 5
    assert metrics.accepted_unsupported_citation_count == 0
    assert all(not result.accepted_citation_ids for result in results)


@pytest.mark.integration
def test_real_runtime_ingestion_evaluation_passes_deterministic_safety_gates() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    initialization_sql = (PROJECT_ROOT / "database" / "init.sql").read_text(
        encoding="utf-8"
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(initialization_sql)
    populate_runbook_embeddings(database_url)

    report = evaluate_deterministic_layer(database_url, load_dataset())

    assert report.safety_gates_pass
    assert report.malformed_rejection_rate == evaluation.MetricScore(5, 5)
    assert report.scope_isolation.leaked_document_ids == []
    assert report.retained_row_count == 0
    assert report.frozen_runbooks_before == report.frozen_runbooks_after
