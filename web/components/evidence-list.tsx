import type { Evidence } from "@/lib/types";

interface EvidenceListProps {
  evidence: Evidence[];
  supportingEvidenceIds: string[];
}

const dateTimeFormatter = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "medium",
  timeZone: "UTC",
});

function formatName(value: string): string {
  return value.replaceAll("_", " ");
}

export function EvidenceList({
  evidence,
  supportingEvidenceIds,
}: EvidenceListProps) {
  const supportingIds = new Set(supportingEvidenceIds);
  const evidenceSummary = supportingEvidenceIds.length
    ? `${evidence.length} collected · ${supportingEvidenceIds.length} cited`
    : `${evidence.length} collected`;

  return (
    <section aria-labelledby="evidence-title" className="result-section">
      <div className="section-heading-row">
        <div>
          <p className="section-kicker">Observed incident facts</p>
          <h3 id="evidence-title">Collected Evidence</h3>
        </div>
        <span className="count-summary">{evidenceSummary}</span>
      </div>

      {evidence.length === 0 ? (
        <p className="empty-message">No Evidence was collected.</p>
      ) : (
        <div className="evidence-list">
          {evidence.map((item) => {
            const supportsDiagnosis = supportingIds.has(item.id);
            const details = Object.entries(item.details);

            return (
              <article
                className={`evidence-item${supportsDiagnosis ? " evidence-item-supporting" : ""}`}
                key={item.id}
              >
                <div className="item-heading-row">
                  <div className="badge-row">
                    <span
                      className={`evidence-role ${supportsDiagnosis ? "evidence-role-supporting" : ""}`}
                    >
                      {supportsDiagnosis
                        ? "Supports diagnosis"
                        : "Collected context"}
                    </span>
                    <span className="source-badge">{item.source}</span>
                  </div>
                  <code>{item.id}</code>
                </div>

                <p className="evidence-summary">{item.summary}</p>

                <dl className="item-metadata">
                  <div>
                    <dt>Kind</dt>
                    <dd>{formatName(item.kind)}</dd>
                  </div>
                  <div>
                    <dt>Observed</dt>
                    <dd>
                      <time dateTime={item.observed_at}>
                        {dateTimeFormatter.format(new Date(item.observed_at))} UTC
                      </time>
                    </dd>
                  </div>
                </dl>

                {details.length > 0 && (
                  <dl className="structured-details">
                    {details.map(([name, value]) => (
                      <div key={name}>
                        <dt>{formatName(name)}</dt>
                        <dd>{value}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
