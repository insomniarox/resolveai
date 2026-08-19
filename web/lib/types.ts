export type EvidenceSource = "log" | "deployment";

export type EvidenceKind =
  | "database_connection_timeout"
  | "database_lock_wait"
  | "database_transaction_state"
  | "authentication_certificate_expired"
  | "tls_handshake_validation_failed"
  | "upstream_request_failed"
  | "upstream_health_check"
  | "notification_queue_metrics"
  | "notification_worker_metrics"
  | "http_request_failed"
  | "configuration_change";

export interface Incident {
  id: string;
  title: string;
  description: string;
  service: string;
  started_at: string;
}

export interface Evidence {
  id: string;
  source: EvidenceSource;
  kind: EvidenceKind;
  observed_at: string;
  summary: string;
  details: Record<string, string | number>;
}

export interface RuntimeIncidentBundle {
  schema_version: 1;
  incident: Incident;
  evidence: Evidence[];
  knowledge_documents?: KnowledgeDocument[];
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  content_type: "text/plain" | "text/markdown";
  content: string;
}

export interface RetrievedRunbook {
  id: string;
  title: string;
  service: string;
  content: string;
  similarity_score: number;
}

export interface RetrievedKnowledgeDocument extends KnowledgeDocument {
  similarity_score: number;
}

export interface Diagnosis {
  root_cause_label: string;
  probable_root_cause: string;
  confidence: number;
  recommended_remediation: string;
  human_approval_required: boolean;
  supporting_evidence_ids: string[];
}

export interface ReasonerMetadata {
  provider: string;
  model: string;
}

interface InvestigationResultBase {
  incident_id: string;
  evidence: Evidence[];
  retrieved_runbooks: RetrievedRunbook[];
  retrieved_knowledge_documents: RetrievedKnowledgeDocument[];
  reasoner: ReasonerMetadata;
}

export interface DiagnosedInvestigationResult
  extends InvestigationResultBase {
  status: "diagnosed";
  diagnosis: Diagnosis;
}

export interface InconclusiveInvestigationResult
  extends InvestigationResultBase {
  status: "inconclusive";
  diagnosis: null;
}

export type InvestigationResult =
  | DiagnosedInvestigationResult
  | InconclusiveInvestigationResult;

export type RuntimeFailureCode =
  | "runtime_knowledge_unavailable"
  | "reasoner_timeout"
  | "invalid_citations"
  | "invalid_reasoner_output"
  | "reasoner_unavailable";

export interface RuntimeExecutionMetadata {
  application_version: string;
  prompt_version: string;
  output_schema_version: string;
  retrieval_strategy: "semantic";
  retrieval_limit: number;
  embedding_model: string;
  reasoning_effort: string;
  max_output_tokens: number;
  timeout_seconds: number;
}

export interface InvestigationRunSnapshot {
  schema_version: 1;
  bundle: RuntimeIncidentBundle;
  retrieved_runbooks: RetrievedRunbook[];
  retrieved_knowledge_documents: RetrievedKnowledgeDocument[];
  investigation_result: InvestigationResult | null;
  failure_code: RuntimeFailureCode | null;
  reasoner: ReasonerMetadata;
  execution: RuntimeExecutionMetadata;
  started_at: string;
  completed_at: string;
  duration_ms: number;
}

export interface InvestigationRun {
  id: string;
  created_at: string;
  expires_at: string;
  outcome: "completed" | "failed";
  snapshot: InvestigationRunSnapshot;
}

export interface CreatedInvestigationRun {
  run: InvestigationRun;
  capability_token: string;
}

export interface SavedRuntimeRun {
  run: InvestigationRun;
  capabilityToken: string;
}
