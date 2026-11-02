"""Persistence tests: row mapping always runs; SQL round-trips need
TEST_DATABASE_URL (local Postgres, opt-in)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.images import NormalizedImage

from .conftest import delete_document, png_bytes


def _blocks() -> list[dict]:
    return [
        {
            "id": 1, "order": 1, "label": "table", "bbox": [1.0, 2.0, 3.0, 4.0],
            "content": "<table></table>", "content_html": "<table></table>",
            "page": 0, "page_end": 1,
            "page_bboxes": [
                {"page": 0, "bbox": [1.0, 2.0, 3.0, 4.0]},
                {"page": 1, "bbox": [5.0, 6.0, 7.0, 8.0]},
            ],
        },
        {
            "id": 2, "order": 2, "label": "text", "bbox": [5.0, 6.0, 7.0, 8.0],
            "content": "Total: 99.00", "content_html": None,
            "page": 1, "page_end": 1, "page_bboxes": None,
        },
    ]


def test_block_rows_shape() -> None:
    rows = db.block_rows(7, _blocks())
    assert rows[0]["document_id"] == 7
    assert rows[0]["page_end"] == 1
    assert rows[0]["page_bboxes"].obj == _blocks()[0]["page_bboxes"]  # Json wrapper
    assert rows[1]["page_bboxes"] is None
    assert rows[1]["content_html"] is None


def test_block_rows_defaults_when_page_fields_absent() -> None:
    rows = db.block_rows(1, [{
        "id": 0, "order": 0, "label": "text", "bbox": [0.0, 0.0, 1.0, 1.0],
        "content": "hi", "content_html": None,
    }])
    assert rows[0]["page"] == 0 and rows[0]["page_end"] == 0


def test_save_and_get_document_round_trip(pg) -> None:
    doc_id = db.save_document(db.NewDocument(
        filename="inv.png", mime="image/png", elapsed_ms=42, model="stub", mode="stub",
        pages=[NormalizedImage(png=png_bytes(120, 90), width=120, height=90)],
        blocks=_blocks(), markdown="# hi", raw={"res": {"x": 1}},
    ))
    try:
        got = db.get_document(doc_id)
        assert got is not None
        assert got["pages"][0]["width"] == 120
        assert got["pages"][0]["data_url"].startswith("data:image/png;base64,")
        assert got["blocks"][0]["bbox"] == [1.0, 2.0, 3.0, 4.0]
        assert [pb["page"] for pb in got["blocks"][0]["page_bboxes"]] == [0, 1]
        assert got["blocks"][1]["page"] == 1
        assert got["markdown"] == "# hi"
        assert got["raw"] == {"res": {"x": 1}}  # jsonb round-trips the dict
        assert got["meta"]["doc_type"] == "unknown"
        assert got["meta"]["quality_flags"] == []
        assert any(d["id"] == doc_id for d in db.list_documents())
    finally:
        delete_document(doc_id)


def test_get_document_missing_returns_none(pg) -> None:
    assert db.get_document(999_999) is None


def test_save_failure_cleans_up_files(pg, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(db, "block_rows", boom)
    with pytest.raises(RuntimeError):
        db.save_document(db.NewDocument(
            filename="x.png", mime="image/png", elapsed_ms=1, model="stub", mode="stub",
            pages=[NormalizedImage(png=png_bytes(60, 60), width=60, height=60)],
            blocks=_blocks(), markdown="", raw={},
        ))
    # tx rolled back and the document dir was removed (the parent may remain)
    docs_dir = config.DATA_DIR / "documents"
    assert not docs_dir.exists() or not any(docs_dir.iterdir())


def test_ocr_persists_and_history_round_trip(pg_client: TestClient) -> None:
    r = pg_client.post(
        "/api/ocr", files={"file": ("inv.png", png_bytes(200, 150), "image/png")}
    )
    doc_id = r.json()["meta"]["document_id"]
    try:
        listed = pg_client.get("/api/documents").json()
        assert listed["success"] is True
        entry = next(d for d in listed["data"]["documents"] if d["id"] == doc_id)
        assert entry["filename"] == "inv.png"
        assert entry["doc_type"] == "invoice"  # stub title is "INVOICE" -> rules fire

        detail = pg_client.get(f"/api/documents/{doc_id}").json()
        assert detail["success"] is True
        assert len(detail["data"]["blocks"]) == 3  # stub emits 3 blocks
        assert detail["data"]["pages"][0]["data_url"].startswith("data:image/png;base64,")
        assert detail["meta"]["mode"] == "stub"
    finally:
        delete_document(doc_id)


def test_get_document_endpoint_404(pg_client: TestClient) -> None:
    body = pg_client.get("/api/documents/999999").json()
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"


def test_correct_block_round_trip(pg_client: TestClient) -> None:
    r = pg_client.post(
        "/api/ocr", files={"file": ("inv.png", png_bytes(200, 150), "image/png")}
    )
    doc_id = r.json()["meta"]["document_id"]
    try:
        before = pg_client.get(f"/api/documents/{doc_id}").json()
        assert all(b["reviewed"] is False for b in before["data"]["blocks"])

        fix = pg_client.patch(
            f"/api/documents/{doc_id}/blocks/2",
            json={"corrected_content": "Thank you (corrected)."},
        )
        assert fix.status_code == 200 and fix.json()["success"] is True

        after = pg_client.get(f"/api/documents/{doc_id}").json()
        block = next(b for b in after["data"]["blocks"] if b["id"] == 2)
        assert block["content"] == "Thank you (corrected)."
        assert block["reviewed"] is True
        others = [b for b in after["data"]["blocks"] if b["id"] != 2]
        assert all(b["reviewed"] is False for b in others)
    finally:
        delete_document(doc_id)


def test_correct_block_rejects_empty_and_missing(pg_client: TestClient) -> None:
    empty = pg_client.patch("/api/documents/1/blocks/0", json={"corrected_content": "  "})
    assert empty.status_code == 400
    missing = pg_client.patch(
        "/api/documents/999999/blocks/0", json={"corrected_content": "x"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
