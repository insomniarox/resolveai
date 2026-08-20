"""Protect the frozen Phase 7.6 runtime causal-contract evaluation."""

import hashlib
import os
from pathlib import Path

import psycopg
import pytest

from evals import evaluate_runtime_ingestion as ingestion_evaluation
from evals.evaluate_runtime_contract import (
    CASES_PATH,
    RUNTIME_CONTRACT_CASES_SHA256,
    ContractDeterministicReport,
    ContractPressure,
    build_blind_review_items,
    evaluate_contract_deterministic_layer,
    load_contract_dataset,
    verify_contract_artifact_hashes,
    write_blind_review_packet,
)
from evals.evaluate_runtime_ingestion import (
    MetricScore,
    RuntimeRetrievalResult,
    evaluate_runtime_reasoning_cases,
)
from resolve_ai.models import Hypothesis, InvestigationStatus, ReasonerMetadata
from resolve_ai.reasoning import InsufficientEvidenceError
from resolve_ai.retrieval import populate_runbook_embeddings

PROJECT_ROOT = Path(__file__).parents[1]


def test_runtime_contract_dataset_is_frozen_and_preregistered() -> None:
    verify_contract_artifact_hashes()
    dataset = load_contract_dataset()

    assert hashlib.sha256(CASES_PATH.read_bytes()).hexdigest() == (
        RUNTIME_CONTRACT_CASES_SHA256
    )
    assert len(dataset.cases) == 4
    assert {pressure for case in dataset.cases for pressure in case.pressures} == set(
        ContractPressure
    )
    assert {case.ground_truth.expected_status for case in dataset.cases} == {
        InvestigationStatus.DIAGNOSED,
        InvestigationStatus.INCONCLUSIVE,
    }
    assert all(case.causal_contract.forbidden_claims for case in dataset.cases)


def test_contract_metrics_keep_ranking_and_safety_separate() -> None:
    dataset = load_contract_dataset()
    results = []
    for case in dataset.cases:
        required = [
            expectation.document_id
            for expectation in case.ground_truth.required_knowledge_documents
        ]
        distractors = list(case.ground_truth.distractor_document_ids)
        retrieved = (required + distractors)[:3]
        results.append(
            RuntimeRetrievalResult(
                case=case,
                retrieved_document_ids=retrieved,
                similarity_scores=[0.9 - index / 10 for index in range(len(retrieved))],
                retained_scope_rows=0,
            )
        )

    report = ContractDeterministicReport(
        retrieval_results=results,
        frozen_runbooks_before={"query": ["RUN-001"]},
        frozen_runbooks_after={"query": ["RUN-001"]},
    )

    assert report.runtime_document_top1_accuracy == MetricScore(1, 1)
    assert report.required_document_top3_recall == MetricScore(6, 6)
    assert report.retained_row_count == 0
    assert report.safety_gates_pass

    ranking_miss = results[1]
    results[1] = RuntimeRetrievalResult(
        case=ranking_miss.case,
        retrieved_document_ids=list(reversed(ranking_miss.retrieved_document_ids)),
        similarity_scores=list(reversed(ranking_miss.similarity_scores)),
        retained_scope_rows=0,
    )
    weaker_ranking = ContractDeterministicReport(
        retrieval_results=results,
        frozen_runbooks_before={"query": ["RUN-001"]},
        frozen_runbooks_after={"query": ["RUN-001"]},
    )

    assert weaker_ranking.runtime_document_top1_accuracy == MetricScore(0, 1)
    assert weaker_ranking.safety_gates_pass


def _replace_runtime_boundaries(monkeypatch) -> list:
    """Keep the shared live runner free of provider and database operations."""
    deleted_scopes = []
    monkeypatch.setattr(
        ingestion_evaluation,
        "store_runtime_knowledge_documents",
        lambda **kwargs: len(kwargs["documents"]),
    )
    monkeypatch.setattr(
        ingestion_evaluation,
        "delete_runtime_knowledge_scope",
        lambda database_url, scope_id: deleted_scopes.append(scope_id) or 3,
    )
    monkeypatch.setattr(
        ingestion_evaluation,
        "_count_runtime_scope_rows",
        lambda *args: 0,
    )
    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runbooks",
        lambda **kwargs: [],
    )
    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runtime_knowledge_documents",
        lambda **kwargs: [],
    )
    return deleted_scopes


def test_shared_live_runner_retains_prose_for_label_hidden_review(
    monkeypatch,
    tmp_path,
) -> None:
    deleted_scopes = _replace_runtime_boundaries(monkeypatch)
    dataset = load_contract_dataset()
    cases_by_incident = {case.bundle.incident.id: case for case in dataset.cases}

    def generate_expected_hypothesis(incident, evidence, retrieved_knowledge):
        case = cases_by_incident[incident.id]
        if case.ground_truth.expected_status == InvestigationStatus.INCONCLUSIVE:
            raise InsufficientEvidenceError("synthetic expected abstention")
        return Hypothesis(
            root_cause_label=case.ground_truth.expected_root_cause_label,
            probable_root_cause=(
                f"The failure affected {case.causal_contract.affected_component} "
                f"{case.causal_contract.failure_mode} "
                f"{case.causal_contract.operational_effect}"
            ),
            cited_evidence_ids=case.ground_truth.required_supporting_evidence_ids,
            confidence=0.9,
            recommended_remediation="Reverse the causal change after approval.",
        )

    results = evaluate_runtime_reasoning_cases(
        database_url="postgresql://not-used",
        cases=list(dataset.cases),
        hypothesis_generator=generate_expected_hypothesis,
        reasoner=ReasonerMetadata(provider="hidden-provider", model="hidden-model"),
        repeats=1,
    )
    review_items = build_blind_review_items(results, dataset)
    packet_path = tmp_path / "review.md"
    write_blind_review_packet(packet_path, review_items)
    packet = packet_path.read_text(encoding="utf-8")

    assert len(results) == 4
    assert len(deleted_scopes) == 4
    assert len(review_items) == 3
    assert all(item.probable_root_cause for item in review_items)
    assert "hidden-provider" not in packet
    assert "hidden-model" not in packet
    assert "expected_root_cause_label" not in packet
    assert not any(case.id in packet for case in dataset.cases)
    assert not any(
        case.ground_truth.expected_root_cause_label in packet
        for case in dataset.cases
        if case.ground_truth.expected_root_cause_label is not None
    )


@pytest.mark.integration
def test_real_runtime_contract_evaluation_preserves_safety_gates() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    initialization_sql = (PROJECT_ROOT / "database" / "init.sql").read_text(
        encoding="utf-8"
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(initialization_sql)
    populate_runbook_embeddings(database_url)

    report = evaluate_contract_deterministic_layer(
        database_url,
        load_contract_dataset(),
    )

    assert report.safety_gates_pass
    assert report.retained_row_count == 0
    assert report.frozen_runbooks_before == report.frozen_runbooks_after
