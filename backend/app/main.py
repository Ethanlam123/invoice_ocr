"""FastAPI app: OCR endpoint + health."""

from __future__ import annotations

import asyncio
import base64
import binascii
import time
import urllib.request
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, db
from .blocks import document_markdown, markdown_text, normalize_blocks, normalize_document
from .classify import classify
from .extract import extract_document
from .images import (
    ImageValidationError,
    NormalizedImage,
    is_pdf,
    load_normalized,
    read_upload_capped,
    render_pdf_pages,
)
from .pipeline import InferenceError, OcrBackend, build_backend
from .quality import quality_flags
from .schemas import (
    BlockCorrection,
    DocumentListData,
    DocumentSummary,
    Envelope,
    ErrorOut,
    OcrData,
    PageOut,
    SaveDocumentIn,
)

app = FastAPI(title="Invoice OCR Viewer API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.ALLOWED_ORIGINS),
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


async def get_backend() -> OcrBackend:
    # async dependency: first-request init cannot race in the event loop
    backend: OcrBackend | None = getattr(app.state, "backend", None)
    if backend is None:
        backend = build_backend()
        app.state.backend = backend
    return backend


BackendDep = Annotated[OcrBackend, Depends(get_backend)]


def fail(status: int, code: str, message: str) -> JSONResponse:
    body = Envelope(success=False, error=ErrorOut(code=code, message=message))
    return JSONResponse(status_code=status, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # keep the error envelope shape for FastAPI's own 422s (e.g. missing file
    # part, non-integer path params)
    return fail(422, "invalid_request", "Request parameters are missing or invalid.")


@app.get("/api/health")
async def health(backend: BackendDep) -> Envelope:
    vlm = "skipped"
    if backend.mode == "real":
        vlm = "ok" if await _vlm_reachable() else "unreachable"
    return Envelope(
        success=True, meta={"backend": "ok", "vlm_server": vlm, "mode": backend.mode}
    )


async def _vlm_reachable() -> bool:
    url = config.VLM_SERVER_URL.rstrip("/") + "/v1/models"

    def _probe() -> None:
        with urllib.request.urlopen(url, timeout=3) as resp:
            resp.read(64)

    try:
        await asyncio.to_thread(_probe)
        return True
    except Exception:
        return False


@app.post("/api/ocr")
async def ocr(file: UploadFile, backend: BackendDep) -> Envelope:
    try:
        data = await read_upload_capped(file)
        pages: list[NormalizedImage] = (
            render_pdf_pages(data) if is_pdf(data) else [load_normalized(data)]
        )
    except ImageValidationError as exc:
        status = 413 if exc.code == "file_too_large" else 400
        return fail(status, exc.code, exc.message)

    started = time.perf_counter()
    try:
        raw = await backend.run([p.png for p in pages])
    except InferenceError as exc:
        status = 503 if exc.code in ("vlm_server_unreachable", "pipeline_unavailable",
                                      "pipeline_init_failed") else 500
        return fail(status, exc.code, exc.message)
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    try:
        if "pages" in raw:  # multi-page: {"page_count": N, "pages": [...]}
            for page_json in raw["pages"]:
                page_json.pop("input_path", None)
            blocks = normalize_document(raw["pages"])
            markdown = document_markdown(raw["pages"])
        else:  # single-page v1 shape
            raw = {k: v for k, v in raw.items() if k != "input_path"}
            res = raw.get("res", raw)
            blocks = normalize_blocks(res)
            markdown = markdown_text(res)
        data = OcrData(
            pages=[
                PageOut(
                    index=i,
                    width=p.width,
                    height=p.height,
                    mime="image/png",
                    data_url="data:image/png;base64," + base64.b64encode(p.png).decode(),
                )
                for i, p in enumerate(pages)
            ],
            blocks=blocks,
            markdown=markdown,
            raw=raw,
        )
    except Exception as exc:
        return fail(500, "normalization_failed", f"Failed to normalize pipeline output: {exc}")

    doc_type, _confidence = classify(blocks)
    flags = quality_flags(blocks)
    extracted, math_flags = extract_document(blocks, doc_type)
    flags += math_flags

    meta: dict[str, Any] = {
        "elapsed_ms": elapsed_ms,
        "model": config.MODEL_NAME if backend.mode == "real" else "stub",
        "mode": backend.mode,
        "page_count": len(pages),
        "doc_type": doc_type,
        "quality_flags": flags,
        "extracted": extracted,
    }
    # Storage is a separate reviewer decision (POST /api/documents, the UI
    # Save button) - the OCR run itself stays side-effect free.
    return Envelope(success=True, data=data, meta=meta)


@app.post("/api/documents")
async def save_document(payload: SaveDocumentIn) -> Envelope:
    """Persist a completed OCR run the reviewer chose to keep."""
    if not db.persistence_enabled():
        return fail(503, "persistence_disabled", "DATABASE_URL is not set; history is off.")
    pages: list[NormalizedImage] = []
    total_bytes = 0
    try:
        for p in payload.pages:
            header, sep, b64 = p.data_url.partition(",")
            if not sep or not header.startswith("data:") or ";base64" not in header:
                raise ValueError("not a base64 data URL")
            png = base64.b64decode(b64, validate=True)
            total_bytes += len(png)
            # cap matches the worst case the OCR flow itself can emit
            if total_bytes > config.MAX_FILE_BYTES * config.MAX_PDF_PAGES:
                raise ValueError("page images exceed the size limit")
            pages.append(load_normalized(png))
    except (ValueError, binascii.Error):
        return fail(400, "invalid_request", "pages must be valid base64 PNG data URLs.")
    doc_id = await asyncio.to_thread(
        db.save_document,
        db.NewDocument(
            filename=payload.filename,
            mime=payload.mime,
            elapsed_ms=payload.elapsed_ms,
            model=payload.model,
            mode=payload.mode,
            doc_type=payload.doc_type,
            quality_flags=payload.quality_flags,
            extracted=payload.extracted,
            pages=pages,
            blocks=[b.model_dump() for b in payload.blocks],
            markdown=payload.markdown,
            raw=payload.raw,
        ),
    )
    return Envelope(success=True, data=None, meta={"document_id": doc_id})


@app.get("/api/documents")
async def list_documents() -> Envelope:
    if not db.persistence_enabled():
        return fail(503, "persistence_disabled", "DATABASE_URL is not set; history is off.")
    docs = await asyncio.to_thread(db.list_documents)
    return Envelope(
        success=True,
        data=DocumentListData(documents=[DocumentSummary(**d) for d in docs]),
        meta={"count": len(docs)},
    )


@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: int) -> Envelope:
    if not db.persistence_enabled():
        return fail(503, "persistence_disabled", "DATABASE_URL is not set; history is off.")
    try:
        doc = await asyncio.to_thread(db.get_document, doc_id)
    except OSError as exc:
        return fail(500, "storage_error", f"Stored page image is missing: {exc}")
    if doc is None:
        return fail(404, "not_found", f"Document {doc_id} not found.")
    meta = doc.pop("meta")
    # validates stored rows against the same contract the live endpoint emits
    return Envelope(success=True, data=OcrData(**doc), meta=meta)


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: int) -> Envelope:
    """Remove a stored document (rows + page files) - the history page's Delete."""
    if not db.persistence_enabled():
        return fail(503, "persistence_disabled", "DATABASE_URL is not set; history is off.")
    deleted = await asyncio.to_thread(db.delete_document, doc_id)
    if not deleted:
        return fail(404, "not_found", f"Document {doc_id} not found.")
    return Envelope(success=True)


@app.patch("/api/documents/{doc_id}/blocks/{block_id}")
async def correct_block(doc_id: int, block_id: int, correction: BlockCorrection) -> Envelope:
    """Store a human correction for one block (review workflow)."""
    # input validation first, so it holds even with persistence disabled
    body = correction.corrected_content.strip()
    if not body:
        return fail(400, "invalid_request", "corrected_content must not be empty.")
    if len(correction.corrected_content) > config.MAX_CORRECTION_CHARS:
        return fail(
            400, "invalid_request",
            f"corrected_content exceeds {config.MAX_CORRECTION_CHARS} characters.",
        )
    if not db.persistence_enabled():
        return fail(503, "persistence_disabled", "DATABASE_URL is not set; history is off.")
    updated = await asyncio.to_thread(db.correct_block, doc_id, block_id, body)
    if not updated:
        return fail(404, "not_found", f"Block {block_id} of document {doc_id} not found.")
    return Envelope(success=True, meta={"document_id": doc_id, "block_id": block_id})
