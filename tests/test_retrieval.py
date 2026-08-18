"""Exercise lexical retrieval inputs and the real PostgreSQL boundary."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from resolve_ai import retrieval
from resolve_ai.models import KnowledgeDocument
from resolve_ai.retrieval import (
    RuntimeKnowledgeError,
    delete_runtime_knowledge_scope,
    populate_runbook_embeddings,
    search_runbooks,
    semantic_search_runbooks,
    semantic_search_runtime_knowledge_documents,
    store_runtime_knowledge_documents,
)


@pytest.mark.parametrize(
    ("database_url", "query", "limit", "expected_message"),
    [
        ("", "timeout", 1, "database_url must not be empty"),
        ("postgresql://not-used", " ", 1, "query must not be empty"),
        ("postgresql://not-used", "timeout", 0, "limit must be greater than zero"),
    ],
)
def test_search_runbooks_rejects_invalid_inputs(
    database_url: str,
    query: str,
    limit: int,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        search_runbooks(database_url=database_url, query=query, limit=limit)


@pytest.mark.parametrize(
    ("database_url", "query", "limit", "expected_message"),
    [
        ("", "timeout", 1, "database_url must not be empty"),
        ("postgresql://not-used", " ", 1, "query must not be empty"),
        ("postgresql://not-used", "timeout", 0, "limit must be greater than zero"),
    ],
)
def test_semantic_search_runbooks_rejects_inputs_before_embedding(
    database_url: str,
    query: str,
    limit: int,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError, match=expected_message):
        semantic_search_runbooks(
            database_url=database_url,
            query=query,
            limit=limit,
        )


def test_vector_parameter_contains_explicit_python_numeric_values() -> None:
    embedding = [0.0] * 384
    embedding[0] = 0.25
    embedding[1] = -1.5

    parameter = retrieval._format_vector_for_postgres(embedding)

    assert parameter.startswith("[0.25,-1.5,0.0")
    assert parameter.endswith("]")
    assert parameter.count(",") == 383


def test_vector_parameter_rejects_wrong_dimensions_and_non_finite_values() -> None:
    with pytest.raises(ValueError, match="384 numeric values"):
        retrieval._format_vector_for_postgres([0.0])

    embedding = [0.0] * 384
    embedding[0] = float("nan")
    with pytest.raises(ValueError, match="must be finite"):
        retrieval._format_vector_for_postgres(embedding)


def test_runtime_document_embedding_failure_happens_before_connecting(
    monkeypatch,
) -> None:
    document = KnowledgeDocument(
        id="DOC-901",
        title="Runtime guide",
        content_type="text/plain",
        content="Bounded reference content.",
    )
    calls: list[str] = []
    monkeypatch.setattr(
        retrieval,
        "generate_document_embeddings",
        lambda documents: (_ for _ in ()).throw(RuntimeError("embedding failed")),
    )
    monkeypatch.setattr(
        retrieval.psycopg,
        "connect",
        lambda database_url: calls.append(database_url),
    )

    with pytest.raises(RuntimeKnowledgeError, match="could not be stored"):
        store_runtime_knowledge_documents(
            database_url="postgresql://not-used",
            scope_id=uuid4(),
            documents=[document],
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )

    assert calls == []


@pytest.mark.integration
def test_connection_pool_query_ranks_lexical_matches_by_weight() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    initialization_sql = (
        Path(__file__).parents[1] / "database" / "init.sql"
    ).read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        connection.execute(initialization_sql)

    # RUN-001 matches the phrase and timeout in its A-weighted title. RUN-003 is
    # intentionally unrelated to connection pools and matches only timeout in its
    # B-weighted body, so this assertion tests PostgreSQL's lexical score.
    results = search_runbooks(
        database_url=database_url,
        query='"connection pool" OR timeout',
        limit=3,
    )

    assert [result.id for result in results] == ["RUN-001", "RUN-003"]
    assert results[0].rank_score > results[1].rank_score
    assert results[0].service == "payment-service"


@pytest.mark.integration
def test_semantic_query_respects_limit_and_similarity_order() -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    initialization_sql = (
        Path(__file__).parents[1] / "database" / "init.sql"
    ).read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        connection.execute(initialization_sql)
        # Force this test to exercise document generation and persistence even
        # when the developer database was populated by an earlier command.
        connection.execute("UPDATE runbooks SET embedding = NULL")

    assert populate_runbook_embeddings(database_url) == 9

    results = semantic_search_runbooks(
        database_url=database_url,
        query="requests wait for a reusable database session",
        limit=3,
    )

    assert len(results) == 3
    corpus_ids = {f"RUN-{number:03}" for number in range(1, 10)}
    assert all(result.id in corpus_ids for result in results)
    assert [result.similarity_score for result in results] == sorted(
        (result.similarity_score for result in results),
        reverse=True,
    )


@pytest.mark.integration
def test_runtime_knowledge_is_atomic_scoped_and_deletable(monkeypatch) -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")

    initialization_sql = (
        Path(__file__).parents[1] / "database" / "init.sql"
    ).read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        connection.execute(initialization_sql)

    first_scope = uuid4()
    second_scope = uuid4()
    documents = [
        KnowledgeDocument(
            id="DOC-901",
            title="Invoice receipt lifecycle",
            content_type="text/markdown",
            content="Receipt callbacks complete pending invoices.",
        )
    ]
    document_vector = [0.0] * 384
    document_vector[0] = 1.0
    monkeypatch.setattr(
        retrieval,
        "generate_document_embeddings",
        lambda texts: [document_vector for _ in texts],
    )
    monkeypatch.setattr(
        retrieval,
        "generate_query_embedding",
        lambda query: document_vector,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=15)

    assert (
        store_runtime_knowledge_documents(
            database_url,
            first_scope,
            documents,
            expires_at,
        )
        == 1
    )
    assert (
        store_runtime_knowledge_documents(
            database_url,
            second_scope,
            [documents[0].model_copy(update={"id": "DOC-902"})],
            expires_at,
        )
        == 1
    )

    rollback_scope = uuid4()
    duplicate_documents = [
        documents[0].model_copy(update={"id": "DOC-DUPLICATE"}),
        documents[0].model_copy(update={"id": "DOC-DUPLICATE"}),
    ]
    with pytest.raises(RuntimeKnowledgeError, match="could not be stored"):
        store_runtime_knowledge_documents(
            database_url,
            rollback_scope,
            duplicate_documents,
            expires_at,
        )
    with psycopg.connect(database_url) as connection:
        rollback_count = connection.execute(
            """
            SELECT count(*)
            FROM runtime_knowledge_documents
            WHERE scope_id = %s
            """,
            (rollback_scope,),
        ).fetchone()
    assert rollback_count == (0,)

    first_results = semantic_search_runtime_knowledge_documents(
        database_url,
        first_scope,
        "pending invoice receipt",
        3,
    )
    assert [result.id for result in first_results] == ["DOC-901"]
    assert delete_runtime_knowledge_scope(database_url, first_scope) == 1
    assert (
        semantic_search_runtime_knowledge_documents(
            database_url,
            first_scope,
            "pending invoice receipt",
            3,
        )
        == []
    )
    second_results = semantic_search_runtime_knowledge_documents(
        database_url,
        second_scope,
        "pending invoice receipt",
        3,
    )
    assert [result.id for result in second_results] == ["DOC-902"]
    assert delete_runtime_knowledge_scope(database_url, second_scope) == 1
