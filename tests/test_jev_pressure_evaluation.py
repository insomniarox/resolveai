"""Keep pressure cases frozen and candidate ordering independent of truth."""

from evals.evaluate_jev_decisions import validate_answers
from evals.evaluate_jev_pressure import build_trial, load_cases


def test_atomic_pressure_trials_preserve_truth_when_order_changes():
    cases = load_cases()
    assert len(cases) == 10
    for case in cases:
        original = build_trial(case)
        reverse = build_trial(case, True)
        assert original["expected"] == reverse["expected"]
        assert original["request"]["state"] == reverse["request"]["state"]
        assert (
            original["request"]["questions"]["cause"]["criteria"]
            == reverse["request"]["questions"]["cause"]["criteria"]
        )
        assert list(original["request"]["questions"]["cause"]["criteria"]) != list(
            reverse["request"]["questions"]["cause"]["criteria"]
        )
        validate_answers(original["expected"], original["request"]["questions"])
        assert "expected_cause" not in str(original["request"])
