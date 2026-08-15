"""Exercise lexical retrieval inputs and the real PostgreSQL boundary."""

import os
from pathlib import Path

import psycopg
import pytest

from resolve_ai import retrieval
from resolve_ai.retrieval import (
    populate_runbook_embeddings,
    search_runbooks,
    semantic_search_runbooks,
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
