"""Coordinate the investigation with ordinary Python functions.

"Orchestration" means deciding which steps run and in which order. For Phase 1
the complete workflow is a straight line:

raw context -> collect evidence -> generate hypothesis -> verify -> final result

There are no loops, retries, persistent state, or conditional tool calls, so a
workflow framework such as LangGraph would make this sequence harder to follow.
"""

from resolve_ai.fake_model import generate_hypothesis
from resolve_ai.models import (
    Evidence,
    EvidenceKind,
    EvidenceSource,
    Hypothesis,
    IncidentContext,
    InvestigationResult,
)


class UnknownEvidenceError(Exception):
    """Raised when a hypothesis cites evidence that was not collected."""


def investigate_incident(context: IncidentContext) -> InvestigationResult:
    """Run the complete synchronous Phase 1 workflow for one incident.

    This is the main domain function. It accepts data rather than an HTTP request,
    which is why tests can call it directly without starting FastAPI or Uvicorn.
    """
    log_evidence = inspect_logs(context)
    deployment_evidence = inspect_deployments(context)
    evidence = log_evidence + deployment_evidence

    # Hypothesis generation proposes a conclusion; verification is deliberately
    # a separate application step because model output must not be trusted blindly.
    hypothesis = generate_hypothesis(evidence)
    return verify_hypothesis(context.incident.id, hypothesis, evidence)


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
) -> InvestigationResult:
    """Promote a hypothesis after checking only that its citations exist.

    Phase 1 deliberately does not judge whether cited evidence semantically
    proves the claim. That more difficult evaluation problem remains postponed.
    """
    # Turn the list into a lookup table such as {"LOG-001": Evidence(...)}.
    # This makes checking and resolving each citation direct and readable.
    evidence_by_id = {item.id: item for item in evidence}
    missing_ids = [
        evidence_id
        for evidence_id in hypothesis.cited_evidence_ids
        if evidence_id not in evidence_by_id
    ]

    if missing_ids:
        missing = ", ".join(missing_ids)
        raise UnknownEvidenceError(f"Hypothesis cited unknown evidence: {missing}")

    # Return only the evidence chosen by the hypothesis, in citation order. The
    # uncited observations remain available internally but are not presented as
    # support for a conclusion the fake did not associate with them.
    cited_evidence = [
        evidence_by_id[evidence_id] for evidence_id in hypothesis.cited_evidence_ids
    ]

    return InvestigationResult(
        incident_id=incident_id,
        probable_root_cause=hypothesis.probable_root_cause,
        evidence=cited_evidence,
        confidence=hypothesis.confidence,
        recommended_remediation=hypothesis.recommended_remediation,
        # Both current remediations mutate runtime configuration, so approval is
        # application policy rather than a decision delegated to the fake model.
        human_approval_required=True,
    )
