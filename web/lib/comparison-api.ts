import {
  isEvidence,
  isRetrievedRunbook,
  isRetrievedKnowledgeDocument,
} from "./api";
import type {
  Evidence,
  RetrievedRunbook,
  RetrievedKnowledgeDocument,
  RuntimeIncidentBundle,
} from "./types";

export type Provider = "openrouter" | "jev";
export type Relation = "supports" | "contradicts" | "unrelated";
export interface DecisionCall {
  stage: "cause" | "evidence";
  duration_ms: number;
  model: string;
  usage: {
    input_tokens?: number | null;
    output_tokens?: number | null;
    reported_cost_usd?: number | null;
    estimated_cost_usd?: number | null;
    cost_basis?: string | null;
  };
  answers: Record<string, string>;
  confidence: Record<string, number>;
}
export interface Branch {
  provider: Provider;
  model: string;
  outcome: "supported" | "inconclusive" | "failed";
  candidate_index?: number | null;
  supporting_evidence_ids: string[];
  evidence_relations: Record<string, Relation>;
  error_code?: string | null;
  started_at: string;
  start_offset_ms: number;
  duration_ms: number;
  calls: DecisionCall[];
  attempted_calls: number;
}
export interface Prepared {
  comparison_id: string;
  input_sha256: string;
  started_at: string;
  preparation_ms: number;
  candidates: string[];
  evidence: Evidence[];
  runbooks: RetrievedRunbook[];
  documents: RetrievedKnowledgeDocument[];
}
export type ComparisonEvent =
  | { type: "prepared"; prepared: Prepared }
  | { type: "branch"; branch: Branch }
  | {
      type: "finished";
      finished: {
        duration_ms: number;
        cleanup: "not_needed" | "completed" | "deferred";
      };
    }
  | {
      type: "error";
      error: "preparation_unavailable" | "internal_error" | "input_too_large";
    };
export interface ComparisonMetadata {
  protocol: string;
  models: Record<Provider, string>;
  available: Record<Provider, boolean>;
  max_candidates: number;
}

function record(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}
function nonnegative(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v) && v >= 0;
}
function integer(v: unknown): v is number {
  return nonnegative(v) && Number.isInteger(v);
}
function text(v: unknown): v is string {
  return typeof v === "string" && v.length > 0;
}
function date(v: unknown): v is string {
  return text(v) && Number.isFinite(Date.parse(v));
}
function strings(v: unknown): v is string[] {
  return Array.isArray(v) && v.every(text);
}
function call(v: unknown): v is DecisionCall {
  return (
    record(v) &&
    ["cause", "evidence"].includes(String(v.stage)) &&
    nonnegative(v.duration_ms) &&
    text(v.model) &&
    record(v.usage) &&
    (v.usage.input_tokens == null || integer(v.usage.input_tokens)) &&
    (v.usage.output_tokens == null || integer(v.usage.output_tokens)) &&
    (v.usage.reported_cost_usd == null ||
      nonnegative(v.usage.reported_cost_usd)) &&
    (v.usage.estimated_cost_usd == null ||
      nonnegative(v.usage.estimated_cost_usd)) &&
    (v.usage.cost_basis == null || text(v.usage.cost_basis)) &&
    record(v.answers) &&
    Object.values(v.answers).every(text) &&
    record(v.confidence) &&
    Object.values(v.confidence).every((n) => nonnegative(n) && n <= 1)
  );
}
export function parseComparisonEvent(value: unknown): ComparisonEvent {
  let valid = false;
  if (record(value)) {
    const p = value.prepared,
      b = value.branch,
      f = value.finished;
    if (value.type === "prepared")
      valid =
        record(p) &&
        text(p.comparison_id) &&
        text(p.input_sha256) &&
        date(p.started_at) &&
        nonnegative(p.preparation_ms) &&
        strings(p.candidates) &&
        p.candidates.length > 0 &&
        p.candidates.length <= 5 &&
        Array.isArray(p.evidence) &&
        p.evidence.every(isEvidence) &&
        Array.isArray(p.runbooks) &&
        p.runbooks.every(isRetrievedRunbook) &&
        Array.isArray(p.documents) &&
        p.documents.every(isRetrievedKnowledgeDocument);
    if (value.type === "branch")
      valid =
        record(b) &&
        ["jev", "openrouter"].includes(String(b.provider)) &&
        text(b.model) &&
        ["supported", "inconclusive", "failed"].includes(String(b.outcome)) &&
        (b.candidate_index == null ||
          (integer(b.candidate_index) && b.candidate_index <= 4)) &&
        strings(b.supporting_evidence_ids) &&
        record(b.evidence_relations) &&
        Object.values(b.evidence_relations).every((r) =>
          ["supports", "contradicts", "unrelated"].includes(String(r)),
        ) &&
        date(b.started_at) &&
        nonnegative(b.start_offset_ms) &&
        nonnegative(b.duration_ms) &&
        integer(b.attempted_calls) &&
        b.attempted_calls <= 2 &&
        Array.isArray(b.calls) &&
        b.calls.length <= b.attempted_calls &&
        b.calls.every(call) &&
        (b.outcome === "failed"
          ? [
              "timeout",
              "unavailable",
              "invalid_output",
              "internal_error",
            ].includes(String(b.error_code))
          : b.error_code == null) &&
        (b.outcome === "supported"
          ? integer(b.candidate_index) && b.supporting_evidence_ids.length > 0
          : b.candidate_index == null &&
            b.supporting_evidence_ids.length === 0);
    if (value.type === "finished")
      valid =
        record(f) &&
        nonnegative(f.duration_ms) &&
        ["not_needed", "completed", "deferred"].includes(String(f.cleanup));
    if (value.type === "error")
      valid = [
        "preparation_unavailable",
        "internal_error",
        "input_too_large",
      ].includes(String(value.error));
  }
  if (!valid) throw new Error("The comparison returned an invalid response.");
  return value as ComparisonEvent;
}

export async function fetchComparisonMetadata(
  signal?: AbortSignal,
): Promise<ComparisonMetadata> {
  const response = await fetch("/api/runtime/comparison", {
    signal,
    cache: "no-store",
  });
  if (!response.ok) throw new Error("Comparison configuration is unavailable.");
  const v: unknown = await response.json();
  if (
    !record(v) ||
    !text(v.protocol) ||
    !record(v.models) ||
    !text(v.models.jev) ||
    !text(v.models.openrouter) ||
    !record(v.available) ||
    typeof v.available.jev !== "boolean" ||
    typeof v.available.openrouter !== "boolean" ||
    v.max_candidates !== 5
  )
    throw new Error("Invalid comparison configuration.");
  return v as unknown as ComparisonMetadata;
}

export async function streamComparison(
  input: { bundle: RuntimeIncidentBundle; candidates: string[] },
  onEvent: (event: ComparisonEvent) => void,
  signal?: AbortSignal,
) {
  const response = await fetch("/api/runtime/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
  });
  if (!response.ok)
    throw new Error(
      response.status === 429
        ? "An investigation is already running. Retry shortly."
        : response.status === 422
          ? "Check the incident and candidate hypotheses."
          : response.status === 503
            ? "Both providers must be configured on the server."
            : "The comparison could not start.",
    );
  if (!response.body) throw new Error("The comparison stream is unavailable.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    finished = false,
    prepared: Prepared | null = null,
    failed = false;
  const providers = new Set<Provider>();
  function consume(line: string) {
    if (!line.trim()) return;
    if (finished) throw new Error("Unexpected event after completion.");
    const event = parseComparisonEvent(JSON.parse(line));
    if (event.type === "prepared") {
      if (prepared || providers.size || failed)
        throw new Error("Duplicate preparation event.");
      prepared = event.prepared;
    } else if (event.type === "branch") {
      const b = event.branch;
      if (!prepared || failed || providers.has(b.provider))
        throw new Error("Unexpected provider event.");
      const ids = new Set(prepared.evidence.map((e) => e.id));
      if (
        (b.candidate_index != null &&
          b.candidate_index >= prepared.candidates.length) ||
        b.supporting_evidence_ids.some((id) => !ids.has(id)) ||
        Object.keys(b.evidence_relations).some((id) => !ids.has(id))
      )
        throw new Error("Unknown comparison citation or hypothesis.");
      providers.add(b.provider);
    } else if (event.type === "error") failed = true;
    else {
      if (!failed && providers.size !== 2)
        throw new Error("The comparison ended before both providers returned.");
      finished = true;
    }
    onEvent(event);
  }
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      if (buffer.length > 512_000)
        throw new Error("The comparison response is too large.");
      let newline;
      while ((newline = buffer.indexOf("\n")) !== -1) {
        consume(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
      }
      if (done) break;
    }
    consume(buffer);
    if (!finished)
      throw new Error(
        "Connection closed before the comparison finished. Completed results are retained.",
      );
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
