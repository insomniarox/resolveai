"""Search the synthetic runbook corpus with PostgreSQL retrieval operations.

Phase 2 starts with one visible lexical retrieval operation. PostgreSQL performs
tokenization, matching, and ranking; this module supplies the parameterized SQL
and converts database rows into structured application results.

Semantic retrieval remains a separate operation beside lexical retrieval. Its
flow is explicit: query text becomes a Python embedding, that vector is passed
to parameterized pgvector SQL, and PostgreSQL returns cosine-ranked runbooks.

Lexical and semantic ranking remain independently callable and measurable. The
investigation workflow consumes semantic results as reference knowledge, but
retrieval does not perform diagnosis. There is no generic retriever abstraction
because only this concrete implementation exists today.
"""

import math

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from resolve_ai.embeddings import (
    EMBEDDING_DIMENSIONS,
    build_runbook_embedding_text,
    generate_document_embeddings,
    generate_query_embedding,
)
from resolve_ai.models import RetrievedRunbook


class RunbookSearchResult(BaseModel):
    """Represent one runbook and its relevance score for a particular query."""

    id: str
    title: str
    service: str
    content: str
    rank_score: float


_SEARCH_RUNBOOKS_SQL = """
WITH search_query AS (
    SELECT websearch_to_tsquery('english', %s) AS value
)
SELECT
    runbooks.id,
    runbooks.title,
    runbooks.service,
    runbooks.content,
    ts_rank(runbooks.search_vector, search_query.value) AS rank_score
FROM runbooks
CROSS JOIN search_query
WHERE runbooks.search_vector @@ search_query.value
ORDER BY rank_score DESC, runbooks.id ASC
LIMIT %s
"""

_SEARCH_RUNBOOKS_SEMANTIC_SQL = """
WITH query_embedding AS (
    SELECT %s::vector(384) AS value
)
SELECT
    runbooks.id,
    runbooks.title,
    runbooks.service,
    runbooks.content,
    1 - (runbooks.embedding <=> query_embedding.value) AS similarity_score
FROM runbooks
CROSS JOIN query_embedding
WHERE runbooks.embedding IS NOT NULL
ORDER BY runbooks.embedding <=> query_embedding.value ASC, runbooks.id ASC
LIMIT %s
"""

_SELECT_RUNBOOKS_WITHOUT_EMBEDDINGS_SQL = """
SELECT id, title, content
FROM runbooks
WHERE embedding IS NULL
ORDER BY id ASC
"""

_UPDATE_RUNBOOK_EMBEDDING_SQL = """
UPDATE runbooks
SET embedding = %s::vector(384)
WHERE id = %s
"""

_COUNT_RUNBOOKS_WITHOUT_EMBEDDINGS_SQL = """
SELECT count(*)
FROM runbooks
WHERE embedding IS NULL
"""


def _validate_search_inputs(database_url: str, query: str, limit: int) -> None:
    """Validate inputs shared by the two concrete search operations."""
    if not database_url.strip():
        raise ValueError("database_url must not be empty")
    if not query.strip():
        raise ValueError("query must not be empty")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")


def _format_vector_for_postgres(vector: list[float]) -> str:
    """Serialize ordinary finite Python values for a parameterized vector cast."""
    if len(vector) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"embedding must contain {EMBEDDING_DIMENSIONS} numeric values"
        )
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("embedding values must be finite")
    return "[" + ",".join(repr(value) for value in vector) + "]"


def search_runbooks(
    database_url: str,
    query: str,
    limit: int,
) -> list[RunbookSearchResult]:
    """Return runbooks ordered by PostgreSQL lexical relevance.

    The database URL is explicit because PostgreSQL is a required input to this
    operation, just like the query and result limit. Callers remain responsible
    for choosing which database the read should use.
    """
    _validate_search_inputs(database_url, query, limit)

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(_SEARCH_RUNBOOKS_SQL, (query, limit)).fetchall()

    return [RunbookSearchResult.model_validate(row) for row in rows]


def semantic_search_runbooks(
    database_url: str,
    query: str,
    limit: int,
) -> list[RetrievedRunbook]:
    """Embed a query, then return runbooks ordered by pgvector similarity.

    The two operations are kept as separate statements so the boundary remains
    visible: the embedding model produces ordinary Python numbers first, then
    PostgreSQL receives their parameterized vector representation for ranking.
    """
    _validate_search_inputs(database_url, query, limit)

    query_embedding = generate_query_embedding(query)
    query_vector_parameter = _format_vector_for_postgres(query_embedding)

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            _SEARCH_RUNBOOKS_SEMANTIC_SQL,
            (query_vector_parameter, limit),
        ).fetchall()

    return [RetrievedRunbook.model_validate(row) for row in rows]


def populate_runbook_embeddings(database_url: str) -> int:
    """Generate and store embeddings only for runbooks that need one."""
    if not database_url.strip():
        raise ValueError("database_url must not be empty")

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(_SELECT_RUNBOOKS_WITHOUT_EMBEDDINGS_SQL).fetchall()
        if not rows:
            return 0

        documents = [
            build_runbook_embedding_text(row["title"], row["content"]) for row in rows
        ]
        document_embeddings = generate_document_embeddings(documents)
        updates = [
            (_format_vector_for_postgres(embedding), row["id"])
            for row, embedding in zip(rows, document_embeddings, strict=True)
        ]

        with connection.cursor() as cursor:
            cursor.executemany(_UPDATE_RUNBOOK_EMBEDDING_SQL, updates)

    return len(rows)


def count_runbooks_without_embeddings(database_url: str) -> int:
    """Return the number of corpus rows not ready for semantic evaluation."""
    if not database_url.strip():
        raise ValueError("database_url must not be empty")

    with psycopg.connect(database_url) as connection:
        row = connection.execute(_COUNT_RUNBOOKS_WITHOUT_EMBEDDINGS_SQL).fetchone()

    if row is None:
        raise RuntimeError("embedding count query returned no row")
    return int(row[0])
