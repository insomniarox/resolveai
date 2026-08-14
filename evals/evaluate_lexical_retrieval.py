"""Measure PostgreSQL lexical retrieval on the shared runbook benchmark.

This is an evaluation command, not a regression test. A missed benchmark case
is recorded in the Top-1 score rather than raised as a test failure.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from resolve_ai.retrieval import search_runbooks

QueryKind = Literal["direct_vocabulary", "paraphrased"]


class RunbookRetrievalCase(BaseModel):
    """Describe one strategy-neutral query and its human-labeled answer."""

    id: str
    query_kind: QueryKind
    query: str
    expected_runbook_id: str


@dataclass(frozen=True)
class RunbookRetrievalCaseResult:
    """Record ranked IDs returned for one benchmark case."""

    case: RunbookRetrievalCase
    retrieved_runbook_ids: list[str]

    @property
    def top_1_correct(self) -> bool:
        """Return whether the expected runbook is the first result."""
        return bool(
            self.retrieved_runbook_ids
            and self.retrieved_runbook_ids[0] == self.case.expected_runbook_id
        )


@dataclass(frozen=True)
class Top1Score:
    """Keep the Top-1 numerator and denominator visible beside the accuracy."""

    correct: int
    total: int

    @property
    def accuracy(self) -> float:
        """Return the fraction of cases with the expected document at rank one."""
        if self.total == 0:
            raise ValueError("Top-1 accuracy requires at least one evaluation case")
        return self.correct / self.total


def load_cases(path: Path) -> list[RunbookRetrievalCase]:
    """Load and validate the visible JSON benchmark dataset."""
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    return [RunbookRetrievalCase.model_validate(case) for case in raw_cases]


def evaluate_cases(
    database_url: str,
    cases: list[RunbookRetrievalCase],
    limit: int = 3,
) -> list[RunbookRetrievalCaseResult]:
    """Run every case through the real PostgreSQL lexical search operation."""
    results: list[RunbookRetrievalCaseResult] = []

    for case in cases:
        retrieved_runbooks = search_runbooks(
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


def calculate_top_1_score(
    results: list[RunbookRetrievalCaseResult],
    query_kind: QueryKind | None = None,
) -> Top1Score:
    """Calculate overall or per-query-kind Top-1 accuracy."""
    selected_results = [
        result
        for result in results
        if query_kind is None or result.case.query_kind == query_kind
    ]
    return Top1Score(
        correct=sum(result.top_1_correct for result in selected_results),
        total=len(selected_results),
    )


def print_report(results: list[RunbookRetrievalCaseResult]) -> None:
    """Print case outcomes followed by overall and per-kind Top-1 scores."""
    for result in results:
        retrieved = ", ".join(result.retrieved_runbook_ids) or "no results"
        outcome = "correct" if result.top_1_correct else "miss"
        print(
            f"{result.case.id}: {outcome} | expected="
            f"{result.case.expected_runbook_id} | retrieved={retrieved}"
        )

    print()
    for label, query_kind in (
        ("Overall", None),
        ("Direct vocabulary", "direct_vocabulary"),
        ("Paraphrased", "paraphrased"),
    ):
        score = calculate_top_1_score(results, query_kind)
        print(f"{label} Top-1: {score.correct}/{score.total} ({score.accuracy:.0%})")


def main() -> None:
    """Parse command-line inputs and run the lexical retrieval benchmark."""
    parser = argparse.ArgumentParser(
        description="Evaluate PostgreSQL lexical runbook retrieval."
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="PostgreSQL connection URL containing the runbook corpus.",
    )
    args = parser.parse_args()

    cases_path = Path(__file__).with_name("runbook_retrieval_cases.json")
    cases = load_cases(cases_path)
    results = evaluate_cases(args.database_url, cases)
    print_report(results)


if __name__ == "__main__":
    main()
