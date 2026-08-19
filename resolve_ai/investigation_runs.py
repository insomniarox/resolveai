"""Persist explicit, immutable runtime investigation snapshots.

A run has no public listing or update operation. Possession of its high-entropy
capability token grants read and delete access until the fixed expiry time.
Only a SHA-256 digest of that token is stored in PostgreSQL.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from resolve_ai import APPLICATION_VERSION
from resolve_ai.embeddings import EMBEDDING_MODEL_NAME
from resolve_ai.investigation import RUNBOOK_RETRIEVAL_LIMIT
from resolve_ai.models import (
    InvestigationResult,
    ReasonerMetadata,
    RetrievedKnowledgeDocument,
    RetrievedRunbook,
)
from resolve_ai.openai_model import (
    MODEL_MAX_OUTPUT_TOKENS,
    MODEL_REASONING_EFFORT,
    MODEL_TIMEOUT_SECONDS,
    RUNTIME_OUTPUT_SCHEMA_VERSION,
    RUNTIME_PROMPT_VERSION,
)
from resolve_ai.runtime_input import RuntimeIncidentBundle
from resolve_ai.runtime_investigation import (
    RuntimeFailureCode,
    RuntimeInvestigationAttempt,
    RuntimeInvestigationFailure,
)

INVESTIGATION_RUN_RETENTION = timedelta(hours=1)


class InvestigationRunOutcome(StrEnum):
    """Distinguish a reasoned result from a safely categorized failure."""

    COMPLETED = "completed"
    FAILED = "failed"


class RuntimeExecutionMetadata(BaseModel):
    """Record the bounded configuration needed to explain run differences."""

    model_config = ConfigDict(frozen=True)

    application_version: str
    prompt_version: str
    output_schema_version: str
    retrieval_strategy: Literal["semantic"]
    retrieval_limit: int = Field(gt=0)
    embedding_model: str
    reasoning_effort: str
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)


def current_runtime_execution_metadata() -> RuntimeExecutionMetadata:
    """Describe the concrete runtime settings compiled into this application."""
    return RuntimeExecutionMetadata(
        application_version=APPLICATION_VERSION,
        prompt_version=RUNTIME_PROMPT_VERSION,
        output_schema_version=RUNTIME_OUTPUT_SCHEMA_VERSION,
        retrieval_strategy="semantic",
        retrieval_limit=RUNBOOK_RETRIEVAL_LIMIT,
        embedding_model=EMBEDDING_MODEL_NAME,
        reasoning_effort=MODEL_REASONING_EFFORT,
        max_output_tokens=MODEL_MAX_OUTPUT_TOKENS,
        timeout_seconds=MODEL_TIMEOUT_SECONDS,
    )


class InvestigationRunSnapshot(BaseModel):
    """Versioned, self-contained provenance for one runtime attempt."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal[1] = 1
    bundle: RuntimeIncidentBundle
    retrieved_runbooks: list[RetrievedRunbook]
    retrieved_knowledge_documents: list[RetrievedKnowledgeDocument]
    investigation_result: InvestigationResult | None
    failure_code: RuntimeFailureCode | None
    reasoner: ReasonerMetadata
    execution: RuntimeExecutionMetadata
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_outcome(self) -> "InvestigationRunSnapshot":
        """Require exactly one completed result or stable failure category."""
        has_result = self.investigation_result is not None
        has_failure = self.failure_code is not None
        if has_result == has_failure:
            raise ValueError("snapshot must contain exactly one result or failure")
        if (
            self.investigation_result is not None
            and self.investigation_result.incident_id != self.bundle.incident.id
        ):
            raise ValueError("snapshot result must belong to the submitted incident")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        return self


class InvestigationRun(BaseModel):
    """Return one saved run without exposing its stored token digest."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    created_at: datetime
    expires_at: datetime
    outcome: InvestigationRunOutcome
    snapshot: InvestigationRunSnapshot


class CreatedInvestigationRun(BaseModel):
    """Return a newly saved run and its one-time plaintext capability."""

    run: InvestigationRun
    capability_token: str = Field(min_length=32)


class InvestigationRunStorageError(Exception):
    """Hide database details behind a stable storage boundary."""


_DELETE_EXPIRED_RUNS_SQL = """
DELETE FROM investigation_runs
WHERE expires_at <= now()
"""

_INSERT_RUN_SQL = """
INSERT INTO investigation_runs (
    id,
    capability_token_hash,
    created_at,
    expires_at,
    outcome,
    snapshot
)
VALUES (%s, %s, %s, %s, %s, %s)
"""

_SELECT_RUN_SQL = """
SELECT id, created_at, expires_at, outcome, snapshot
FROM investigation_runs
WHERE id = %s
    AND capability_token_hash = %s
    AND expires_at > now()
"""

_DELETE_RUN_SQL = """
DELETE FROM investigation_runs
WHERE id = %s
    AND capability_token_hash = %s
    AND expires_at > now()
"""


def _token_digest(capability_token: str) -> bytes:
    """Hash a capability token into the only representation we persist."""
    if not capability_token.strip():
        raise ValueError("capability_token must not be empty")
    return hashlib.sha256(capability_token.encode("utf-8")).digest()


def snapshot_from_attempt(
    bundle: RuntimeIncidentBundle,
    attempt: RuntimeInvestigationAttempt,
) -> InvestigationRunSnapshot:
    """Build a completed immutable snapshot from shared runtime execution."""
    return InvestigationRunSnapshot(
        bundle=bundle.model_copy(deep=True),
        retrieved_runbooks=[
            item.model_copy(deep=True) for item in attempt.result.retrieved_runbooks
        ],
        retrieved_knowledge_documents=[
            item.model_copy(deep=True)
            for item in attempt.result.retrieved_knowledge_documents
        ],
        investigation_result=attempt.result.model_copy(deep=True),
        failure_code=None,
        reasoner=attempt.result.reasoner.model_copy(deep=True),
        execution=current_runtime_execution_metadata(),
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        duration_ms=attempt.duration_ms,
    )


def snapshot_from_failure(
    bundle: RuntimeIncidentBundle,
    failure: RuntimeInvestigationFailure,
) -> InvestigationRunSnapshot:
    """Build a failed snapshot without persisting provider exception details."""
    return InvestigationRunSnapshot(
        bundle=bundle.model_copy(deep=True),
        retrieved_runbooks=failure.retrieved_runbooks,
        retrieved_knowledge_documents=failure.retrieved_knowledge_documents,
        investigation_result=None,
        failure_code=failure.code,
        reasoner=failure.reasoner,
        execution=current_runtime_execution_metadata(),
        started_at=failure.started_at,
        completed_at=failure.completed_at,
        duration_ms=failure.duration_ms,
    )


def create_investigation_run(
    *,
    database_url: str,
    snapshot: InvestigationRunSnapshot,
    retention: timedelta = INVESTIGATION_RUN_RETENTION,
) -> CreatedInvestigationRun:
    """Persist a snapshot once and return the plaintext capability once."""
    if not database_url.strip():
        raise ValueError("database_url must not be empty")
    if retention <= timedelta(0):
        raise ValueError("retention must be greater than zero")

    run_id = uuid4()
    capability_token = secrets.token_urlsafe(32)
    created_at = datetime.now(UTC)
    expires_at = created_at + retention
    outcome = (
        InvestigationRunOutcome.COMPLETED
        if snapshot.investigation_result is not None
        else InvestigationRunOutcome.FAILED
    )

    try:
        with psycopg.connect(database_url) as connection:
            connection.execute(_DELETE_EXPIRED_RUNS_SQL)
            connection.execute(
                _INSERT_RUN_SQL,
                (
                    run_id,
                    _token_digest(capability_token),
                    created_at,
                    expires_at,
                    outcome.value,
                    Jsonb(snapshot.model_dump(mode="json")),
                ),
            )
    except psycopg.Error as error:
        raise InvestigationRunStorageError(
            "investigation run could not be stored"
        ) from error

    return CreatedInvestigationRun(
        run=InvestigationRun(
            id=run_id,
            created_at=created_at,
            expires_at=expires_at,
            outcome=outcome,
            snapshot=snapshot,
        ),
        capability_token=capability_token,
    )


def get_investigation_run(
    *,
    database_url: str,
    run_id: UUID,
    capability_token: str,
) -> InvestigationRun | None:
    """Read one unexpired run when both its ID and capability match."""
    if not database_url.strip():
        raise ValueError("database_url must not be empty")
    try:
        digest = _token_digest(capability_token)
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            connection.execute(_DELETE_EXPIRED_RUNS_SQL)
            row = connection.execute(_SELECT_RUN_SQL, (run_id, digest)).fetchone()
        return InvestigationRun.model_validate(row) if row is not None else None
    except (psycopg.Error, ValidationError) as error:
        raise InvestigationRunStorageError(
            "investigation run could not be read"
        ) from error


def delete_investigation_run(
    *,
    database_url: str,
    run_id: UUID,
    capability_token: str,
) -> bool:
    """Delete one unexpired run when both its ID and capability match."""
    if not database_url.strip():
        raise ValueError("database_url must not be empty")
    try:
        digest = _token_digest(capability_token)
        with psycopg.connect(database_url) as connection:
            connection.execute(_DELETE_EXPIRED_RUNS_SQL)
            cursor = connection.execute(_DELETE_RUN_SQL, (run_id, digest))
            deleted = cursor.rowcount
    except psycopg.Error as error:
        raise InvestigationRunStorageError(
            "investigation run could not be deleted"
        ) from error
    return deleted == 1
