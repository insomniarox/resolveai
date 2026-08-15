"""Protect the frozen retrieval-dependent Phase 3 benchmark slice."""

import hashlib
import json
import re
from pathlib import Path

from evals.evaluate_investigations import (
    CORE_CASES_PATH,
    RETRIEVAL_DEPENDENT_CASES_PATH,
    load_benchmark_slice,
    load_cases,
)
from evals.evaluate_lexical_retrieval import load_cases as load_retrieval_cases
from resolve_ai.investigation import inspect_deployments, inspect_logs

PROJECT_ROOT = Path(__file__).parents[1]
RETRIEVAL_CASES_PATH = PROJECT_ROOT / "evals" / "runbook_retrieval_cases.json"
DATABASE_INIT_PATH = PROJECT_ROOT / "database" / "init.sql"

# The core artifact was frozen before INC-008 through INC-010 were added.
CORE_BENCHMARK_SHA256 = (
    "df204565818e30b02f330f65bc47a1756b77d13ffd234ad62dbd95d4fedd4871"
)
RETRIEVAL_DEPENDENT_BENCHMARK_SHA256 = (
    "37eb1117be695d6066a334766e8a1b28458b6b59cba12a818fa218e4737e79bd"
)
ORIGINAL_RETRIEVAL_CASES_SHA256 = (
    "25681df94a6509205518e6bb6156da142594d1f8e2460efc4fb8d70138b02fa4"
)
EXPANDED_RETRIEVAL_BENCHMARK_SHA256 = (
    "5327add74821f0a19c49b8082025c482dade11a681d788fbda7009abaa6d5dee"
)


def test_original_seven_case_artifact_remains_byte_for_byte_frozen() -> None:
    digest = hashlib.sha256(CORE_CASES_PATH.read_bytes()).hexdigest()

    assert digest == CORE_BENCHMARK_SHA256
    assert [case.context.incident.id for case in load_benchmark_slice("core")] == [
        f"INC-{number:03}" for number in range(1, 8)
    ]


def test_loads_three_retrieval_dependent_cases_with_frozen_ground_truth() -> None:
    cases = load_cases(RETRIEVAL_DEPENDENT_CASES_PATH)

    digest = hashlib.sha256(RETRIEVAL_DEPENDENT_CASES_PATH.read_bytes()).hexdigest()
    assert digest == RETRIEVAL_DEPENDENT_BENCHMARK_SHA256
    assert [case.context.incident.id for case in cases] == [
        "INC-008",
        "INC-009",
        "INC-010",
    ]
    assert [case.ground_truth.root_cause_label for case in cases] == [
        "connection_pool_exhaustion",
        "upstream_tls_identity_mismatch",
        "notification_provider_outage",
    ]
    assert [case.ground_truth.required_supporting_evidence_ids for case in cases] == [
        ["DEP-004:database_client_profile_id", "LOG-017"],
        ["DEP-005:tax_connector_profile_id", "LOG-020"],
        ["LOG-022", "LOG-023"],
    ]
    assert [case.ground_truth.acceptable_supporting_evidence_ids for case in cases] == [
        ["DEP-004:database_client_profile_id", "LOG-017", "LOG-018"],
        ["DEP-005:tax_connector_profile_id", "LOG-020"],
        ["LOG-022", "LOG-023", "LOG-024"],
    ]
    assert [case.ground_truth.relevant_runbook_ids for case in cases] == [
        ["RUN-007"],
        ["RUN-008"],
        ["RUN-009"],
    ]
    assert [case.ground_truth.remediation_label for case in cases] == [
        "restore_previous_connection_pool_size",
        "correct_upstream_certificate_identity",
        "restore_or_fail_over_notification_provider",
    ]


def test_combined_slice_has_unique_incidents_and_valid_evidence_ids() -> None:
    core_cases = load_benchmark_slice("core")
    extension_cases = load_benchmark_slice("retrieval-dependent")
    combined_cases = load_benchmark_slice("combined")

    assert combined_cases == core_cases + extension_cases
    assert len(combined_cases) == 10

    extension_evidence_ids: list[str] = []
    core_evidence_ids = {
        evidence.id
        for case in core_cases
        for evidence in inspect_logs(case.context) + inspect_deployments(case.context)
    }
    for case in extension_cases:
        evidence = inspect_logs(case.context) + inspect_deployments(case.context)
        available_ids = {item.id for item in evidence}
        required = set(case.ground_truth.required_supporting_evidence_ids)
        acceptable = set(case.ground_truth.acceptable_supporting_evidence_ids)

        assert required <= acceptable <= available_ids
        assert not any(item_id.startswith("RUN-") for item_id in acceptable)
        assert all(
            runbook_id.startswith("RUN-")
            for runbook_id in case.ground_truth.relevant_runbook_ids
        )
        extension_evidence_ids.extend(item.id for item in evidence)

    assert len(extension_evidence_ids) == len(set(extension_evidence_ids))
    assert not core_evidence_ids.intersection(extension_evidence_ids)


def test_new_observations_do_not_encode_the_expected_interpretation() -> None:
    pool_case, tls_case, lifecycle_case = load_cases(RETRIEVAL_DEPENDENT_CASES_PATH)

    pool_log = pool_case.context.logs[0]
    assert pool_log.kind == "upstream_request_failed"
    assert set(pool_log.details) == {"internal_code", "state", "wait_ms"}

    tls_log = tls_case.context.logs[0]
    assert set(tls_log.details) == {"connector_profile_id", "internal_code"}

    lifecycle_details = lifecycle_case.context.logs[0].details
    assert set(lifecycle_details) == {
        "s4_previous_items",
        "s4_current_items",
        "s1_current_items",
        "oldest_s4_item_age_seconds",
    }


def test_runbook_seed_contains_exactly_nine_unique_documents() -> None:
    initialization_sql = DATABASE_INIT_PATH.read_text(encoding="utf-8")
    runbook_ids = re.findall(r"\(\s*'(RUN-\d{3})',", initialization_sql)

    assert runbook_ids == [f"RUN-{number:03}" for number in range(1, 10)]
    assert len(runbook_ids) == len(set(runbook_ids))
    assert (
        "Payment database client profiles and admission telemetry" in initialization_sql
    )
    assert (
        "Tax connector route profiles and certificate inventory" in initialization_sql
    )
    assert "Notification delivery lifecycle and probe coverage" in initialization_sql


def test_retrieval_benchmark_preserves_original_cases_and_adds_six() -> None:
    benchmark_bytes = RETRIEVAL_CASES_PATH.read_bytes()
    raw_cases = json.loads(benchmark_bytes)
    original_cases = json.dumps(
        raw_cases[:12], sort_keys=True, separators=(",", ":")
    ).encode()
    cases = load_retrieval_cases(RETRIEVAL_CASES_PATH)

    assert hashlib.sha256(benchmark_bytes).hexdigest() == (
        EXPANDED_RETRIEVAL_BENCHMARK_SHA256
    )
    assert hashlib.sha256(original_cases).hexdigest() == ORIGINAL_RETRIEVAL_CASES_SHA256
    assert len(cases) == 18
    assert [
        (case.id, case.query_kind, case.expected_runbook_id) for case in cases[12:]
    ] == [
        ("database-client-profile-direct", "direct_vocabulary", "RUN-007"),
        ("database-client-profile-paraphrased", "paraphrased", "RUN-007"),
        ("tax-route-profile-direct", "direct_vocabulary", "RUN-008"),
        ("tax-route-profile-paraphrased", "paraphrased", "RUN-008"),
        ("notification-lifecycle-direct", "direct_vocabulary", "RUN-009"),
        ("notification-lifecycle-paraphrased", "paraphrased", "RUN-009"),
    ]
    new_queries = " ".join(case.query for case in cases[12:])
    assert "PGX-17" not in new_queries
    assert "TLS-PV-2" not in new_queries
    assert not re.search(r"\bS4\b", new_queries)
