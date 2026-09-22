import type {
  Diagnosis,
  Evidence,
  EvidenceKind,
  EvidenceSource,
  Incident,
  InvestigationRun,
  InvestigationResult,
  CreatedInvestigationRun,
  KnowledgeDocument,
  ReasonerMetadata,
  RetrievedKnowledgeDocument,
  RetrievedRunbook,
  RuntimeFailureCode,
  RuntimeExecutionMetadata,
  RuntimeIncidentBundle,
} from "./types";
import { EVIDENCE_KINDS, EVIDENCE_SOURCES } from "./types";

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

const evidenceSources = new Set<EvidenceSource>(EVIDENCE_SOURCES);
const evidenceKinds = new Set<EvidenceKind>(EVIDENCE_KINDS);
const runtimeFailureCodes = new Set<RuntimeFailureCode>([
  "runtime_knowledge_unavailable",
  "reasoner_timeout",
  "invalid_citations",
  "invalid_reasoner_output",
  "reasoner_unavailable",
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

export function isEvidence(value: unknown): value is Evidence {
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

function isKnowledgeDocument(value: unknown): value is KnowledgeDocument {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    (value.content_type === "text/plain" ||
      value.content_type === "text/markdown") &&
    typeof value.content === "string"
  );
}

function isRuntimeIncidentBundle(value: unknown): value is RuntimeIncidentBundle {
  return (
    isRecord(value) &&
    value.schema_version === 1 &&
    isIncident(value.incident) &&
    Array.isArray(value.evidence) &&
    value.evidence.every(isEvidence) &&
    (value.knowledge_documents === undefined ||
      (Array.isArray(value.knowledge_documents) &&
        value.knowledge_documents.every(isKnowledgeDocument)))
  );
}

export function isRetrievedRunbook(value: unknown): value is RetrievedRunbook {
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

export function isRetrievedKnowledgeDocument(
  value: unknown,
): value is RetrievedKnowledgeDocument {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.title === "string" &&
    (value.content_type === "text/plain" ||
      value.content_type === "text/markdown") &&
    typeof value.content === "string" &&
    typeof value.similarity_score === "number" &&
    Number.isFinite(value.similarity_score)
  );
}

function isDiagnosis(value: unknown): value is Diagnosis {
  return (
    isRecord(value) &&
    typeof value.root_cause_label === "string" &&
    /^[a-z0-9]+(?:_[a-z0-9]+)*$/.test(value.root_cause_label) &&
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

function isReasonerMetadata(value: unknown): value is ReasonerMetadata {
  return (
    isRecord(value) &&
    typeof value.provider === "string" &&
    value.provider.length > 0 &&
    typeof value.model === "string" &&
    value.model.length > 0
  );
}

function isRuntimeExecutionMetadata(
  value: unknown,
): value is RuntimeExecutionMetadata {
  return (
    isRecord(value) &&
    typeof value.application_version === "string" &&
    typeof value.prompt_version === "string" &&
    typeof value.output_schema_version === "string" &&
    value.retrieval_strategy === "semantic" &&
    typeof value.retrieval_limit === "number" &&
    Number.isInteger(value.retrieval_limit) &&
    value.retrieval_limit > 0 &&
    typeof value.embedding_model === "string" &&
    typeof value.reasoning_effort === "string" &&
    typeof value.max_output_tokens === "number" &&
    Number.isInteger(value.max_output_tokens) &&
    value.max_output_tokens > 0 &&
    typeof value.timeout_seconds === "number" &&
    Number.isFinite(value.timeout_seconds) &&
    value.timeout_seconds > 0
  );
}

function isInvestigationResult(value: unknown): value is InvestigationResult {
  if (
    !isRecord(value) ||
    typeof value.incident_id !== "string" ||
    !Array.isArray(value.evidence) ||
    !value.evidence.every(isEvidence) ||
    !Array.isArray(value.retrieved_runbooks) ||
    !value.retrieved_runbooks.every(isRetrievedRunbook) ||
    !Array.isArray(value.retrieved_knowledge_documents) ||
    !value.retrieved_knowledge_documents.every(isRetrievedKnowledgeDocument) ||
    !isReasonerMetadata(value.reasoner)
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

function isInvestigationRun(value: unknown): value is InvestigationRun {
  if (
    !isRecord(value) ||
    typeof value.id !== "string" ||
    !isDateTime(value.created_at) ||
    !isDateTime(value.expires_at) ||
    (value.outcome !== "completed" && value.outcome !== "failed") ||
    !isRecord(value.snapshot)
  ) {
    return false;
  }

  const snapshot = value.snapshot;
  const resultIsValid =
    snapshot.investigation_result === null ||
    isInvestigationResult(snapshot.investigation_result);
  const failureIsValid =
    snapshot.failure_code === null ||
    (typeof snapshot.failure_code === "string" &&
      runtimeFailureCodes.has(snapshot.failure_code as RuntimeFailureCode));
  const hasResult = snapshot.investigation_result !== null;
  const hasFailure = snapshot.failure_code !== null;

  return (
    snapshot.schema_version === 1 &&
    isRuntimeIncidentBundle(snapshot.bundle) &&
    Array.isArray(snapshot.retrieved_runbooks) &&
    snapshot.retrieved_runbooks.every(isRetrievedRunbook) &&
    Array.isArray(snapshot.retrieved_knowledge_documents) &&
    snapshot.retrieved_knowledge_documents.every(isRetrievedKnowledgeDocument) &&
    resultIsValid &&
    failureIsValid &&
    hasResult !== hasFailure &&
    isReasonerMetadata(snapshot.reasoner) &&
    isRuntimeExecutionMetadata(snapshot.execution) &&
    isDateTime(snapshot.started_at) &&
    isDateTime(snapshot.completed_at) &&
    typeof snapshot.duration_ms === "number" &&
    Number.isInteger(snapshot.duration_ms) &&
    snapshot.duration_ms >= 0 &&
    ((value.outcome === "completed" && hasResult) ||
      (value.outcome === "failed" && hasFailure))
  );
}

function isCreatedInvestigationRun(
  value: unknown,
): value is CreatedInvestigationRun {
  return (
    isRecord(value) &&
    isInvestigationRun(value.run) &&
    typeof value.capability_token === "string" &&
    value.capability_token.length >= 32
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
      } else if (isRecord(errorBody) && Array.isArray(errorBody.detail)) {
        const validationMessages = errorBody.detail.flatMap((item) => {
          if (
            !isRecord(item) ||
            !Array.isArray(item.loc) ||
            typeof item.msg !== "string"
          ) {
            return [];
          }
          const location = item.loc
            .filter((part) => part !== "body")
            .map(String)
            .join(".");
          return `${location || "bundle"}: ${item.msg}`;
        });
        if (validationMessages.length > 0) {
          message = `Invalid runtime bundle — ${validationMessages.join("; ")}`;
        }
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

export async function investigateRuntimeBundle(
  bundle: unknown,
): Promise<InvestigationResult> {
  const value = await requestJson("/api/runtime/investigate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bundle),
  });
  if (!isInvestigationResult(value)) {
    throw new UnexpectedResponseError();
  }
  return value;
}

export async function createRuntimeInvestigationRun(
  bundle: unknown,
): Promise<CreatedInvestigationRun> {
  const value = await requestJson("/api/runtime/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bundle),
  });
  if (!isCreatedInvestigationRun(value)) {
    throw new UnexpectedResponseError();
  }
  return value;
}

export async function fetchRuntimeInvestigationRun(
  runId: string,
  capabilityToken: string,
): Promise<InvestigationRun> {
  const value = await requestJson(
    `/api/runtime/runs/${encodeURIComponent(runId)}`,
    {
      cache: "no-store",
      headers: { Authorization: `Bearer ${capabilityToken}` },
    },
  );
  if (!isInvestigationRun(value)) {
    throw new UnexpectedResponseError();
  }
  return value;
}

export async function deleteRuntimeInvestigationRun(
  runId: string,
  capabilityToken: string,
): Promise<void> {
  const response = await fetch(`/api/runtime/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${capabilityToken}`,
    },
  });
  if (!response.ok) {
    let message = `ResolveAI request failed with status ${response.status}.`;
    try {
      const errorBody: unknown = await response.json();
      if (isRecord(errorBody) && typeof errorBody.detail === "string") {
        message = errorBody.detail;
      }
    } catch {
      // A proxy or server failure may not have a JSON response body.
    }
    throw new ApiRequestError(message, response.status);
  }
}

export async function fetchRuntimeReasoner(): Promise<ReasonerMetadata> {
  const value = await requestJson("/api/runtime/reasoner", { cache: "no-store" });
  if (!isReasonerMetadata(value)) {
    throw new UnexpectedResponseError();
  }
  return value;
}
