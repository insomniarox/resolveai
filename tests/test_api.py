"""Exercise the public HTTP contract without starting a real network server."""

from fastapi.testclient import TestClient

from resolve_ai.api import app

client = TestClient(app)


def test_investigate_incident_returns_structured_result() -> None:
    response = client.post("/incidents/INC-001/investigate")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "INC-001"
    assert body["confidence"] == 0.9
    assert body["human_approval_required"] is True
    assert {item["id"] for item in body["evidence"]} == {
        "DEP-001:database_connection_pool_size",
        "LOG-001",
    }


def test_investigate_expired_certificate_incident() -> None:
    response = client.post("/incidents/INC-002/investigate")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "INC-002"
    assert "payment-api-client" in body["probable_root_cause"]
    assert [item["id"] for item in body["evidence"]] == ["LOG-003"]
    assert body["human_approval_required"] is True


def test_investigate_unknown_incident_returns_not_found() -> None:
    response = client.post("/incidents/INC-999/investigate")

    assert response.status_code == 404
    assert response.json() == {"detail": "Incident INC-999 was not found."}
