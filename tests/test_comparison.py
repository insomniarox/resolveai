"""Protect paired context, independent failures, admission, and cleanup ownership."""

from copy import deepcopy
from threading import Barrier
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from resolve_ai import api, comparison
from resolve_ai.comparison_models import ComparisonInput, DecisionCall, DecisionUsage
from resolve_ai.comparison_reasoner import MODELS
from resolve_ai.retrieval import RuntimeKnowledgeError


def request():
    return ComparisonInput.model_validate(
        {
            "bundle": {
                "schema_version": 1,
                "incident": {
                    "id": "I1",
                    "title": "Requests fail",
                    "description": "A service is degraded.",
                    "service": "svc",
                    "started_at": "2026-09-21T09:00:00Z",
                },
                "evidence": [
                    {
                        "id": "E1",
                        "source": "log",
                        "kind": "http_request_failed",
                        "observed_at": "2026-09-21T09:00:01Z",
                        "summary": "The provider returned a failure.",
                        "details": {},
                    }
                ],
            },
            "candidates": ["The provider is unavailable."],
        }
    )


def answer(provider, state, questions, stage):
    return DecisionCall(
        stage=stage,
        duration_ms=1,
        model=MODELS[provider],
        usage=DecisionUsage(input_tokens=10, output_tokens=2),
        answers={key: "c0" if stage == "cause" else "supports" for key in questions},
    )


def test_parallel_context_and_cleanup_once(monkeypatch):
    req = request()
    req.bundle.knowledge_documents = []
    gate = Barrier(2)
    seen = []

    def caller(provider, state, questions, stage):
        if stage == "cause":
            seen.append(deepcopy(state))
            state["evidence"].clear()
            gate.wait(timeout=2)
        return answer(provider, state, questions, stage)

    monkeypatch.setattr(
        comparison, "retrieve_investigation_references", lambda *args: ([], [])
    )
    events = []
    comparison.run_comparison(req, "unused", events.append, caller)
    assert seen[0] == seen[1]
    assert [e.type for e in events] == ["prepared", "branch", "branch", "finished"]
    assert {e.branch.provider for e in events if e.branch} == {"jev", "openrouter"}
    assert all(e.branch.supporting_evidence_ids == ["E1"] for e in events if e.branch)
    assert events[-1].finished.cleanup == "not_needed"
    assert len(req.bundle.evidence) == 1


def test_provider_failure_does_not_hide_other_result(monkeypatch):
    monkeypatch.setattr(
        comparison, "retrieve_investigation_references", lambda *args: ([], [])
    )

    def caller(provider, *args):
        if provider == "jev":
            raise ValueError("private provider output")
        return answer(provider, *args)

    events = []
    comparison.run_comparison(request(), "unused", events.append, caller)
    branches = {e.branch.provider: e.branch for e in events if e.branch}
    assert branches["jev"].error_code == "invalid_output"
    assert branches["openrouter"].outcome == "supported"
    assert "private provider" not in str(events)


def test_abstention_skips_second_request():
    stages = []

    def caller(provider, state, questions, stage):
        stages.append(stage)
        result = answer(provider, state, questions, stage)
        result.answers = {"cause": "none"}
        return result

    branch = comparison.execute_branch(
        "jev", {"evidence": []}, ["A cause"], perf_counter(), caller
    )
    assert branch.outcome == "inconclusive"
    assert stages == ["cause"]


def test_contradiction_prevents_supported_result():
    def caller(provider, state, questions, stage):
        result = answer(provider, state, questions, stage)
        if stage == "evidence":
            result.answers = {"e0": "contradicts"}
        return result

    branch = comparison.execute_branch(
        "jev", {"evidence": [{"id": "E1"}]}, ["A cause"], perf_counter(), caller
    )
    assert branch.outcome == "inconclusive"
    assert branch.supporting_evidence_ids == []


def test_scope_cleanup_survives_preparation_failure(monkeypatch):
    req = request()
    from resolve_ai.runtime_input import RuntimeKnowledgeDocumentInput

    req.bundle.knowledge_documents = [
        RuntimeKnowledgeDocumentInput(
            id="D1", title="Guide", content_type="text/plain", content="Reference text"
        )
    ]
    scopes = []
    monkeypatch.setattr(
        comparison,
        "store_runtime_knowledge_documents",
        lambda **kw: scopes.append(kw["scope_id"]),
    )

    def fail(*args):
        raise RuntimeKnowledgeError("private database details")

    monkeypatch.setattr(comparison, "retrieve_investigation_references", fail)
    deleted = []
    monkeypatch.setattr(
        comparison,
        "delete_runtime_knowledge_scope",
        lambda db, scope: deleted.append(scope),
    )
    events = []
    comparison.run_comparison(req, "unused", events.append, answer)
    assert scopes == deleted and len(deleted) == 1
    assert [e.type for e in events] == ["error", "finished"]
    assert events[-1].finished.cleanup == "completed"


def test_oversized_input_never_calls_providers(monkeypatch):
    from resolve_ai.models import RetrievedRunbook

    monkeypatch.setattr(
        comparison,
        "retrieve_investigation_references",
        lambda *args: (
            [
                RetrievedRunbook(
                    id="R1",
                    title="Guide",
                    service="svc",
                    content="x" * 31000,
                    similarity_score=0.9,
                )
            ],
            [],
        ),
    )

    def forbidden(*args):
        pytest.fail("Oversized context must fail before spending")

    events = []
    comparison.run_comparison(request(), "unused", events.append, forbidden)
    assert events[0].error == "input_too_large"
    assert events[-1].type == "finished"


def test_stream_admission_and_release(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("DATABASE_URL", "unused")
    monkeypatch.setattr(
        comparison, "retrieve_investigation_references", lambda *args: ([], [])
    )
    monkeypatch.setattr(
        api,
        "run_comparison",
        lambda req, db, emit: comparison.run_comparison(req, db, emit, answer),
    )
    client = TestClient(api.app)
    api._runtime_reasoner_gate.acquire()
    try:
        assert (
            client.post(
                "/runtime/compare", json=request().model_dump(mode="json")
            ).status_code
            == 429
        )
    finally:
        api._runtime_reasoner_gate.release()
    response = client.post("/runtime/compare", json=request().model_dump(mode="json"))
    assert response.status_code == 200
    import json

    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[-1]["type"] == "finished"
    assert len([e for e in events if e["type"] == "branch"]) == 2
    assert api._runtime_reasoner_gate.acquire(blocking=False)
    api._runtime_reasoner_gate.release()


def test_candidates_are_bounded_and_distinct():
    value = request().model_dump(mode="json")
    for candidates in [[], ["same", "SAME"], ["x" * 501], ["a cause"] * 6]:
        with pytest.raises(ValidationError):
            ComparisonInput.model_validate({**value, "candidates": candidates})


@pytest.mark.integration
def test_real_scoped_preparation_is_shared_and_removed():
    import os

    import psycopg

    from resolve_ai.runtime_input import RuntimeKnowledgeDocumentInput

    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL required")
    req = request()
    req.bundle.knowledge_documents = [
        RuntimeKnowledgeDocumentInput(
            id="COMPARISON-DOC",
            title="Provider failure guide",
            content_type="text/plain",
            content="The provider is unavailable when it reports an outage and rejects requests.",
        )
    ]
    with psycopg.connect(database_url) as connection:
        before = connection.execute(
            "SELECT id, content, embedding::text FROM runbooks ORDER BY id"
        ).fetchall()
    seen = []

    def caller(provider, state, questions, stage):
        if stage == "cause":
            seen.append(deepcopy(state))
        return answer(provider, state, questions, stage)

    events = []
    comparison.run_comparison(req, database_url, events.append, caller)
    assert events[-1].finished.cleanup == "completed"
    assert len(seen) == 2 and seen[0] == seen[1]
    assert any(r["id"] == "COMPARISON-DOC" for r in seen[0]["references"])
    with psycopg.connect(database_url) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM runtime_knowledge_documents WHERE document_id = 'COMPARISON-DOC'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT id, content, embedding::text FROM runbooks ORDER BY id"
            ).fetchall()
            == before
        )


def test_request_worker_finishes_without_stream_consumer(monkeypatch):
    """Dropping the browser consumer cannot strand the gate or block cleanup."""
    from threading import BoundedSemaphore, Event

    started, finish, released = Event(), Event(), Event()
    semaphore = BoundedSemaphore(1)

    class Gate:
        def acquire(self, **kwargs):
            return semaphore.acquire(**kwargs)

        def release(self):
            semaphore.release()
            released.set()

    def work(req, db, emit):
        started.set()
        assert finish.wait(2)

    monkeypatch.setattr(api, "_runtime_reasoner_gate", Gate())
    monkeypatch.setattr(api, "run_comparison", work)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("DATABASE_URL", "unused")
    response = api.compare_runtime_endpoint(request())
    assert response.media_type == "application/x-ndjson"
    assert started.wait(2)
    assert not semaphore.acquire(blocking=False)
    finish.set()
    assert released.wait(2)
    assert semaphore.acquire(blocking=False)
    semaphore.release()


@pytest.mark.parametrize(
    "model, tokens, estimate",
    [
        ("jev-1.13.0", 1000, 0.000042),
        ("jev-future", 1000, None),
        ("jev-1.13.0", None, None),
        ("jev-1.13.0", 0, 0),
    ],
)
def test_jev_estimate_is_separate_from_reported_cost(
    monkeypatch, model, tokens, estimate
):
    from types import SimpleNamespace

    from resolve_ai import comparison_reasoner

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def system_one(self, **kwargs):
            return SimpleNamespace(
                model=model,
                choices={"cause": SimpleNamespace(choice="c0", confidence=0.9)},
                usage=SimpleNamespace(
                    model_dump=lambda: {"input_tokens": tokens, "output_tokens": 10}
                ),
            )

    monkeypatch.setattr(comparison_reasoner, "TypeSafeClient", Client)
    result = comparison_reasoner.ask(
        "jev", {}, comparison_reasoner.cause_questions(["Provider failure"]), "cause"
    )
    assert result.usage.reported_cost_usd is None
    if estimate is None:
        assert result.usage.estimated_cost_usd is None
    else:
        assert result.usage.estimated_cost_usd == pytest.approx(estimate)


def test_reference_roles_reach_both_models_without_becoming_evidence(monkeypatch):
    from resolve_ai.models import RetrievedKnowledgeDocument, RetrievedRunbook

    runbook = RetrievedRunbook(
        id="R1",
        title="Official guide",
        service="svc",
        content="Expected behavior",
        similarity_score=0.8,
    )
    document = RetrievedKnowledgeDocument(
        id="D1",
        title="Incident notes",
        content_type="text/plain",
        content="Supplemental context",
        similarity_score=0.9,
    )
    monkeypatch.setattr(
        comparison,
        "retrieve_investigation_references",
        lambda *args: ([runbook], [document]),
    )
    states = []

    def caller(provider, state, questions, stage):
        states.append((provider, deepcopy(state)))
        return answer(provider, state, questions, stage)

    events = []
    comparison.run_comparison(request(), "unused", events.append, caller)
    assert {provider for provider, _ in states} == {"jev", "openrouter"}
    for _, state in states:
        assert [r["reference_type"] for r in state["references"]] == [
            "official_runbook",
            "attached_document",
        ]
        assert [e["id"] for e in state["evidence"]] == ["E1"]
    assert events[0].prepared.runbooks == [runbook]
    assert events[0].prepared.documents == [document]
