from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.novel_forge.api import create_app
from tests.conftest import ready_memo


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(tmp_path)
    return TestClient(app)


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_books_empty(client: TestClient):
    r = client.get("/books")
    assert r.status_code == 200
    assert r.json() == []


def test_book_not_found(client: TestClient):
    r = client.get("/books/missing")
    assert r.status_code == 404


def test_chapter_response_no_body(client: TestClient, tmp_path: Path):
    from app.novel_forge.service import NovelForgeService

    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")
    svc.create_chapter("test", 1, "One")
    src = tmp_path / "c1.md"
    src.write_text("正文。\n", encoding="utf-8")
    svc.write_revision("test", 1, src)
    svc.lint_chapter("test", 1)
    ready_memo(svc, "test", 1)
    svc.review_chapter("test", 1)
    svc.approve_chapter("test", 1, "ok")

    r = client.get("/books/test/chapters/1")
    assert r.status_code == 200
    data = r.json()
    assert data["number"] == 1
    assert data["state"] == "approved"
    assert "body" not in data
    assert "canon_facts" in data
    assert "finding_counts" in data
    assert data["finding_counts"] == {
        "blocking": 0,
        "advisory": 0,
        "S1": 0,
        "S2": 0,
        "S3": 0,
        "S4": 0,
    }
    assert data["current_revision"] is not None
    assert "id" in data["current_revision"]
    assert "number" in data["current_revision"]
    assert "hash" in data["current_revision"]
    assert "file_path" in data["current_revision"]


def test_audit_endpoint(client: TestClient, tmp_path: Path):
    from app.novel_forge.service import NovelForgeService

    svc = NovelForgeService(tmp_path)
    svc.init_book("test", "Test Book")

    r = client.get("/books/test/audit")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
