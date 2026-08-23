"use client";

import { useState } from "react";

import { InvestigationWorkspace } from "@/components/investigation-workspace";
import { RuntimeInvestigationWorkspace } from "@/components/runtime-investigation-workspace";

type InvestigationMode = "guided" | "runtime";

export function InvestigationModeWorkspace() {
  const [mode, setMode] = useState<InvestigationMode>("guided");

  return (
    <>
      <section aria-label="Investigation path" className="path-switcher panel">
        <div>
          <p className="section-kicker">Choose a reviewer path</p>
          <h2>Investigation input</h2>
        </div>
        <div aria-label="Investigation input type" className="path-tabs" role="tablist">
          <button
            aria-controls="guided-workspace"
            aria-selected={mode === "guided"}
            className="path-tab"
            id="guided-tab"
            onClick={() => setMode("guided")}
            role="tab"
            type="button"
          >
            Guided demo
          </button>
          <button
            aria-controls="runtime-workspace"
            aria-selected={mode === "runtime"}
            className="path-tab"
            id="runtime-tab"
            onClick={() => setMode("runtime")}
            role="tab"
            type="button"
          >
            Runtime input
          </button>
        </div>
        <p className="path-description">
          {mode === "guided"
            ? "Prepared synthetic fixtures provide a fast, deterministic architecture tour."
            : "Enter one bounded version-1 incident bundle through a form or JSON. Process it transiently, or save up to two one-hour provenance snapshots for comparison."}
        </p>
      </section>

      <div
        aria-labelledby={mode === "guided" ? "guided-tab" : "runtime-tab"}
        id={mode === "guided" ? "guided-workspace" : "runtime-workspace"}
        role="tabpanel"
      >
        {mode === "guided" ? (
          <InvestigationWorkspace />
        ) : (
          <RuntimeInvestigationWorkspace />
        )}
      </div>
    </>
  );
}
