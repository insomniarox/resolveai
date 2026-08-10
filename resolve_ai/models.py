"""Define the data shapes exchanged by the Phase 1 workflow.

Pydantic models are typed data containers. When we create one, Pydantic checks
that its values match the declared fields. FastAPI also uses the same models to
describe and validate JSON responses.

The models follow the data through three stages:

1. ``IncidentContext`` contains raw synthetic operational records.
2. Those records are normalized into a common list of ``Evidence`` objects.
3. The fake creates an unverified ``Hypothesis`` and the application promotes it
   to an ``InvestigationResult`` only after checking its citations.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class EvidenceSource(StrEnum):
    """Identify where an evidence item came from."""

    LOG = "log"
    DEPLOYMENT = "deployment"


class EvidenceKind(StrEnum):
    """Identify the operational fact represented by an evidence item."""

    DATABASE_CONNECTION_TIMEOUT = "database_connection_timeout"
    AUTHENTICATION_CERTIFICATE_EXPIRED = "authentication_certificate_expired"
    HTTP_REQUEST_FAILED = "http_request_failed"
    CONFIGURATION_CHANGE = "configuration_change"


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


class Hypothesis(BaseModel):
    """Represent unverified model-shaped output.

    The cited IDs are claims made by the fake. At this point the application has
    not checked that those IDs refer to evidence it actually collected.
    """

    probable_root_cause: str
    cited_evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    recommended_remediation: str


class InvestigationResult(BaseModel):
    """Represent the final API result after citation IDs have been resolved.

    Unlike ``Hypothesis``, this model contains complete ``Evidence`` objects
    rather than untrusted citation strings. It is the public response contract.
    """

    incident_id: str
    probable_root_cause: str
    evidence: list[Evidence]
    confidence: float = Field(ge=0, le=1)
    recommended_remediation: str
    human_approval_required: bool
