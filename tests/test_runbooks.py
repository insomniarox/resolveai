"""Official library validation, embedding failures and persistent upload contracts."""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from resolve_ai import api, runbooks
from resolve_ai.runbooks import LibraryRunbook, RunbookUpload

ADMIN_TOKEN = "a" * 64
RUNBOOK = {"title": "Guide", "service": "svc", "content": "Check logs"}


@pytest.mark.parametrize(
    "fields",
    [
        {"title": " ", "service": "svc", "content": "procedure"},
        {"title": "Guide", "service": "svc", "content": "x" * 6001},
        {"title": "Guide", "service": "svc", "content": ""},
        {"title": "Guide", "service": "svc", "content": "bad\x00text"},
    ],
)
def test_invalid_upload_never_reaches_storage(monkeypatch, fields):
    monkeypatch.setenv("RUNBOOK_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setattr(
        api, "upload_runbook", lambda *a: pytest.fail("unexpected write")
    )
    assert (
        TestClient(api.app)
        .post(
            "/runbooks", json=fields, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        .status_code
        == 422
    )


def test_library_and_upload_api(monkeypatch):
    monkeypatch.setenv("RUNBOOK_ADMIN_TOKEN", ADMIN_TOKEN)
    stored = LibraryRunbook(
        id="UPLOAD-1", title="Guide", service="svc", content="Check logs", ready=True
    )
    monkeypatch.setattr(api, "_get_database_url", lambda: "db")
    monkeypatch.setattr(api, "list_runbooks", lambda db: [stored])
    monkeypatch.setattr(api, "upload_runbook", lambda db, doc: stored)
    client = TestClient(api.app)
    assert client.get("/runbooks").json() == [stored.model_dump()]
    response = client.post(
        "/runbooks", json=RUNBOOK, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    )
    assert response.status_code == 201
    assert response.json() == stored.model_dump()
    assert ADMIN_TOKEN not in response.text


def test_library_read_needs_no_admin_token(monkeypatch):
    monkeypatch.delenv("RUNBOOK_ADMIN_TOKEN", raising=False)
    stored = LibraryRunbook(
        id="RUN-001", title="Guide", service="svc", content="Check logs", ready=True
    )
    monkeypatch.setattr(api, "_get_database_url", lambda: "db")
    monkeypatch.setattr(api, "list_runbooks", lambda db: [stored])
    response = TestClient(api.app).get("/runbooks")
    assert response.status_code == 200
    assert response.json() == [stored.model_dump()]


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer wrong", "Basic abc", "Bearer " + "b" * 64],
)
def test_upload_requires_valid_admin_token(monkeypatch, authorization):
    monkeypatch.setenv("RUNBOOK_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setattr(
        api, "_get_database_url", lambda: pytest.fail("unexpected database access")
    )
    monkeypatch.setattr(
        api, "upload_runbook", lambda *a: pytest.fail("unexpected write")
    )
    headers = {"Authorization": authorization} if authorization else {}
    response = TestClient(api.app).post("/runbooks", json=RUNBOOK, headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert ADMIN_TOKEN not in response.text


@pytest.mark.parametrize("configured", [None, "too-short"])
def test_upload_fails_closed_without_configured_secret(monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("RUNBOOK_ADMIN_TOKEN", raising=False)
    else:
        monkeypatch.setenv("RUNBOOK_ADMIN_TOKEN", configured)
    monkeypatch.setattr(
        api, "_get_database_url", lambda: pytest.fail("unexpected database access")
    )
    monkeypatch.setattr(
        api, "upload_runbook", lambda *a: pytest.fail("unexpected write")
    )
    response = TestClient(api.app).post(
        "/runbooks", json=RUNBOOK, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    )
    assert response.status_code == 503
    assert "not configured" in response.text


def test_embedding_failure_does_not_connect_or_write(monkeypatch):
    monkeypatch.setattr(runbooks, "generate_document_embeddings", lambda _: [[0.0]])
    monkeypatch.setattr(
        runbooks.psycopg,
        "connect",
        lambda *a, **k: pytest.fail("unexpected connection"),
    )
    with pytest.raises(ValueError, match="384"):
        runbooks.upload_runbook(
            "db", RunbookUpload(title="Guide", service="svc", content="Check logs")
        )


def test_upload_embeds_title_and_content_before_parameterized_insert(monkeypatch):
    calls = []
    monkeypatch.setattr(
        runbooks,
        "generate_document_embeddings",
        lambda texts: calls.append(texts) or [[0.0] * 384],
    )

    class Connection:
        def execute(self, sql, params):
            calls.append((sql, params))

    @contextmanager
    def connect(*args):
        yield Connection()

    monkeypatch.setattr(runbooks.psycopg, "connect", connect)
    result = runbooks.upload_runbook(
        "db", RunbookUpload(title="Owner's guide", service="svc", content="Check logs")
    )
    assert "Owner's guide" in calls[0][0]
    assert "Check logs" in calls[0][0]
    sql, params = calls[1]
    assert "Owner's guide" not in sql
    assert params[:4] == (result.id, "Owner's guide", "svc", "Check logs")
    assert result.ready


def test_library_failure_is_safe(monkeypatch):
    monkeypatch.setattr(api, "_get_database_url", lambda: "db")

    def fail(*args):
        raise RuntimeError("private database configuration")

    monkeypatch.setattr(api, "list_runbooks", fail)
    response = TestClient(api.app).get("/runbooks")
    assert response.status_code == 503
    assert "private" not in response.text
