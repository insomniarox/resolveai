"""Protect evaluation fairness, frozen inputs, and honest failure denominators."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest

from evals.evaluate_jev_decisions import (
    VARIANTS,
    attempt,
    build_trial,
    digest,
    load_cases,
    summarize,
    validate_answers,
)


def test_frozen_trials_keep_truth_out_of_requests_and_inputs_unchanged():
    cases = load_cases()
    before = deepcopy(cases)
    for case in cases:
        for variant in VARIANTS:
            trial = build_trial(case, variant)
            assert set(trial["request"]) == {"state", "questions"}
            assert trial["request_sha256"] == digest(trial["request"])
            validate_answers(trial["expected"], trial["request"]["questions"])
            assert "expected_cause" not in str(trial["request"])
            assert "ground_truth" not in str(trial["request"])
    assert cases == before
    assert {c["split"] for c in cases} == {"development", "holdout"}


def test_missing_evidence_removes_answer_bearing_report():
    trial = build_trial(load_cases()[0], "missing_evidence")
    assert trial["request"]["state"]["evidence"] == []
    assert trial["request"]["state"]["incident"] == {
        "description": "An incident was reported; observations are unavailable."
    }
    assert trial["expected"] == {"cause": "none"}


def test_parallel_attempts_receive_isolated_identical_requests():
    trial = build_trial(load_cases()[0], "structured")
    barrier = Barrier(2)
    seen = []

    def caller(request):
        seen.append(digest(request))
        request["state"]["evidence"].clear()
        barrier.wait(timeout=2)
        return trial["expected"], {}, "test-model", {}

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(attempt, trial, p, caller) for p in ("jev", "openrouter")
        ]
        records = [f.result() for f in futures]
    assert seen == [trial["request_sha256"]] * 2
    assert trial["request"]["state"]["evidence"]
    assert all(r["outcome"] == "completed" for r in records)


def test_failures_remain_in_denominators_without_leaking_error_text():
    trial = build_trial(load_cases()[0], "structured")

    def fail(request):
        raise ValueError("secret-request-data")

    record = attempt(trial, "jev", fail)
    assert "secret-request-data" not in str(record)
    summary = summarize([record])[0]
    assert summary["failures"] == 1
    assert summary["cause_total"] == 1
    assert summary["cause_correct"] == 0
    assert summary["evidence_total"] == 2
    assert summary["completed_median_ms"] is None


@pytest.mark.parametrize(
    "answers", [{}, {"cause": "invented"}, {"cause": "a", "extra": "a"}]
)
def test_invalid_answers_are_not_silently_scored(answers):
    with pytest.raises(ValueError):
        validate_answers(answers, {"cause": {"criteria": {"a": "A"}}})


def test_invalid_output_retains_usage_for_failed_attempt():
    trial = build_trial(load_cases()[0], "structured")
    record = attempt(
        trial,
        "jev",
        lambda request: (
            {"cause": "invented"},
            {"output": "invented"},
            "model",
            {"cost": 0.01},
        ),
    )
    assert record["outcome"] == "failed"
    assert record["raw_response"] == {"output": "invented"}
    assert summarize([record])[0]["cost_usd"] == 0.01


def test_cli_cap_and_exclusive_output_prevent_calls(monkeypatch, tmp_path):
    from evals import evaluate_jev_decisions as evaluator

    def forbidden(request):
        pytest.fail("Preflight must prevent provider calls")

    monkeypatch.setattr(evaluator, "call_jev", forbidden)
    monkeypatch.setattr(evaluator, "call_openrouter", forbidden)
    output = tmp_path / "results.jsonl"
    monkeypatch.setattr(
        "sys.argv", ["evaluate", "--live", "--max-calls", "1", "--output", str(output)]
    )
    with pytest.raises(SystemExit):
        evaluator.main()
    assert not output.exists()
    output.write_text("preserve this result")
    monkeypatch.setattr("sys.argv", ["evaluate", "--live", "--output", str(output)])
    with pytest.raises(SystemExit):
        evaluator.main()
    assert output.read_text() == "preserve this result"
