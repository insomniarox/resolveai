"""Persistent official procedure library, shared across investigations."""

from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, field_validator

from resolve_ai.embeddings import (
    build_runbook_embedding_text,
    generate_document_embeddings,
)
from resolve_ai.retrieval import _format_vector_for_postgres


class RunbookUpload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    service: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=6000)

    @field_validator("title", "service", "content")
    @classmethod
    def reject_null_bytes(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("Runbooks must be text without null bytes")
        return value


class LibraryRunbook(RunbookUpload):
    id: str
    ready: bool


def list_runbooks(database_url: str) -> list[LibraryRunbook]:
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        rows = connection.execute(
            "SELECT id, title, service, content, embedding IS NOT NULL AS ready "
            "FROM runbooks ORDER BY title, id"
        ).fetchall()
    return [LibraryRunbook.model_validate(row) for row in rows]


def upload_runbook(database_url: str, document: RunbookUpload) -> LibraryRunbook:
    # Embed before insertion: a failed embedding never leaves a half-ready upload.
    vectors = generate_document_embeddings(
        [build_runbook_embedding_text(document.title, document.content)]
    )
    if len(vectors) != 1:
        raise ValueError("Expected one runbook embedding")
    vector = _format_vector_for_postgres(vectors[0])
    runbook = LibraryRunbook(
        **document.model_dump(), id=f"UPLOAD-{uuid4()}", ready=True
    )
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO runbooks (id, title, service, content, embedding) "
            "VALUES (%s, %s, %s, %s, %s::vector(384))",
            (runbook.id, runbook.title, runbook.service, runbook.content, vector),
        )
    return runbook
