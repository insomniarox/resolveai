"""Expose the investigation workflow as an HTTP API.

This module is intentionally small because FastAPI is only the transport layer:
it translates an HTTP request into a call to our Python workflow, then translates
the returned Pydantic model into JSON. The investigation itself remains in
``investigation.py`` so it can be understood and tested without running a server.

The API has two operations:

* ``GET /incidents`` lets callers discover the available synthetic incidents.
* ``POST /incidents/{incident_id}/investigate`` runs the investigation workflow.

Investigation request flow:

1. FastAPI extracts ``incident_id`` from the URL.
2. The route loads synthetic operational data for that ID.
3. The route passes that data and the configured database to the workflow.
4. FastAPI serializes the returned ``InvestigationResult`` as JSON.
"""

import os

from fastapi import FastAPI, HTTPException, status

from resolve_ai.fixtures import get_incident_context, list_incidents
from resolve_ai.investigation import investigate_incident
from resolve_ai.models import Incident, InvestigationResult

# Uvicorn imports this application object from ``resolve_ai.api:app`` when the
# development server starts. Creating it does not start a server by itself.
app = FastAPI(title="ResolveAI", version="0.1.0")


def _get_database_url() -> str:
    """Read the required retrieval database configuration explicitly."""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.strip():
        raise RuntimeError("DATABASE_URL must be set to investigate an incident")
    return database_url


@app.get("/incidents", response_model=list[Incident])
def list_incidents_endpoint() -> list[Incident]:
    """Return the incidents that callers can choose to investigate."""
    return list_incidents()


@app.post(
    "/incidents/{incident_id}/investigate",
    response_model=InvestigationResult,
    status_code=status.HTTP_200_OK,
)
def investigate_incident_endpoint(incident_id: str) -> InvestigationResult:
    """Load one incident and pass it into the domain workflow.

    ``incident_id`` is a URL value such as ``INC-001``. The return annotation and
    ``response_model`` tell FastAPI to validate and serialize the result using the
    ``InvestigationResult`` schema.
    """
    context = get_incident_context(incident_id)
    if context is None:
        # A missing fixture is an HTTP concern, so the route translates ``None``
        # into a 404 instead of teaching the domain workflow about HTTP errors.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} was not found.",
        )

    return investigate_incident(context, database_url=_get_database_url())
