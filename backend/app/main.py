"""FastAPI app: OCR endpoint + health."""

from __future__ import annotations

import base64
import time
from typing import Annotated

from fastapi import Depends, FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .blocks import markdown_text, normalize_blocks
from .images import ImageValidationError, load_normalized
from .pipeline import InferenceError, OcrBackend, build_backend
from .schemas import Envelope, ErrorOut, ImageOut, OcrData

app = FastAPI(title="Invoice OCR Viewer API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.ALLOWED_ORIGINS),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_backend() -> OcrBackend:
    backend: OcrBackend | None = getattr(app.state, "backend", None)
    if backend is None:
        backend = build_backend()
        app.state.backend = backend
    return backend


BackendDep = Annotated[OcrBackend, Depends(get_backend)]


def fail(status: int, code: str, message: str) -> JSONResponse:
    body = Envelope(success=False, error=ErrorOut(code=code, message=message))
    return JSONResponse(status_code=status, content=body.model_dump())


@app.get("/api/health")
async def health(backend: BackendDep) -> Envelope:
    vlm = "skipped"
    if backend.mode == "real":
        vlm = "ok" if await _vlm_reachable() else "unreachable"
    return Envelope(
        success=True, meta={"backend": "ok", "vlm_server": vlm, "mode": backend.mode}
    )


async def _vlm_reachable() -> bool:
    import urllib.request

    url = config.VLM_SERVER_URL.rstrip("/") + "/v1/models"
    try:
        def _probe() -> None:
            with urllib.request.urlopen(url, timeout=3) as resp:
                resp.read(64)

        await __import__("asyncio").to_thread(_probe)
        return True
    except Exception:
        return False


@app.post("/api/ocr")
async def ocr(file: UploadFile, backend: BackendDep) -> Envelope:
    data = await file.read()
    try:
        img = load_normalized(data)
    except ImageValidationError as exc:
        status = 413 if exc.code == "file_too_large" else 400
        return fail(status, exc.code, exc.message)

    started = time.perf_counter()
    try:
        raw = await backend.run(img.png)
    except InferenceError as exc:
        status = 503 if exc.code in ("vlm_server_unreachable", "pipeline_unavailable",
                                      "pipeline_init_failed") else 500
        return fail(status, exc.code, exc.message)
    elapsed_ms = round((time.perf_counter() - started) * 1000)

    # pipeline JSON may nest single-image results under "res"
    res = raw.get("res", raw) if isinstance(raw, dict) else {}
    return Envelope(
        success=True,
        data=OcrData(
            image=ImageOut(
                width=img.width,
                height=img.height,
                mime="image/png",
                data_url="data:image/png;base64," + base64.b64encode(img.png).decode(),
            ),
            blocks=normalize_blocks(res),
            markdown=markdown_text(res),
            raw=raw,
        ),
        meta={
            "elapsed_ms": elapsed_ms,
            "model": config.MODEL_NAME if backend.mode == "real" else "stub",
            "mode": backend.mode,
        },
    )
