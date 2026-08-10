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
)


def test_investigation_identifies_connection_pool_exhaustion() -> None:
    context = get_incident_context("INC-001")

    assert context is not None
    result = investigate_incident(context)

    assert result.incident_id == "INC-001"
    assert "reduced the database connection pool from 20 to 5" in (
        result.probable_root_cause
    )
    assert {item.id for item in result.evidence} == {
        "DEP-001:database_connection_pool_size",
        "LOG-001",
    }
    assert result.human_approval_required is True


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
