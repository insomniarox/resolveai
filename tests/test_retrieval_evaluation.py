"""Verify retrieval evaluation logic without asserting strategy quality."""

import pytest

from evals.evaluate_lexical_retrieval import (
    RunbookRetrievalCase,
    RunbookRetrievalCaseResult,
    Top1Score,
    calculate_top_1_score,
)


def _result(
    case_id: str,
    query_kind: str,
    expected_runbook_id: str,
    retrieved_runbook_ids: list[str],
) -> RunbookRetrievalCaseResult:
    return RunbookRetrievalCaseResult(
        case=RunbookRetrievalCase(
            id=case_id,
            query_kind=query_kind,
            query="A fabricated query for metric testing",
            expected_runbook_id=expected_runbook_id,
        ),
        retrieved_runbook_ids=retrieved_runbook_ids,
    )


def test_top_1_score_counts_correct_wrong_and_empty_results() -> None:
    results = [
        _result("correct", "direct_vocabulary", "RUN-001", ["RUN-001"]),
        _result("wrong", "direct_vocabulary", "RUN-002", ["RUN-003"]),
        _result("empty", "paraphrased", "RUN-003", []),
    ]

    score = calculate_top_1_score(results)

    assert score == Top1Score(correct=1, total=3)
    assert score.accuracy == pytest.approx(1 / 3)


def test_top_1_score_can_select_one_query_kind() -> None:
    results = [
        _result("direct", "direct_vocabulary", "RUN-001", ["RUN-001"]),
        _result("paraphrased", "paraphrased", "RUN-002", []),
    ]

    direct_score = calculate_top_1_score(results, "direct_vocabulary")
    paraphrased_score = calculate_top_1_score(results, "paraphrased")

    assert direct_score == Top1Score(correct=1, total=1)
    assert paraphrased_score == Top1Score(correct=0, total=1)


def test_top_1_accuracy_rejects_an_empty_selection() -> None:
    with pytest.raises(ValueError, match="at least one evaluation case"):
        _accuracy = Top1Score(correct=0, total=0).accuracy
