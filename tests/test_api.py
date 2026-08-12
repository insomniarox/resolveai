"""Exercise the public HTTP contract without starting a real network server."""

from fastapi.testclient import TestClient

from resolve_ai.api import app

client = TestClient(app)


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
