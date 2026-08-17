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
}

export interface RetrievedRunbook {
  id: string;
  title: string;
  service: string;
  content: string;
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
