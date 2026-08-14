"""Verify the semantic evaluator uses ranked IDs from semantic search."""

from evals.evaluate_lexical_retrieval import RunbookRetrievalCase
from evals.evaluate_semantic_retrieval import evaluate_cases
from resolve_ai.models import RetrievedRunbook


def test_evaluate_cases_records_semantic_result_order(monkeypatch) -> None:
    def fake_semantic_search_runbooks(
        database_url: str,
        query: str,
        limit: int,
    ) -> list[RetrievedRunbook]:
        assert database_url == "postgresql://example"
        assert query == "paraphrased operational symptom"
        assert limit == 3
        return [
            RetrievedRunbook(
                id="RUN-002",
                title="Expected",
                service="authentication-service",
                content="Expected content",
                similarity_score=0.8,
            ),
            RetrievedRunbook(
                id="RUN-001",
                title="Second",
                service="payment-service",
                content="Second content",
                similarity_score=0.6,
            ),
        ]

    monkeypatch.setattr(
        "evals.evaluate_semantic_retrieval.semantic_search_runbooks",
        fake_semantic_search_runbooks,
    )
    cases = [
        RunbookRetrievalCase(
            id="semantic-case",
            query_kind="paraphrased",
            query="paraphrased operational symptom",
            expected_runbook_id="RUN-002",
        )
    ]

    results = evaluate_cases("postgresql://example", cases)

    assert results[0].retrieved_runbook_ids == ["RUN-002", "RUN-001"]
    assert results[0].top_1_correct is True
