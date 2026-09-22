"use client";

import { useState } from "react";
import { comparisonPackages } from "@/lib/comparison-packages";

export function ComparisonPackageLibrary({
  disabled,
  onLoad,
  onLoadOriginal,
}: {
  disabled: boolean;
  onLoad: (id: string) => void;
  onLoadOriginal: () => void;
}) {
  const [selectedId, setSelectedId] = useState(comparisonPackages[0].id);
  const selected = comparisonPackages.find((item) => item.id === selectedId)!;
  const { bundle, candidates } = selected.request;
  return (
    <aside
      className="panel package-library"
      aria-labelledby="package-library-title"
    >
      <div className="panel-heading">
        <div>
          <p className="section-kicker">Synthetic incident library</p>
          <h2 id="package-library-title">Explore a scenario</h2>
        </div>
        <span className="count-summary">10</span>
      </div>
      <div className="runtime-form">
        <label htmlFor="comparison-package">Incident package</label>
        <select
          id="comparison-package"
          value={selectedId}
          disabled={disabled}
          onChange={(event) => setSelectedId(event.target.value)}
        >
          {comparisonPackages.map((item, index) => (
            <option key={item.id} value={item.id}>
              {index + 1}. {item.request.bundle.incident.title}
            </option>
          ))}
        </select>
        <div className="package-preview" aria-live="polite">
          <p className="section-kicker">{selected.domain}</p>
          <h3>{bundle.incident.title}</h3>
          <p>{selected.synopsis}</p>
          <dl className="package-counts">
            <div>
              <dt>Observations</dt>
              <dd>{bundle.evidence.length}</dd>
            </div>
            <div>
              <dt>References</dt>
              <dd>{bundle.knowledge_documents?.length ?? 0}</dd>
            </div>
            <div>
              <dt>Hypotheses</dt>
              <dd>{candidates.length}</dd>
            </div>
          </dl>
          <p className="package-contents-label">Included reference documents</p>
          <ul>
            {bundle.knowledge_documents?.map((doc) => (
              <li key={doc.id}>{doc.title}</li>
            ))}
          </ul>
        </div>
        <button
          className="primary-button"
          type="button"
          disabled={disabled}
          onClick={() => onLoad(selectedId)}
        >
          Load selected package
        </button>
        <p className="comparison-note">
          Replaces the incident, observations, documents and hypotheses in the
          editor. Loading a package does not run the models.
        </p>
        <button
          className="secondary-button"
          type="button"
          disabled={disabled}
          onClick={onLoadOriginal}
        >
          Load original invoice example
        </button>
        <p className="comparison-note">
          Fictional systems and records, written as incident exercises. These
          packages are not accuracy benchmarks.
        </p>
      </div>
    </aside>
  );
}
