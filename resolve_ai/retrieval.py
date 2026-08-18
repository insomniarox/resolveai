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
from datetime import datetime
from uuid import UUID

import psycopg
from opentelemetry import trace
from psycopg.rows import dict_row
from pydantic import BaseModel

from resolve_ai.embeddings import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL_NAME,
    build_document_embedding_text,
    build_runbook_embedding_text,
    generate_document_embeddings,
    generate_query_embedding,
)
from resolve_ai.models import (
    KnowledgeDocument,
    RetrievedKnowledgeDocument,
    RetrievedRunbook,
)

tracer = trace.get_tracer(__name__)


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

_DELETE_EXPIRED_RUNTIME_KNOWLEDGE_SQL = """
DELETE FROM runtime_knowledge_documents
WHERE expires_at <= now()
"""

_INSERT_RUNTIME_KNOWLEDGE_SQL = """
INSERT INTO runtime_knowledge_documents (
    scope_id,
    document_id,
    title,
    content_type,
    content,
    embedding,
    expires_at
)
VALUES (%s, %s, %s, %s, %s, %s::vector(384), %s)
"""

_SEARCH_RUNTIME_KNOWLEDGE_SEMANTIC_SQL = """
WITH query_embedding AS (
    SELECT %s::vector(384) AS value
)
SELECT
    runtime_knowledge_documents.document_id AS id,
    runtime_knowledge_documents.title,
    runtime_knowledge_documents.content_type,
    runtime_knowledge_documents.content,
    1 - (
        runtime_knowledge_documents.embedding <=> query_embedding.value
    ) AS similarity_score
FROM runtime_knowledge_documents
CROSS JOIN query_embedding
WHERE runtime_knowledge_documents.scope_id = %s
    AND runtime_knowledge_documents.expires_at > now()
ORDER BY
    runtime_knowledge_documents.embedding <=> query_embedding.value ASC,
    runtime_knowledge_documents.document_id ASC
LIMIT %s
"""

_DELETE_RUNTIME_KNOWLEDGE_SCOPE_SQL = """
DELETE FROM runtime_knowledge_documents
WHERE scope_id = %s
"""


class RuntimeKnowledgeError(Exception):
    """Report a failed runtime document storage or retrieval operation."""


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

    with tracer.start_as_current_span(
        "generate_query_embedding",
        attributes={"resolveai.embedding.model": EMBEDDING_MODEL_NAME},
    ) as embedding_span:
        query_embedding = generate_query_embedding(query)
        embedding_span.set_attribute(
            "resolveai.embedding.vector_dimensions",
            len(query_embedding),
        )

    query_vector_parameter = _format_vector_for_postgres(query_embedding)

    with tracer.start_as_current_span("query_runbooks") as query_span:
        with psycopg.connect(database_url, row_factory=dict_row) as connection:
            rows = connection.execute(
                _SEARCH_RUNBOOKS_SEMANTIC_SQL,
                (query_vector_parameter, limit),
            ).fetchall()

        results = [RetrievedRunbook.model_validate(row) for row in rows]
        query_span.set_attribute(
            "resolveai.retrieval.result_count",
            len(results),
        )

    return results


def store_runtime_knowledge_documents(
    database_url: str,
    scope_id: UUID,
    documents: list[KnowledgeDocument],
    expires_at: datetime,
) -> int:
    """Embed and atomically store one complete request-scoped document set.

    Every vector is generated and validated before PostgreSQL sees an INSERT.
    The connection context then commits all rows together or rolls them all back.
    """
    if not database_url.strip():
        raise ValueError("database_url must not be empty")
    if not documents:
        raise ValueError("documents must not be empty")
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("expires_at must include a UTC offset")

    embedding_texts = [
        build_document_embedding_text(document.title, document.content)
        for document in documents
    ]
    try:
        document_embeddings = generate_document_embeddings(embedding_texts)
        rows = [
            (
                scope_id,
                document.id,
                document.title,
                document.content_type,
                document.content,
                _format_vector_for_postgres(embedding),
                expires_at,
            )
            for document, embedding in zip(
                documents,
                document_embeddings,
                strict=True,
            )
        ]

        with psycopg.connect(database_url) as connection:
            connection.execute(_DELETE_EXPIRED_RUNTIME_KNOWLEDGE_SQL)
            with connection.cursor() as cursor:
                cursor.executemany(_INSERT_RUNTIME_KNOWLEDGE_SQL, rows)
    except (psycopg.Error, RuntimeError, ValueError) as error:
        raise RuntimeKnowledgeError(
            "runtime knowledge documents could not be stored"
        ) from error

    return len(rows)


def semantic_search_runtime_knowledge_documents(
    database_url: str,
    scope_id: UUID,
    query: str,
    limit: int,
) -> list[RetrievedKnowledgeDocument]:
    """Return semantic matches only from one unexpired runtime scope."""
    _validate_search_inputs(database_url, query, limit)

    try:
        with tracer.start_as_current_span(
            "generate_runtime_knowledge_query_embedding",
            attributes={"resolveai.embedding.model": EMBEDDING_MODEL_NAME},
        ) as embedding_span:
            query_embedding = generate_query_embedding(query)
            embedding_span.set_attribute(
                "resolveai.embedding.vector_dimensions",
                len(query_embedding),
            )

        query_vector_parameter = _format_vector_for_postgres(query_embedding)
        with tracer.start_as_current_span("query_runtime_knowledge") as query_span:
            with psycopg.connect(
                database_url,
                row_factory=dict_row,
            ) as connection:
                rows = connection.execute(
                    _SEARCH_RUNTIME_KNOWLEDGE_SEMANTIC_SQL,
                    (query_vector_parameter, scope_id, limit),
                ).fetchall()

            results = [RetrievedKnowledgeDocument.model_validate(row) for row in rows]
            query_span.set_attribute(
                "resolveai.retrieval.result_count",
                len(results),
            )
    except (psycopg.Error, RuntimeError, ValueError) as error:
        raise RuntimeKnowledgeError(
            "runtime knowledge documents could not be retrieved"
        ) from error

    return results


def delete_runtime_knowledge_scope(database_url: str, scope_id: UUID) -> int:
    """Delete every document owned by one server-generated request scope."""
    if not database_url.strip():
        raise ValueError("database_url must not be empty")

    try:
        with psycopg.connect(database_url) as connection:
            cursor = connection.execute(
                _DELETE_RUNTIME_KNOWLEDGE_SCOPE_SQL,
                (scope_id,),
            )
            deleted = cursor.rowcount
    except psycopg.Error as error:
        raise RuntimeKnowledgeError(
            "runtime knowledge scope could not be deleted"
        ) from error

    return deleted


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
