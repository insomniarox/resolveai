"""Validate and adapt transient user-supplied investigation bundles.

Runtime transport models intentionally remain separate from the frozen fixture
models. They define the bounded public JSON contract, then convert validated
values into the ordinary ``Incident`` and ``Evidence`` domain objects consumed
by the shared investigation workflow.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from resolve_ai.models import Evidence, EvidenceKind, EvidenceSource, Incident

_Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$",
    ),
]
_ServiceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
_Title = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
]
_Description = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]
_Summary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2_000),
]
_DetailKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]
_DetailText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


def _require_timezone(value: datetime) -> datetime:
    """Reject ambiguous local timestamps at the public runtime boundary."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a UTC offset")
    return value


class RuntimeIncidentInput(BaseModel):
    """Describe one previously unseen incident in the versioned bundle."""

    model_config = ConfigDict(extra="forbid")

    id: _Identifier
    title: _Title
    description: _Description
    service: _ServiceName
    started_at: datetime

    _validate_started_at = field_validator("started_at")(_require_timezone)

    def to_domain(self) -> Incident:
        """Create the domain incident without sharing transport-model state."""
        return Incident(
            id=self.id,
            title=self.title,
            description=self.description,
            service=self.service,
            started_at=self.started_at,
        )


class RuntimeEvidenceInput(BaseModel):
    """Describe one normalized observation supplied by the runtime caller."""

    model_config = ConfigDict(extra="forbid")

    id: _Identifier
    source: EvidenceSource
    kind: EvidenceKind
    observed_at: datetime
    summary: _Summary
    details: dict[_DetailKey, _DetailText | StrictInt] = Field(
        default_factory=dict,
        max_length=20,
    )

    _validate_observed_at = field_validator("observed_at")(_require_timezone)

    def to_domain(self) -> Evidence:
        """Create domain Evidence while preserving normalized input order."""
        return Evidence(
            id=self.id,
            source=self.source,
            kind=self.kind,
            observed_at=self.observed_at,
            summary=self.summary,
            details=dict(self.details),
        )


class RuntimeIncidentBundle(BaseModel):
    """Version 1 of the bounded, transient runtime investigation contract."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    incident: RuntimeIncidentInput
    evidence: list[RuntimeEvidenceInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_unique_evidence_ids(self) -> "RuntimeIncidentBundle":
        """Keep citations unambiguous by rejecting duplicate observation IDs."""
        ids = [item.id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique")
        return self

    def to_domain(self) -> tuple[Incident, list[Evidence]]:
        """Adapt the public DTO into the shared investigation input boundary."""
        return self.incident.to_domain(), [item.to_domain() for item in self.evidence]
