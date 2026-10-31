"""Backend configuration (environment-overridable constants)."""

from __future__ import annotations

import os

# MLX-VLM inference server (recognition only; layout runs in this process on CPU)
VLM_SERVER_URL = os.environ.get("VLM_SERVER_URL", "http://localhost:8111/")
MODEL_NAME = os.environ.get("VLM_MODEL_NAME", "mlx-community/PaddleOCR-VL-1.6-4bit")

# "real" uses PaddleOCRVL + MLX-VLM server; "stub" returns deterministic fake
# results for unit/API tests without touching any model.
BACKEND_MODE = os.environ.get("OCR_BACKEND", "real")

# Upload limits (trust boundary)
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 30_000_000
MIN_SIDE = 50
ALLOWED_FORMATS = frozenset({"JPEG", "PNG"})

# CORS: local dev frontend only
ALLOWED_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
