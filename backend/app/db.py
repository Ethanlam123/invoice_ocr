"""Postgres persistence: one writer (OCR result -> three tables) + two readers.

No ORM by decision: the whole path is four fixed statements and the pipeline
already yields dicts (see README "Why no ORM"). DATABASE_URL unset ->
persistence off and the app stays stateless (unit tests, quick demo).
"""

from __future__ import annotations

import base64
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from . import config
from .images import NormalizedImage

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_pool: ConnectionPool | None = None


@dataclass(frozen=True)
class NewDocument:
    """Everything a successful OCR run persists."""

    filename: str
    mime: str
    elapsed_ms: int
    model: str
    mode: str
    pages: list[NormalizedImage]
    blocks: list[dict[str, Any]]  # BlockOut-shaped dicts
    markdown: str
    raw: dict[str, Any]
    doc_type: str = "unknown"
    quality_flags: list[str] | None = None
    extracted: dict[str, Any] | None = None


def persistence_enabled() -> bool:
    return bool(config.DATABASE_URL)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=4, open=True)
        with _pool.connection() as conn:  # block exit commits the idempotent DDL
            conn.execute(SCHEMA_PATH.read_text())
    return _pool


def close_pool() -> None:
    """Drop the cached pool so the next get_pool re-reads config (tests, reload)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def block_rows(document_id: int, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """BlockOut-shaped dicts -> INSERT parameter dicts."""
    return [
        {
            "document_id": document_id,
            "block_id": b["id"],
            "block_order": b["order"],
            "page": b.get("page", 0),
            "page_end": b.get("page_end", 0),
            "page_bboxes": Json(b["page_bboxes"]) if b.get("page_bboxes") else None,
            "label": b["label"],
            "bbox": b["bbox"],
            "content": b["content"],
            "content_html": b["content_html"],
        }
        for b in blocks
    ]


def save_document(doc: NewDocument) -> int:
    """Persist one OCR result. Page PNGs go to DATA_DIR, rows in one transaction;
    if anything fails the document directory is removed and the tx rolls back."""
    params = {
        "filename": doc.filename[:200],  # client-supplied; cap before storing
        "mime": doc.mime,
        "page_count": len(doc.pages),
        "elapsed_ms": doc.elapsed_ms,
        "model": doc.model,
        "mode": doc.mode,
        "doc_type": doc.doc_type,
        "quality_flags": Json(doc.quality_flags or []),
        "extracted": Json(doc.extracted or {}),
        "markdown": doc.markdown,
        "raw": Json(doc.raw),
    }
    with get_pool().connection() as conn:
        doc_id = int(
            conn.execute(
                "INSERT INTO documents (filename, mime, page_count, elapsed_ms, model,"
                " mode, doc_type, quality_flags, extracted, markdown, raw)"
                " VALUES (%(filename)s, %(mime)s, %(page_count)s, %(elapsed_ms)s,"
                " %(model)s, %(mode)s, %(doc_type)s, %(quality_flags)s, %(extracted)s,"
                " %(markdown)s, %(raw)s) RETURNING id",
                params,
            ).fetchone()[0]
        )
        doc_dir = config.DATA_DIR / "documents" / str(doc_id)
        try:
            doc_dir.mkdir(parents=True, exist_ok=True)
            for index, page in enumerate(doc.pages):
                image_path = doc_dir / f"page_{index}.png"
                image_path.write_bytes(page.png)
                conn.execute(
                    "INSERT INTO document_pages (document_id, page_index, width, height,"
                    " image_path) VALUES (%s, %s, %s, %s, %s)",
                    (doc_id, index, page.width, page.height, str(image_path)),
                )
            rows = block_rows(doc_id, doc.blocks)
            if rows:
                with conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO blocks (document_id, block_id, block_order, page,"
                        " page_end, page_bboxes, label, bbox, content, content_html)"
                        " VALUES (%(document_id)s, %(block_id)s, %(block_order)s, %(page)s,"
                        " %(page_end)s, %(page_bboxes)s, %(label)s, %(bbox)s, %(content)s,"
                        " %(content_html)s)",
                        rows,
                    )
        except Exception:
            shutil.rmtree(doc_dir, ignore_errors=True)
            raise
    return doc_id


def list_documents(limit: int = 50) -> list[dict[str, Any]]:
    with get_pool().connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        rows = cur.execute(
            "SELECT id, filename, doc_type, page_count, quality_flags, created_at"
            " FROM documents ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "filename": r["filename"],
            "doc_type": r["doc_type"],
            "page_count": r["page_count"],
            "quality_flags": r["quality_flags"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


def get_document(doc_id: int) -> dict[str, Any] | None:
    """Stored document -> OcrData-shaped dict + meta, the same contract the
    viewer already renders for POST /api/ocr (pages re-encoded as data URLs)."""
    with get_pool().connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        doc = cur.execute(
            "SELECT filename, mime, page_count, elapsed_ms, model, mode, doc_type,"
            " quality_flags, extracted, markdown, raw, created_at"
            " FROM documents WHERE id = %s",
            (doc_id,),
        ).fetchone()
        if doc is None:
            return None
        pages = cur.execute(
            "SELECT page_index, width, height, image_path FROM document_pages"
            " WHERE document_id = %s ORDER BY page_index",
            (doc_id,),
        ).fetchall()
        blocks = cur.execute(
            "SELECT block_id, block_order, page, page_end, page_bboxes, label, bbox,"
            " content, content_html FROM blocks WHERE document_id = %s"
            " ORDER BY page, block_order",
            (doc_id,),
        ).fetchall()
    return {
        "pages": [
            {
                "index": p["page_index"],
                "width": p["width"],
                "height": p["height"],
                "mime": "image/png",
                "data_url": _png_data_url(p["image_path"]),
            }
            for p in pages
        ],
        "blocks": [
            {
                "id": b["block_id"],
                "order": b["block_order"],
                "page": b["page"],
                "page_end": b["page_end"],
                "page_bboxes": b["page_bboxes"],
                "label": b["label"],
                "bbox": b["bbox"],
                "content": b["content"],
                "content_html": b["content_html"],
            }
            for b in blocks
        ],
        "markdown": doc["markdown"],
        "raw": doc["raw"],
        "meta": {
            "filename": doc["filename"],
            "mime": doc["mime"],
            "elapsed_ms": doc["elapsed_ms"],
            "model": doc["model"],
            "mode": doc["mode"],
            "page_count": doc["page_count"],
            "doc_type": doc["doc_type"],
            "quality_flags": doc["quality_flags"],
            "extracted": doc["extracted"],
            "created_at": doc["created_at"].isoformat(),
        },
    }


def _png_data_url(image_path: str) -> str:
    png = Path(image_path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(png).decode()
