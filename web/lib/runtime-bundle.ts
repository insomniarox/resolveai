import {
  EVIDENCE_KINDS,
  EVIDENCE_SOURCES,
  type Evidence,
  type KnowledgeDocument,
  type RuntimeIncidentBundle,
} from "./types";

export const MAX_RUNTIME_EVIDENCE = 50;
export const MAX_RUNTIME_DETAILS = 20;
export const MAX_RUNTIME_DOCUMENTS = 5;
export const MAX_RUNTIME_DOCUMENT_CHARACTERS = 8_000;
export const MAX_RUNTIME_DOCUMENT_TOTAL_CHARACTERS = 20_000;

export const RUNTIME_IDENTIFIER_PATTERN =
  "[A-Za-z0-9][A-Za-z0-9._:\\/\\-]*";
export const RUNTIME_DETAIL_KEY_PATTERN =
  "[A-Za-z0-9][A-Za-z0-9._\\-]*";

const identifierPattern = new RegExp(`^${RUNTIME_IDENTIFIER_PATTERN}$`);
const detailKeyPattern = new RegExp(`^${RUNTIME_DETAIL_KEY_PATTERN}$`);
const evidenceSources = new Set<string>(EVIDENCE_SOURCES);
const evidenceKinds = new Set<string>(EVIDENCE_KINDS);

export const EXAMPLE_RUNTIME_BUNDLE: RuntimeIncidentBundle = {
  schema_version: 1,
  incident: {
    id: "USER-INC-901",
    title: "Invoice delivery receipts are stalled",
    description: "Invoices remain pending after the signing provider accepts them.",
    service: "invoice-delivery-runtime-service",
    started_at: "2026-08-17T09:00:00Z",
  },
  evidence: [
    {
      id: "USER-LOG-901",
      source: "log",
      kind: "upstream_request_failed",
      observed_at: "2026-08-17T09:00:10Z",
      summary: "Signing receipt callbacks returned HTTP 503.",
      details: {
        endpoint: "signing.partner.example/receipt",
        status_code: 503,
      },
    },
    {
      id: "USER-LOG-902",
      source: "log",
      kind: "notification_queue_metrics",
      observed_at: "2026-08-17T09:00:15Z",
      summary: "1,240 invoices remained in SIGNED_PENDING_RECEIPT.",
      details: { pending_count: 1240 },
    },
    {
      id: "USER-LOG-903",
      source: "log",
      kind: "upstream_health_check",
      observed_at: "2026-08-17T09:00:20Z",
      summary: "The signing provider upload health check remained healthy.",
      details: { status_code: 200 },
    },
  ],
  knowledge_documents: [
    {
      id: "DOC-901",
      title: "Invoice signing lifecycle and probe coverage",
      content_type: "text/markdown",
      content:
        "# Signing lifecycle\n\nSIGNED_PENDING_RECEIPT means the provider accepted the invoice, but only a successful receipt callback completes delivery. Delivery workers no longer own invoices in this state. The upload health check does not test the receipt callback endpoint.",
    },
  ],
};

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function cloneExampleRuntimeBundle(): RuntimeIncidentBundle {
  return clone(EXAMPLE_RUNTIME_BUNDLE);
}

export function readableOption(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function nextId(prefix: string, reservedIds: Iterable<string>): string {
  const reserved = new Set(reservedIds);
  let index = 1;
  while (reserved.has(`${prefix}-${String(index).padStart(3, "0")}`)) {
    index += 1;
  }
  return `${prefix}-${String(index).padStart(3, "0")}`;
}

export function createRuntimeEvidence(existing: readonly Evidence[]): Evidence {
  return {
    id: nextId(
      "USER-EVIDENCE",
      existing.map((item) => item.id),
    ),
    source: "log",
    kind: "http_request_failed",
    observed_at: new Date().toISOString(),
    summary: "",
    details: {},
  };
}

export function createRuntimeDocument(
  reservedIds: Iterable<string>,
): KnowledgeDocument {
  return {
    id: nextId("DOC", reservedIds),
    title: "",
    content_type: "text/plain",
    content: "",
  };
}

export function toDateTimeLocalValue(value: string): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  const localTime = date.getTime() - date.getTimezoneOffset() * 60_000;
  return new Date(localTime).toISOString().slice(0, 16);
}

function hasUtcOffset(value: string): boolean {
  return /(Z|[+-]\d{2}:\d{2})$/.test(value);
}

function normalizeFormTimestamp(value: string): string {
  if (!value || hasUtcOffset(value)) return value;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

export function prepareRuntimeBundle(
  bundle: RuntimeIncidentBundle,
): RuntimeIncidentBundle {
  const prepared = clone(bundle);
  prepared.incident.started_at = normalizeFormTimestamp(
    prepared.incident.started_at,
  );
  prepared.evidence = prepared.evidence.map((item) => ({
    ...item,
    observed_at: normalizeFormTimestamp(item.observed_at),
  }));
  prepared.knowledge_documents = prepared.knowledge_documents ?? [];
  return prepared;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, allowed: string[]): boolean {
  const allowedKeys = new Set(allowed);
  return Object.keys(value).every((key) => allowedKeys.has(key));
}

function isBoundedText(
  value: unknown,
  maximum: number,
  minimum = 1,
): value is string {
  return (
    typeof value === "string" &&
    value.trim().length >= minimum &&
    value.length <= maximum
  );
}

function isOffsetTimestamp(value: unknown): value is string {
  return (
    typeof value === "string" &&
    hasUtcOffset(value) &&
    !Number.isNaN(Date.parse(value))
  );
}

export function validateRuntimeBundle(value: unknown): string[] {
  const errors: string[] = [];
  if (!isRecord(value)) return ["The runtime bundle must be an object."];
  if (!hasOnlyKeys(value, ["schema_version", "incident", "evidence", "knowledge_documents"])) {
    errors.push("The runtime bundle contains an unknown field.");
  }
  if (value.schema_version !== 1) errors.push("Schema version must be 1.");

  const incident = value.incident;
  if (!isRecord(incident)) {
    errors.push("Incident information is required.");
  } else {
    if (!hasOnlyKeys(incident, ["id", "title", "description", "service", "started_at"])) {
      errors.push("The incident contains an unknown field.");
    }
    if (
      !isBoundedText(incident.id, 128) ||
      !identifierPattern.test(incident.id)
    ) {
      errors.push("Incident ID must use 1 to 128 letters, numbers, or . _ : / - characters.");
    }
    if (!isBoundedText(incident.title, 160)) {
      errors.push("Incident title must contain 1 to 160 characters.");
    }
    if (!isBoundedText(incident.description, 2_000)) {
      errors.push("Incident description must contain 1 to 2,000 characters.");
    }
    if (!isBoundedText(incident.service, 100)) {
      errors.push("Incident service must contain 1 to 100 characters.");
    }
    if (!isOffsetTimestamp(incident.started_at)) {
      errors.push("Incident start time must be a valid timestamp with a UTC offset.");
    }
  }

  const evidence = value.evidence;
  if (
    !Array.isArray(evidence) ||
    evidence.length < 1 ||
    evidence.length > MAX_RUNTIME_EVIDENCE
  ) {
    errors.push("Provide between 1 and 50 evidence items.");
  }

  const evidenceIds: string[] = [];
  if (Array.isArray(evidence)) {
    evidence.forEach((item, index) => {
      const position = index + 1;
      if (!isRecord(item)) {
        errors.push(`Evidence ${position} must be an object.`);
        return;
      }
      if (!hasOnlyKeys(item, ["id", "source", "kind", "observed_at", "summary", "details"])) {
        errors.push(`Evidence ${position} contains an unknown field.`);
      }
      if (!isBoundedText(item.id, 128) || !identifierPattern.test(item.id)) {
        errors.push(`Evidence ${position} has an invalid ID.`);
      } else {
        evidenceIds.push(item.id);
      }
      if (typeof item.source !== "string" || !evidenceSources.has(item.source)) {
        errors.push(`Evidence ${position} has an unsupported source.`);
      }
      if (typeof item.kind !== "string" || !evidenceKinds.has(item.kind)) {
        errors.push(`Evidence ${position} has an unsupported kind.`);
      }
      if (!isOffsetTimestamp(item.observed_at)) {
        errors.push(`Evidence ${position} needs a valid timestamp with a UTC offset.`);
      }
      if (!isBoundedText(item.summary, 2_000)) {
        errors.push(`Evidence ${position} summary must contain 1 to 2,000 characters.`);
      }
      if (!isRecord(item.details)) {
        errors.push(`Evidence ${position} details must be an object.`);
        return;
      }
      const detailEntries = Object.entries(item.details);
      if (detailEntries.length > MAX_RUNTIME_DETAILS) {
        errors.push(`Evidence ${position} can contain at most 20 details.`);
      }
      detailEntries.forEach(([key, detailValue]) => {
        if (key.length > 64 || !detailKeyPattern.test(key)) {
          errors.push(`Evidence ${position} has an invalid detail key.`);
        }
        if (
          !(
            (typeof detailValue === "string" &&
              detailValue.trim().length >= 1 &&
              detailValue.length <= 500) ||
            (typeof detailValue === "number" && Number.isInteger(detailValue))
          )
        ) {
          errors.push(
            `Evidence ${position} detail ${key || "value"} must be a nonblank string or integer.`,
          );
        }
      });
    });
  }

  if (new Set(evidenceIds).size !== evidenceIds.length) {
    errors.push("Evidence IDs must be unique.");
  }

  const documents = value.knowledge_documents ?? [];
  if (!Array.isArray(documents) || documents.length > MAX_RUNTIME_DOCUMENTS) {
    errors.push("Provide no more than five knowledge documents.");
    return errors;
  }

  const documentIds: string[] = [];
  let totalCharacters = 0;
  documents.forEach((item, index) => {
    const position = index + 1;
    if (!isRecord(item)) {
      errors.push(`Knowledge document ${position} must be an object.`);
      return;
    }
    if (!hasOnlyKeys(item, ["id", "title", "content_type", "content"])) {
      errors.push(`Knowledge document ${position} contains an unknown field.`);
    }
    if (!isBoundedText(item.id, 128) || !identifierPattern.test(item.id)) {
      errors.push(`Knowledge document ${position} has an invalid ID.`);
    } else {
      documentIds.push(item.id);
    }
    if (!isBoundedText(item.title, 160)) {
      errors.push(`Knowledge document ${position} title must contain 1 to 160 characters.`);
    }
    if (item.content_type !== "text/plain" && item.content_type !== "text/markdown") {
      errors.push(`Knowledge document ${position} must be plain text or Markdown.`);
    }
    if (
      typeof item.content !== "string" ||
      !item.content.trim() ||
      item.content.length > MAX_RUNTIME_DOCUMENT_CHARACTERS ||
      item.content.includes("\0")
    ) {
      errors.push(`Knowledge document ${position} must contain 1 to 8,000 valid text characters.`);
    }
    if (typeof item.content === "string") totalCharacters += item.content.length;
  });

  if (new Set(documentIds).size !== documentIds.length) {
    errors.push("Knowledge document IDs must be unique.");
  }
  if (documentIds.some((id) => evidenceIds.includes(id))) {
    errors.push("Knowledge document IDs must differ from evidence IDs.");
  }
  if (totalCharacters > MAX_RUNTIME_DOCUMENT_TOTAL_CHARACTERS) {
    errors.push("Knowledge documents can contain at most 20,000 characters in total.");
  }
  return errors;
}

export function parseRuntimeBundleJson(text: string): RuntimeIncidentBundle {
  const value: unknown = JSON.parse(text);
  const errors = validateRuntimeBundle(value);
  if (errors.length > 0) throw new Error(errors.join(" "));
  return clone(value) as RuntimeIncidentBundle;
}

export async function runtimeDocumentsFromFiles(
  files: readonly File[],
  existingDocuments: readonly KnowledgeDocument[],
  reservedIds: Iterable<string>,
): Promise<KnowledgeDocument[]> {
  if (existingDocuments.length + files.length > MAX_RUNTIME_DOCUMENTS) {
    throw new Error("A runtime bundle can contain at most five documents.");
  }

  const documents: KnowledgeDocument[] = [];
  const ids = new Set(reservedIds);
  let totalCharacters = existingDocuments.reduce(
    (total, item) => total + item.content.length,
    0,
  );

  for (const file of files) {
    const lowerName = file.name.toLowerCase();
    const isMarkdown = lowerName.endsWith(".md");
    if (!isMarkdown && !lowerName.endsWith(".txt")) {
      throw new Error(`${file.name} is not a .txt or .md file.`);
    }
    if (file.size > 64_000) {
      throw new Error(`${file.name} is too large to read as a bounded text document.`);
    }

    const content = await file.text();
    if (!content.trim() || content.includes("\0")) {
      throw new Error(`${file.name} does not contain valid nonblank text.`);
    }
    if (content.length > MAX_RUNTIME_DOCUMENT_CHARACTERS) {
      throw new Error(`${file.name} contains more than 8,000 characters.`);
    }
    totalCharacters += content.length;
    if (totalCharacters > MAX_RUNTIME_DOCUMENT_TOTAL_CHARACTERS) {
      throw new Error("Attached documents would exceed the 20,000-character total.");
    }

    const id = nextId("DOC", ids);
    ids.add(id);
    const title = file.name.replace(/\.(md|txt)$/i, "").trim().slice(0, 160);
    documents.push({
      id,
      title: title || "Attached document",
      content_type: isMarkdown ? "text/markdown" : "text/plain",
      content,
    });
  }
  return documents;
}
