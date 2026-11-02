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


def _pdf_bytes(pages: list[tuple[int, int]]) -> bytes:
    """Small multi-page PDF from PIL images (page renders back to pixel size)."""
    imgs = [Image.new("RGB", size, "white") for size in pages]
    buf = io.BytesIO()
    imgs[0].save(buf, save_all=True, append_images=imgs[1:], format="PDF", resolution=150)
    return buf.getvalue()


def test_ocr_success_envelope(client: TestClient) -> None:
    r = _post(client, png_bytes(200, 150))
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True and body["error"] is None
    data = body["data"]
    assert len(data["pages"]) == 1
    assert data["pages"][0]["width"] == 200 and data["pages"][0]["height"] == 150
    assert data["pages"][0]["data_url"].startswith("data:image/png;base64,")
    assert [b["id"] for b in data["blocks"]] == [0, 1, 2]
    assert data["blocks"][1]["content_html"].startswith("<table")
    assert all(b["page"] == 0 for b in data["blocks"])
    assert body["meta"]["mode"] == "stub" and body["meta"]["page_count"] == 1
    assert isinstance(data["raw"], dict)  # raw pipeline JSON for download


def test_pdf_two_pages_envelope_and_merge_span(client: TestClient) -> None:
    r = _post(client, _pdf_bytes([(300, 400), (300, 400)]), filename="a.pdf",
              mime="application/pdf")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data["pages"]) == 2
    for i, p in enumerate(data["pages"]):
        assert p["index"] == i and p["width"] == 300 and p["height"] == 400
        assert p["data_url"].startswith("data:image/png;base64,")
    assert r.json()["meta"]["page_count"] == 2
    # stub mirrors the engine merge: page-0 table owns the HTML, page-1
    # fragment is group-linked and must not be emitted as its own block
    blocks = {b["id"]: b for b in data["blocks"]}
    assert blocks[1]["page"] == 0 and blocks[1]["page_end"] == 1
    assert [pb["page"] for pb in blocks[1]["page_bboxes"]] == [0, 1]
    assert blocks[1]["content_html"].startswith("<table")
    assert blocks[10 + 1]["page"] == 1  # trailing text block on page 2
    assert all(b["content"] != "" for b in data["blocks"])
    assert "input_path" not in str(data["raw"])


def test_pdf_rejects_too_many_pages(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setattr(config, "MAX_PDF_PAGES", 2)
    r = _post(client, _pdf_bytes([(100, 100)] * 3), filename="a.pdf", mime="application/pdf")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "too_many_pages"


def test_pdf_rejects_corrupt_pdf(client: TestClient) -> None:
    r = _post(client, b"%PDF-1.4 garbage", filename="a.pdf", mime="application/pdf")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "undecodable"


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


def test_ocr_malformed_pipeline_output_returns_envelope(client: TestClient) -> None:
    class Malformed:
        async def run(self, png: bytes) -> dict:
            # block_bbox missing: normalization must fail visibly, not crash to
            # FastAPI's default 500 body
            return {"parsing_res_list": [{"block_id": 0, "block_label": "text"}]}

    app.dependency_overrides[get_backend] = lambda: Malformed()
    r = _post(client, png_bytes(200, 150))
    assert r.status_code == 500
    body = r.json()
    assert body["success"] is False and body["data"] is None
    assert body["error"]["code"] == "normalization_failed"


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    meta = r.json()["meta"]
    assert meta["backend"] == "ok" and meta["mode"] == "stub"


def test_history_endpoints_disabled_without_database(client: TestClient) -> None:
    for path in ("/api/documents", "/api/documents/1"):
        body = client.get(path).json()
        assert body["success"] is False
        assert body["error"]["code"] == "persistence_disabled"


def test_ocr_meta_has_no_document_id_without_database(client: TestClient) -> None:
    r = _post(client, png_bytes(200, 150))
    meta = r.json()["meta"]
    assert "document_id" not in meta
    assert "persistence" not in meta


def test_ocr_meta_carries_classification_and_extraction(client: TestClient) -> None:
    r = _post(client, _pdf_bytes([(300, 400), (300, 400)]), filename="a.pdf",
              mime="application/pdf")
    meta = r.json()["meta"]
    assert meta["doc_type"] == "invoice"  # stub title is "INVOICE"
    # stub page-2 text block "Total: 99.00" is extractable
    assert meta["extracted"]["total"]["value"] == 99.0
    assert meta["quality_flags"] == []
