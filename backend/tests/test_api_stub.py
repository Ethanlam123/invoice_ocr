"""API tests against the stub backend - no model involved (see scripts/run_real_inference.py
for the live-model check)."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app, get_backend
from app.pipeline import InferenceError

from .conftest import png_bytes


def _post(client: TestClient, content: bytes, filename: str = "a.png", mime: str = "image/png"):
    return client.post("/api/ocr", files={"file": (filename, content, mime)})


def test_ocr_success_envelope(client: TestClient) -> None:
    r = _post(client, png_bytes(200, 150))
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True and body["error"] is None
    data = body["data"]
    assert data["image"]["width"] == 200 and data["image"]["height"] == 150
    assert data["image"]["data_url"].startswith("data:image/png;base64,")
    assert [b["id"] for b in data["blocks"]] == [0, 1, 2]
    assert data["blocks"][1]["content_html"].startswith("<table")
    assert body["meta"]["mode"] == "stub"
    assert isinstance(data["raw"], dict)  # raw pipeline JSON for download


def test_ocr_rejects_undecodable(client: TestClient) -> None:
    r = _post(client, b"\x00\x01not-an-image")
    assert r.status_code == 400
    body = r.json()
    assert body["success"] is False and body["data"] is None
    assert body["error"]["code"] == "undecodable"


def test_ocr_rejects_gif(client: TestClient) -> None:
    buf = io.BytesIO()
    Image.new("RGB", (120, 120)).save(buf, format="GIF")
    r = _post(client, buf.getvalue(), filename="a.gif", mime="image/gif")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "unsupported_format"


def test_ocr_rejects_oversize(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setattr(config, "MAX_FILE_BYTES", 16)
    r = _post(client, png_bytes(200, 150))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"


def test_ocr_rejects_oversized_stream_before_buffering(client: TestClient) -> None:
    # 11 MB garbage: must hit the running byte cap, not be buffered and decoded
    r = _post(client, b"\x89PNG" + b"x" * (11 * 1024 * 1024))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"


def test_ocr_response_strips_internal_temp_path(client: TestClient) -> None:
    r = _post(client, png_bytes(200, 150))
    raw = r.json()["data"]["raw"]
    assert "input_path" not in raw
    assert "parsing_res_list" in raw


def test_ocr_missing_file_field_returns_envelope(client: TestClient) -> None:
    r = client.post("/api/ocr")
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "invalid_request"


def test_ocr_inference_failure_is_visible(client: TestClient) -> None:
    class Broken:
        async def run(self, png: bytes) -> dict:
            raise InferenceError("inference_failed", "boom")

    app.dependency_overrides[get_backend] = lambda: Broken()
    r = _post(client, png_bytes(200, 150))
    assert r.status_code == 500
    body = r.json()
    assert body["success"] is False and body["data"] is None
    assert body["error"]["code"] == "inference_failed"


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    meta = r.json()["meta"]
    assert meta["backend"] == "ok" and meta["mode"] == "stub"
