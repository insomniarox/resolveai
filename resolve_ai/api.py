"""Expose the investigation workflow as an HTTP API.

This module is intentionally small because FastAPI is only the transport layer:
it translates an HTTP request into a call to our Python workflow, then translates
the returned Pydantic model into JSON. The investigation itself remains in
``investigation.py`` so it can be understood and tested without running a server.

The API has seven operations:

* ``GET /incidents`` lets callers discover the available synthetic incidents.
* ``POST /incidents/{incident_id}/investigate`` runs the investigation workflow.
* ``GET /runtime/reasoner`` discloses safe server-side model metadata.
* ``POST /runtime/investigate`` accepts one transient versioned runtime bundle.
* ``POST /runtime/runs`` explicitly saves one short-lived investigation.
* ``GET /runtime/runs/{run_id}`` reads a run with its bearer capability.
* ``DELETE /runtime/runs/{run_id}`` deletes a run with its bearer capability.

Prepared-incident request flow:

1. FastAPI extracts ``incident_id`` from the URL.
2. The route loads synthetic operational data for that ID.
3. The route passes that data and the configured database to the workflow.
4. FastAPI serializes the returned ``InvestigationResult`` as JSON.
"""

import os
from datetime import timedelta
from threading import BoundedSemaphore
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Response, status

from resolve_ai import APPLICATION_VERSION
from resolve_ai.fixtures import get_incident_context, list_incidents
from resolve_ai.investigation import investigate_incident
from resolve_ai.investigation_runs import (
    CreatedInvestigationRun,
    InvestigationRun,
    InvestigationRunStorageError,
    create_investigation_run,
    delete_investigation_run,
    get_investigation_run,
    snapshot_from_attempt,
    snapshot_from_failure,
)
from resolve_ai.models import Incident, InvestigationResult, ReasonerMetadata
from resolve_ai.runtime_input import RuntimeIncidentBundle
from resolve_ai.runtime_investigation import (
    RuntimeFailureCode,
    RuntimeInvestigationFailure,
    execute_runtime_investigation,
)
from resolve_ai.runtime_reasoner import (
    ConfiguredRuntimeReasoner,
    RuntimeReasonerConfigurationError,
    get_runtime_reasoner,
)
from resolve_ai.telemetry import configure_console_tracing

configure_console_tracing()

# Uvicorn imports this application object from ``resolve_ai.api:app`` when the
# development server starts. Creating it does not start a server by itself.
app = FastAPI(title="ResolveAI", version=APPLICATION_VERSION)
_runtime_reasoner_gate = BoundedSemaphore(value=1)
_runtime_knowledge_retention = timedelta(minutes=15)


def _get_database_url() -> str:
    """Read the required retrieval database configuration explicitly."""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.strip():
        raise RuntimeError("DATABASE_URL must be set to investigate an incident")
    return database_url


def _get_runtime_reasoner_or_503() -> ConfiguredRuntimeReasoner:
    """Load the server reasoner without exposing configuration details."""
    try:
        return get_runtime_reasoner()
    except RuntimeReasonerConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime reasoning is not configured.",
        ) from error


def _acquire_runtime_reasoner() -> None:
    """Reject overlapping provider work before an investigation begins."""
    if not _runtime_reasoner_gate.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Runtime reasoning is busy. Please retry shortly.",
        )


def _runtime_failure_http_exception(
    failure: RuntimeInvestigationFailure,
) -> HTTPException:
    """Preserve the transient endpoint's stable HTTP failure contract."""
    responses = {
        RuntimeFailureCode.RUNTIME_KNOWLEDGE_UNAVAILABLE: (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Runtime knowledge is temporarily unavailable.",
        ),
        RuntimeFailureCode.REASONER_TIMEOUT: (
            status.HTTP_504_GATEWAY_TIMEOUT,
            "The runtime reasoner timed out. Please retry.",
        ),
        RuntimeFailureCode.INVALID_CITATIONS: (
            status.HTTP_502_BAD_GATEWAY,
            "The runtime reasoner returned invalid evidence citations.",
        ),
        RuntimeFailureCode.INVALID_REASONER_OUTPUT: (
            status.HTTP_502_BAD_GATEWAY,
            "The runtime reasoner returned an invalid response.",
        ),
        RuntimeFailureCode.REASONER_UNAVAILABLE: (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The runtime reasoner is temporarily unavailable.",
        ),
    }
    status_code, detail = responses[failure.code]
    return HTTPException(status_code=status_code, detail=detail)


def _bearer_capability(authorization: str | None) -> str | None:
    """Parse an exact bearer capability without placing it in a URL."""
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    if separator and scheme.lower() == "bearer" and token and " " not in token:
        return token
    return None


def _run_not_found() -> HTTPException:
    """Give missing and unauthorized callers the same non-disclosing response."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Investigation run was not found.",
    )


def _run_storage_unavailable() -> HTTPException:
    """Hide PostgreSQL details behind a stable API response."""
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Investigation run storage is temporarily unavailable.",
    )


@app.get("/incidents", response_model=list[Incident])
def list_incidents_endpoint() -> list[Incident]:
    """Return the incidents that callers can choose to investigate."""
    return list_incidents()


@app.get("/runtime/reasoner", response_model=ReasonerMetadata)
def get_runtime_reasoner_endpoint() -> ReasonerMetadata:
    """Return safe metadata for the configured server-side runtime reasoner."""
    return _get_runtime_reasoner_or_503().metadata


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
    reasoner = _get_runtime_reasoner_or_503()
    database_url = _get_database_url()
    _acquire_runtime_reasoner()
    try:
        attempt = execute_runtime_investigation(
            bundle=bundle,
            database_url=database_url,
            reasoner=reasoner,
            knowledge_retention=_runtime_knowledge_retention,
        )
    except RuntimeInvestigationFailure as failure:
        raise _runtime_failure_http_exception(failure) from failure
    finally:
        _runtime_reasoner_gate.release()
    return attempt.result


@app.post(
    "/runtime/runs",
    response_model=CreatedInvestigationRun,
    status_code=status.HTTP_201_CREATED,
)
def create_runtime_run_endpoint(
    bundle: RuntimeIncidentBundle,
) -> CreatedInvestigationRun:
    """Explicitly execute and save one immutable, one-hour run snapshot."""
    reasoner = _get_runtime_reasoner_or_503()
    database_url = _get_database_url()
    _acquire_runtime_reasoner()
    try:
        try:
            attempt = execute_runtime_investigation(
                bundle=bundle,
                database_url=database_url,
                reasoner=reasoner,
                knowledge_retention=_runtime_knowledge_retention,
            )
        except RuntimeInvestigationFailure as failure:
            snapshot = snapshot_from_failure(bundle, failure)
        else:
            snapshot = snapshot_from_attempt(bundle, attempt)
    finally:
        _runtime_reasoner_gate.release()

    try:
        return create_investigation_run(
            database_url=database_url,
            snapshot=snapshot,
        )
    except InvestigationRunStorageError as error:
        raise _run_storage_unavailable() from error


@app.get(
    "/runtime/runs/{run_id}",
    response_model=InvestigationRun,
    status_code=status.HTTP_200_OK,
)
def get_runtime_run_endpoint(
    run_id: UUID,
    authorization: Annotated[str | None, Header()] = None,
) -> InvestigationRun:
    """Read an unexpired run using its bearer capability."""
    capability_token = _bearer_capability(authorization)
    if capability_token is None:
        raise _run_not_found()
    try:
        run = get_investigation_run(
            database_url=_get_database_url(),
            run_id=run_id,
            capability_token=capability_token,
        )
    except InvestigationRunStorageError as error:
        raise _run_storage_unavailable() from error
    if run is None:
        raise _run_not_found()
    return run


@app.delete(
    "/runtime/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_runtime_run_endpoint(
    run_id: UUID,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """Delete an unexpired run using its bearer capability."""
    capability_token = _bearer_capability(authorization)
    if capability_token is None:
        raise _run_not_found()
    try:
        deleted = delete_investigation_run(
            database_url=_get_database_url(),
            run_id=run_id,
            capability_token=capability_token,
        )
    except InvestigationRunStorageError as error:
        raise _run_storage_unavailable() from error
    if not deleted:
        raise _run_not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
