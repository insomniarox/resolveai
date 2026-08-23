"use client";

import { useEffect, useRef, useState } from "react";

import { InvestigationResult } from "@/components/investigation-result";
import { RuntimeBundleEditor } from "@/components/runtime-bundle-editor";
import { RuntimeRunComparison } from "@/components/runtime-run-comparison";
import {
  ApiRequestError,
  UnexpectedResponseError,
  createRuntimeInvestigationRun,
  deleteRuntimeInvestigationRun,
  fetchRuntimeInvestigationRun,
  fetchRuntimeReasoner,
  investigateRuntimeBundle,
} from "@/lib/api";
import type {
  InvestigationRun,
  InvestigationResult as InvestigationResultData,
  ReasonerMetadata,
  RuntimeIncidentBundle,
  SavedRuntimeRun,
} from "@/lib/types";
import {
  cloneExampleRuntimeBundle,
  prepareRuntimeBundle,
  validateRuntimeBundle,
} from "@/lib/runtime-bundle";

type RequestState = "idle" | "loading" | "success" | "error";
type RuntimeAction = "transient" | "saved";

function describeError(error: unknown): string {
  if (error instanceof ApiRequestError || error instanceof UnexpectedResponseError) {
    return error.message;
  }
  if (error instanceof TypeError) {
    return "Unable to reach ResolveAI. Check that the FastAPI backend is running.";
  }
  return "The runtime investigation failed. Please retry.";
}

export function RuntimeInvestigationWorkspace() {
  const formRef = useRef<HTMLFormElement>(null);
  const [bundle, setBundle] = useState<RuntimeIncidentBundle>(
    cloneExampleRuntimeBundle,
  );
  const [inputErrors, setInputErrors] = useState<string[]>([]);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [result, setResult] = useState<InvestigationResultData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reasoner, setReasoner] = useState<ReasonerMetadata | null>(null);
  const [reasonerError, setReasonerError] = useState<string | null>(null);
  const [activeAction, setActiveAction] = useState<RuntimeAction | null>(null);
  const [savedRuns, setSavedRuns] = useState<SavedRuntimeRun[]>([]);
  const [lastSavedRun, setLastSavedRun] = useState<InvestigationRun | null>(null);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchRuntimeReasoner()
      .then((metadata) => {
        if (active) setReasoner(metadata);
      })
      .catch((caught: unknown) => {
        if (active) setReasonerError(describeError(caught));
      });
    return () => {
      active = false;
    };
  }, []);

  async function runInvestigation(action: RuntimeAction) {
    if (requestState === "loading") return;
    if (!formRef.current?.reportValidity()) return;

    const preparedBundle = prepareRuntimeBundle(bundle);
    const validationErrors = validateRuntimeBundle(preparedBundle);
    if (validationErrors.length > 0) {
      setInputErrors(validationErrors);
      setError("Fix the runtime input before starting the investigation.");
      setRequestState("error");
      return;
    }

    if (action === "saved" && savedRuns.length >= 2) {
      setError("Delete one saved run before saving another comparison run.");
      setRequestState("error");
      return;
    }
    const comparedIncidentId = savedRuns[0]?.run.snapshot.bundle.incident.id ?? null;
    if (
      action === "saved" &&
      comparedIncidentId &&
      preparedBundle.incident.id !== comparedIncidentId
    ) {
      setError(
        `Saved comparisons must use the same incident ID (${comparedIncidentId}).`,
      );
      setRequestState("error");
      return;
    }

    setBundle(preparedBundle);
    setInputErrors([]);
    setRequestState("loading");
    setActiveAction(action);
    setResult(null);
    setLastSavedRun(null);
    setError(null);
    setComparisonError(null);

    try {
      if (action === "saved") {
        const created = await createRuntimeInvestigationRun(preparedBundle);
        const fetched = await fetchRuntimeInvestigationRun(
          created.run.id,
          created.capability_token,
        );
        setSavedRuns((current) => [
          ...current,
          { run: fetched, capabilityToken: created.capability_token },
        ]);
        setLastSavedRun(fetched);
        setResult(fetched.snapshot.investigation_result);
      } else {
        setResult(await investigateRuntimeBundle(preparedBundle));
      }
      setRequestState("success");
    } catch (caught) {
      setError(describeError(caught));
      setRequestState("error");
    } finally {
      setActiveAction(null);
    }
  }

  async function deleteSavedRun(savedRun: SavedRuntimeRun) {
    if (deletingRunId !== null) return;
    setDeletingRunId(savedRun.run.id);
    setComparisonError(null);
    try {
      await deleteRuntimeInvestigationRun(
        savedRun.run.id,
        savedRun.capabilityToken,
      );
      setSavedRuns((current) =>
        current.filter((item) => item.run.id !== savedRun.run.id),
      );
      if (lastSavedRun?.id === savedRun.run.id) setLastSavedRun(null);
    } catch (caught) {
      setComparisonError(describeError(caught));
    } finally {
      setDeletingRunId(null);
    }
  }

  function resetExample() {
    setBundle(cloneExampleRuntimeBundle());
    setInputErrors([]);
    setRequestState("idle");
    setResult(null);
    setLastSavedRun(null);
    setError(null);
  }

  return (
    <>
      <div className="runtime-grid">
        <section className="runtime-input-panel panel">
          <div className="panel-heading">
            <div>
              <p className="section-kicker">Own-data path</p>
              <h2 id="runtime-input-title">Versioned incident bundle</h2>
            </div>
            <span className="count-summary">
              {reasoner
                ? `${reasoner.provider} · ${reasoner.model}`
                : "Checking reasoner"}
            </span>
          </div>

          <form
            className="runtime-form"
            ref={formRef}
            onSubmit={(event) => {
              event.preventDefault();
              void runInvestigation("transient");
            }}
          >
            <p className="runtime-guidance">
              Enter one incident and 1–50 normalized Evidence items. You can also
              attach up to five short text or Markdown documents for this
              investigation.
            </p>
            <RuntimeBundleEditor
              bundle={bundle}
              disabled={requestState === "loading"}
              errors={inputErrors}
              onChange={(nextBundle) => {
                setBundle(nextBundle);
                setInputErrors([]);
              }}
            />
            <p className="runtime-limit-note" id="runtime-limit-note">
              Supplied knowledge uses a request-only retrieval scope removed when
              the request finishes; interrupted scopes become ineligible after 15
              minutes. Input and results are not retained unless you explicitly
              use Save run. A saved immutable snapshot expires after one hour and
              requires its in-memory capability to read or delete. The displayed
              provider may process or retain reasoning input under its own policy.
              Do not submit secrets or confidential production data.
            </p>
            {reasonerError && (
              <p className="runtime-provider-error" role="status">
                Provider status unavailable: {reasonerError}
              </p>
            )}
            <div className="runtime-actions">
              <button
                className="primary-button"
                disabled={requestState === "loading"}
                type="submit"
              >
                {activeAction === "transient"
                  ? "Investigating…"
                  : "Investigate transiently"}
              </button>
              <button
                className="secondary-button"
                disabled={requestState === "loading" || savedRuns.length >= 2}
                onClick={() => void runInvestigation("saved")}
                type="button"
              >
                {activeAction === "saved"
                  ? "Saving run…"
                  : "Save run for comparison"}
              </button>
              <button
                className="secondary-button"
                disabled={requestState === "loading"}
                onClick={resetExample}
                type="button"
              >
                Reset example
              </button>
            </div>
          </form>
        </section>

        <section aria-live="polite" className="runtime-result-panel panel">
          {requestState === "idle" && (
            <div className="empty-workspace">
              <p className="section-kicker">Ready</p>
              <h2>Investigate previously unseen input</h2>
              <p>Edit the example through the form or apply another valid version-1 JSON bundle.</p>
            </div>
          )}

          {requestState === "loading" && (
            <div className="request-message">
              <strong>ResolveAI is investigating the runtime bundle.</strong>
              <p>
                The bounded live-model request may take several seconds.
                {activeAction === "saved"
                  ? " Its immutable provenance snapshot will then be retained for one hour."
                  : " The final structured result will appear when it completes."}
              </p>
            </div>
          )}

          {requestState === "error" && (
            <div className="investigation-error" role="alert">
              <p className="section-kicker">Request failed</p>
              <h3>Runtime investigation failed</h3>
              <p>{error}</p>
            </div>
          )}

          {requestState === "success" && result && (
            <>
              <div className="runtime-result-heading">
                <div>
                  <p className="section-kicker">
                    {lastSavedRun ? "Saved result" : "Transient result"}
                  </p>
                  <h2>Result for {result.incident_id}</h2>
                </div>
                <span className="count-summary">
                  {result.reasoner.provider} · {result.reasoner.model}
                </span>
              </div>
              <InvestigationResult result={result} />
            </>
          )}

          {requestState === "success" && !result && lastSavedRun && (
            <div className="investigation-error" role="status">
              <p className="section-kicker">Failed attempt saved</p>
              <h3>Reasoning did not produce a result</h3>
              <p>
                Stable failure:{" "}
                {lastSavedRun.snapshot.failure_code?.replaceAll("_", " ")}.
                The submitted input, retrieved references, reasoner identity, and
                timing remain available in the comparison below.
              </p>
            </div>
          )}
        </section>
      </div>

      {comparisonError && (
        <p className="saved-runs-error" role="alert">
          {comparisonError}
        </p>
      )}
      <RuntimeRunComparison
        deletingRunId={deletingRunId}
        onDelete={(savedRun) => void deleteSavedRun(savedRun)}
        runs={savedRuns}
      />
    </>
  );
}
