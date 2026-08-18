"""Expose the investigation workflow as an HTTP API.

This module is intentionally small because FastAPI is only the transport layer:
it translates an HTTP request into a call to our Python workflow, then translates
the returned Pydantic model into JSON. The investigation itself remains in
``investigation.py`` so it can be understood and tested without running a server.

The API has four operations:

* ``GET /incidents`` lets callers discover the available synthetic incidents.
* ``POST /incidents/{incident_id}/investigate`` runs the investigation workflow.
* ``GET /runtime/reasoner`` discloses safe server-side model metadata.
* ``POST /runtime/investigate`` accepts one transient versioned runtime bundle.

Prepared-incident request flow:

1. FastAPI extracts ``incident_id`` from the URL.
2. The route loads synthetic operational data for that ID.
3. The route passes that data and the configured database to the workflow.
4. FastAPI serializes the returned ``InvestigationResult`` as JSON.
"""

import logging
import os
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, status
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    ContentFilterFinishReasonError,
    LengthFinishReasonError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from resolve_ai.fixtures import get_incident_context, list_incidents
from resolve_ai.investigation import (
    UnknownEvidenceError,
    investigate_evidence,
    investigate_incident,
)
from resolve_ai.models import Incident, InvestigationResult, ReasonerMetadata
from resolve_ai.retrieval import (
    RuntimeKnowledgeError,
    delete_runtime_knowledge_scope,
    store_runtime_knowledge_documents,
)
from resolve_ai.runtime_input import RuntimeIncidentBundle
from resolve_ai.runtime_reasoner import (
    RuntimeReasonerConfigurationError,
    get_runtime_reasoner,
)
from resolve_ai.telemetry import configure_console_tracing

configure_console_tracing()

# Uvicorn imports this application object from ``resolve_ai.api:app`` when the
# development server starts. Creating it does not start a server by itself.
app = FastAPI(title="ResolveAI", version="0.1.0")
_runtime_reasoner_gate = BoundedSemaphore(value=1)
_runtime_knowledge_retention = timedelta(minutes=15)
logger = logging.getLogger(__name__)


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


@app.get("/runtime/reasoner", response_model=ReasonerMetadata)
def get_runtime_reasoner_endpoint() -> ReasonerMetadata:
    """Return safe metadata for the configured server-side runtime reasoner."""
    try:
        return get_runtime_reasoner().metadata
    except RuntimeReasonerConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime reasoning is not configured.",
        ) from error


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


@app.post(
    "/runtime/investigate",
    response_model=InvestigationResult,
    status_code=status.HTTP_200_OK,
)
def investigate_runtime_bundle_endpoint(
    bundle: RuntimeIncidentBundle,
) -> InvestigationResult:
    """Investigate one validated bundle without storing it or changing fixtures."""
    try:
        reasoner = get_runtime_reasoner()
    except RuntimeReasonerConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime reasoning is not configured.",
        ) from error

    database_url = _get_database_url()
    incident, evidence, knowledge_documents = bundle.to_domain()
    if not _runtime_reasoner_gate.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Runtime reasoning is busy. Please retry shortly.",
        )

    knowledge_scope_id: UUID | None = None
    try:
        if knowledge_documents:
            knowledge_scope_id = uuid4()
            store_runtime_knowledge_documents(
                database_url=database_url,
                scope_id=knowledge_scope_id,
                documents=knowledge_documents,
                expires_at=datetime.now(UTC) + _runtime_knowledge_retention,
            )

        return investigate_evidence(
            incident=incident,
            evidence=evidence,
            database_url=database_url,
            hypothesis_generator=reasoner.generate,
            reasoner=reasoner.metadata,
            knowledge_scope_id=knowledge_scope_id,
        )
    except RuntimeKnowledgeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime knowledge is temporarily unavailable.",
        ) from error
    except APITimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="The runtime reasoner timed out. Please retry.",
        ) from error
    except UnknownEvidenceError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The runtime reasoner returned invalid evidence citations.",
        ) from error
    except (
        ValidationError,
        RuntimeError,
        LengthFinishReasonError,
        ContentFilterFinishReasonError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The runtime reasoner returned an invalid response.",
        ) from error
    except (
        AuthenticationError,
        PermissionDeniedError,
        RateLimitError,
        APIConnectionError,
        APIStatusError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The runtime reasoner is temporarily unavailable.",
        ) from error
    finally:
        if knowledge_scope_id is not None:
            try:
                delete_runtime_knowledge_scope(database_url, knowledge_scope_id)
            except RuntimeKnowledgeError:
                # Expired rows are excluded from retrieval and purged by a later
                # ingestion. Cleanup failure must not conceal the real outcome.
                logger.error("Failed to delete a runtime knowledge scope")
        _runtime_reasoner_gate.release()
