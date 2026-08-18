"""Define the small boundary shared by concrete reasoning implementations."""

from collections.abc import Callable

from resolve_ai.models import (
    Evidence,
    Hypothesis,
    Incident,
    RetrievedReferenceKnowledge,
)

HypothesisGenerator = Callable[
    [Incident, list[Evidence], list[RetrievedReferenceKnowledge]],
    Hypothesis,
]


class InsufficientEvidenceError(Exception):
    """Raised when a reasoner cannot support a diagnosis from the supplied facts."""
