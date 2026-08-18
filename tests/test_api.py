"""Exercise the public HTTP contract without starting a real network server."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx import Request
from openai import APITimeoutError

from resolve_ai import api
from resolve_ai.api import app
from resolve_ai.fake_model import generate_fake_hypothesis
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

    monkeypatch.setattr(api, "uuid4", lambda: scope_id)

    def store_documents(**kwargs):
        calls["stored"] = kwargs
        return 1

    def delete_scope(database_url, deleted_scope_id):
        calls["deleted"] = (database_url, deleted_scope_id)
        return 1

    monkeypatch.setattr(api, "store_runtime_knowledge_documents", store_documents)
    monkeypatch.setattr(api, "delete_runtime_knowledge_scope", delete_scope)
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
        api,
        "store_runtime_knowledge_documents",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeKnowledgeError("database detail")
        ),
    )
    monkeypatch.setattr(api, "delete_runtime_knowledge_scope", lambda *args: 0)

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
    monkeypatch.setattr(api, "store_runtime_knowledge_documents", lambda **kwargs: 1)
    monkeypatch.setattr(
        api,
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
