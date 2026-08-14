"""Measure pgvector semantic retrieval on the shared runbook benchmark."""

import argparse
from pathlib import Path

from evals.evaluate_lexical_retrieval import (
    RunbookRetrievalCase,
    RunbookRetrievalCaseResult,
    load_cases,
    print_report,
)
from resolve_ai.retrieval import (
    count_runbooks_without_embeddings,
    semantic_search_runbooks,
)


def evaluate_cases(
    database_url: str,
    cases: list[RunbookRetrievalCase],
    limit: int = 3,
) -> list[RunbookRetrievalCaseResult]:
    """Run every unchanged case through PostgreSQL semantic search."""
    results: list[RunbookRetrievalCaseResult] = []

    for case in cases:
        retrieved_runbooks = semantic_search_runbooks(
            database_url=database_url,
            query=case.query,
            limit=limit,
        )
        results.append(
            RunbookRetrievalCaseResult(
                case=case,
                retrieved_runbook_ids=[runbook.id for runbook in retrieved_runbooks],
            )
        )

    return results


def main() -> None:
    """Validate corpus setup and run the semantic retrieval benchmark."""
    parser = argparse.ArgumentParser(
        description="Evaluate PostgreSQL semantic runbook retrieval."
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="PostgreSQL connection URL containing populated runbook embeddings.",
    )
    args = parser.parse_args()

    missing_embeddings = count_runbooks_without_embeddings(args.database_url)
    if missing_embeddings:
        raise RuntimeError(
            f"semantic evaluation requires populated embeddings; "
            f"{missing_embeddings} runbook(s) are missing one"
        )

    cases_path = Path(__file__).with_name("runbook_retrieval_cases.json")
    cases = load_cases(cases_path)
    results = evaluate_cases(args.database_url, cases)
    print_report(results)


if __name__ == "__main__":
    main()
