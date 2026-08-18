import type { RetrievedKnowledgeDocument } from "@/lib/types";

interface RuntimeKnowledgeListProps {
  documents: RetrievedKnowledgeDocument[];
}

export function RuntimeKnowledgeList({
  documents,
}: RuntimeKnowledgeListProps) {
  return (
    <section aria-labelledby="runtime-knowledge-title" className="result-section">
      <div className="section-heading-row">
        <div>
          <p className="section-kicker">Request-scoped guidance</p>
          <h3 id="runtime-knowledge-title">Retrieved runtime knowledge</h3>
        </div>
        <span className="count-summary">{documents.length} retrieved</span>
      </div>

      <p className="semantic-note">
        These documents were supplied with this request. Similarity represents
        retrieval relevance, not causal Evidence or diagnosis confidence.
      </p>

      <div className="runbook-list">
        {documents.map((document, index) => (
          <article className="runbook-item" key={document.id}>
            <div className="item-heading-row">
              <div className="badge-row">
                <span className="rank-badge">Rank {index + 1}</span>
                <span className="service-label">{document.content_type}</span>
              </div>
              <code>{document.id}</code>
            </div>
            <h4>{document.title}</h4>
            <p>{document.content}</p>
            <p className="similarity-score">
              Semantic similarity{" "}
              <strong>{document.similarity_score.toFixed(3)}</strong>
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
