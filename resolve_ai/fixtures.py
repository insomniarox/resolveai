"""Provide synthetic operational data without a database.

In a production system, incidents, logs, and deployments would come from
different external systems. Phase 1 keeps them in one Python dictionary so the
investigation flow is visible before persistence or tool integrations are added.

These records are input to the investigation. They are not model responses and
they contain no real production or customer data.
"""

from datetime import UTC, datetime

from resolve_ai.models import (
    ConfigurationChange,
    Deployment,
    EvidenceKind,
    Incident,
    IncidentContext,
    LogEntry,
)

_INCIDENT_CONTEXTS: dict[str, IncidentContext] = {
    # Timeline: the deployment reduces the pool at 10:31, then database timeouts
    # and failed payment requests begin at 10:37. The fake must discover this
    # relationship from normalized evidence rather than from the incident ID.
    "INC-001": IncidentContext(
        incident=Incident(
            id="INC-001",
            title="Payments API returning HTTP 500 responses",
            description="Payment requests began failing after the morning deployment.",
            service="payment-service",
            started_at=datetime(2026, 8, 8, 10, 37, tzinfo=UTC),
        ),
        logs=[
            LogEntry(
                id="LOG-001",
                timestamp=datetime(2026, 8, 8, 10, 37, 12, tzinfo=UTC),
                service="payment-service",
                kind=EvidenceKind.DATABASE_CONNECTION_TIMEOUT,
                message="Timed out while acquiring a database connection.",
            ),
            LogEntry(
                id="LOG-002",
                timestamp=datetime(2026, 8, 8, 10, 37, 13, tzinfo=UTC),
                service="payment-service",
                kind=EvidenceKind.HTTP_REQUEST_FAILED,
                message="POST /payments completed with HTTP 500.",
            ),
        ],
        deployments=[
            Deployment(
                id="DEP-001",
                service="payment-service",
                version="2026.08.08.1",
                deployed_at=datetime(2026, 8, 8, 10, 31, tzinfo=UTC),
                configuration_changes=[
                    ConfigurationChange(
                        setting="database_connection_pool_size",
                        previous_value=20,
                        new_value=5,
                    )
                ],
            )
        ],
    ),
    # This incident has no causal deployment change. Its useful fact is the
    # explicit certificate-expiration log emitted when authentication fails.
    "INC-002": IncidentContext(
        incident=Incident(
            id="INC-002",
            title="Authentication requests rejected",
            description="Services began receiving authentication failures.",
            service="authentication-service",
            started_at=datetime(2026, 8, 8, 11, 5, tzinfo=UTC),
        ),
        logs=[
            LogEntry(
                id="LOG-003",
                timestamp=datetime(2026, 8, 8, 11, 5, 1, tzinfo=UTC),
                service="authentication-service",
                kind=EvidenceKind.AUTHENTICATION_CERTIFICATE_EXPIRED,
                message="The payment-api-client certificate has expired.",
                details={"certificate_name": "payment-api-client"},
            ),
            LogEntry(
                id="LOG-004",
                timestamp=datetime(2026, 8, 8, 11, 5, 2, tzinfo=UTC),
                service="authentication-service",
                kind=EvidenceKind.HTTP_REQUEST_FAILED,
                message="POST /tokens completed with HTTP 401.",
            ),
        ],
        deployments=[
            Deployment(
                id="DEP-002",
                service="authentication-service",
                version="2026.08.08.2",
                deployed_at=datetime(2026, 8, 8, 9, 0, tzinfo=UTC),
                configuration_changes=[],
            )
        ],
    ),
    # The available data shows impact but no supported cause. This fixture makes
    # uncertainty observable: ResolveAI should return an inconclusive result
    # instead of guessing or turning a normal investigation outcome into a 500.
    "INC-003": IncidentContext(
        incident=Incident(
            id="INC-003",
            title="Notification delivery failures",
            description="Outbound notifications began failing.",
            service="notification-service",
            started_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        ),
        logs=[
            LogEntry(
                id="LOG-005",
                timestamp=datetime(2026, 8, 8, 12, 0, 1, tzinfo=UTC),
                service="notification-service",
                kind=EvidenceKind.HTTP_REQUEST_FAILED,
                message="POST /messages completed with HTTP 503.",
            )
        ],
        deployments=[
            Deployment(
                id="DEP-003",
                service="notification-service",
                version="2026.08.08.3",
                deployed_at=datetime(2026, 8, 8, 8, 0, tzinfo=UTC),
                configuration_changes=[],
            )
        ],
    ),
}


def list_incidents() -> list[Incident]:
    """Return safe incident copies in chronological order.

    Discovery returns only each ``Incident`` and does not expose its logs or
    deployments. Sorting explicitly avoids making the API order depend on where
    fixtures happen to appear in this file.
    """
    incidents = [
        context.incident.model_copy(deep=True)
        for context in _INCIDENT_CONTEXTS.values()
    ]
    return sorted(incidents, key=lambda incident: incident.started_at)


def get_incident_context(incident_id: str) -> IncidentContext | None:
    """Look up one incident, returning ``None`` when the ID is unknown.

    ``model_copy(deep=True)`` produces a new context including new nested lists
    and models. Without that copy, accidental mutation during one request or test
    could change the module-level fixture seen by a later request.
    """
    context = _INCIDENT_CONTEXTS.get(incident_id)
    if context is None:
        return None
    return context.model_copy(deep=True)
