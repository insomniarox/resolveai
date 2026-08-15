"""Exercise domain behavior directly, independently from FastAPI."""

from datetime import UTC, datetime

import pytest

from resolve_ai.fake_model import InsufficientEvidenceError, generate_hypothesis
from resolve_ai.fixtures import get_incident_context
from resolve_ai.investigation import (
    UnknownEvidenceError,
    build_runbook_query,
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
    RetrievedRunbook,
    RootCauseLabel,
)


def _retrieved_runbook(
    runbook_id: str,
    similarity_score: float,
) -> RetrievedRunbook:
    """Build concise retrieved knowledge for orchestration tests."""
    return RetrievedRunbook(
        id=runbook_id,
        title=f"Title for {runbook_id}",
        service="payment-service",
        content=f"Content for {runbook_id}",
        similarity_score=similarity_score,
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


def test_investigation_includes_ordered_runbooks_without_citing_them(
    monkeypatch,
) -> None:
    context = get_incident_context("INC-001")
    retrieved_runbooks = [
        _retrieved_runbook("RUN-004", 0.81),
        _retrieved_runbook("RUN-001", 0.79),
    ]
    search_call: dict[str, str | int] = {}

    def fake_semantic_search(
        database_url: str,
        query: str,
        limit: int,
    ) -> list[RetrievedRunbook]:
        search_call.update(
            database_url=database_url,
            query=query,
            limit=limit,
        )
        return retrieved_runbooks

    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runbooks",
        fake_semantic_search,
    )

    assert context is not None
    result = investigate_incident(context, database_url="postgresql://test")

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
    assert [runbook.id for runbook in result.retrieved_runbooks] == [
        "RUN-004",
        "RUN-001",
    ]
    assert search_call == {
        "database_url": "postgresql://test",
        "query": build_runbook_query(context, result.evidence),
        "limit": 3,
    }
    assert not {"RUN-004", "RUN-001"} & {item.id for item in result.evidence}
    assert not {"RUN-004", "RUN-001"} & set(result.diagnosis.supporting_evidence_ids)
    assert result.diagnosis.human_approval_required is True


def test_inconclusive_investigation_still_contains_retrieved_knowledge(
    monkeypatch,
) -> None:
    context = get_incident_context("INC-003")
    retrieved_runbooks = [_retrieved_runbook("RUN-003", 0.72)]
    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runbooks",
        lambda database_url, query, limit: retrieved_runbooks,
    )

    assert context is not None
    result = investigate_incident(context, database_url="postgresql://test")

    assert result.status == InvestigationStatus.INCONCLUSIVE
    assert result.diagnosis is None
    assert [item.id for item in result.evidence] == ["LOG-005"]
    assert [runbook.id for runbook in result.retrieved_runbooks] == ["RUN-003"]


def test_runbook_query_is_deterministic_and_uses_reported_and_observed_facts() -> None:
    context = get_incident_context("INC-001")
    assert context is not None
    evidence = inspect_logs(context) + inspect_deployments(context)

    query = build_runbook_query(context, evidence)

    assert query == (
        "Incident: Payments API returning HTTP 500 responses\n"
        "Description: Payment requests began failing after the morning deployment.\n"
        "Observed evidence:\n"
        "- Timed out while acquiring a database connection.\n"
        "- POST /payments completed with HTTP 500.\n"
        "- Deployment DEP-001 changed database_connection_pool_size from 20 to 5."
    )
    assert "INC-001" not in query


def test_changing_retrieved_candidates_does_not_change_diagnosis(monkeypatch) -> None:
    context = get_incident_context("INC-001")
    assert context is not None
    candidates = [_retrieved_runbook("RUN-001", 0.9)]

    def fake_semantic_search(
        database_url: str,
        query: str,
        limit: int,
    ) -> list[RetrievedRunbook]:
        return list(candidates)

    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runbooks",
        fake_semantic_search,
    )
    first_result = investigate_incident(context, database_url="postgresql://test")

    candidates[:] = [_retrieved_runbook("RUN-004", 0.99)]
    second_result = investigate_incident(context, database_url="postgresql://test")

    assert first_result.diagnosis == second_result.diagnosis
    assert [item.id for item in first_result.retrieved_runbooks] == ["RUN-001"]
    assert [item.id for item in second_result.retrieved_runbooks] == ["RUN-004"]


def test_investigation_passes_incident_evidence_and_runbooks_to_reasoner(
    monkeypatch,
) -> None:
    context = get_incident_context("INC-001")
    assert context is not None
    runbooks = [_retrieved_runbook("RUN-001", 0.9)]
    received: dict = {}

    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runbooks",
        lambda database_url, query, limit: runbooks,
    )

    def reasoner(incident, evidence, retrieved_runbooks):
        received.update(
            incident=incident,
            evidence=evidence,
            retrieved_runbooks=retrieved_runbooks,
        )
        return Hypothesis(
            root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
            probable_root_cause="The observed pool reduction caused timeouts.",
            cited_evidence_ids=[
                "DEP-001:database_connection_pool_size",
                "LOG-001",
            ],
            confidence=0.8,
            recommended_remediation="Restore the previous pool size.",
        )

    result = investigate_incident(
        context,
        database_url="postgresql://test",
        hypothesis_generator=reasoner,
    )

    assert received["incident"] == context.incident
    assert [item.id for item in received["evidence"]] == [
        "LOG-001",
        "LOG-002",
        "DEP-001:database_connection_pool_size",
    ]
    assert received["retrieved_runbooks"] == runbooks
    assert result.diagnosis is not None
    assert (
        result.diagnosis.root_cause_label == RootCauseLabel.CONNECTION_POOL_EXHAUSTION
    )
    assert result.diagnosis.probable_root_cause == (
        "The observed pool reduction caused timeouts."
    )


def test_retrieval_failure_is_not_mislabeled_as_inconclusive(monkeypatch) -> None:
    context = get_incident_context("INC-003")
    assert context is not None

    def fail_semantic_search(
        database_url: str,
        query: str,
        limit: int,
    ) -> list[RetrievedRunbook]:
        raise ConnectionError("PostgreSQL retrieval failed")

    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runbooks",
        fail_semantic_search,
    )

    with pytest.raises(ConnectionError, match="PostgreSQL retrieval failed"):
        investigate_incident(context, database_url="postgresql://test")


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
        root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
        probable_root_cause="An unverified cause.",
        cited_evidence_ids=["EVIDENCE-DOES-NOT-EXIST"],
        confidence=0.5,
        recommended_remediation="Review the incident manually.",
    )

    with pytest.raises(UnknownEvidenceError, match="EVIDENCE-DOES-NOT-EXIST"):
        verify_hypothesis(context.incident.id, hypothesis, evidence, [])


def test_verification_copies_ordered_lists_into_the_domain_result() -> None:
    context = get_incident_context("INC-001")
    assert context is not None
    evidence = inspect_logs(context) + inspect_deployments(context)
    hypothesis = Hypothesis(
        root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
        probable_root_cause="A test cause.",
        cited_evidence_ids=[
            "DEP-001:database_connection_pool_size",
            "LOG-001",
        ],
        confidence=0.5,
        recommended_remediation="Review the test configuration.",
    )

    retrieved_runbooks = [
        _retrieved_runbook("RUN-004", 0.8),
        _retrieved_runbook("RUN-001", 0.7),
    ]
    result = verify_hypothesis(
        context.incident.id,
        hypothesis,
        evidence,
        retrieved_runbooks,
    )

    assert result.diagnosis is not None
    assert result.diagnosis.supporting_evidence_ids is not hypothesis.cited_evidence_ids
    assert result.evidence is not evidence
    assert result.retrieved_runbooks is not retrieved_runbooks

    hypothesis.cited_evidence_ids.reverse()
    evidence.clear()
    retrieved_runbooks.reverse()

    assert result.diagnosis.supporting_evidence_ids == [
        "DEP-001:database_connection_pool_size",
        "LOG-001",
    ]
    assert [item.id for item in result.evidence] == [
        "LOG-001",
        "LOG-002",
        "DEP-001:database_connection_pool_size",
    ]
    assert [item.id for item in result.retrieved_runbooks] == ["RUN-004", "RUN-001"]
