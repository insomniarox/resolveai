"""Bounded comparison contracts, separate from generated diagnoses and saved runs."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from resolve_ai.models import Evidence, RetrievedKnowledgeDocument, RetrievedRunbook
from resolve_ai.runtime_input import RuntimeIncidentBundle

Provider = Literal["jev", "openrouter"]
CandidateText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)
]


class ComparisonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bundle: RuntimeIncidentBundle
    candidates: list[CandidateText] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_candidates(self):
        if len({c.casefold() for c in self.candidates}) != len(self.candidates):
            raise ValueError("Candidate hypotheses must be distinct")
        return self


class DecisionUsage(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reported_cost_usd: float | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    cost_basis: str | None = None


class DecisionCall(BaseModel):
    stage: Literal["cause", "evidence"]
    duration_ms: float = Field(ge=0)
    model: str
    usage: DecisionUsage
    answers: dict[str, str]
    confidence: dict[str, Annotated[float, Field(ge=0, le=1)]] = Field(
        default_factory=dict
    )


class ComparisonBranch(BaseModel):
    provider: Provider
    model: str
    outcome: Literal["supported", "inconclusive", "failed"]
    candidate_index: int | None = Field(default=None, ge=0, le=4)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    evidence_relations: dict[str, str] = Field(default_factory=dict)
    error_code: (
        Literal["timeout", "unavailable", "invalid_output", "internal_error"] | None
    ) = None
    started_at: datetime
    start_offset_ms: float = Field(ge=0)
    duration_ms: float = Field(ge=0)
    calls: list[DecisionCall] = Field(default_factory=list)
    attempted_calls: int = Field(default=0, ge=0, le=2)


class PreparedComparison(BaseModel):
    comparison_id: UUID
    input_sha256: str
    started_at: datetime
    preparation_ms: float = Field(ge=0)
    candidates: list[str]
    evidence: list[Evidence]
    runbooks: list[RetrievedRunbook]
    documents: list[RetrievedKnowledgeDocument]


class ComparisonFinished(BaseModel):
    duration_ms: float = Field(ge=0)
    cleanup: Literal["not_needed", "completed", "deferred"]


class ComparisonEvent(BaseModel):
    type: Literal["prepared", "branch", "finished", "error"]
    prepared: PreparedComparison | None = None
    branch: ComparisonBranch | None = None
    finished: ComparisonFinished | None = None
    error: (
        Literal["preparation_unavailable", "internal_error", "input_too_large"] | None
    ) = None
