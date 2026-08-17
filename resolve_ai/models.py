"""Define the data shapes exchanged by the Phase 1 workflow.

Pydantic models are typed data containers. When we create one, Pydantic checks
that its values match the declared fields. FastAPI also uses the same models to
describe and validate JSON responses.

The models follow the data through these stages:

1. ``IncidentContext`` contains raw synthetic operational records.
2. Those records are normalized into a common list of ``Evidence`` objects.
3. Semantic retrieval produces ordered ``RetrievedRunbook`` reference knowledge.
4. The evidence-only fake either creates an unverified ``Hypothesis`` or reports
   that the available evidence does not match a supported diagnosis.
5. The application returns a diagnosed or inconclusive ``InvestigationResult``
   containing evidence and retrieved knowledge as separate lists.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class EvidenceSource(StrEnum):
    """Identify where an evidence item came from."""

    LOG = "log"
    DEPLOYMENT = "deployment"


class EvidenceKind(StrEnum):
    """Identify the operational fact represented by an evidence item."""

    DATABASE_CONNECTION_TIMEOUT = "database_connection_timeout"
    DATABASE_LOCK_WAIT = "database_lock_wait"
    DATABASE_TRANSACTION_STATE = "database_transaction_state"
    AUTHENTICATION_CERTIFICATE_EXPIRED = "authentication_certificate_expired"
    TLS_HANDSHAKE_VALIDATION_FAILED = "tls_handshake_validation_failed"
    UPSTREAM_REQUEST_FAILED = "upstream_request_failed"
    UPSTREAM_HEALTH_CHECK = "upstream_health_check"
    NOTIFICATION_QUEUE_METRICS = "notification_queue_metrics"
    NOTIFICATION_WORKER_METRICS = "notification_worker_metrics"
    HTTP_REQUEST_FAILED = "http_request_failed"
    CONFIGURATION_CHANGE = "configuration_change"


class InvestigationStatus(StrEnum):
    """Tell API clients whether the workflow reached a supported diagnosis."""

    DIAGNOSED = "diagnosed"
    INCONCLUSIVE = "inconclusive"


class RootCauseLabel(StrEnum):
    """Name the normalized incident causes used by deterministic evaluation."""

    CONNECTION_POOL_EXHAUSTION = "connection_pool_exhaustion"
    EXPIRED_CLIENT_CERTIFICATE = "expired_client_certificate"
    DATABASE_LOCK_CONTENTION = "database_lock_contention"
    UPSTREAM_TLS_IDENTITY_MISMATCH = "upstream_tls_identity_mismatch"
    NOTIFICATION_PROVIDER_OUTAGE = "notification_provider_outage"
    NOTIFICATION_WORKER_BACKLOG = "notification_worker_backlog"


# Runtime model output must be normalized enough for APIs, traces, and UI display,
# but it must not be restricted to the frozen benchmark's six expected labels.
RootCauseName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$",
    ),
]


class Incident(BaseModel):
    """Describe the reported operational problem that starts an investigation."""

    id: str
    title: str
    description: str
    service: str
    started_at: datetime


class LogEntry(BaseModel):
    """Represent one raw synthetic application-log record."""

    id: str
    timestamp: datetime
    service: str
    kind: EvidenceKind
    message: str
    details: dict[str, str | int] = Field(default_factory=dict)


class ConfigurationChange(BaseModel):
    """Record one numeric setting changed by a deployment."""

    setting: str
    previous_value: int
    new_value: int


class Deployment(BaseModel):
    """Represent one raw synthetic deployment-history record."""

    id: str
    service: str
    version: str
    deployed_at: datetime
    configuration_changes: list[ConfigurationChange]


class IncidentContext(BaseModel):
    """Group the incident and all raw data available to investigate it.

    Passing one context object keeps the core workflow independent from the
    current in-memory storage choice. This is a concrete data object, not a
    repository or service abstraction.
    """

    incident: Incident
    logs: list[LogEntry]
    deployments: list[Deployment]


class Evidence(BaseModel):
    """Represent a source record in the common format consumed by the fake.

    Logs and deployments have different raw shapes. Normalizing both into
    ``Evidence`` lets hypothesis generation consume one list while preserving
    the original source, timestamp, identifier, and structured facts.
    """

    id: str
    source: EvidenceSource
    kind: EvidenceKind
    observed_at: datetime
    summary: str
    details: dict[str, str | int] = Field(default_factory=dict)


class RetrievedRunbook(BaseModel):
    """Represent operational guidance selected as relevant to an incident.

    A retrieved runbook is reference knowledge, not an observed incident fact.
    Its similarity score describes query relevance and must not be interpreted
    as causal evidence or diagnosis confidence.
    """

    id: str
    title: str
    service: str
    content: str
    similarity_score: float


class Hypothesis(BaseModel):
    """Represent unverified model-shaped output.

    The cited IDs are claims made by the fake. At this point the application has
    not checked that those IDs refer to evidence it actually collected.
    """

    root_cause_label: RootCauseName
    probable_root_cause: str
    cited_evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    recommended_remediation: str


class Diagnosis(BaseModel):
    """Group the fields that exist only when ResolveAI found a diagnosis.

    Keeping these values together prevents partially populated diagnoses such as
    a root cause without a confidence or remediation. This is verified
    application output, while ``Hypothesis`` remains unverified model-shaped
    output with citation IDs.
    """

    root_cause_label: RootCauseName
    probable_root_cause: str
    confidence: float = Field(ge=0, le=1)
    recommended_remediation: str
    human_approval_required: bool
    supporting_evidence_ids: list[str] = Field(min_length=1)


class ReasonerMetadata(BaseModel):
    """Identify the server-selected reasoner without exposing credentials."""

    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=120)


def deterministic_reasoner_metadata() -> ReasonerMetadata:
    """Describe the stable fake used by the guided demo and benchmark."""
    return ReasonerMetadata(
        provider="deterministic",
        model="evidence-only-fake-v1",
    )


class InvestigationResult(BaseModel):
    """Represent either a diagnosed or inconclusive investigation.

    ``evidence`` contains observations collected from this incident, while
    ``retrieved_runbooks`` contains ordered reference knowledge found for it.
    Keeping the lists separate prevents semantic similarity from being presented
    as causal support. A diagnosed result identifies its verified evidence subset
    through ``Diagnosis.supporting_evidence_ids``.
    """

    incident_id: str
    status: InvestigationStatus
    diagnosis: Diagnosis | None
    evidence: list[Evidence]
    retrieved_runbooks: list[RetrievedRunbook]
    reasoner: ReasonerMetadata = Field(default_factory=deterministic_reasoner_metadata)
