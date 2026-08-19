import type { SavedRuntimeRun } from "@/lib/types";

interface RuntimeRunComparisonProps {
  deletingRunId: string | null;
  onDelete: (savedRun: SavedRuntimeRun) => void;
  runs: SavedRuntimeRun[];
}

type ComparisonSignalStatus = "same" | "different" | "not-applicable";

interface ComparisonSignal {
  label: string;
  status: ComparisonSignalStatus;
}

function displayLabel(value: string): string {
  return value.replaceAll("_", " ");
}

function referenceSummary(savedRun: SavedRuntimeRun): string[] {
  const snapshot = savedRun.run.snapshot;
  return [
    ...snapshot.retrieved_runbooks.map(
      (item) => `${item.id} · ${item.similarity_score.toFixed(3)}`,
    ),
    ...snapshot.retrieved_knowledge_documents.map(
      (item) => `${item.id} (runtime) · ${item.similarity_score.toFixed(3)}`,
    ),
  ];
}

function exactMatch(left: unknown, right: unknown): ComparisonSignalStatus {
  return JSON.stringify(left) === JSON.stringify(right) ? "same" : "different";
}

function diagnosedLabel(savedRun: SavedRuntimeRun): string | null {
  const result = savedRun.run.snapshot.investigation_result;
  return result?.status === "diagnosed"
    ? result.diagnosis.root_cause_label
    : null;
}

function supportingCitations(savedRun: SavedRuntimeRun): string[] {
  const result = savedRun.run.snapshot.investigation_result;
  return result?.status === "diagnosed"
    ? [...result.diagnosis.supporting_evidence_ids].sort()
    : [];
}

function outcomeStatus(savedRun: SavedRuntimeRun): string {
  const snapshot = savedRun.run.snapshot;
  return snapshot.investigation_result?.status ?? `failed:${snapshot.failure_code}`;
}

function retrievedReferences(savedRun: SavedRuntimeRun) {
  const snapshot = savedRun.run.snapshot;
  return [
    ...snapshot.retrieved_runbooks.map((item) => ({
      kind: "runbook",
      id: item.id,
      score: item.similarity_score,
    })),
    ...snapshot.retrieved_knowledge_documents.map((item) => ({
      kind: "runtime",
      id: item.id,
      score: item.similarity_score,
    })),
  ];
}

function comparisonSignals(runs: SavedRuntimeRun[]): ComparisonSignal[] {
  if (runs.length !== 2) return [];
  const [first, second] = runs;
  const firstReferences = retrievedReferences(first);
  const secondReferences = retrievedReferences(second);
  const firstLabel = diagnosedLabel(first);
  const secondLabel = diagnosedLabel(second);

  return [
    {
      label: "Incident ID",
      status: exactMatch(
        first.run.snapshot.bundle.incident.id,
        second.run.snapshot.bundle.incident.id,
      ),
    },
    {
      label: "Submitted bundle",
      status: exactMatch(first.run.snapshot.bundle, second.run.snapshot.bundle),
    },
    {
      label: "Evidence IDs",
      status: exactMatch(
        first.run.snapshot.bundle.evidence.map((item) => item.id),
        second.run.snapshot.bundle.evidence.map((item) => item.id),
      ),
    },
    {
      label: "Knowledge IDs",
      status: exactMatch(
        (first.run.snapshot.bundle.knowledge_documents ?? []).map(
          (item) => item.id,
        ),
        (second.run.snapshot.bundle.knowledge_documents ?? []).map(
          (item) => item.id,
        ),
      ),
    },
    {
      label: "Outcome status",
      status: exactMatch(outcomeStatus(first), outcomeStatus(second)),
    },
    {
      label: "Citation set",
      status: exactMatch(
        supportingCitations(first),
        supportingCitations(second),
      ),
    },
    {
      label: "Retrieval order",
      status: exactMatch(
        firstReferences.map((item) => `${item.kind}:${item.id}`),
        secondReferences.map((item) => `${item.kind}:${item.id}`),
      ),
    },
    {
      label: "Retrieval scores",
      status: exactMatch(
        firstReferences.map((item) => item.score),
        secondReferences.map((item) => item.score),
      ),
    },
    {
      label: "Raw label",
      status:
        firstLabel === null || secondLabel === null
          ? "not-applicable"
          : exactMatch(firstLabel, secondLabel),
    },
    {
      label: "Reasoner",
      status: exactMatch(first.run.snapshot.reasoner, second.run.snapshot.reasoner),
    },
    {
      label: "Execution settings",
      status: exactMatch(
        first.run.snapshot.execution,
        second.run.snapshot.execution,
      ),
    },
  ];
}

export function RuntimeRunComparison({
  deletingRunId,
  onDelete,
  runs,
}: RuntimeRunComparisonProps) {
  if (runs.length === 0) return null;
  const signals = comparisonSignals(runs);

  return (
    <section aria-labelledby="saved-comparison-title" className="saved-runs panel">
      <div className="saved-runs-heading">
        <div>
          <p className="section-kicker">Short-lived provenance</p>
          <h2 id="saved-comparison-title">Saved run comparison</h2>
        </div>
        <span className="count-summary">{runs.length} / 2 saved</span>
      </div>
      <p className="comparison-guidance">
        Compare the complete record, not only the raw root-cause label. Labels are
        preserved exactly because wording can vary even when other stored facts
        agree. Diagnosis prose remains a human-review field.
      </p>
      {signals.length > 0 && (
        <div className="comparison-signals">
          <div>
            <p className="section-kicker">Exact stored-value comparison</p>
            <h3>Deterministic signals</h3>
          </div>
          <p>
            These signals compare identifiers and values only. They do not judge
            whether two diagnosis paragraphs are semantically equivalent.
          </p>
          <ul>
            {signals.map((signal) => (
              <li key={signal.label}>
                <span>{signal.label}</span>
                <strong className={`comparison-signal-${signal.status}`}>
                  {signal.status === "not-applicable"
                    ? "not applicable"
                    : signal.status}
                </strong>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="comparison-grid">
        {runs.map((savedRun, index) => {
          const { run } = savedRun;
          const { investigation_result: result } = run.snapshot;
          const references = referenceSummary(savedRun);
          return (
            <article className="comparison-card" key={run.id}>
              <div className="comparison-card-heading">
                <div>
                  <p className="section-kicker">Run {index + 1}</p>
                  <code>{run.id}</code>
                </div>
                <span
                  className={`status-badge ${
                    run.outcome === "completed"
                      ? "status-complete"
                      : "status-error"
                  }`}
                >
                  {run.outcome}
                </span>
              </div>

              <dl className="comparison-facts">
                <div>
                  <dt>Incident</dt>
                  <dd>{run.snapshot.bundle.incident.id}</dd>
                </div>
                <div>
                  <dt>Reasoner</dt>
                  <dd>
                    {run.snapshot.reasoner.provider} · {run.snapshot.reasoner.model}
                  </dd>
                </div>
                <div>
                  <dt>Latency</dt>
                  <dd>{run.snapshot.duration_ms.toLocaleString()} ms</dd>
                </div>
                <div>
                  <dt>Expires</dt>
                  <dd>
                    <time dateTime={run.expires_at}>
                      {new Date(run.expires_at).toLocaleString()}
                    </time>
                  </dd>
                </div>
              </dl>

              <details className="execution-details">
                <summary>Execution settings</summary>
                <dl>
                  <div>
                    <dt>Application</dt>
                    <dd>{run.snapshot.execution.application_version}</dd>
                  </div>
                  <div>
                    <dt>Prompt / output schema</dt>
                    <dd>
                      {run.snapshot.execution.prompt_version} ·{" "}
                      {run.snapshot.execution.output_schema_version}
                    </dd>
                  </div>
                  <div>
                    <dt>Retrieval</dt>
                    <dd>
                      {run.snapshot.execution.retrieval_strategy} Top-
                      {run.snapshot.execution.retrieval_limit}
                    </dd>
                  </div>
                  <div>
                    <dt>Embedding</dt>
                    <dd>{run.snapshot.execution.embedding_model}</dd>
                  </div>
                  <div>
                    <dt>Reasoning budget</dt>
                    <dd>
                      {run.snapshot.execution.reasoning_effort} ·{" "}
                      {run.snapshot.execution.max_output_tokens.toLocaleString()} tokens
                      · {run.snapshot.execution.timeout_seconds}s timeout
                    </dd>
                  </div>
                </dl>
              </details>

              {result?.status === "diagnosed" && (
                <div className="comparison-diagnosis">
                  <span>Raw root-cause label</span>
                  <code>{result.diagnosis.root_cause_label}</code>
                  <p>{result.diagnosis.probable_root_cause}</p>
                  <span>Supporting Evidence IDs</span>
                  <div className="citation-list">
                    {result.diagnosis.supporting_evidence_ids.map((id) => (
                      <code key={id}>{id}</code>
                    ))}
                  </div>
                </div>
              )}
              {result?.status === "inconclusive" && (
                <p className="comparison-outcome">
                  <strong>Inconclusive:</strong> no supported diagnosis.
                </p>
              )}
              {run.snapshot.failure_code && (
                <p className="comparison-outcome">
                  <strong>Stable failure:</strong>{" "}
                  {displayLabel(run.snapshot.failure_code)}
                </p>
              )}

              <div className="comparison-references">
                <span>Ordered retrieved references</span>
                {references.length > 0 ? (
                  <ol>
                    {references.map((reference) => (
                      <li key={reference}>{reference}</li>
                    ))}
                  </ol>
                ) : (
                  <p>None recorded.</p>
                )}
              </div>

              <button
                className="secondary-button danger-button"
                disabled={deletingRunId !== null}
                onClick={() => onDelete(savedRun)}
                type="button"
              >
                {deletingRunId === run.id ? "Deleting…" : "Delete saved run"}
              </button>
            </article>
          );
        })}
      </div>
    </section>
  );
}
