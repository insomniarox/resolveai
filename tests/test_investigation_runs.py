"""Verify immutable saved-run models and their concrete PostgreSQL lifecycle."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from pydantic import ValidationError

from resolve_ai.investigation_runs import (
    InvestigationRunSnapshot,
    create_investigation_run,
    current_runtime_execution_metadata,
    delete_investigation_run,
    get_investigation_run,
)
from resolve_ai.models import (
    InvestigationResult,
    InvestigationStatus,
    ReasonerMetadata,
)
from resolve_ai.runtime_input import RuntimeIncidentBundle


def _bundle() -> RuntimeIncidentBundle:
    """Build a small valid runtime input for snapshot tests."""
    return RuntimeIncidentBundle.model_validate(
        {
            "schema_version": 1,
            "incident": {
                "id": "USER-INC-SAVED",
                "title": "Delayed invoice callbacks",
                "description": "Callbacks are delayed without a supported cause.",
                "service": "invoice-runtime-service",
                "started_at": "2026-08-19T09:00:00Z",
            },
            "evidence": [
                {
                    "id": "USER-LOG-SAVED",
                    "source": "log",
                    "kind": "http_request_failed",
                    "observed_at": "2026-08-19T09:00:10Z",
                    "summary": "A callback returned HTTP 500.",
                    "details": {"status_code": 500},
                }
            ],
        }
    )


def _completed_snapshot() -> InvestigationRunSnapshot:
    """Build one completed inconclusive snapshot with exact submitted input."""
    bundle = _bundle()
    _, evidence, _ = bundle.to_domain()
    reasoner = ReasonerMetadata(provider="openrouter", model="test-model")
    started_at = datetime(2026, 8, 19, 9, 0, tzinfo=UTC)
    return InvestigationRunSnapshot(
        bundle=bundle,
        retrieved_runbooks=[],
        retrieved_knowledge_documents=[],
        investigation_result=InvestigationResult(
            incident_id=bundle.incident.id,
            status=InvestigationStatus.INCONCLUSIVE,
            diagnosis=None,
            evidence=evidence,
            retrieved_runbooks=[],
            reasoner=reasoner,
        ),
        failure_code=None,
        reasoner=reasoner,
        execution=current_runtime_execution_metadata(),
        started_at=started_at,
        completed_at=started_at + timedelta(milliseconds=12),
        duration_ms=12,
    )


def test_snapshot_requires_exactly_one_result_or_stable_failure() -> None:
    valid = _completed_snapshot()

    with pytest.raises(
        ValidationError,
        match="exactly one result or failure",
    ):
        InvestigationRunSnapshot(
            **valid.model_dump(exclude={"investigation_result", "failure_code"}),
            investigation_result=None,
            failure_code=None,
        )


def test_current_execution_metadata_records_the_concrete_runtime_settings() -> None:
    metadata = current_runtime_execution_metadata()

    assert metadata.application_version == "0.1.0"
    assert metadata.prompt_version == "runtime-investigation-v1"
    assert metadata.output_schema_version == "runtime-reasoning-decision-v1"
    assert metadata.retrieval_strategy == "semantic"
    assert metadata.retrieval_limit == 3
    assert metadata.embedding_model == "BAAI/bge-small-en-v1.5"
    assert metadata.reasoning_effort == "medium"
    assert metadata.max_output_tokens == 4_000
    assert metadata.timeout_seconds == 30.0


def test_snapshot_rejects_a_result_for_another_incident() -> None:
    valid = _completed_snapshot()
    wrong_result = valid.investigation_result.model_copy(
        update={"incident_id": "USER-INC-OTHER"}
    )

    with pytest.raises(ValidationError, match="submitted incident"):
        InvestigationRunSnapshot(
            **valid.model_dump(exclude={"investigation_result"}),
            investigation_result=wrong_result,
        )


@pytest.mark.integration
def test_saved_run_capability_read_expiry_and_delete_lifecycle() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    initialization_sql = (
        Path(__file__).parents[1] / "database" / "init.sql"
    ).read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        connection.execute(initialization_sql)

    created = create_investigation_run(
        database_url=database_url,
        snapshot=_completed_snapshot(),
    )
    run_id = created.run.id
    expired_run_id = None
    try:
        with psycopg.connect(database_url) as connection:
            stored_hash, stored_snapshot = connection.execute(
                """
                SELECT capability_token_hash, snapshot
                FROM investigation_runs
                WHERE id = %s
                """,
                (run_id,),
            ).fetchone()

        assert stored_hash != created.capability_token.encode("utf-8")
        assert len(stored_hash) == 32
        assert stored_snapshot["bundle"]["incident"]["id"] == "USER-INC-SAVED"
        assert "capability_token" not in stored_snapshot

        assert (
            get_investigation_run(
                database_url=database_url,
                run_id=run_id,
                capability_token="wrong-capability",
            )
            is None
        )
        fetched = get_investigation_run(
            database_url=database_url,
            run_id=run_id,
            capability_token=created.capability_token,
        )
        assert fetched == created.run
        assert delete_investigation_run(
            database_url=database_url,
            run_id=run_id,
            capability_token=created.capability_token,
        )
        assert (
            get_investigation_run(
                database_url=database_url,
                run_id=run_id,
                capability_token=created.capability_token,
            )
            is None
        )

        expired = create_investigation_run(
            database_url=database_url,
            snapshot=_completed_snapshot(),
        )
        expired_run_id = expired.run.id
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                UPDATE investigation_runs
                SET created_at = now() - interval '2 hours',
                    expires_at = now() - interval '1 hour'
                WHERE id = %s
                """,
                (expired_run_id,),
            )
        assert (
            get_investigation_run(
                database_url=database_url,
                run_id=expired_run_id,
                capability_token=expired.capability_token,
            )
            is None
        )
        with psycopg.connect(database_url) as connection:
            remaining = connection.execute(
                "SELECT count(*) FROM investigation_runs WHERE id = %s",
                (expired_run_id,),
            ).fetchone()
        assert remaining == (0,)
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "DELETE FROM investigation_runs WHERE id = ANY(%s)",
                ([run_id, expired_run_id] if expired_run_id else [run_id],),
            )
