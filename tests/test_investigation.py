"""Exercise domain behavior directly, independently from FastAPI."""

from datetime import UTC, datetime

import pytest

from resolve_ai.fake_model import InsufficientEvidenceError, generate_hypothesis
from resolve_ai.fixtures import get_incident_context
from resolve_ai.investigation import (
    UnknownEvidenceError,
    inspect_deployments,
    inspect_logs,
    investigate_incident,
    verify_hypothesis,
)
from resolve_ai.models import (
    Evidence,
    EvidenceKind,
    EvidenceSource,
    Hypothesis,
    InvestigationStatus,
)


def _pool_change(
    evidence_id: str,
    observed_at: datetime,
    previous_value: int,
    new_value: int,
) -> Evidence:
    """Build concise pool-change evidence for temporal-rule tests."""
    return Evidence(
        id=evidence_id,
        source=EvidenceSource.DEPLOYMENT,
        kind=EvidenceKind.CONFIGURATION_CHANGE,
        observed_at=observed_at,
        summary=f"Pool size changed from {previous_value} to {new_value}.",
        details={
            "setting": "database_connection_pool_size",
            "previous_value": previous_value,
            "new_value": new_value,
        },
    )


def test_investigation_identifies_connection_pool_exhaustion() -> None:
    context = get_incident_context("INC-001")

    assert context is not None
    result = investigate_incident(context)

    assert result.incident_id == "INC-001"
    assert result.status == InvestigationStatus.DIAGNOSED
    assert result.diagnosis is not None
    assert "reduced the database connection pool from 20 to 5" in (
        result.diagnosis.probable_root_cause
    )
    assert [item.id for item in result.evidence] == [
        "LOG-001",
        "LOG-002",
        "DEP-001:database_connection_pool_size",
    ]
    assert result.diagnosis.supporting_evidence_ids == [
        "DEP-001:database_connection_pool_size",
        "LOG-001",
    ]
    assert result.diagnosis.human_approval_required is True


def test_investigation_is_inconclusive_when_no_rule_matches() -> None:
    context = get_incident_context("INC-003")

    assert context is not None
    result = investigate_incident(context)

    assert result.status == InvestigationStatus.INCONCLUSIVE
    assert result.diagnosis is None
    assert [item.id for item in result.evidence] == ["LOG-005"]


def test_fake_model_derives_values_and_citations_from_supplied_evidence() -> None:
    observed_at = datetime(2026, 8, 8, tzinfo=UTC)
    evidence = [
        Evidence(
            id="deployment-from-test",
            source=EvidenceSource.DEPLOYMENT,
            kind=EvidenceKind.CONFIGURATION_CHANGE,
            observed_at=observed_at,
            summary="A test deployment changed the pool size.",
            details={
                "setting": "database_connection_pool_size",
                "previous_value": 40,
                "new_value": 10,
            },
        ),
        Evidence(
            id="log-from-test",
            source=EvidenceSource.LOG,
            kind=EvidenceKind.DATABASE_CONNECTION_TIMEOUT,
            observed_at=observed_at,
            summary="A test connection timed out.",
        ),
    ]

    hypothesis = generate_hypothesis(evidence)

    assert "from 40 to 10" in hypothesis.probable_root_cause
    assert hypothesis.cited_evidence_ids == [
        "deployment-from-test",
        "log-from-test",
    ]
    assert hypothesis.recommended_remediation.endswith("to 40.")


def test_fake_model_ignores_old_reduction_after_pool_is_restored() -> None:
    old_reduction = _pool_change(
        "old-reduction",
        datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
        previous_value=20,
        new_value=5,
    )
    later_restoration = _pool_change(
        "later-restoration",
        datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        previous_value=5,
        new_value=20,
    )
    timeout = Evidence(
        id="timeout",
        source=EvidenceSource.LOG,
        kind=EvidenceKind.DATABASE_CONNECTION_TIMEOUT,
        observed_at=datetime(2026, 8, 8, 10, 37, tzinfo=UTC),
        summary="A database connection timed out.",
    )
    evidence = [old_reduction, timeout, later_restoration]
    original_order = [item.id for item in evidence]

    with pytest.raises(InsufficientEvidenceError):
        generate_hypothesis(evidence)

    assert [item.id for item in evidence] == original_order


def test_fake_model_uses_latest_reduction_independent_of_input_order() -> None:
    old_restoration = _pool_change(
        "old-restoration",
        datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
        previous_value=5,
        new_value=20,
    )
    latest_reduction = _pool_change(
        "latest-reduction",
        datetime(2026, 8, 8, 10, 0, tzinfo=UTC),
        previous_value=20,
        new_value=5,
    )
    timeout = Evidence(
        id="timeout",
        source=EvidenceSource.LOG,
        kind=EvidenceKind.DATABASE_CONNECTION_TIMEOUT,
        observed_at=datetime(2026, 8, 8, 10, 37, tzinfo=UTC),
        summary="A database connection timed out.",
    )
    chronological_evidence = [old_restoration, latest_reduction, timeout]
    reordered_evidence = [timeout, latest_reduction, old_restoration]

    chronological_hypothesis = generate_hypothesis(chronological_evidence)
    reordered_hypothesis = generate_hypothesis(reordered_evidence)

    expected_citations = ["latest-reduction", "timeout"]
    assert chronological_hypothesis.cited_evidence_ids == expected_citations
    assert reordered_hypothesis.cited_evidence_ids == expected_citations
    assert [item.id for item in reordered_evidence] == [
        "timeout",
        "latest-reduction",
        "old-restoration",
    ]


def test_fake_model_rejects_unrelated_evidence() -> None:
    evidence = [
        Evidence(
            id="LOG-UNRELATED",
            source=EvidenceSource.LOG,
            kind=EvidenceKind.HTTP_REQUEST_FAILED,
            observed_at=datetime(2026, 8, 8, tzinfo=UTC),
            summary="A request failed.",
        )
    ]

    with pytest.raises(InsufficientEvidenceError):
        generate_hypothesis(evidence)


def test_fake_model_derives_certificate_name_from_supplied_evidence() -> None:
    evidence = [
        Evidence(
            id="certificate-log-from-test",
            source=EvidenceSource.LOG,
            kind=EvidenceKind.AUTHENTICATION_CERTIFICATE_EXPIRED,
            observed_at=datetime(2026, 8, 8, tzinfo=UTC),
            summary="A test certificate expired.",
            details={"certificate_name": "checkout-api-client"},
        )
    ]

    hypothesis = generate_hypothesis(evidence)

    assert "checkout-api-client" in hypothesis.probable_root_cause
    assert hypothesis.cited_evidence_ids == ["certificate-log-from-test"]
    assert "checkout-api-client" in hypothesis.recommended_remediation


def test_verification_rejects_a_citation_that_does_not_exist() -> None:
    context = get_incident_context("INC-001")
    assert context is not None
    evidence = inspect_logs(context) + inspect_deployments(context)
    hypothesis = Hypothesis(
        probable_root_cause="An unverified cause.",
        cited_evidence_ids=["EVIDENCE-DOES-NOT-EXIST"],
        confidence=0.5,
        recommended_remediation="Review the incident manually.",
    )

    with pytest.raises(UnknownEvidenceError, match="EVIDENCE-DOES-NOT-EXIST"):
        verify_hypothesis(context.incident.id, hypothesis, evidence)


def test_verification_copies_ordered_lists_into_the_domain_result() -> None:
    context = get_incident_context("INC-001")
    assert context is not None
    evidence = inspect_logs(context) + inspect_deployments(context)
    hypothesis = Hypothesis(
        probable_root_cause="A test cause.",
        cited_evidence_ids=[
            "DEP-001:database_connection_pool_size",
            "LOG-001",
        ],
        confidence=0.5,
        recommended_remediation="Review the test configuration.",
    )

    result = verify_hypothesis(context.incident.id, hypothesis, evidence)

    assert result.diagnosis is not None
    assert result.diagnosis.supporting_evidence_ids is not hypothesis.cited_evidence_ids
    assert result.evidence is not evidence

    hypothesis.cited_evidence_ids.reverse()
    evidence.clear()

    assert result.diagnosis.supporting_evidence_ids == [
        "DEP-001:database_connection_pool_size",
        "LOG-001",
    ]
    assert [item.id for item in result.evidence] == [
        "LOG-001",
        "LOG-002",
        "DEP-001:database_connection_pool_size",
    ]
