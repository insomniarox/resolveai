import { EvidenceList } from "@/components/evidence-list";
import { ReferenceKnowledgeList } from "@/components/reference-knowledge-list";
import type { InvestigationResult as InvestigationResultData } from "@/lib/types";

interface InvestigationResultProps {
  result: InvestigationResultData;
}

function formatLabel(value: string): string {
  return value.replaceAll("_", " ");
}

export function InvestigationResult({ result }: InvestigationResultProps) {
  const supportingEvidenceIds =
    result.status === "diagnosed"
      ? result.diagnosis.supporting_evidence_ids
      : [];

  return (
    <div className="investigation-result">
      {result.status === "diagnosed" ? (
        <section
          aria-labelledby="diagnosis-title"
          className="diagnosis-panel result-section"
        >
          <div className="section-heading-row">
            <div>
              <p className="section-kicker">Investigation complete</p>
              <h3 id="diagnosis-title">Probable root cause</h3>
            </div>
            <span className="status-badge status-complete">Diagnosed</span>
          </div>

          <p className="probable-cause">
            {result.diagnosis.probable_root_cause}
          </p>

          <div className="diagnosis-facts">
            <div>
              <span>Normalized label</span>
              <strong>{formatLabel(result.diagnosis.root_cause_label)}</strong>
            </div>
            <div>
              <span>Model confidence</span>
              <strong>{Math.round(result.diagnosis.confidence * 100)}%</strong>
              <small>Not a calibrated probability</small>
            </div>
          </div>

          <div className="remediation-block">
            <h4>Recommended remediation</h4>
            <p>{result.diagnosis.recommended_remediation}</p>
          </div>

          <div className="citation-block">
            <h4>Supporting Evidence IDs</h4>
            <div className="citation-list">
              {result.diagnosis.supporting_evidence_ids.map((id) => (
                <code key={id}>{id}</code>
              ))}
            </div>
          </div>

          {result.diagnosis.human_approval_required && (
            <aside className="approval-note">
              <strong>Human approval required</strong>
              <p>
                This recommendation would require human approval before
                execution. No action has been performed.
              </p>
            </aside>
          )}
        </section>
      ) : (
        <section
          aria-labelledby="inconclusive-title"
          className="inconclusive-panel result-section"
        >
          <div className="section-heading-row">
            <div>
              <p className="section-kicker">Investigation complete</p>
              <h3 id="inconclusive-title">No supported diagnosis</h3>
            </div>
            <span className="status-badge status-inconclusive">
              Inconclusive
            </span>
          </div>
          <p>
            ResolveAI collected observations but could not support a diagnosis
            from the available Evidence.
          </p>
        </section>
      )}

      <EvidenceList
        evidence={result.evidence}
        supportingEvidenceIds={supportingEvidenceIds}
      />
      <ReferenceKnowledgeList runbooks={result.retrieved_runbooks} />
    </div>
  );
}
