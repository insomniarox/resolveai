import type {
  Diagnosis,
  Evidence,
  EvidenceKind,
  EvidenceSource,
  Incident,
  InvestigationResult,
  RetrievedRunbook,
  RootCauseLabel,
} from "@/lib/types";

export const UNEXPECTED_RESPONSE_MESSAGE =
  "ResolveAI returned an unexpected response.";

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export class UnexpectedResponseError extends Error {
  constructor() {
    super(UNEXPECTED_RESPONSE_MESSAGE);
    this.name = "UnexpectedResponseError";
  }
}

const evidenceSources = new Set<EvidenceSource>(["log", "deployment"]);
const evidenceKinds = new Set<EvidenceKind>([
  "database_connection_timeout",
  "database_lock_wait",
  "database_transaction_state",
  "authentication_certificate_expired",
  "tls_handshake_validation_failed",
  "upstream_request_failed",
  "upstream_health_check",
  "notification_queue_metrics",
  "notification_worker_metrics",
  "http_request_failed",
  "configuration_change",
]);
const rootCauseLabels = new Set<RootCauseLabel>([
  "connection_pool_exhaustion",
  "expired_client_certificate",
  "database_lock_contention",
  "upstream_tls_identity_mismatch",
  "notification_provider_outage",
  "notification_worker_backlog",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isDateTime(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

function isIncident(value: unknown): value is Incident {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    typeof value.description === "string" &&
    typeof value.service === "string" &&
    isDateTime(value.started_at)
  );
}

function isEvidenceDetails(
  value: unknown,
): value is Record<string, string | number> {
  return (
    isRecord(value) &&
    Object.values(value).every(
      (item) => typeof item === "string" || typeof item === "number",
    )
  );
}

function isEvidence(value: unknown): value is Evidence {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.source === "string" &&
    evidenceSources.has(value.source as EvidenceSource) &&
    typeof value.kind === "string" &&
    evidenceKinds.has(value.kind as EvidenceKind) &&
    isDateTime(value.observed_at) &&
    typeof value.summary === "string" &&
    isEvidenceDetails(value.details)
  );
}

function isRetrievedRunbook(value: unknown): value is RetrievedRunbook {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    typeof value.service === "string" &&
    typeof value.content === "string" &&
    typeof value.similarity_score === "number" &&
    Number.isFinite(value.similarity_score)
  );
}

function isDiagnosis(value: unknown): value is Diagnosis {
  return (
    isRecord(value) &&
    typeof value.root_cause_label === "string" &&
    rootCauseLabels.has(value.root_cause_label as RootCauseLabel) &&
    typeof value.probable_root_cause === "string" &&
    typeof value.confidence === "number" &&
    value.confidence >= 0 &&
    value.confidence <= 1 &&
    typeof value.recommended_remediation === "string" &&
    typeof value.human_approval_required === "boolean" &&
    isStringArray(value.supporting_evidence_ids) &&
    value.supporting_evidence_ids.length > 0
  );
}

function isInvestigationResult(value: unknown): value is InvestigationResult {
  if (
    !isRecord(value) ||
    typeof value.incident_id !== "string" ||
    !Array.isArray(value.evidence) ||
    !value.evidence.every(isEvidence) ||
    !Array.isArray(value.retrieved_runbooks) ||
    !value.retrieved_runbooks.every(isRetrievedRunbook)
  ) {
    return false;
  }

  if (value.status === "inconclusive") {
    return value.diagnosis === null;
  }

  if (value.status !== "diagnosed" || !isDiagnosis(value.diagnosis)) {
    return false;
  }

  const collectedEvidenceIds = new Set(
    value.evidence.map((item) => item.id),
  );
  return value.diagnosis.supporting_evidence_ids.every((id) =>
    collectedEvidenceIds.has(id),
  );
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    throw new UnexpectedResponseError();
  }
}

async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: "application/json", ...init?.headers },
  });

  if (!response.ok) {
    let message = `ResolveAI request failed with status ${response.status}.`;

    try {
      const errorBody: unknown = await response.json();
      if (isRecord(errorBody) && typeof errorBody.detail === "string") {
        message = errorBody.detail;
      }
    } catch {
      // FastAPI may return a non-JSON body for an unhandled server failure.
    }

    throw new ApiRequestError(message, response.status);
  }

  return readJson(response);
}

export async function fetchIncidents(): Promise<Incident[]> {
  const value = await requestJson("/api/incidents", { cache: "no-store" });
  if (!Array.isArray(value) || !value.every(isIncident)) {
    throw new UnexpectedResponseError();
  }
  return value;
}

export async function investigateIncident(
  incidentId: string,
): Promise<InvestigationResult> {
  const value = await requestJson(
    `/api/incidents/${encodeURIComponent(incidentId)}/investigate`,
    { method: "POST" },
  );
  if (!isInvestigationResult(value)) {
    throw new UnexpectedResponseError();
  }
  return value;
}
