"""Execute one runtime investigation and preserve its observable provenance.

The HTTP API has two ways to use this operation: a transient response and an
explicitly saved run. Keeping execution here ensures both paths perform the
same retrieval, reasoning, validation, timing, and request-scoped cleanup.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from time import perf_counter
from uuid import UUID, uuid4

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

from resolve_ai.investigation import UnknownEvidenceError, investigate_evidence
from resolve_ai.models import (
    InvestigationResult,
    ReasonerMetadata,
    RetrievedKnowledgeDocument,
    RetrievedReferenceKnowledge,
    RetrievedRunbook,
)
from resolve_ai.retrieval import (
    RuntimeKnowledgeError,
    delete_runtime_knowledge_scope,
    store_runtime_knowledge_documents,
)
from resolve_ai.runtime_input import RuntimeIncidentBundle
from resolve_ai.runtime_reasoner import ConfiguredRuntimeReasoner

logger = logging.getLogger(__name__)


class RuntimeFailureCode(StrEnum):
    """Stable, non-sensitive categories for failed runtime attempts."""

    RUNTIME_KNOWLEDGE_UNAVAILABLE = "runtime_knowledge_unavailable"
    REASONER_TIMEOUT = "reasoner_timeout"
    INVALID_CITATIONS = "invalid_citations"
    INVALID_REASONER_OUTPUT = "invalid_reasoner_output"
    REASONER_UNAVAILABLE = "reasoner_unavailable"


@dataclass(frozen=True)
class RuntimeInvestigationAttempt:
    """Capture the successful result and timing of one runtime execution."""

    result: InvestigationResult
    started_at: datetime
    completed_at: datetime
    duration_ms: int


class RuntimeInvestigationFailure(Exception):
    """Carry safe failure provenance while retaining the original exception."""

    def __init__(
        self,
        *,
        code: RuntimeFailureCode,
        reasoner: ReasonerMetadata,
        retrieved_runbooks: list[RetrievedRunbook],
        retrieved_knowledge_documents: list[RetrievedKnowledgeDocument],
        started_at: datetime,
        completed_at: datetime,
        duration_ms: int,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.reasoner = reasoner.model_copy(deep=True)
        self.retrieved_runbooks = [
            item.model_copy(deep=True) for item in retrieved_runbooks
        ]
        self.retrieved_knowledge_documents = [
            item.model_copy(deep=True) for item in retrieved_knowledge_documents
        ]
        self.started_at = started_at
        self.completed_at = completed_at
        self.duration_ms = duration_ms


def _failure_code(error: Exception) -> RuntimeFailureCode | None:
    """Translate known execution failures into a durable public vocabulary."""
    if isinstance(error, RuntimeKnowledgeError):
        return RuntimeFailureCode.RUNTIME_KNOWLEDGE_UNAVAILABLE
    if isinstance(error, APITimeoutError):
        return RuntimeFailureCode.REASONER_TIMEOUT
    if isinstance(error, UnknownEvidenceError):
        return RuntimeFailureCode.INVALID_CITATIONS
    if isinstance(
        error,
        (
            ValidationError,
            RuntimeError,
            LengthFinishReasonError,
            ContentFilterFinishReasonError,
        ),
    ):
        return RuntimeFailureCode.INVALID_REASONER_OUTPUT
    if isinstance(
        error,
        (
            AuthenticationError,
            PermissionDeniedError,
            RateLimitError,
            APIConnectionError,
            APIStatusError,
        ),
    ):
        return RuntimeFailureCode.REASONER_UNAVAILABLE
    return None


def execute_runtime_investigation(
    *,
    bundle: RuntimeIncidentBundle,
    database_url: str,
    reasoner: ConfiguredRuntimeReasoner,
    knowledge_retention: timedelta,
) -> RuntimeInvestigationAttempt:
    """Execute a validated bundle and clean up any temporary knowledge scope."""
    incident, evidence, knowledge_documents = bundle.to_domain()
    started_at = datetime.now(UTC)
    started_clock = perf_counter()
    knowledge_scope_id: UUID | None = None
    retrieved_runbooks: list[RetrievedRunbook] = []
    retrieved_documents: list[RetrievedKnowledgeDocument] = []

    def capture_retrieval(
        generated_incident,
        generated_evidence,
        retrieved_knowledge: list[RetrievedReferenceKnowledge],
    ):
        """Record the exact ordered references passed into the reasoner."""
        retrieved_runbooks.extend(
            item.model_copy(deep=True)
            for item in retrieved_knowledge
            if isinstance(item, RetrievedRunbook)
        )
        retrieved_documents.extend(
            item.model_copy(deep=True)
            for item in retrieved_knowledge
            if isinstance(item, RetrievedKnowledgeDocument)
        )
        return reasoner.generate(
            generated_incident,
            generated_evidence,
            retrieved_knowledge,
        )

    try:
        if knowledge_documents:
            knowledge_scope_id = uuid4()
            store_runtime_knowledge_documents(
                database_url=database_url,
                scope_id=knowledge_scope_id,
                documents=knowledge_documents,
                expires_at=started_at + knowledge_retention,
            )

        result = investigate_evidence(
            incident=incident,
            evidence=evidence,
            database_url=database_url,
            hypothesis_generator=capture_retrieval,
            reasoner=reasoner.metadata,
            knowledge_scope_id=knowledge_scope_id,
        )
    except Exception as error:
        code = _failure_code(error)
        if code is None:
            raise
        completed_at = datetime.now(UTC)
        raise RuntimeInvestigationFailure(
            code=code,
            reasoner=reasoner.metadata,
            retrieved_runbooks=retrieved_runbooks,
            retrieved_knowledge_documents=retrieved_documents,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=max(0, round((perf_counter() - started_clock) * 1000)),
        ) from error
    finally:
        if knowledge_scope_id is not None:
            try:
                delete_runtime_knowledge_scope(database_url, knowledge_scope_id)
            except RuntimeKnowledgeError:
                # Expired rows are excluded from retrieval and purged by a later
                # ingestion. Cleanup failure must not conceal the real outcome.
                logger.error("Failed to delete a runtime knowledge scope")

    completed_at = datetime.now(UTC)
    return RuntimeInvestigationAttempt(
        result=result,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=max(0, round((perf_counter() - started_clock) * 1000)),
    )
