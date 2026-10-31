"""OCR pipeline wrapper: lazy singleton, single-flight, temp-file hygiene."""

from __future__ import annotations

import asyncio
import io
import json
import tempfile
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from . import config


class InferenceError(RuntimeError):
    """Raised when inference cannot run or fails. `code` maps to an API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class OcrBackend(ABC):
    """Async single-request interface. Implementations must be safe to reuse."""

    mode: str = "real"

    @abstractmethod
    async def run(self, png: bytes) -> dict[str, Any]:
        """Run inference on normalized PNG bytes; return pipeline result JSON."""


class RealPipeline(OcrBackend):
    """PaddleOCRVL pipeline: layout (CPU) + recognition via MLX-VLM server.

    Model/pipeline objects are created once and reused; a lock serializes
    inference (local PoC, one at a time - no queue service).
    """

    def __init__(self) -> None:
        self._pipeline: Any = None
        self._lock = asyncio.Lock()

    async def run(self, png: bytes) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._run_sync, png)

    def _check_vlm_server(self) -> None:
        url = config.VLM_SERVER_URL.rstrip("/") + "/v1/models"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                resp.read(64)
        except Exception as exc:
            raise InferenceError(
                "vlm_server_unreachable",
                f"MLX-VLM server at {config.VLM_SERVER_URL} is unreachable "
                f"({exc}). Start it with: scripts/dev.sh or the README quickstart.",
            ) from exc

    def _ensure_pipeline(self) -> Any:
        if self._pipeline is None:
            try:
                from paddleocr import PaddleOCRVL
            except Exception as exc:
                raise InferenceError(
                    "pipeline_unavailable", f"Failed to import PaddleOCR: {exc}"
                ) from exc
            try:
                # Rotation/unwarp disabled: block_bbox then maps 1:1 to the
                # normalized input image pixels (see app/images.py).
                self._pipeline = PaddleOCRVL(
                    vl_rec_backend="mlx-vlm-server",
                    vl_rec_server_url=config.VLM_SERVER_URL,
                    vl_rec_api_model_name=config.MODEL_NAME,
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                )
            except Exception as exc:
                raise InferenceError(
                    "pipeline_init_failed", f"Failed to initialize PaddleOCRVL: {exc}"
                ) from exc
        return self._pipeline

    def _run_sync(self, png: bytes) -> dict[str, Any]:
        self._ensure_pipeline()
        self._check_vlm_server()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.write(png)
            img_path = Path(tf.name)
        try:
            try:
                result = next(iter(self._pipeline.predict(str(img_path))))
            except InferenceError:
                raise
            except Exception as exc:
                raise InferenceError("inference_failed", f"OCR inference failed: {exc}") from exc
            # save_to_json converts numpy arrays to lists; round-trip for clean dicts
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
                json_path = Path(tf.name)
            try:
                result.save_to_json(str(json_path))
                return json.loads(json_path.read_text())
            finally:
                json_path.unlink(missing_ok=True)
        finally:
            img_path.unlink(missing_ok=True)


class StubPipeline(OcrBackend):
    """Deterministic fake for unit/API tests. Never touches any model."""

    mode = "stub"

    async def run(self, png: bytes) -> dict[str, Any]:
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            w, h = im.size
        return {
            "parsing_res_list": [
                {
                    "block_id": 0,
                    "block_order": 0,
                    "block_label": "title",
                    "block_bbox": [w * 0.08, h * 0.04, w * 0.45, h * 0.09],
                    "block_content": "INVOICE",
                },
                {
                    "block_id": 1,
                    "block_order": 1,
                    "block_label": "table",
                    "block_bbox": [w * 0.08, h * 0.30, w * 0.92, h * 0.60],
                    "block_content": (
                        "<table><tr><th>Item</th><th>Qty</th></tr>"
                        "<tr><td>Service</td><td>2</td></tr></table>"
                    ),
                },
                {
                    "block_id": 2,
                    "block_order": 2,
                    "block_label": "text",
                    "block_bbox": [w * 0.08, h * 0.90, w * 0.60, h * 0.95],
                    "block_content": "Thank you for your business.",
                },
            ],
            "markdown": {"text": "# INVOICE\n\n<table><tr><th>Item</th></tr></table>"},
        }


def build_backend() -> OcrBackend:
    if config.BACKEND_MODE == "stub":
        return StubPipeline()
    return RealPipeline()
