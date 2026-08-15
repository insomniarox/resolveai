"""Verify the stable tracing semantics of one investigation."""

from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode

import resolve_ai.investigation as investigation_module
import resolve_ai.retrieval as retrieval_module
from resolve_ai.embeddings import EMBEDDING_DIMENSIONS
from resolve_ai.fixtures import get_incident_context


def _runbook_row() -> dict[str, str | float]:
    return {
        "id": "RUN-001",
        "title": "Database connection pool timeout diagnosis",
        "service": "payment-service",
        "content": "Test reference knowledge.",
        "similarity_score": 0.9,
    }


def _spans_by_name(exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    return {span.name: span for span in exporter.get_finished_spans()}


def _assert_children(
    spans: dict[str, ReadableSpan],
    parent_name: str,
    child_names: set[str],
) -> None:
    parent = spans[parent_name]
    actual_children = {
        span.name for span in spans.values() if span.parent == parent.context
    }
    assert actual_children == child_names


def test_investigation_trace_outcome_and_error_semantics(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(
        investigation_module,
        "tracer",
        provider.get_tracer("resolve_ai.investigation.test"),
    )
    monkeypatch.setattr(
        retrieval_module,
        "tracer",
        provider.get_tracer("resolve_ai.retrieval.test"),
    )

    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.execute.return_value.fetchall.return_value = [_runbook_row()]
    monkeypatch.setattr(
        retrieval_module,
        "generate_query_embedding",
        lambda query: [0.0] * EMBEDDING_DIMENSIONS,
    )
    monkeypatch.setattr(
        retrieval_module.psycopg,
        "connect",
        lambda database_url, row_factory: connection,
    )
    diagnosed_context = get_incident_context("INC-001")
    assert diagnosed_context is not None

    investigation_module.investigate_incident(
        diagnosed_context,
        database_url="postgresql://test",
    )

    spans = _spans_by_name(exporter)
    assert set(spans) == {
        "investigation",
        "retrieve_runbooks",
        "generate_query_embedding",
        "query_runbooks",
        "generate_hypothesis",
        "verify_citations",
    }
    _assert_children(
        spans,
        "investigation",
        {"retrieve_runbooks", "generate_hypothesis", "verify_citations"},
    )
    _assert_children(
        spans,
        "retrieve_runbooks",
        {"generate_query_embedding", "query_runbooks"},
    )
    assert (
        spans["investigation"].attributes["resolveai.investigation.status"]
        == "diagnosed"
    )
    assert spans["investigation"].status.status_code is StatusCode.UNSET

    exporter.clear()
    inconclusive_context = get_incident_context("INC-003")
    assert inconclusive_context is not None

    investigation_module.investigate_incident(
        inconclusive_context,
        database_url="postgresql://test",
    )

    spans = _spans_by_name(exporter)
    assert set(spans) == {
        "investigation",
        "retrieve_runbooks",
        "generate_query_embedding",
        "query_runbooks",
        "generate_hypothesis",
    }
    _assert_children(
        spans,
        "investigation",
        {"retrieve_runbooks", "generate_hypothesis"},
    )
    _assert_children(
        spans,
        "retrieve_runbooks",
        {"generate_query_embedding", "query_runbooks"},
    )
    assert (
        spans["investigation"].attributes["resolveai.investigation.status"]
        == "inconclusive"
    )
    assert (
        spans["generate_hypothesis"].attributes["resolveai.reasoning.outcome"]
        == "inconclusive"
    )
    assert spans["generate_hypothesis"].status.status_code is StatusCode.UNSET
    assert spans["investigation"].status.status_code is StatusCode.UNSET

    exporter.clear()

    def fail_retrieval(database_url: str, row_factory) -> None:
        raise ConnectionError("PostgreSQL retrieval failed")

    monkeypatch.setattr(
        retrieval_module.psycopg,
        "connect",
        fail_retrieval,
    )

    with pytest.raises(ConnectionError, match="PostgreSQL retrieval failed"):
        investigation_module.investigate_incident(
            diagnosed_context,
            database_url="postgresql://test",
        )

    spans = _spans_by_name(exporter)
    assert set(spans) == {
        "investigation",
        "retrieve_runbooks",
        "generate_query_embedding",
        "query_runbooks",
    }
    _assert_children(spans, "investigation", {"retrieve_runbooks"})
    _assert_children(
        spans,
        "retrieve_runbooks",
        {"generate_query_embedding", "query_runbooks"},
    )
    assert spans["generate_query_embedding"].status.status_code is StatusCode.UNSET
    assert spans["query_runbooks"].status.status_code is StatusCode.ERROR
    assert spans["retrieve_runbooks"].status.status_code is StatusCode.ERROR
    assert spans["investigation"].status.status_code is StatusCode.ERROR

    provider.shutdown()
