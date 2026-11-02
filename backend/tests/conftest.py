"""Shared fixtures: tiny PNGs and a FastAPI client wired to the stub backend."""

from __future__ import annotations

import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import config, db
from app.main import app, get_backend
from app.pipeline import StubPipeline


def png_bytes(width: int = 200, height: int = 150, color=(250, 250, 248)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    # persistence off for stub API tests even if the shell exports DATABASE_URL
    monkeypatch.setattr(config, "DATABASE_URL", "")
    db.close_pool()
    app.dependency_overrides[get_backend] = lambda: StubPipeline()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    db.close_pool()


@pytest.fixture
def pg(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """A real Postgres (TEST_DATABASE_URL) with writes isolated to tmp_path.
    Skipped unless the env var is set - SQL round-trips are opt-in."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set; SQL round-trip needs a local Postgres")
    monkeypatch.setattr(config, "DATABASE_URL", url)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    db.close_pool()
    yield
    db.close_pool()


@pytest.fixture
def pg_client(pg, monkeypatch: pytest.MonkeyPatch):
    app.dependency_overrides[get_backend] = lambda: StubPipeline()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def delete_document(doc_id: int) -> None:
    """Test cleanup: remove a document row (cascades) by id."""
    with db.get_pool().connection() as conn:
        conn.execute("DELETE FROM documents WHERE id = %s", (doc_id,))
