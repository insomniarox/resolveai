"""Generate local query and runbook embeddings with one concrete model.

The model boundary is intentionally small and visible. This module turns text
into ordinary Python ``list[float]`` values; PostgreSQL storage and ranking stay
in ``retrieval.py``.
"""

from functools import cache
from typing import Protocol

from fastembed import TextEmbedding

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384


class _ModelVector(Protocol):
    """Describe only the model-array operation needed by this module."""

    def tolist(self) -> list[int | float]: ...


@cache
def _get_embedding_model() -> TextEmbedding:
    """Load the local model once per Python process."""
    return TextEmbedding(model_name=EMBEDDING_MODEL_NAME)


def build_runbook_embedding_text(title: str, content: str) -> str:
    """Create the stable text representation embedded for one runbook."""
    return f"Title: {title}\n\nContent: {content}"


def _ordinary_python_vector(model_vector: _ModelVector) -> list[float]:
    """Convert a model array explicitly into ordinary Python numeric values."""
    values = model_vector.tolist()
    return [float(value) for value in values]


def generate_query_embedding(query: str) -> list[float]:
    """Embed one search query in the model's query representation."""
    model_vector = next(_get_embedding_model().query_embed([query]))
    return _ordinary_python_vector(model_vector)


def generate_document_embeddings(documents: list[str]) -> list[list[float]]:
    """Embed runbook documents in one batch using the passage representation."""
    model_vectors = _get_embedding_model().passage_embed(documents)
    return [_ordinary_python_vector(vector) for vector in model_vectors]
