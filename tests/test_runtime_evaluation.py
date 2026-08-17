"""Validate the opt-in runtime evaluation set without provider calls."""

from evals.evaluate_runtime_reasoning import load_cases


def test_runtime_reasoning_cases_cover_phase_7_2_boundaries() -> None:
    cases = load_cases()

    assert len(cases) == 4
    assert {case.id for case in cases} == {
        "runtime-lock-contention",
        "runtime-provider-outage",
        "runtime-open-taxonomy-dns",
        "runtime-insufficient-evidence",
    }
    outside_taxonomy = next(
        case for case in cases if case.id == "runtime-open-taxonomy-dns"
    )
    assert outside_taxonomy.expected_root_cause_label == (
        "upstream_dns_resolution_failure"
    )
