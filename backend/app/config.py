"""Backend configuration (environment-overridable constants)."""

from __future__ import annotations

import os
from pathlib import Path

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

# PDF uploads: pages are rendered here and fed to the pipeline page by page,
# so block_bbox keeps referring to pixels we also return as page images.
PDF_MAGIC = b"%PDF-"
PDF_RENDER_DPI = 150
MAX_PDF_PAGES = 8  # 8 pages x ~20 s stays under the 5 min client timeout

# CORS: local dev frontend only
ALLOWED_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")

# Postgres persistence: opt-in. Unset -> the app stays stateless (tests, demo).
DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Page PNGs live on disk; the DB stores paths only (keeps rows small).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR") or REPO_ROOT / "data")
