"""Exercise the in-memory data boundary independently from FastAPI."""

from resolve_ai.fixtures import list_incidents


def test_list_incidents_returns_chronological_isolated_copies() -> None:
    incidents = list_incidents()

    assert [incident.id for incident in incidents] == ["INC-001", "INC-002", "INC-003"]

    incidents[0].title = "Changed only in this test"
    refreshed_incidents = list_incidents()

    assert refreshed_incidents[0].title == "Payments API returning HTTP 500 responses"
