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
    async def run(self, pngs: list[bytes]) -> dict[str, Any]:
        """Run inference on normalized PNG bytes (one per page); return
        pipeline result JSON: single-page v1 dict, or
        {"page_count": N, "pages": [per-page dicts]} for multi-page."""


class RealPipeline(OcrBackend):
    """PaddleOCRVL pipeline: layout (CPU) + recognition via MLX-VLM server.

    Model/pipeline objects are created once and reused; a lock serializes
    inference (local PoC, one at a time - no queue service).
    """

    def __init__(self) -> None:
        self._pipeline: Any = None
        self._lock = asyncio.Lock()

    async def run(self, pngs: list[bytes]) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._run_sync, pngs)

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

    def _run_sync(self, pngs: list[bytes]) -> dict[str, Any]:
        self._ensure_pipeline()
        self._check_vlm_server()
        if len(pngs) == 1:
            return self._run_one(pngs[0])
        return self._run_many(pngs)

    def _predict_png(self, png: bytes) -> tuple[Any, Path]:
        """Write PNG bytes to a temp file, run one page of inference.

        Returns (result, temp_path); caller owns deleting the temp file."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
            tf.write(png)
            img_path = Path(tf.name)
        try:
            return next(iter(self._pipeline.predict(str(img_path)))), img_path
        except InferenceError:
            img_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            img_path.unlink(missing_ok=True)
            raise InferenceError("inference_failed", f"OCR inference failed: {exc}") from exc

    def _run_one(self, png: bytes) -> dict[str, Any]:
        """Single page: the original v1 path, unchanged shape."""
        result, img_path = self._predict_png(png)
        try:
            return self._result_json(result)
        finally:
            img_path.unlink(missing_ok=True)

    def _run_many(self, pngs: list[bytes]) -> dict[str, Any]:
        """Multi-page: per-page predict, then the engine's cross-page merge.

        restructure_pages(concatenate_pages=False) returns one result per page;
        merged tables keep full HTML on the owner page while continuation
        fragments get content "" and global_group_id = owner's global_block_id
        (parsed back in app.blocks.normalize_document).
        """
        results = []
        img_paths: list[Path] = []
        try:
            for png in pngs:
                result, img_path = self._predict_png(png)
                results.append(result)
                img_paths.append(img_path)
            try:
                pages = list(
                    self._pipeline.restructure_pages(
                        results, merge_tables=True, relevel_titles=False,
                        concatenate_pages=False,
                    )
                )
            except Exception as exc:
                raise InferenceError(
                    "inference_failed", f"Cross-page restructuring failed: {exc}"
                ) from exc
            page_jsons = [self._result_json(r) for r in pages]
            return {"page_count": len(page_jsons), "pages": page_jsons}
        finally:
            for p in img_paths:
                p.unlink(missing_ok=True)

    def _result_json(self, result: Any) -> dict[str, Any]:
        # save_to_json converts numpy arrays to lists; round-trip for clean dicts
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            json_path = Path(tf.name)
        try:
            result.save_to_json(str(json_path))
            return json.loads(json_path.read_text())
        finally:
            json_path.unlink(missing_ok=True)


class StubPipeline(OcrBackend):
    """Deterministic fake for unit/API tests. Never touches any model."""

    mode = "stub"

    async def run(self, pngs: list[bytes]) -> dict[str, Any]:
        if len(pngs) == 1:
            return self._page(pngs[0], single=True)
        # multi-page fake mirrors the engine's merge contract: page 0 owns the
        # merged table HTML, page 1's fragment is emptied and group-linked
        pages = [self._page(pngs[0], single=False), self._fragment_page(pngs[1])]
        return {"page_count": len(pages), "pages": pages}

    def _page(self, png: bytes, single: bool) -> dict[str, Any]:
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            w, h = im.size

        def g(n: int) -> dict[str, int]:
            # global ids are only present in multi-page results (engine adds
            # them during restructure_pages)
            if single:
                return {}
            return {"global_block_id": n, "global_group_id": n}

        result = {
            "input_path": "/tmp/stub-should-be-stripped.png",
            "parsing_res_list": [
                {
                    "block_id": 0,
                    "block_order": 0,
                    "block_label": "title",
                    "block_bbox": [w * 0.08, h * 0.04, w * 0.45, h * 0.09],
                    "block_content": "INVOICE",
                    **g(0),
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
                    **g(1),
                },
                {
                    "block_id": 2,
                    "block_order": 2,
                    "block_label": "text",
                    "block_bbox": [w * 0.08, h * 0.90, w * 0.60, h * 0.95],
                    "block_content": "Thank you for your business.",
                    **g(2),
                },
            ],
            "markdown": {"text": "# INVOICE\n\n<table><tr><th>Item</th></tr></table>"},
        }
        return result

    def _fragment_page(self, png: bytes) -> dict[str, Any]:
        """Page 2: table continuation fragment (group-linked to page 1's table)
        plus one normal trailing block."""
        from PIL import Image

        with Image.open(io.BytesIO(png)) as im:
            w, h = im.size
        return {
            "input_path": "/tmp/stub-should-be-stripped-p2.png",
            "parsing_res_list": [
                {
                    "block_id": 0,
                    "block_order": 0,
                    "block_label": "table",
                    "block_bbox": [w * 0.08, h * 0.05, w * 0.92, h * 0.35],
                    "block_content": "",  # emptied by the engine's merge
                    "global_block_id": 10,
                    "global_group_id": 1,  # owner = page 1's table (global id 1)
                },
                {
                    "block_id": 1,
                    "block_order": 1,
                    "block_label": "text",
                    "block_bbox": [w * 0.08, h * 0.80, w * 0.60, h * 0.85],
                    "block_content": "Total: 99.00",
                    "global_block_id": 11,
                    "global_group_id": 11,
                },
            ],
            "markdown": {"text": "Total: 99.00"},
        }


def build_backend() -> OcrBackend:
    if config.BACKEND_MODE == "stub":
        return StubPipeline()
    return RealPipeline()
