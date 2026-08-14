"""Verify the explicit text-to-ordinary-Python-vector boundary."""

from resolve_ai import embeddings


class _FakeModelVector:
    def __init__(self, values: list[int | float]) -> None:
        self._values = values

    def tolist(self) -> list[int | float]:
        return self._values


class _FakeEmbeddingModel:
    def query_embed(self, queries: list[str]):
        assert queries == ["credential is no longer valid"]
        yield _FakeModelVector([1, 2.5])

    def passage_embed(self, documents: list[str]):
        assert documents == ["first document", "second document"]
        yield _FakeModelVector([3, 4.5])
        yield _FakeModelVector([5, 6.5])


def test_build_runbook_embedding_text_uses_title_and_content() -> None:
    text = embeddings.build_runbook_embedding_text(
        title="Authentication certificate rotation",
        content="Replace an expired certificate.",
    )

    assert text == (
        "Title: Authentication certificate rotation\n\n"
        "Content: Replace an expired certificate."
    )


def test_embedding_generation_returns_ordinary_python_floats(monkeypatch) -> None:
    fake_model = _FakeEmbeddingModel()
    monkeypatch.setattr(embeddings, "_get_embedding_model", lambda: fake_model)

    query_embedding = embeddings.generate_query_embedding(
        "credential is no longer valid"
    )
    document_embeddings = embeddings.generate_document_embeddings(
        ["first document", "second document"]
    )

    assert query_embedding == [1.0, 2.5]
    assert document_embeddings == [[3.0, 4.5], [5.0, 6.5]]
    assert all(type(value) is float for value in query_embedding)
