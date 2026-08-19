"""Exercise the public HTTP contract without starting a real network server."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import Request
from openai import APITimeoutError

from resolve_ai import api, runtime_investigation
from resolve_ai.api import app
from resolve_ai.fake_model import generate_fake_hypothesis
from resolve_ai.investigation_runs import (
    CreatedInvestigationRun,
    InvestigationRun,
    InvestigationRunOutcome,
)
from resolve_ai.models import (
    Hypothesis,
    ReasonerMetadata,
    RetrievedKnowledgeDocument,
    RetrievedRunbook,
)
from resolve_ai.retrieval import RuntimeKnowledgeError
from resolve_ai.runtime_reasoner import (
    ConfiguredRuntimeReasoner,
    RuntimeReasonerConfigurationError,
)

client = TestClient(app)


def _runtime_bundle() -> dict:
    """Build one novel bundle that matches the deterministic pool pattern."""
    return {
        "schema_version": 1,
        "incident": {
            "id": "USER-INC-901",
            "title": "Checkout requests timing out",
            "description": "A previously unseen checkout service is degraded.",
            "service": "checkout-runtime-service",
            "started_at": "2026-08-17T09:00:00Z",
        },
        "evidence": [
            {
                "id": "USER-DEP-901:database_connection_pool_size",
                "source": "deployment",
                "kind": "configuration_change",
                "observed_at": "2026-08-17T08:55:00Z",
                "summary": "A runtime deployment reduced the connection pool.",
                "details": {
                    "setting": "database_connection_pool_size",
                    "previous_value": 30,
                    "new_value": 6,
                },
            },
            {
                "id": "USER-LOG-901",
                "source": "log",
                "kind": "database_connection_timeout",
                "observed_at": "2026-08-17T09:00:10Z",
                "summary": "Checkout timed out while acquiring a connection.",
                "details": {},
            },
            {
                "id": "USER-LOG-902",
                "source": "log",
                "kind": "http_request_failed",
                "observed_at": "2026-08-17T09:00:11Z",
                "summary": "POST /checkout returned HTTP 500.",
                "details": {"status_code": 500},
            },
        ],
    }


def _add_runtime_document(bundle: dict) -> None:
    """Add one bounded request-scoped document to a runtime bundle."""
    bundle["knowledge_documents"] = [
        {
            "id": "DOC-901",
            "title": "Checkout session lifecycle",
            "content_type": "text/markdown",
            "content": "A checkout waits when every reusable session is assigned.",
        }
    ]


def _created_run(snapshot, token: str = "capability-token-with-enough-entropy"):
    """Build the storage result returned to API tests after execution."""
    created_at = datetime(2026, 8, 19, 10, 0, tzinfo=UTC)
    outcome = (
        InvestigationRunOutcome.COMPLETED
        if snapshot.investigation_result is not None
        else InvestigationRunOutcome.FAILED
    )
    return CreatedInvestigationRun(
        run=InvestigationRun(
            id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            created_at=created_at,
            expires_at=created_at + timedelta(hours=1),
            outcome=outcome,
            snapshot=snapshot,
        ),
        capability_token=token,
    )


@pytest.fixture(autouse=True)
def configure_test_retrieval(monkeypatch) -> None:
    """Keep API contract tests deterministic without requiring PostgreSQL."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")
    retrieved_runbooks = [
        RetrievedRunbook(
            id="RUN-004",
            title="Database lock contention and blocked transactions",
            service="payment-service",
            content="Test runbook content.",
            similarity_score=0.8,
        ),
        RetrievedRunbook(
            id="RUN-001",
            title="Database connection pool timeout diagnosis",
            service="payment-service",
            content="Second test runbook content.",
            similarity_score=0.7,
        ),
    ]
    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runbooks",
        lambda database_url, query, limit: retrieved_runbooks,
    )
    monkeypatch.setattr(
        "resolve_ai.api.get_runtime_reasoner",
        lambda: ConfiguredRuntimeReasoner(
            metadata=ReasonerMetadata(
                provider="openrouter",
                model="openai/gpt-5.6-luna",
            ),
            generate=generate_fake_hypothesis,
        ),
    )


def test_list_incidents_returns_available_incidents() -> None:
    response = client.get("/incidents")

    assert response.status_code == 200
    body = response.json()
    assert [incident["id"] for incident in body] == [
        "INC-001",
        "INC-002",
        "INC-003",
    ]
    assert body[0] == {
        "id": "INC-001",
        "title": "Payments API returning HTTP 500 responses",
        "description": "Payment requests began failing after the morning deployment.",
        "service": "payment-service",
        "started_at": "2026-08-08T10:37:00Z",
    }


def test_investigate_incident_returns_structured_result() -> None:
    response = client.post("/incidents/INC-001/investigate")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "INC-001"
    assert body["status"] == "diagnosed"
    assert body["diagnosis"]["root_cause_label"] == "connection_pool_exhaustion"
    assert body["diagnosis"]["confidence"] == 0.9
    assert body["diagnosis"]["human_approval_required"] is True
    assert body["diagnosis"]["supporting_evidence_ids"] == [
        "DEP-001:database_connection_pool_size",
        "LOG-001",
    ]
    assert [item["id"] for item in body["evidence"]] == [
        "LOG-001",
        "LOG-002",
        "DEP-001:database_connection_pool_size",
    ]
    assert [item["id"] for item in body["retrieved_runbooks"]] == [
        "RUN-004",
        "RUN-001",
    ]
    assert body["retrieved_runbooks"][0]["similarity_score"] == 0.8
    assert body["reasoner"] == {
        "provider": "deterministic",
        "model": "evidence-only-fake-v1",
    }


def test_investigate_expired_certificate_incident() -> None:
    response = client.post("/incidents/INC-002/investigate")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "INC-002"
    assert "payment-api-client" in body["diagnosis"]["probable_root_cause"]
    assert body["diagnosis"]["supporting_evidence_ids"] == ["LOG-003"]
    assert [item["id"] for item in body["evidence"]] == ["LOG-003", "LOG-004"]
    assert body["diagnosis"]["human_approval_required"] is True


def test_investigate_incident_returns_inconclusive_result() -> None:
    response = client.post("/incidents/INC-003/investigate")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "INC-003"
    assert body["status"] == "inconclusive"
    assert body["diagnosis"] is None
    assert [item["id"] for item in body["evidence"]] == ["LOG-005"]


def test_investigate_unknown_incident_returns_not_found() -> None:
    response = client.post("/incidents/INC-999/investigate")

    assert response.status_code == 404
    assert response.json() == {"detail": "Incident INC-999 was not found."}


def test_runtime_bundle_investigates_novel_evidence_without_changing_fixtures() -> None:
    response = client.post("/runtime/investigate", json=_runtime_bundle())

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "USER-INC-901"
    assert body["status"] == "diagnosed"
    assert body["diagnosis"]["root_cause_label"] == "connection_pool_exhaustion"
    assert body["diagnosis"]["supporting_evidence_ids"] == [
        "USER-DEP-901:database_connection_pool_size",
        "USER-LOG-901",
    ]
    assert [item["id"] for item in body["evidence"]] == [
        "USER-DEP-901:database_connection_pool_size",
        "USER-LOG-901",
        "USER-LOG-902",
    ]
    assert body["reasoner"] == {
        "provider": "openrouter",
        "model": "openai/gpt-5.6-luna",
    }
    assert client.get("/incidents").json()[0]["id"] == "INC-001"
    assert len(client.get("/incidents").json()) == 3


def test_runtime_bundle_retrieves_and_cleans_up_scoped_knowledge(monkeypatch) -> None:
    bundle = _runtime_bundle()
    _add_runtime_document(bundle)
    scope_id = UUID("12345678-1234-5678-1234-567812345678")
    calls: dict[str, object] = {}
    retrieved_document = RetrievedKnowledgeDocument(
        id="DOC-901",
        title="Checkout session lifecycle",
        content_type="text/markdown",
        content="A checkout waits when every reusable session is assigned.",
        similarity_score=0.91,
    )

    monkeypatch.setattr(runtime_investigation, "uuid4", lambda: scope_id)

    def store_documents(**kwargs):
        calls["stored"] = kwargs
        return 1

    def delete_scope(database_url, deleted_scope_id):
        calls["deleted"] = (database_url, deleted_scope_id)
        return 1

    monkeypatch.setattr(
        runtime_investigation,
        "store_runtime_knowledge_documents",
        store_documents,
    )
    monkeypatch.setattr(
        runtime_investigation,
        "delete_runtime_knowledge_scope",
        delete_scope,
    )
    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runtime_knowledge_documents",
        lambda database_url, scope_id, query, limit: [retrieved_document],
    )

    response = client.post("/runtime/investigate", json=bundle)

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["retrieved_knowledge_documents"]] == ["DOC-901"]
    assert calls["stored"]["scope_id"] == scope_id
    assert calls["stored"]["documents"][0].id == "DOC-901"
    assert calls["deleted"] == ("postgresql://test", scope_id)


def test_runtime_knowledge_failure_is_stable_503(monkeypatch) -> None:
    bundle = _runtime_bundle()
    _add_runtime_document(bundle)
    monkeypatch.setattr(
        runtime_investigation,
        "store_runtime_knowledge_documents",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeKnowledgeError("database detail")
        ),
    )
    monkeypatch.setattr(
        runtime_investigation,
        "delete_runtime_knowledge_scope",
        lambda *args: 0,
    )

    response = client.post("/runtime/investigate", json=bundle)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Runtime knowledge is temporarily unavailable."
    }
    assert "database detail" not in response.text


def test_runtime_reasoner_endpoint_exposes_only_safe_metadata() -> None:
    response = client.get("/runtime/reasoner")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openrouter",
        "model": "openai/gpt-5.6-luna",
    }


def test_runtime_reasoner_configuration_failure_is_stable_503(monkeypatch) -> None:
    def fail_configuration():
        raise RuntimeReasonerConfigurationError("secret detail")

    monkeypatch.setattr(api, "get_runtime_reasoner", fail_configuration)

    response = client.post("/runtime/investigate", json=_runtime_bundle())

    assert response.status_code == 503
    assert response.json() == {"detail": "Runtime reasoning is not configured."}
    assert "secret" not in response.text


def test_runtime_reasoner_invalid_response_is_stable_502(monkeypatch) -> None:
    def invalid_response(incident, evidence, retrieved_runbooks):
        raise RuntimeError("provider-specific response detail")

    monkeypatch.setattr(
        api,
        "get_runtime_reasoner",
        lambda: ConfiguredRuntimeReasoner(
            metadata=ReasonerMetadata(provider="openrouter", model="test-model"),
            generate=invalid_response,
        ),
    )

    response = client.post("/runtime/investigate", json=_runtime_bundle())

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The runtime reasoner returned an invalid response."
    }
    assert "provider-specific" not in response.text


def test_runtime_reasoner_timeout_is_stable_504(monkeypatch) -> None:
    bundle = _runtime_bundle()
    _add_runtime_document(bundle)
    deleted_scopes: list[UUID] = []

    def time_out(incident, evidence, retrieved_runbooks):
        raise APITimeoutError(request=Request("POST", "https://provider.test"))

    monkeypatch.setattr(
        api,
        "get_runtime_reasoner",
        lambda: ConfiguredRuntimeReasoner(
            metadata=ReasonerMetadata(provider="openrouter", model="test-model"),
            generate=time_out,
        ),
    )
    monkeypatch.setattr(
        runtime_investigation,
        "store_runtime_knowledge_documents",
        lambda **kwargs: 1,
    )
    monkeypatch.setattr(
        runtime_investigation,
        "delete_runtime_knowledge_scope",
        lambda database_url, scope_id: deleted_scopes.append(scope_id) or 1,
    )
    monkeypatch.setattr(
        "resolve_ai.investigation.semantic_search_runtime_knowledge_documents",
        lambda database_url, scope_id, query, limit: [],
    )

    response = client.post("/runtime/investigate", json=bundle)

    assert response.status_code == 504
    assert response.json() == {
        "detail": "The runtime reasoner timed out. Please retry."
    }
    assert len(deleted_scopes) == 1


def test_runtime_reasoner_accepts_an_outside_taxonomy_label(monkeypatch) -> None:
    def diagnose_dns(incident, evidence, retrieved_runbooks):
        return Hypothesis(
            root_cause_label="upstream_dns_resolution_failure",
            probable_root_cause="The upstream hostname cannot be resolved.",
            cited_evidence_ids=[evidence[0].id],
            confidence=0.8,
            recommended_remediation="Restore the upstream DNS record.",
        )

    monkeypatch.setattr(
        api,
        "get_runtime_reasoner",
        lambda: ConfiguredRuntimeReasoner(
            metadata=ReasonerMetadata(provider="openrouter", model="test-model"),
            generate=diagnose_dns,
        ),
    )

    response = client.post("/runtime/investigate", json=_runtime_bundle())

    assert response.status_code == 200
    assert response.json()["diagnosis"]["root_cause_label"] == (
        "upstream_dns_resolution_failure"
    )


def test_runtime_reasoner_rejects_overlapping_requests(monkeypatch) -> None:
    acquired = api._runtime_reasoner_gate.acquire(blocking=False)
    assert acquired
    try:
        response = client.post("/runtime/investigate", json=_runtime_bundle())
    finally:
        api._runtime_reasoner_gate.release()

    assert response.status_code == 429
    assert response.json() == {
        "detail": "Runtime reasoning is busy. Please retry shortly."
    }


def test_runtime_bundle_can_return_an_honest_inconclusive_result() -> None:
    bundle = _runtime_bundle()
    bundle["incident"]["id"] = "USER-INC-902"
    bundle["evidence"] = [bundle["evidence"][2]]

    response = client.post("/runtime/investigate", json=bundle)

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "USER-INC-902"
    assert body["status"] == "inconclusive"
    assert body["diagnosis"] is None
    assert [item["id"] for item in body["evidence"]] == ["USER-LOG-902"]


def test_runtime_run_explicitly_saves_a_complete_provenance_snapshot(
    monkeypatch,
) -> None:
    saved: dict[str, object] = {}

    def save_run(**kwargs):
        saved.update(kwargs)
        return _created_run(kwargs["snapshot"])

    monkeypatch.setattr(api, "create_investigation_run", save_run)

    response = client.post("/runtime/runs", json=_runtime_bundle())

    assert response.status_code == 201
    body = response.json()
    assert body["capability_token"] == "capability-token-with-enough-entropy"
    assert body["run"]["outcome"] == "completed"
    snapshot = body["run"]["snapshot"]
    assert snapshot["schema_version"] == 1
    assert snapshot["bundle"]["incident"]["id"] == "USER-INC-901"
    assert snapshot["investigation_result"]["diagnosis"]["root_cause_label"] == (
        "connection_pool_exhaustion"
    )
    assert [item["id"] for item in snapshot["retrieved_runbooks"]] == [
        "RUN-004",
        "RUN-001",
    ]
    assert snapshot["failure_code"] is None
    assert snapshot["reasoner"] == {
        "provider": "openrouter",
        "model": "openai/gpt-5.6-luna",
    }
    assert snapshot["execution"] == {
        "application_version": "0.1.0",
        "prompt_version": "runtime-investigation-v1",
        "output_schema_version": "runtime-reasoning-decision-v1",
        "retrieval_strategy": "semantic",
        "retrieval_limit": 3,
        "embedding_model": "BAAI/bge-small-en-v1.5",
        "reasoning_effort": "medium",
        "max_output_tokens": 4000,
        "timeout_seconds": 30.0,
    }
    assert snapshot["duration_ms"] >= 0
    assert saved["database_url"] == "postgresql://test"


def test_runtime_run_saves_a_stable_failure_without_provider_details(
    monkeypatch,
) -> None:
    def invalid_response(incident, evidence, retrieved_knowledge):
        raise RuntimeError("provider secret should not be persisted")

    monkeypatch.setattr(
        api,
        "get_runtime_reasoner",
        lambda: ConfiguredRuntimeReasoner(
            metadata=ReasonerMetadata(provider="openrouter", model="test-model"),
            generate=invalid_response,
        ),
    )
    monkeypatch.setattr(
        api,
        "create_investigation_run",
        lambda **kwargs: _created_run(kwargs["snapshot"]),
    )

    response = client.post("/runtime/runs", json=_runtime_bundle())

    assert response.status_code == 201
    body = response.json()
    assert body["run"]["outcome"] == "failed"
    snapshot = body["run"]["snapshot"]
    assert snapshot["investigation_result"] is None
    assert snapshot["failure_code"] == "invalid_reasoner_output"
    assert [item["id"] for item in snapshot["retrieved_runbooks"]] == [
        "RUN-004",
        "RUN-001",
    ]
    assert "provider secret" not in response.text


def test_runtime_run_read_requires_the_matching_bearer_capability(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def save_run(**kwargs):
        created = _created_run(kwargs["snapshot"])
        captured["run"] = created.run
        return created

    monkeypatch.setattr(api, "create_investigation_run", save_run)
    created = client.post("/runtime/runs", json=_runtime_bundle()).json()
    run_id = created["run"]["id"]

    def read_run(**kwargs):
        captured["read"] = kwargs
        if kwargs["capability_token"] != created["capability_token"]:
            return None
        return captured["run"]

    monkeypatch.setattr(api, "get_investigation_run", read_run)

    assert client.get(f"/runtime/runs/{run_id}").status_code == 404
    assert (
        client.get(
            f"/runtime/runs/{run_id}",
            headers={"Authorization": "Bearer wrong-capability"},
        ).status_code
        == 404
    )
    response = client.get(
        f"/runtime/runs/{run_id}",
        headers={"Authorization": f"Bearer {created['capability_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == run_id
    assert captured["read"]["run_id"] == UUID(run_id)


def test_runtime_run_delete_requires_capability_and_returns_no_content(
    monkeypatch,
) -> None:
    run_id = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    deleted: dict[str, object] = {}

    def delete_run(**kwargs):
        deleted.update(kwargs)
        return kwargs["capability_token"] == "matching-capability"

    monkeypatch.setattr(api, "delete_investigation_run", delete_run)

    wrong = client.delete(
        f"/runtime/runs/{run_id}",
        headers={"Authorization": "Bearer wrong-capability"},
    )
    assert wrong.status_code == 404

    response = client.delete(
        f"/runtime/runs/{run_id}",
        headers={"Authorization": "Bearer matching-capability"},
    )
    assert response.status_code == 204
    assert response.content == b""
    assert deleted["run_id"] == run_id


@pytest.mark.parametrize(
    "mutate",
    [
        lambda bundle: bundle.update(schema_version=2),
        lambda bundle: bundle["incident"].update(started_at="2026-08-17T09:00:00"),
        lambda bundle: bundle["evidence"].append(bundle["evidence"][0].copy()),
        lambda bundle: bundle["incident"].update(unexpected="value"),
    ],
    ids=["unknown-schema", "naive-timestamp", "duplicate-evidence-id", "extra-field"],
)
def test_runtime_bundle_rejects_invalid_public_inputs(mutate) -> None:
    bundle = _runtime_bundle()
    mutate(bundle)

    response = client.post("/runtime/investigate", json=bundle)

    assert response.status_code == 422


def test_runtime_bundle_rejects_more_than_fifty_evidence_items() -> None:
    bundle = _runtime_bundle()
    template = bundle["evidence"][2]
    bundle["evidence"] = [
        {**template, "id": f"USER-LOG-{index:03d}"} for index in range(51)
    ]

    response = client.post("/runtime/investigate", json=bundle)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "documents",
    [
        [
            {
                "id": f"DOC-{index}",
                "title": "Document",
                "content_type": "text/plain",
                "content": "bounded content",
            }
            for index in range(6)
        ],
        [
            {
                "id": "DOC-SAME",
                "title": "First",
                "content_type": "text/plain",
                "content": "first",
            },
            {
                "id": "DOC-SAME",
                "title": "Second",
                "content_type": "text/markdown",
                "content": "second",
            },
        ],
        [
            {
                "id": f"DOC-{index}",
                "title": "Document",
                "content_type": "text/plain",
                "content": "x" * 5_000,
            }
            for index in range(5)
        ],
    ],
    ids=["too-many-documents", "duplicate-document-id", "aggregate-content-limit"],
)
def test_runtime_bundle_rejects_invalid_knowledge_document_sets(documents) -> None:
    bundle = _runtime_bundle()
    bundle["knowledge_documents"] = documents

    response = client.post("/runtime/investigate", json=bundle)

    assert response.status_code == 422


def test_runtime_bundle_rejects_knowledge_id_that_matches_evidence() -> None:
    bundle = _runtime_bundle()
    _add_runtime_document(bundle)
    bundle["knowledge_documents"][0]["id"] = bundle["evidence"][0]["id"]

    response = client.post("/runtime/investigate", json=bundle)

    assert response.status_code == 422
