"""Verify investigation benchmark parsing, outcomes, and metric arithmetic."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evals import evaluate_investigations as evaluation
from evals.evaluate_investigations import (
    CaseOutcome,
    InvestigationCaseResult,
    InvestigationGroundTruth,
    calculate_metrics,
    classify_completed_result,
    load_cases,
)
from resolve_ai.fixtures import get_incident_context
from resolve_ai.investigation import (
    UnknownEvidenceError,
    inspect_deployments,
    inspect_logs,
)
from resolve_ai.models import (
    Diagnosis,
    Hypothesis,
    InvestigationResult,
    InvestigationStatus,
    RetrievedRunbook,
    RootCauseLabel,
)

CASES_PATH = Path(__file__).parents[1] / "evals" / "investigation_cases.json"


def _diagnosed_result(
    incident_id: str,
    cited_evidence_ids: list[str],
    root_cause_label: RootCauseLabel = RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
) -> InvestigationResult:
    """Build model-shaped output for deterministic evaluator tests."""
    return InvestigationResult(
        incident_id=incident_id,
        status=InvestigationStatus.DIAGNOSED,
        diagnosis=Diagnosis(
            root_cause_label=root_cause_label,
            probable_root_cause="Synthetic diagnosis used by a metric test.",
            confidence=0.8,
            recommended_remediation="Synthetic remediation.",
            human_approval_required=True,
            supporting_evidence_ids=cited_evidence_ids,
        ),
        evidence=[],
        retrieved_runbooks=[],
    )


def test_loads_seven_frozen_cases_and_preserves_phase_one_contexts() -> None:
    cases = load_cases(CASES_PATH)

    assert len(cases) == 7
    assert [case.context.incident.id for case in cases] == [
        "INC-001",
        "INC-002",
        "INC-003",
        "INC-004",
        "INC-005",
        "INC-006",
        "INC-007",
    ]
    for case in cases[:3]:
        existing_context = get_incident_context(case.context.incident.id)
        assert existing_context is not None
        assert case.context == existing_context

    provider_truth = cases[5].ground_truth
    assert provider_truth.required_supporting_evidence_ids == ["LOG-011", "LOG-012"]
    assert provider_truth.acceptable_supporting_evidence_ids == [
        "LOG-011",
        "LOG-012",
        "LOG-013",
    ]
    worker_truth = cases[6].ground_truth
    assert worker_truth.required_supporting_evidence_ids == ["LOG-014", "LOG-015"]
    assert worker_truth.acceptable_supporting_evidence_ids == [
        "LOG-014",
        "LOG-015",
        "LOG-016",
    ]
    assert (
        sum(len(case.ground_truth.required_supporting_evidence_ids) for case in cases)
        == 10
    )


def test_ground_truth_rejects_required_evidence_that_is_not_acceptable() -> None:
    with pytest.raises(
        ValidationError,
        match="required supporting evidence must also be acceptable",
    ):
        InvestigationGroundTruth.model_validate(
            {
                "expected_status": "diagnosed",
                "root_cause_label": "database_lock_contention",
                "required_supporting_evidence_ids": ["LOG-required"],
                "acceptable_supporting_evidence_ids": [],
                "relevant_runbook_ids": ["RUN-004"],
                "remediation_label": (
                    "resolve_blocking_transaction_and_reduce_transaction_scope"
                ),
                "prohibited_root_cause_labels": [],
            }
        )


def test_optional_differential_evidence_is_accepted_but_not_required() -> None:
    provider_case = load_cases(CASES_PATH)[5]

    with_optional_context = _diagnosed_result(
        "INC-006",
        ["LOG-011", "LOG-012", "LOG-013"],
        RootCauseLabel.NOTIFICATION_PROVIDER_OUTAGE,
    )
    assert (
        classify_completed_result(
            provider_case,
            with_optional_context,
            RootCauseLabel.NOTIFICATION_PROVIDER_OUTAGE,
        )
        == CaseOutcome.CORRECT_ANSWER
    )

    missing_required = _diagnosed_result(
        "INC-006",
        ["LOG-011", "LOG-013"],
        RootCauseLabel.NOTIFICATION_PROVIDER_OUTAGE,
    )
    assert (
        classify_completed_result(
            provider_case,
            missing_required,
            RootCauseLabel.NOTIFICATION_PROVIDER_OUTAGE,
        )
        == CaseOutcome.INCORRECT_ANSWER
    )


def test_outcomes_distinguish_extraneous_from_unsupported_citations() -> None:
    pool_case = load_cases(CASES_PATH)[0]
    required_ids = ["DEP-001:database_connection_pool_size", "LOG-001"]

    acceptable = _diagnosed_result("INC-001", required_ids)
    assert (
        classify_completed_result(
            pool_case,
            acceptable,
            RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
        )
        == CaseOutcome.CORRECT_ANSWER
    )
    acceptable_case_result = InvestigationCaseResult(
        case=pool_case,
        actual_status=InvestigationStatus.DIAGNOSED,
        predicted_root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
        cited_evidence_ids=required_ids,
        outcome=CaseOutcome.CORRECT_ANSWER,
    )
    assert acceptable_case_result.citation_precision == 1
    assert acceptable_case_result.citation_recall == 1

    extraneous = _diagnosed_result("INC-001", [*required_ids, "LOG-002"])
    assert (
        classify_completed_result(
            pool_case,
            extraneous,
            RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
        )
        == CaseOutcome.CORRECT_WITH_EXTRANEOUS_EVIDENCE
    )
    extraneous_case_result = InvestigationCaseResult(
        case=pool_case,
        actual_status=InvestigationStatus.DIAGNOSED,
        predicted_root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
        cited_evidence_ids=[*required_ids, "LOG-002"],
        outcome=CaseOutcome.CORRECT_WITH_EXTRANEOUS_EVIDENCE,
    )
    assert extraneous_case_result.citation_precision == pytest.approx(2 / 3)
    assert extraneous_case_result.citation_recall == 1
    assert extraneous_case_result.unsupported_citation_ids == []

    unsupported = _diagnosed_result("INC-001", [*required_ids, "LOG-999"])
    assert (
        classify_completed_result(
            pool_case,
            unsupported,
            RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
        )
        == CaseOutcome.UNSUPPORTED_ANSWER
    )
    unsupported_case_result = InvestigationCaseResult(
        case=pool_case,
        actual_status=InvestigationStatus.DIAGNOSED,
        predicted_root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
        cited_evidence_ids=[*required_ids, "LOG-999"],
        outcome=CaseOutcome.UNSUPPORTED_ANSWER,
    )
    assert unsupported_case_result.unsupported_citation_ids == ["LOG-999"]


def test_incorrect_root_cause_with_valid_evidence_has_no_citation_score() -> None:
    pool_case = load_cases(CASES_PATH)[0]
    required_ids = ["DEP-001:database_connection_pool_size", "LOG-001"]
    result = _diagnosed_result(
        "INC-001",
        required_ids,
        RootCauseLabel.DATABASE_LOCK_CONTENTION,
    )

    outcome = classify_completed_result(
        pool_case,
        result,
        RootCauseLabel.DATABASE_LOCK_CONTENTION,
    )
    case_result = InvestigationCaseResult(
        case=pool_case,
        actual_status=InvestigationStatus.DIAGNOSED,
        predicted_root_cause_label=RootCauseLabel.DATABASE_LOCK_CONTENTION,
        cited_evidence_ids=required_ids,
        outcome=outcome,
    )

    assert outcome == CaseOutcome.INCORRECT_ANSWER
    assert case_result.citation_precision is None
    assert case_result.citation_recall is None
    assert case_result.unsupported_citation_ids == []


def test_incorrect_root_cause_keeps_unknown_citation_independently_visible() -> None:
    pool_case = load_cases(CASES_PATH)[0]
    cited_ids = ["LOG-001", "LOG-999"]
    result = _diagnosed_result(
        "INC-001",
        cited_ids,
        RootCauseLabel.DATABASE_LOCK_CONTENTION,
    )

    outcome = classify_completed_result(
        pool_case,
        result,
        RootCauseLabel.DATABASE_LOCK_CONTENTION,
    )
    case_result = InvestigationCaseResult(
        case=pool_case,
        actual_status=InvestigationStatus.DIAGNOSED,
        predicted_root_cause_label=RootCauseLabel.DATABASE_LOCK_CONTENTION,
        cited_evidence_ids=cited_ids,
        outcome=outcome,
    )

    assert outcome == CaseOutcome.INCORRECT_ANSWER
    assert case_result.citation_precision is None
    assert case_result.citation_recall is None
    assert case_result.unsupported_citation_ids == ["LOG-999"]


def test_metrics_use_acceptable_precision_and_required_recall() -> None:
    pool_case, _, ambiguous_case, lock_case = load_cases(CASES_PATH)[:4]
    results = [
        InvestigationCaseResult(
            case=pool_case,
            actual_status=InvestigationStatus.DIAGNOSED,
            predicted_root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
            cited_evidence_ids=[
                "DEP-001:database_connection_pool_size",
                "LOG-001",
            ],
            outcome=CaseOutcome.CORRECT_ANSWER,
        ),
        InvestigationCaseResult(
            case=ambiguous_case,
            actual_status=InvestigationStatus.DIAGNOSED,
            predicted_root_cause_label=RootCauseLabel.NOTIFICATION_PROVIDER_OUTAGE,
            cited_evidence_ids=["LOG-005"],
            outcome=CaseOutcome.UNSUPPORTED_ANSWER,
        ),
        InvestigationCaseResult(
            case=lock_case,
            actual_status=None,
            predicted_root_cause_label=None,
            cited_evidence_ids=[],
            outcome=CaseOutcome.SYSTEM_FAILURE,
            error="ConnectionError: database unavailable",
        ),
    ]

    metrics = calculate_metrics(results)

    assert metrics.status_accuracy.numerator == 1
    assert metrics.status_accuracy.denominator == 3
    assert metrics.root_cause_accuracy.numerator == 1
    assert metrics.root_cause_accuracy.denominator == 2
    assert metrics.evidence_citation_precision.numerator == 2
    assert metrics.evidence_citation_precision.denominator == 2
    assert metrics.evidence_citation_recall.numerator == 2
    assert metrics.evidence_citation_recall.denominator == 2


def test_evaluation_records_system_failure_and_continues(monkeypatch) -> None:
    pool_case, _, ambiguous_case = load_cases(CASES_PATH)[:3]

    def fake_investigation(context, database_url, hypothesis_generator):
        if context.incident.id == "INC-001":
            raise ConnectionError("database unavailable")
        return InvestigationResult(
            incident_id=context.incident.id,
            status=InvestigationStatus.INCONCLUSIVE,
            diagnosis=None,
            evidence=[],
            retrieved_runbooks=[],
        )

    monkeypatch.setattr(evaluation, "investigate_incident", fake_investigation)

    results = evaluation.evaluate_cases(
        "postgresql://test",
        [pool_case, ambiguous_case],
    )

    assert [result.outcome for result in results] == [
        CaseOutcome.SYSTEM_FAILURE,
        CaseOutcome.CORRECT_INCONCLUSIVE,
    ]
    assert results[0].error == "ConnectionError: database unavailable"


def test_evaluation_records_unverifiable_model_citation_as_unsupported(
    monkeypatch,
) -> None:
    pool_case = load_cases(CASES_PATH)[0]

    def fake_investigation(context, database_url, hypothesis_generator):
        hypothesis_generator(
            context.incident,
            inspect_logs(context) + inspect_deployments(context),
            [],
        )
        raise UnknownEvidenceError("Hypothesis cited unknown evidence: LOG-999")

    def unsupported_reasoner(incident, evidence, retrieved_runbooks):
        return Hypothesis(
            root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
            probable_root_cause="The pool was exhausted.",
            cited_evidence_ids=["LOG-001", "LOG-999"],
            confidence=0.8,
            recommended_remediation="Restore pool capacity.",
        )

    monkeypatch.setattr(evaluation, "investigate_incident", fake_investigation)

    result = evaluation.evaluate_cases(
        "postgresql://test",
        [pool_case],
        hypothesis_generator=unsupported_reasoner,
    )[0]

    assert result.outcome == CaseOutcome.UNSUPPORTED_ANSWER
    assert result.actual_status == InvestigationStatus.DIAGNOSED
    assert result.cited_evidence_ids == ["LOG-001", "LOG-999"]
    assert result.unsupported_citation_ids == ["LOG-999"]


def test_evaluation_keeps_wrong_diagnosis_incorrect_with_unknown_citation(
    monkeypatch,
) -> None:
    pool_case = load_cases(CASES_PATH)[0]

    def fake_investigation(context, database_url, hypothesis_generator):
        hypothesis_generator(
            context.incident,
            inspect_logs(context) + inspect_deployments(context),
            [],
        )
        raise UnknownEvidenceError("Hypothesis cited unknown evidence: LOG-999")

    def wrong_unsupported_reasoner(incident, evidence, retrieved_runbooks):
        return Hypothesis(
            root_cause_label=RootCauseLabel.DATABASE_LOCK_CONTENTION,
            probable_root_cause="A transaction is holding a required lock.",
            cited_evidence_ids=["LOG-001", "LOG-999"],
            confidence=0.8,
            recommended_remediation="Inspect blocking transactions.",
        )

    monkeypatch.setattr(evaluation, "investigate_incident", fake_investigation)

    result = evaluation.evaluate_cases(
        "postgresql://test",
        [pool_case],
        hypothesis_generator=wrong_unsupported_reasoner,
    )[0]

    assert result.outcome == CaseOutcome.INCORRECT_ANSWER
    assert result.citation_precision is None
    assert result.citation_recall is None
    assert result.unsupported_citation_ids == ["LOG-999"]


def test_evaluation_can_withhold_runbooks_only_from_reasoner(monkeypatch) -> None:
    ambiguous_case = load_cases(CASES_PATH)[2]
    retrieved_runbooks = [
        RetrievedRunbook(
            id="RUN-003",
            title="Notification delivery failures",
            service="notification-service",
            content="Synthetic runbook content.",
            similarity_score=0.9,
        )
    ]
    received_runbooks: list[RetrievedRunbook] | None = None

    def fake_investigation(context, database_url, hypothesis_generator):
        hypothesis_generator(context.incident, [], retrieved_runbooks)
        return InvestigationResult(
            incident_id=context.incident.id,
            status=InvestigationStatus.INCONCLUSIVE,
            diagnosis=None,
            evidence=[],
            retrieved_runbooks=retrieved_runbooks,
        )

    def reasoner(incident, evidence, runbooks):
        nonlocal received_runbooks
        received_runbooks = runbooks
        return Hypothesis(
            root_cause_label=RootCauseLabel.NOTIFICATION_PROVIDER_OUTAGE,
            probable_root_cause="Synthetic hypothesis.",
            cited_evidence_ids=["LOG-005"],
            confidence=0.5,
            recommended_remediation="Inspect the notification path.",
        )

    monkeypatch.setattr(evaluation, "investigate_incident", fake_investigation)

    evaluation.evaluate_cases(
        "postgresql://test",
        [ambiguous_case],
        hypothesis_generator=reasoner,
        runbooks_enabled=False,
    )

    assert received_runbooks == []


def test_report_includes_reasoner_and_model_identity(capsys) -> None:
    ambiguous_case = load_cases(CASES_PATH)[2]
    result = InvestigationCaseResult(
        case=ambiguous_case,
        actual_status=InvestigationStatus.INCONCLUSIVE,
        predicted_root_cause_label=None,
        cited_evidence_ids=[],
        outcome=CaseOutcome.CORRECT_INCONCLUSIVE,
    )

    evaluation.print_report(
        [result],
        reasoner_name="openai",
        model_name="model-snapshot",
        runbooks_enabled=False,
    )

    output = capsys.readouterr().out
    assert "Reasoner: openai" in output
    assert "Model: model-snapshot" in output
    assert "Runbooks: disabled" in output
