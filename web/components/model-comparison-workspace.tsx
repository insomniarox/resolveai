"use client";

import { useEffect, useRef, useState } from "react";
import { ComparisonPackageLibrary } from "./comparison-package-library";
import {
  cloneComparisonPackage,
  comparisonPackages,
  downloadComparisonJson,
} from "@/lib/comparison-packages";
import { RuntimeBundleEditor } from "./runtime-bundle-editor";
import {
  cloneExampleRuntimeBundle,
  prepareRuntimeBundle,
  validateRuntimeBundle,
} from "@/lib/runtime-bundle";
import {
  fetchComparisonMetadata,
  streamComparison,
  type Branch,
  type ComparisonEvent,
  type ComparisonMetadata,
  type Prepared,
  type Provider,
} from "@/lib/comparison-api";
import type { RuntimeIncidentBundle } from "@/lib/types";

const names = { openrouter: "OpenRouter", jev: "Jev" };
const initialCandidates = [
  "The signing provider receipt callback endpoint is unavailable.",
  "Local invoice delivery workers are backlogged.",
  "The signing provider upload endpoint is unavailable.",
];
const ms = (value: number) =>
  value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`;
const failureText: Record<string, string> = {
  timeout: "The provider timed out. Run a new comparison to retry.",
  unavailable:
    "The provider is unavailable. Check its server configuration or retry later.",
  invalid_output: "The provider returned an invalid decision.",
  internal_error: "The provider branch failed unexpectedly.",
};

function ResultColumn({
  provider,
  branch,
  prepared,
  running,
  model,
}: {
  provider: Provider;
  branch?: Branch;
  prepared: Prepared | null;
  running: boolean;
  model?: string;
}) {
  const tokens =
    branch?.calls.length &&
    branch.calls.every(
      (c) => c.usage.input_tokens != null && c.usage.output_tokens != null,
    )
      ? branch.calls.reduce(
          (sum, c) =>
            sum + (c.usage.input_tokens ?? 0) + (c.usage.output_tokens ?? 0),
          0,
        )
      : null;
  const costs = branch?.calls.map((c) => c.usage.reported_cost_usd);
  const cost =
    branch?.outcome !== "failed" &&
    costs?.length &&
    costs.every((c) => c != null)
      ? costs.reduce<number>((sum, c) => sum + (c ?? 0), 0)
      : null;
  return (
    <article className={`panel comparison-result ${provider}`}>
      <header>
        <span className="provider-dot" aria-hidden="true" />
        <h3>{names[provider]}</h3>
        <span className="branch-outcome">
          {branch
            ? branch.outcome === "supported"
              ? "Hypothesis supported"
              : branch.outcome === "inconclusive"
                ? "Inconclusive"
                : "Failed"
            : running
              ? "Running"
              : "Ready"}
        </span>
      </header>
      <p className="comparison-model">
        {branch?.model ?? model ?? "Checking model configuration"}
      </p>
      {branch ? (
        <>
          <dl className="comparison-metrics">
            <div>
              <dt>Route time</dt>
              <dd>{ms(branch.duration_ms)}</dd>
            </div>
            <div>
              <dt>Reported tokens</dt>
              <dd>{tokens?.toLocaleString() ?? "Unavailable"}</dd>
            </div>
            <div>
              <dt>Reported cost</dt>
              <dd>{cost != null ? `$${cost.toFixed(6)}` : "Unavailable"}</dd>
            </div>
            <div>
              <dt>Accuracy</dt>
              <dd>Not assessed</dd>
            </div>
          </dl>
          {branch.outcome === "failed" ? (
            <p role="alert">
              {failureText[branch.error_code ?? "internal_error"]}
            </p>
          ) : branch.candidate_index != null ? (
            <p className="selected-hypothesis">
              {prepared?.candidates[branch.candidate_index]}
            </p>
          ) : (
            <p className="selected-hypothesis">
              No listed hypothesis is established by the available evidence.
            </p>
          )}
          <p className="comparison-note">
            {branch.attempted_calls} model{" "}
            {branch.attempted_calls === 1 ? "call" : "calls"} · No retries ·
            Human review required
          </p>
          {branch.calls[0]?.confidence.cause != null && (
            <p className="comparison-note">
              Choice confidence{" "}
              {(branch.calls[0].confidence.cause * 100).toFixed(1)}%. This
              measures concentration among choices, not diagnosis accuracy.
            </p>
          )}
        </>
      ) : (
        <p className="comparison-empty">
          {running
            ? "Assessing the same incident and candidate hypotheses."
            : "Submit the incident to see this route’s result."}
        </p>
      )}
    </article>
  );
}

export function ModelComparisonWorkspace() {
  const [bundle, setBundle] = useState<RuntimeIncidentBundle>(
    () => cloneComparisonPackage(comparisonPackages[0].id).bundle,
  );
  const [candidates, setCandidates] = useState(
    () => cloneComparisonPackage(comparisonPackages[0].id).candidates,
  );
  const [loadedPackage, setLoadedPackage] = useState(
    "Checkout locks package loaded",
  );
  const [editorVersion, setEditorVersion] = useState(0);
  const [metadata, setMetadata] = useState<ComparisonMetadata | null>(null);
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<ComparisonEvent[]>([]);
  const [submitted, setSubmitted] = useState<{
    bundle: RuntimeIncidentBundle;
    candidates: string[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [stale, setStale] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const prepared = events.find((e) => e.type === "prepared")?.prepared ?? null;
  const branches = Object.fromEntries(
    events
      .filter((e) => e.type === "branch")
      .map((e) => [e.branch.provider, e.branch]),
  ) as Partial<Record<Provider, Branch>>;
  const finished = events.find((e) => e.type === "finished")?.finished;
  const extent = Math.max(
    1,
    finished?.duration_ms ?? 0,
    ...Object.values(branches).map((b) => b.start_offset_ms + b.duration_ms),
  );
  useEffect(() => {
    const abort = new AbortController();
    fetchComparisonMetadata(abort.signal)
      .then(setMetadata)
      .catch(() => {
        if (!abort.signal.aborted)
          setError(
            "Comparison configuration could not be loaded. Refresh to retry.",
          );
      });
    return () => {
      abort.abort();
      controller.current?.abort();
    };
  }, []);
  const configured = metadata?.available.jev && metadata?.available.openrouter;
  async function run() {
    if (running || !form.current?.reportValidity()) return;
    const input = {
      bundle: prepareRuntimeBundle(bundle),
      candidates: candidates.map((c) => c.trim()),
    };
    const validation = validateRuntimeBundle(input.bundle);
    if (
      new Set(input.candidates.map((c) => c.toLowerCase())).size !==
      input.candidates.length
    )
      validation.push("Use distinct candidate hypotheses.");
    setErrors(validation);
    if (validation.length) return;
    const abort = new AbortController();
    controller.current = abort;
    setRunning(true);
    setEvents([]);
    setSubmitted(input);
    setStale(false);
    setError(null);
    const timeout = setTimeout(() => abort.abort(), 120_000);
    try {
      await streamComparison(
        input,
        (event) => {
          setEvents((current) => [...current, event]);
          if (event.type === "error")
            setError(
              event.error === "input_too_large"
                ? "This comparison has too much context. Shorten the evidence or reference documents and try again."
                : "Shared preparation failed. Check the database and retry.",
            );
        },
        abort.signal,
      );
    } catch (caught) {
      setError(
        abort.signal.aborted
          ? "The connection timed out. Completed results remain below; the server will finish cleanup."
          : caught instanceof Error
            ? caught.message
            : "The comparison failed.",
      );
    } finally {
      clearTimeout(timeout);
      setRunning(false);
    }
  }
  function download() {
    downloadComparisonJson(
      { protocol: metadata?.protocol, input: submitted, events },
      `comparison-${prepared?.comparison_id ?? "partial"}.json`,
    );
  }
  function loadInput(
    input: { bundle: RuntimeIncidentBundle; candidates: string[] },
    label: string,
  ) {
    setBundle(input.bundle);
    setCandidates(input.candidates);
    setErrors([]);
    setStale(events.length > 0);
    setLoadedPackage(label);
    setEditorVersion((version) => version + 1);
  }
  return (
    <div className="comparison-workspace dashboard-grid">
      <ComparisonPackageLibrary
        disabled={running}
        onLoad={(id) => {
          const input = cloneComparisonPackage(id);
          loadInput(input, `${input.bundle.incident.title} package loaded`);
        }}
        onLoadOriginal={() =>
          loadInput(
            {
              bundle: cloneExampleRuntimeBundle(),
              candidates: [...initialCandidates],
            },
            "Original invoice example loaded",
          )
        }
      />
      <div className="comparison-main">
        <form
          ref={form}
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
          className="panel comparison-input"
        >
          <div className="panel-heading">
            <div>
              <p className="section-kicker">Shared input · OpenRouter + Jev</p>
              <h2>Compare models</h2>
            </div>
            <span className="count-summary">Experimental</span>
          </div>
          <div className="runtime-form">
            <div className="comparison-incident-summary">
              <p className="comparison-note" role="status">
                {loadedPackage}
              </p>
              <h3>{bundle.incident.title}</h3>
              <p>{bundle.incident.description}</p>
              <code>{bundle.incident.service}</code>
            </div>
            <details className="comparison-editor-details">
              <summary>
                Edit incident and evidence{" "}
                <span>
                  {bundle.evidence.length} observations ·{" "}
                  {(bundle.knowledge_documents ?? []).length} documents
                </span>
              </summary>
              <RuntimeBundleEditor
                key={editorVersion}
                bundle={bundle}
                disabled={running}
                errors={errors}
                onChange={(b) => {
                  setBundle(b);
                  setLoadedPackage("Custom input");
                  setErrors([]);
                  setStale(events.length > 0);
                }}
              />
            </details>
            <fieldset
              className="runtime-fieldset candidate-fieldset"
              disabled={running}
            >
              <legend>Candidate hypotheses</legend>
              <p className="comparison-note">
                Enter up to five specific causes. Both models assess these same
                options and can choose &quot;none established.&quot;
              </p>
              {candidates.map((candidate, i) => (
                <div className="candidate-row" key={i}>
                  <label htmlFor={`candidate-${i}`}>
                    {String.fromCharCode(65 + i)}
                  </label>
                  <textarea
                    rows={2}
                    aria-label={`Hypothesis ${String.fromCharCode(65 + i)}`}
                    id={`candidate-${i}`}
                    value={candidate}
                    minLength={3}
                    maxLength={500}
                    required
                    onChange={(e) => {
                      setCandidates(
                        candidates.map((c, j) =>
                          i === j ? e.target.value : c,
                        ),
                      );
                      setStale(events.length > 0);
                    }}
                  />
                  <button
                    type="button"
                    className="secondary-button"
                    aria-label={`Remove hypothesis ${String.fromCharCode(65 + i)}`}
                    disabled={candidates.length === 1}
                    onClick={() => {
                      setCandidates(candidates.filter((_, j) => i !== j));
                      setStale(events.length > 0);
                    }}
                  >
                    Remove
                  </button>
                </div>
              ))}
              {candidates.length < 5 && (
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => {
                    setCandidates([...candidates, ""]);
                    setLoadedPackage("Custom input");
                    setStale(events.length > 0);
                  }}
                >
                  Add hypothesis
                </button>
              )}
            </fieldset>
            <p className="comparison-note">
              Runbook similarity ranks reference material, not observations.
              Both models read every observation and judge its role using the
              shared context. Retrieved references and their scores appear with
              the results.
            </p>
            <details className="comparison-json-details">
              <summary>Complete request JSON</summary>
              <p className="comparison-note">
                Includes the current incident, observations, reference documents
                and hypotheses. Apply edits in the bundle editor before
                downloading.
              </p>
              <div className="runtime-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() =>
                    downloadComparisonJson(
                      {
                        bundle: prepareRuntimeBundle(bundle),
                        candidates: candidates.map((c) => c.trim()),
                      },
                      "comparison-input.json",
                    )
                  }
                >
                  Download input JSON
                </button>
                <a
                  className="secondary-button"
                  href="/comparison-input.schema.json"
                  download
                >
                  Download JSON Schema
                </a>
              </div>
              <pre>
                {JSON.stringify(
                  {
                    bundle: prepareRuntimeBundle(bundle),
                    candidates: candidates.map((c) => c.trim()),
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
            <div className="comparison-actions">
              <button
                className="primary-button"
                disabled={running || !configured}
                type="submit"
              >
                {running ? "Comparing…" : "Run comparison"}
              </button>
              <span>
                {running
                  ? "Results appear as each route finishes."
                  : "Transient results · Up to two calls per provider"}
              </span>
            </div>
            {metadata && !configured && (
              <p role="alert">
                Configure{" "}
                {(["jev", "openrouter"] as Provider[])
                  .filter((p) => !metadata.available[p])
                  .map((p) => names[p])
                  .join(" and ")}{" "}
                on the server to enable comparison.
              </p>
            )}
            {errors.length > 0 && (
              <ul role="alert">
                {errors.map((e) => (
                  <li key={e}>{e}</li>
                ))}
              </ul>
            )}
          </div>
        </form>
        {error && (
          <p className="error-banner" role="alert">
            {error}
          </p>
        )}
        {stale && (
          <p role="status" className="comparison-stale">
            Input changed. The results below belong to the previous submission.
          </p>
        )}
        <section
          className="panel comparison-timeline"
          aria-label="Comparison timeline"
        >
          <header>
            <h3>Comparison timing</h3>
            <span aria-live="polite">
              {finished
                ? `${ms(finished.duration_ms)} total`
                : running
                  ? "In progress"
                  : "Awaiting a comparison"}
            </span>
          </header>
          <div className="clock-row">
            <span>Preparation</span>
            <div className="clock-track">
              <div
                className="clock-bar preparation"
                style={{
                  width: `${prepared ? Math.max(1, (prepared.preparation_ms / extent) * 100) : 0}%`,
                }}
              />
            </div>
            <span>{prepared ? ms(prepared.preparation_ms) : "—"}</span>
          </div>
          {(["openrouter", "jev"] as Provider[]).map((p) => (
            <div className={`clock-row ${p}`} key={p}>
              <span>{names[p]}</span>
              <div className="clock-track">
                <div
                  className="clock-bar"
                  style={{
                    marginLeft: `${branches[p] ? (branches[p]!.start_offset_ms / extent) * 100 : 0}%`,
                    width: `${branches[p] ? (branches[p]!.duration_ms / extent) * 100 : 0}%`,
                  }}
                />
              </div>
              <span>
                {branches[p]
                  ? ms(branches[p]!.duration_ms)
                  : running
                    ? "Running"
                    : "—"}
              </span>
            </div>
          ))}
          {branches.jev && branches.openrouter && (
            <p className="comparison-note">
              Jev took {ms(branches.jev.duration_ms)}; OpenRouter took{" "}
              {ms(branches.openrouter.duration_ms)}. Timing alone does not
              establish quality.
            </p>
          )}
        </section>
        <div className="comparison-columns" aria-live="polite">
          {(["openrouter", "jev"] as Provider[]).map((p) => (
            <ResultColumn
              key={p}
              provider={p}
              branch={branches[p]}
              prepared={prepared}
              running={running}
              model={metadata?.models[p]}
            />
          ))}
        </div>
        {prepared && (
          <section className="panel comparison-evidence">
            <header>
              <h3>Evidence alignment</h3>
              <button
                type="button"
                className="secondary-button"
                onClick={download}
              >
                Download JSON
              </button>
            </header>
            <p className="comparison-note">
              All {prepared.evidence.length} observations reach both models.
              Each column assesses them against that model&apos;s selected
              hypothesis. Matching labels may refer to different causes.
            </p>
            <div className="comparison-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Observed evidence</th>
                    <th>OpenRouter</th>
                    <th>Jev</th>
                  </tr>
                </thead>
                <tbody>
                  {prepared.evidence.map((e) => (
                    <tr key={e.id}>
                      <td>
                        <code>{e.id}</code>
                        <p>{e.summary}</p>
                        <details className="observation-detail">
                          <summary>Observation details</summary>
                          <p className="comparison-note">
                            {e.source} · {e.kind.replaceAll("_", " ")}
                            <br />
                            {e.observed_at}
                          </p>
                          <dl>
                            {Object.entries(e.details).map(([key, value]) => (
                              <div key={key}>
                                <dt>{key.replaceAll("_", " ")}</dt>
                                <dd>{String(value)}</dd>
                              </div>
                            ))}
                          </dl>
                        </details>
                      </td>
                      {(["openrouter", "jev"] as Provider[]).map((p) => (
                        <td key={p}>
                          <span
                            className={`relation ${branches[p]?.evidence_relations[e.id] ?? ""}`}
                          >
                            {branches[p]?.evidence_relations[e.id] ??
                              "Not assessed"}
                          </span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <section
              className="comparison-retrieval"
              aria-labelledby="retrieval-heading"
            >
              <h3 id="retrieval-heading">
                How references inform the assessment
              </h3>
              <p className="comparison-note">
                The incident and observation summaries form a search query.
                Similarity ranks the top three stored runbooks and up to three
                attached documents separately. Both models receive the same
                retrieved references, including their scores.
              </p>
              <ol className="retrieval-flow">
                <li>
                  <strong>Rank references</strong>
                  <span>Similarity selects reference context.</span>
                </li>
                <li>
                  <strong>Read every observation</strong>
                  <span>
                    No observations are removed or ranked by that score.
                  </span>
                </li>
                <li>
                  <strong>Assess the hypothesis</strong>
                  <span>
                    Each model assigns support, contradiction or unrelated
                    labels.
                  </span>
                </li>
              </ol>
              <p className="comparison-note">
                A higher score means a closer semantic match to the search
                query. It is not a probability that a cause is correct.
                Reference content can inform the model&apos;s interpretation,
                but there is no fixed score-to-observation weighting and this
                comparison does not measure how much an individual reference
                changed a decision.
              </p>
              {[
                { title: "Stored runbooks", items: prepared.runbooks },
                { title: "Attached documents", items: prepared.documents },
              ].map((group) => (
                <div className="reference-group" key={group.title}>
                  <h4>
                    {group.title}{" "}
                    <span className="count-summary">{group.items.length}</span>
                  </h4>
                  {group.items.length === 0 && (
                    <p className="comparison-note">
                      No references retrieved in this group.
                    </p>
                  )}
                  {group.items.map((r, index) => (
                    <details className="reference-detail" key={r.id}>
                      <summary>
                        <span>
                          <span className="reference-rank">#{index + 1}</span>{" "}
                          {r.title}
                        </span>
                        <span className="similarity-score">
                          Similarity {r.similarity_score.toFixed(3)}
                        </span>
                      </summary>
                      <code>
                        {r.id}
                        {"service" in r ? ` · ${r.service}` : ""}
                      </code>
                      <p className="reference-content">{r.content}</p>
                    </details>
                  ))}
                </div>
              ))}
            </section>
            <details>
              <summary>Event log and provenance</summary>
              <p className="comparison-note">
                Comparison {prepared.comparison_id}
                <br />
                Input fingerprint {prepared.input_sha256}
                <br />
                Started {prepared.started_at}
                <br />
                Cleanup: {finished?.cleanup ?? "Pending"}
              </p>
              <pre>
                {JSON.stringify(
                  events.filter((e) => e.type !== "prepared"),
                  null,
                  2,
                )}
              </pre>
            </details>
          </section>
        )}
      </div>
    </div>
  );
}
