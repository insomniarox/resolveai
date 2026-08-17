"use client";

import { useEffect, useState } from "react";

import { InvestigationResult } from "@/components/investigation-result";
import {
  ApiRequestError,
  UnexpectedResponseError,
  fetchRuntimeReasoner,
  investigateRuntimeBundle,
} from "@/lib/api";
import type {
  InvestigationResult as InvestigationResultData,
  ReasonerMetadata,
  RuntimeIncidentBundle,
} from "@/lib/types";

type RequestState = "idle" | "loading" | "success" | "error";

const exampleBundle: RuntimeIncidentBundle = {
  schema_version: 1,
  incident: {
    id: "USER-INC-901",
    title: "Checkout requests timing out",
    description: "A previously unseen checkout service is degraded.",
    service: "checkout-runtime-service",
    started_at: "2026-08-17T09:00:00Z",
  },
  evidence: [
    {
      id: "USER-DEP-901:database_connection_pool_size",
      source: "deployment",
      kind: "configuration_change",
      observed_at: "2026-08-17T08:55:00Z",
      summary: "A deployment reduced the database connection pool.",
      details: {
        setting: "database_connection_pool_size",
        previous_value: 30,
        new_value: 6,
      },
    },
    {
      id: "USER-LOG-901",
      source: "log",
      kind: "database_connection_timeout",
      observed_at: "2026-08-17T09:00:10Z",
      summary: "Checkout timed out while acquiring a database connection.",
      details: {},
    },
    {
      id: "USER-LOG-902",
      source: "log",
      kind: "http_request_failed",
      observed_at: "2026-08-17T09:00:11Z",
      summary: "POST /checkout returned HTTP 500.",
      details: { status_code: 500 },
    },
  ],
};

const exampleJson = JSON.stringify(exampleBundle, null, 2);

function describeError(error: unknown): string {
  if (error instanceof SyntaxError) {
    return "The bundle is not valid JSON. Check commas, quotes, and brackets.";
  }
  if (error instanceof ApiRequestError || error instanceof UnexpectedResponseError) {
    return error.message;
  }
  if (error instanceof TypeError) {
    return "Unable to reach ResolveAI. Check that the FastAPI backend is running.";
  }
  return "The runtime investigation failed. Please retry.";
}

export function RuntimeInvestigationWorkspace() {
  const [bundleText, setBundleText] = useState(exampleJson);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [result, setResult] = useState<InvestigationResultData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reasoner, setReasoner] = useState<ReasonerMetadata | null>(null);
  const [reasonerError, setReasonerError] = useState<string | null>(null);

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

  async function runInvestigation() {
    if (requestState === "loading") return;

    setRequestState("loading");
    setResult(null);
    setError(null);

    try {
      const bundle: unknown = JSON.parse(bundleText);
      const investigation = await investigateRuntimeBundle(bundle);
      setResult(investigation);
      setRequestState("success");
    } catch (caught) {
      setError(describeError(caught));
      setRequestState("error");
    }
  }

  function resetExample() {
    setBundleText(exampleJson);
    setRequestState("idle");
    setResult(null);
    setError(null);
  }

  return (
    <div className="runtime-grid">
      <section className="runtime-input-panel panel">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Transient own-data path</p>
            <h2 id="runtime-input-title">Versioned incident bundle</h2>
          </div>
          <span className="count-summary">
            {reasoner ? `${reasoner.provider} · ${reasoner.model}` : "Checking reasoner"}
          </span>
        </div>

        <form
          className="runtime-form"
          onSubmit={(event) => {
            event.preventDefault();
            void runInvestigation();
          }}
        >
          <p className="runtime-guidance">
            Supply schema version 1, one incident, and 1–50 normalized Evidence
            items. IDs must be unique and timestamps must include a UTC offset.
          </p>
          <label htmlFor="runtime-bundle">Incident bundle JSON</label>
          <textarea
            aria-describedby="runtime-limit-note"
            disabled={requestState === "loading"}
            id="runtime-bundle"
            onChange={(event) => setBundleText(event.target.value)}
            spellCheck={false}
            value={bundleText}
          />
          <p className="runtime-limit-note" id="runtime-limit-note">
            This path sends the bundle to the displayed external inference
            provider. ResolveAI does not persist the input or result; the provider
            may process or retain data under its own policy. Do not submit secrets
            or confidential production data.
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
              {requestState === "loading" ? "Investigating…" : "Investigate bundle"}
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
            <p>Edit the example or paste another valid version-1 bundle.</p>
          </div>
        )}

        {requestState === "loading" && (
          <div className="request-message">
            <strong>ResolveAI is investigating the runtime bundle.</strong>
            <p>
              The bounded live-model request may take several seconds. The final
              structured result will appear when it completes.
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
                <p className="section-kicker">Transient result</p>
                <h2>Result for {result.incident_id}</h2>
              </div>
              <span className="count-summary">
                {result.reasoner.provider} · {result.reasoner.model}
              </span>
            </div>
            <InvestigationResult result={result} />
          </>
        )}
      </section>
    </div>
  );
}
