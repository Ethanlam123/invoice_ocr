"""Shared fixtures: tiny PNGs and a FastAPI client wired to the stub backend."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app, get_backend
from app.pipeline import StubPipeline


def png_bytes(width: int = 200, height: int = 150, color=(250, 250, 248)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def client():
    app.dependency_overrides[get_backend] = lambda: StubPipeline()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
