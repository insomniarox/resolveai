import type { RetrievedRunbook } from "@/lib/types";

interface ReferenceKnowledgeListProps {
  runbooks: RetrievedRunbook[];
}

export function ReferenceKnowledgeList({
  runbooks,
}: ReferenceKnowledgeListProps) {
  return (
    <section aria-labelledby="runbooks-title" className="result-section">
      <div className="section-heading-row">
        <div>
          <p className="section-kicker">Retrieved guidance</p>
          <h3 id="runbooks-title">Related reference knowledge</h3>
        </div>
        <span className="count-summary">{runbooks.length} retrieved</span>
      </div>

      <p className="semantic-note">
        Similarity represents retrieval relevance, not diagnosis confidence or
        causal support.
      </p>

      {runbooks.length === 0 ? (
        <p className="empty-message">
          No related reference knowledge was returned.
        </p>
      ) : (
        <div className="runbook-list">
          {runbooks.map((runbook, index) => (
            <article className="runbook-item" key={runbook.id}>
              <div className="item-heading-row">
                <div className="badge-row">
                  <span className="rank-badge">Rank {index + 1}</span>
                  <span className="service-label">{runbook.service}</span>
                </div>
                <code>{runbook.id}</code>
              </div>
              <h4>{runbook.title}</h4>
              <p>{runbook.content}</p>
              <p className="similarity-score">
                Semantic similarity <strong>{runbook.similarity_score.toFixed(3)}</strong>
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
