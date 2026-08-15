"""Generate one structured hypothesis with a concrete OpenAI model."""

import json
from typing import Self

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, model_validator

from resolve_ai.models import (
    Evidence,
    Hypothesis,
    Incident,
    InvestigationStatus,
    RetrievedRunbook,
    RootCauseLabel,
)
from resolve_ai.reasoning import InsufficientEvidenceError

OPENAI_REASONING_MODEL = "gpt-5.6-luna"

_SYSTEM_INSTRUCTIONS = """You investigate synthetic software incidents.

Use only the supplied incident report, observed Evidence, and RetrievedRunbooks.
Evidence contains observed incident facts. RetrievedRunbooks contain reference
knowledge: retrieval similarity is not causal evidence or diagnosis confidence.

Return diagnosed only when the observed Evidence supports one root-cause label.
Cite only Evidence IDs, never runbook IDs. If competing explanations remain or
the evidence is insufficient, return inconclusive with null diagnosis fields and
an empty cited_evidence_ids list. Do not invent observations or identifiers.
"""


class OpenAIReasoningDecision(BaseModel):
    """Represent both diagnosed and inconclusive structured model output."""

    status: InvestigationStatus
    root_cause_label: RootCauseLabel | None
    probable_root_cause: str | None
    cited_evidence_ids: list[str]
    confidence: float | None = Field(ge=0, le=1)
    recommended_remediation: str | None

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        """Keep diagnosis fields complete or absent as one coherent decision."""
        diagnosis_values = (
            self.root_cause_label,
            self.probable_root_cause,
            self.confidence,
            self.recommended_remediation,
        )

        if self.status == InvestigationStatus.INCONCLUSIVE:
            if any(value is not None for value in diagnosis_values):
                raise ValueError("inconclusive output cannot contain diagnosis fields")
            if self.cited_evidence_ids:
                raise ValueError("inconclusive output cannot cite supporting evidence")
            return self

        if any(value is None for value in diagnosis_values):
            raise ValueError("diagnosed output requires every diagnosis field")
        if not self.cited_evidence_ids:
            raise ValueError("diagnosed output requires supporting evidence IDs")
        return self


def build_openai_reasoning_input(
    incident: Incident,
    evidence: list[Evidence],
    retrieved_runbooks: list[RetrievedRunbook],
) -> str:
    """Serialize the complete reasoning input without adding hidden context."""
    return json.dumps(
        {
            "incident": incident.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "retrieved_runbooks": [
                item.model_dump(mode="json") for item in retrieved_runbooks
            ],
        },
        indent=2,
    )


def generate_openai_hypothesis(
    incident: Incident,
    evidence: list[Evidence],
    retrieved_runbooks: list[RetrievedRunbook],
    *,
    client: OpenAI | None = None,
    model: str = OPENAI_REASONING_MODEL,
) -> Hypothesis:
    """Ask one OpenAI model for a schema-constrained investigation decision."""
    if client is None:
        load_dotenv()
        openai_client = OpenAI()
    else:
        openai_client = client
    response = openai_client.responses.parse(
        model=model,
        input=[
            {"role": "system", "content": _SYSTEM_INSTRUCTIONS},
            {
                "role": "user",
                "content": build_openai_reasoning_input(
                    incident,
                    evidence,
                    retrieved_runbooks,
                ),
            },
        ],
        text_format=OpenAIReasoningDecision,
    )
    decision = response.output_parsed
    if decision is None:
        raise RuntimeError("OpenAI returned no parsed investigation decision")

    if decision.status == InvestigationStatus.INCONCLUSIVE:
        raise InsufficientEvidenceError(
            "The OpenAI reasoner found insufficient evidence for a diagnosis."
        )

    # The decision validator established that diagnosed fields are present.
    if (
        decision.root_cause_label is None
        or decision.probable_root_cause is None
        or decision.confidence is None
        or decision.recommended_remediation is None
    ):
        raise RuntimeError("OpenAI returned an incomplete diagnosed decision")

    return Hypothesis(
        root_cause_label=decision.root_cause_label,
        probable_root_cause=decision.probable_root_cause,
        cited_evidence_ids=list(decision.cited_evidence_ids),
        confidence=decision.confidence,
        recommended_remediation=decision.recommended_remediation,
    )
