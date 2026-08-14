"""Coordinate the investigation with ordinary Python functions.

"Orchestration" means deciding which steps run and in which order. The current
workflow is a short sequence with one expected outcome branch:

raw context -> collect evidence -> retrieve runbooks -> generate hypothesis
                                                        |
                                                        +-> no match -> inconclusive

There are no loops, retries, persistent state, or conditional tool calls, so a
workflow framework such as LangGraph would make this sequence harder to follow.
"""

from resolve_ai.fake_model import InsufficientEvidenceError, generate_hypothesis
from resolve_ai.models import (
    Diagnosis,
    Evidence,
    EvidenceKind,
    EvidenceSource,
    Hypothesis,
    IncidentContext,
    InvestigationResult,
    InvestigationStatus,
    RetrievedRunbook,
)
from resolve_ai.retrieval import semantic_search_runbooks

_RUNBOOK_RETRIEVAL_LIMIT = 3


class UnknownEvidenceError(Exception):
    """Raised when a hypothesis cites evidence that was not collected."""


def investigate_incident(
    context: IncidentContext,
    database_url: str,
) -> InvestigationResult:
    """Run the synchronous workflow with evidence and retrieved knowledge.

    This is the main domain function. It accepts data rather than an HTTP request,
    which is why tests can call it directly without starting FastAPI or Uvicorn.
    PostgreSQL failures intentionally propagate because missing retrieval is a
    system failure, not evidence that the incident is inconclusive.
    """
    log_evidence = inspect_logs(context)
    deployment_evidence = inspect_deployments(context)
    evidence = log_evidence + deployment_evidence

    retrieval_query = build_runbook_query(context, evidence)
    retrieved_runbooks = semantic_search_runbooks(
        database_url=database_url,
        query=retrieval_query,
        limit=_RUNBOOK_RETRIEVAL_LIMIT,
    )

    # Insufficient evidence is an expected investigation outcome, not a server
    # failure. Other exceptions are intentionally not caught here because they
    # represent defects or unexpected failures that should remain visible.
    try:
        hypothesis = generate_hypothesis(evidence)
    except InsufficientEvidenceError:
        return _build_inconclusive_result(
            context.incident.id,
            evidence,
            retrieved_runbooks,
        )

    # Hypothesis generation proposes a conclusion; verification is deliberately
    # a separate application step because model output must not be trusted blindly.
    return verify_hypothesis(
        context.incident.id,
        hypothesis,
        evidence,
        retrieved_runbooks,
    )


def build_runbook_query(
    context: IncidentContext,
    evidence: list[Evidence],
) -> str:
    """Build a deterministic query from the report and observed facts."""
    lines = [
        f"Incident: {context.incident.title}",
        f"Description: {context.incident.description}",
        "Observed evidence:",
    ]
    lines.extend(f"- {item.summary}" for item in evidence)
    return "\n".join(lines)


def _build_inconclusive_result(
    incident_id: str,
    evidence: list[Evidence],
    retrieved_runbooks: list[RetrievedRunbook],
) -> InvestigationResult:
    """Return collected observations without inventing a root cause or action."""
    return InvestigationResult(
        incident_id=incident_id,
        status=InvestigationStatus.INCONCLUSIVE,
        diagnosis=None,
        # The result owns its list container; list() preserves collection order.
        evidence=list(evidence),
        retrieved_runbooks=list(retrieved_runbooks),
    )


def inspect_logs(context: IncidentContext) -> list[Evidence]:
    """Select relevant logs and normalize them into ``Evidence``.

    A log is relevant in this small baseline when it belongs to the affected
    service and happened at or after the reported incident start. More advanced
    time windows and relevance ranking are deliberately postponed.
    """
    evidence: list[Evidence] = []

    for log in context.logs:
        if log.service != context.incident.service:
            continue
        if log.timestamp < context.incident.started_at:
            continue

        # Preserve the source ID so a later hypothesis can cite the exact log.
        evidence.append(
            Evidence(
                id=log.id,
                source=EvidenceSource.LOG,
                kind=log.kind,
                observed_at=log.timestamp,
                summary=log.message,
                details=log.details,
            )
        )

    return evidence


def inspect_deployments(context: IncidentContext) -> list[Evidence]:
    """Select earlier deployments and normalize each configuration change.

    A deployment can contain several changes, so each change becomes its own
    evidence item. Its ID combines the deployment ID and setting name, allowing a
    hypothesis to cite the precise change rather than the whole deployment.
    """
    evidence: list[Evidence] = []

    for deployment in context.deployments:
        if deployment.service != context.incident.service:
            continue
        if deployment.deployed_at > context.incident.started_at:
            continue

        for change in deployment.configuration_changes:
            evidence.append(
                Evidence(
                    id=f"{deployment.id}:{change.setting}",
                    source=EvidenceSource.DEPLOYMENT,
                    kind=EvidenceKind.CONFIGURATION_CHANGE,
                    observed_at=deployment.deployed_at,
                    summary=(
                        f"Deployment {deployment.id} changed {change.setting} from "
                        f"{change.previous_value} to {change.new_value}."
                    ),
                    details={
                        "deployment_id": deployment.id,
                        "version": deployment.version,
                        "setting": change.setting,
                        "previous_value": change.previous_value,
                        "new_value": change.new_value,
                    },
                )
            )

    return evidence


def verify_hypothesis(
    incident_id: str,
    hypothesis: Hypothesis,
    evidence: list[Evidence],
    retrieved_runbooks: list[RetrievedRunbook],
) -> InvestigationResult:
    """Promote a hypothesis after checking only that its citations exist.

    This milestone deliberately does not judge whether cited evidence
    semantically proves the claim. That more difficult evaluation problem remains
    postponed.
    """
    # Turn the list into a lookup table such as {"LOG-001": Evidence(...)} so
    # each model-provided citation can be checked directly.
    evidence_by_id = {item.id: item for item in evidence}
    missing_ids = [
        evidence_id
        for evidence_id in hypothesis.cited_evidence_ids
        if evidence_id not in evidence_by_id
    ]

    if missing_ids:
        missing = ", ".join(missing_ids)
        raise UnknownEvidenceError(f"Hypothesis cited unknown evidence: {missing}")

    return InvestigationResult(
        incident_id=incident_id,
        status=InvestigationStatus.DIAGNOSED,
        diagnosis=Diagnosis(
            probable_root_cause=hypothesis.probable_root_cause,
            confidence=hypothesis.confidence,
            recommended_remediation=hypothesis.recommended_remediation,
            # Both current remediations mutate runtime configuration, so approval
            # is application policy rather than a fake-model decision.
            human_approval_required=True,
            # Diagnosis is a new domain result, so copy the mutable citation list
            # instead of sharing Hypothesis internal state. list() keeps the
            # hypothesis citation order unchanged.
            supporting_evidence_ids=list(hypothesis.cited_evidence_ids),
        ),
        # Include every collected observation, not only the supporting subset.
        # The shallow list copy gives the result its own ordered container.
        evidence=list(evidence),
        # Retrieved guidance remains separate from observed and cited evidence.
        retrieved_runbooks=list(retrieved_runbooks),
    )
