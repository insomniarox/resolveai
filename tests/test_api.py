"""Exercise the public HTTP contract without starting a real network server."""

import pytest
from fastapi.testclient import TestClient

from resolve_ai.api import app
from resolve_ai.models import RetrievedRunbook

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
    assert client.get("/incidents").json()[0]["id"] == "INC-001"
    assert len(client.get("/incidents").json()) == 3


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
