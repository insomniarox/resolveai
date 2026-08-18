"""Provide deterministic hypothesis generation for Phase 1.

This is called a "fake model" because it occupies the place where a future LLM
call may live, but it contains ordinary Python rules and always returns the same
answer for the same evidence. That makes the surrounding application workflow
fully testable while we learn its boundaries.

The fake performs only two supported mappings:

* pool reduction + connection timeout -> connection-pool hypothesis
* expired-certificate log -> expired-certificate hypothesis

It does not inspect incident IDs, call an external service, or invent evidence.
"""

from resolve_ai.models import (
    Evidence,
    EvidenceKind,
    EvidenceSource,
    Hypothesis,
    Incident,
    RetrievedReferenceKnowledge,
    RootCauseLabel,
)
from resolve_ai.reasoning import InsufficientEvidenceError


def generate_hypothesis(evidence: list[Evidence]) -> Hypothesis:
    """Derive a supported hypothesis solely from normalized evidence facts.

    Incident IDs are intentionally absent from this boundary. This prevents the
    fake from becoming a lookup table and keeps its contract useful for a future
    real model implementation.
    """
    connection_timeout = _find_connection_timeout(evidence)
    latest_pool_change = _find_latest_connection_pool_change(evidence)

    # The latest change represents the pool setting in effect when the incident
    # began. An older reduction must not cause a diagnosis if a later deployment
    # restored the pool. A timeout or reduction by itself is still insufficient.
    if (
        connection_timeout is not None
        and latest_pool_change is not None
        and _is_connection_pool_reduction(latest_pool_change)
    ):
        previous_size = latest_pool_change.details["previous_value"]
        new_size = latest_pool_change.details["new_value"]

        return Hypothesis(
            root_cause_label=RootCauseLabel.CONNECTION_POOL_EXHAUSTION,
            probable_root_cause=(
                "A deployment reduced the database connection pool from "
                f"{previous_size} to {new_size}, causing connection acquisition "
                "timeouts."
            ),
            cited_evidence_ids=[latest_pool_change.id, connection_timeout.id],
            confidence=0.9,
            recommended_remediation=(
                f"Restore the database connection pool size to {previous_size}."
            ),
        )

    expired_certificate = _find_expired_certificate(evidence)

    if expired_certificate is not None:
        certificate_name = expired_certificate.details["certificate_name"]
        return Hypothesis(
            root_cause_label=RootCauseLabel.EXPIRED_CLIENT_CERTIFICATE,
            probable_root_cause=(
                f"The {certificate_name} authentication certificate expired, "
                "causing authentication requests to fail."
            ),
            cited_evidence_ids=[expired_certificate.id],
            confidence=0.95,
            recommended_remediation=(
                f"Renew the {certificate_name} certificate through the approved "
                "certificate rotation process."
            ),
        )

    raise InsufficientEvidenceError(
        "No supported hypothesis can be derived from the supplied evidence."
    )


def generate_fake_hypothesis(
    incident: Incident,
    evidence: list[Evidence],
    retrieved_knowledge: list[RetrievedReferenceKnowledge],
) -> Hypothesis:
    """Adapt the evidence-only fake to the shared reasoning boundary."""
    del incident, retrieved_knowledge
    return generate_hypothesis(evidence)


def _find_connection_timeout(evidence: list[Evidence]) -> Evidence | None:
    """Return the first database-timeout log, if the list contains one."""
    for item in evidence:
        if (
            item.source == EvidenceSource.LOG
            and item.kind == EvidenceKind.DATABASE_CONNECTION_TIMEOUT
        ):
            return item
    return None


def _find_latest_connection_pool_change(
    evidence: list[Evidence],
) -> Evidence | None:
    """Return the most recent valid pool change without reordering evidence."""
    latest_change: Evidence | None = None

    for item in evidence:
        if not _is_connection_pool_change(item):
            continue

        if latest_change is None or item.observed_at > latest_change.observed_at:
            latest_change = item

    return latest_change


def _is_connection_pool_change(evidence: Evidence) -> bool:
    """Check that evidence describes a usable connection-pool size change."""
    return (
        evidence.source == EvidenceSource.DEPLOYMENT
        and evidence.kind == EvidenceKind.CONFIGURATION_CHANGE
        and evidence.details.get("setting") == "database_connection_pool_size"
        and isinstance(evidence.details.get("previous_value"), int)
        and isinstance(evidence.details.get("new_value"), int)
    )


def _is_connection_pool_reduction(evidence: Evidence) -> bool:
    """Check whether a valid pool change makes the pool smaller."""
    previous_value = evidence.details.get("previous_value")
    new_value = evidence.details.get("new_value")

    return (
        _is_connection_pool_change(evidence)
        and isinstance(previous_value, int)
        and isinstance(new_value, int)
        and new_value < previous_value
    )


def _find_expired_certificate(evidence: list[Evidence]) -> Evidence | None:
    """Return the first usable expired-certificate log, if one exists."""
    for item in evidence:
        if _is_expired_certificate(item):
            return item
    return None


def _is_expired_certificate(evidence: Evidence) -> bool:
    """Require a certificate name because the diagnosis includes that value."""
    return (
        evidence.source == EvidenceSource.LOG
        and evidence.kind == EvidenceKind.AUTHENTICATION_CERTIFICATE_EXPIRED
        and isinstance(evidence.details.get("certificate_name"), str)
    )
