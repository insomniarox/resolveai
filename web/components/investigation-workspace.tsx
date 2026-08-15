"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { IncidentList } from "@/components/incident-list";
import { InvestigationResult } from "@/components/investigation-result";
import {
  ApiRequestError,
  UnexpectedResponseError,
  fetchIncidents,
  investigateIncident,
} from "@/lib/api";
import type {
  Incident,
  InvestigationResult as InvestigationResultData,
} from "@/lib/types";

type LoadState = "loading" | "ready" | "error";
type InvestigationState = "idle" | "loading" | "success" | "error";

const dateTimeFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "long",
  timeStyle: "short",
  timeZone: "UTC",
});

function describeError(error: unknown, fallback: string): string {
  if (error instanceof UnexpectedResponseError) {
    return error.message;
  }
  if (error instanceof ApiRequestError) {
    return error.message;
  }
  if (error instanceof TypeError) {
    return "Unable to reach ResolveAI. Check that the FastAPI backend is running.";
  }
  return fallback;
}

export function InvestigationWorkspace() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(
    null,
  );
  const [incidentLoadState, setIncidentLoadState] =
    useState<LoadState>("loading");
  const [incidentLoadError, setIncidentLoadError] = useState<string | null>(null);
  const [investigationState, setInvestigationState] =
    useState<InvestigationState>("idle");
  const [investigationResult, setInvestigationResult] =
    useState<InvestigationResultData | null>(null);
  const [investigationError, setInvestigationError] = useState<string | null>(
    null,
  );
  const [investigationNotFound, setInvestigationNotFound] = useState(false);

  const selectedIncident = useMemo(
    () =>
      incidents.find((incident) => incident.id === selectedIncidentId) ?? null,
    [incidents, selectedIncidentId],
  );

  const loadIncidents = useCallback(async () => {
    try {
      const loadedIncidents = await fetchIncidents();
      setIncidents(loadedIncidents);
      setSelectedIncidentId((currentId) => {
        if (
          currentId &&
          loadedIncidents.some((incident) => incident.id === currentId)
        ) {
          return currentId;
        }
        return loadedIncidents[0]?.id ?? null;
      });
      setIncidentLoadState("ready");
    } catch (error) {
      setIncidentLoadState("error");
      setIncidentLoadError(
        describeError(error, "ResolveAI incidents could not be loaded."),
      );
    }
  }, []);

  function refreshIncidents() {
    setIncidentLoadState("loading");
    setIncidentLoadError(null);
    void loadIncidents();
  }

  useEffect(() => {
    let active = true;

    void fetchIncidents().then(
      (loadedIncidents) => {
        if (!active) {
          return;
        }
        setIncidents(loadedIncidents);
        setSelectedIncidentId(loadedIncidents[0]?.id ?? null);
        setIncidentLoadState("ready");
      },
      (error: unknown) => {
        if (!active) {
          return;
        }
        setIncidentLoadState("error");
        setIncidentLoadError(
          describeError(error, "ResolveAI incidents could not be loaded."),
        );
      },
    );

    return () => {
      active = false;
    };
  }, []);

  function selectIncident(incidentId: string) {
    if (incidentId === selectedIncidentId) {
      return;
    }
    setSelectedIncidentId(incidentId);
    setInvestigationState("idle");
    setInvestigationResult(null);
    setInvestigationError(null);
    setInvestigationNotFound(false);
  }

  async function runInvestigation() {
    if (!selectedIncident || investigationState === "loading") {
      return;
    }

    const requestedIncidentId = selectedIncident.id;
    setInvestigationState("loading");
    setInvestigationResult(null);
    setInvestigationError(null);
    setInvestigationNotFound(false);

    try {
      const result = await investigateIncident(requestedIncidentId);
      if (result.incident_id !== requestedIncidentId) {
        throw new UnexpectedResponseError();
      }
      setInvestigationResult(result);
      setInvestigationState("success");
    } catch (error) {
      setInvestigationState("error");
      setInvestigationError(
        describeError(error, "The investigation request failed. Please retry."),
      );
      setInvestigationNotFound(
        error instanceof ApiRequestError && error.status === 404,
      );
    }
  }

  const requestStatus =
    investigationState === "loading"
      ? "Investigating"
      : investigationState === "success"
        ? "Complete"
        : investigationState === "error"
          ? "Failed"
          : "Ready";

  return (
    <div className="dashboard-grid">
      <aside className="incidents-panel panel">
        <div className="panel-heading">
          <div>
            <p className="section-kicker">Synthetic operational reports</p>
            <h2>Incidents</h2>
          </div>
          {incidentLoadState === "ready" && (
            <span className="count-summary">{incidents.length}</span>
          )}
        </div>

        {incidentLoadState === "loading" && (
          <p aria-live="polite" className="loading-message">
            Loading incidents…
          </p>
        )}

        {incidentLoadState === "error" && (
          <div className="inline-error" role="alert">
            <strong>Could not load incidents</strong>
            <p>{incidentLoadError}</p>
            <button
              className="secondary-button"
              onClick={refreshIncidents}
              type="button"
            >
              Retry
            </button>
          </div>
        )}

        {incidentLoadState === "ready" && incidents.length === 0 && (
          <p className="empty-message">No incidents are currently available.</p>
        )}

        {incidentLoadState === "ready" && incidents.length > 0 && (
          <IncidentList
            disabled={investigationState === "loading"}
            incidents={incidents}
            onSelect={selectIncident}
            selectedIncidentId={selectedIncidentId}
          />
        )}
      </aside>

      <section className="workspace-panel panel">
        {selectedIncident ? (
          <>
            <div className="incident-context">
              <div className="context-heading-row">
                <div>
                  <div className="badge-row">
                    <span className="incident-id">{selectedIncident.id}</span>
                    <span className="service-label">
                      {selectedIncident.service}
                    </span>
                  </div>
                  <h2>{selectedIncident.title}</h2>
                </div>
                <span
                  aria-live="polite"
                  className={`status-badge status-${investigationState}`}
                >
                  {requestStatus}
                </span>
              </div>

              <p className="incident-description">
                {selectedIncident.description}
              </p>

              <dl className="context-metadata">
                <div>
                  <dt>Service</dt>
                  <dd>{selectedIncident.service}</dd>
                </div>
                <div>
                  <dt>Started</dt>
                  <dd>
                    <time dateTime={selectedIncident.started_at}>
                      {dateTimeFormatter.format(
                        new Date(selectedIncident.started_at),
                      )} {" "}
                      UTC
                    </time>
                  </dd>
                </div>
              </dl>

              <button
                className="primary-button"
                disabled={investigationState === "loading"}
                onClick={runInvestigation}
                type="button"
              >
                {investigationState === "loading"
                  ? "Investigating…"
                  : "Investigate"}
              </button>
            </div>

            {investigationState === "loading" && (
              <div aria-live="polite" className="request-message">
                <strong>ResolveAI is investigating this incident.</strong>
                <p>The final result will appear when the request completes.</p>
              </div>
            )}

            {investigationState === "error" && (
              <div className="investigation-error" role="alert">
                <p className="section-kicker">Request failed</p>
                <h3>Investigation failed</h3>
                <p>{investigationError}</p>
                <div className="error-actions">
                  <button
                    className="primary-button"
                    onClick={runInvestigation}
                    type="button"
                  >
                    Retry investigation
                  </button>
                  {investigationNotFound && (
                    <button
                      className="secondary-button"
                      onClick={refreshIncidents}
                      type="button"
                    >
                      Refresh incidents
                    </button>
                  )}
                </div>
              </div>
            )}

            {investigationState === "idle" && (
              <div className="ready-message">
                <p className="section-kicker">Ready</p>
                <h3>Run an investigation</h3>
                <p>
                  ResolveAI will return one final diagnosed or inconclusive
                  result from the current backend workflow.
                </p>
              </div>
            )}

            {investigationState === "success" && investigationResult && (
              <InvestigationResult result={investigationResult} />
            )}
          </>
        ) : (
          <div className="empty-workspace">
            <h2>Select an incident</h2>
            <p>Choose an available incident to inspect its context.</p>
          </div>
        )}
      </section>
    </div>
  );
}
