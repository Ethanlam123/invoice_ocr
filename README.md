# Invoice OCR Viewer

Local-first invoice/receipt OCR demo for Apple Silicon Macs. Upload an image, run the
full PaddleOCR-VL pipeline (layout analysis on CPU + recognition via MLX on GPU),
inspect recognized blocks with bidirectional selection between the document image and
the reading-order list, and download the raw inference JSON.

All inference runs locally. No cloud APIs, no auth, no database.

## Architecture

```
Next.js (localhost:3000)                 your browser
   |
   | POST /api/ocr (multipart image)
   v
FastAPI (localhost:8000)                 backend/
   |- validate + EXIF-normalize + re-encode (Pillow)
   |- PaddleOCRVL pipeline                paddleocr 3.7.0 / paddlepaddle 3.2.1 (CPU)
   |     layout: PP-DocLayoutV3 (CPU)     auto-downloaded on first run
   |     recognition: MLX-VLM server ----> vlm-server/
   |- normalize blocks + sanitize table HTML (nh3)
   |
   v
MLX-VLM server (localhost:8111)          mlx-vlm 0.7.11 / mlx 0.32.4
   model: mlx-community/PaddleOCR-VL-1.6-4bit (0.68 GB)
```

- The MLX-VLM server handles recognition only. The full pipeline (layout, reading
  order, table structuring) runs in the backend via `PaddleOCRVL`.
- `block_bbox` coordinates refer to the EXIF-normalized PNG the backend returns in
  the same response, so the SVG overlay always matches the displayed image.
- One inference at a time (process-wide lock). The pipeline and model server are
  reused across requests.

## Requirements

- Apple Silicon Mac (tested: M2, 16 GB, macOS)
- [uv](https://docs.astral.sh/uv/) 0.13+
- Node.js 20+ (tested: 26) with npm
- ~1 GB disk for models (0.68 GB VLM + PP-DocLayoutV3), internet on first run

## Setup

```bash
uv sync --project backend      # FastAPI + paddleocr[doc-parser] + paddlepaddle 3.2.1 (CPU)
uv sync --project vlm-server   # mlx-vlm
cd frontend && npm install && cd ..
```

Locked dependency versions live in `backend/uv.lock` and `vlm-server/uv.lock`
(key pins: paddleocr 3.7.0, paddlepaddle 3.2.1, mlx-vlm 0.7.11, mlx 0.32.4,
fastapi 0.162.0, Next.js 16.4.3).

## Run

```bash
scripts/dev.sh        # starts all three services, logs in /tmp/invoice-ocr-*.log
```

Or manually:

```bash
uv run --project vlm-server mlx_vlm.server --port 8111 --model mlx-community/PaddleOCR-VL-1.6-4bit
(cd backend && uv run uvicorn app.main:app --port 8000)
cd frontend && npm run dev
```

The first VLM server start downloads the 4-bit model (0.68 GB). The first OCR
request additionally downloads the PP-DocLayoutV3 layout model and initializes the
pipeline (~20 s one-time). Open http://localhost:3000.

Health check: `curl localhost:8000/api/health` (reports whether the VLM server is
reachable).

## Usage

1. Drop or choose a JPG/PNG (max 10 MB, 30 MP, min 50 px side).
2. Press Run OCR. Real inference takes roughly 15-20 s per page on an M2.
3. Left: document with region boxes. Right: blocks in reading order.
   Click either side to select; arrows or j / k step through blocks; Esc clears.
   Table blocks render as sanitized HTML with a source toggle.
4. Download JSON returns the raw pipeline result (`parsing_res_list`,
   `layout_det_res`, dimensions).

## Tests

```bash
uv run --project backend pytest          # unit/API tests, stub backend, no model
uv run --project backend ruff check app tests
cd frontend && npm test                  # vitest unit tests
cd frontend && npm run e2e               # Playwright against mocked API
```

Live-model checks (require the services above, never part of pytest):

```bash
uv run --project backend python scripts/run_real_inference.py samples/invoice_sample.png
uv run --project backend python scripts/eval_dataset.py   # after fetching samples, see below
```

Results and timings are recorded in `docs/VALIDATION.md`.

## Dataset samples (optional eval only)

`eval_samples/` is gitignored. A few images can be fetched from
[mychen76/invoices-and-receipts_ocr_v1](https://huggingface.co/datasets/mychen76/invoices-and-receipts_ocr_v1)
via the HF datasets-server rows API (see `scripts/eval_dataset.py`). The dataset
has no license declared, so its images are never committed or redistributed;
stored annotations are used only as a labeled reference (`ast.literal_eval`, never
`eval`).

## Known limitations (v1)

- Layout blocks only; no per-word boxes, no business-field extraction.
- `block_order` is null for some layout classes (header/table/footer); the viewer
  falls back to pipeline order for those.
- Single image per run; no PDF/multi-page/batch.
- English/Latin documents tested; CJK not exercised end-to-end yet.
- The processing state shows elapsed time only - no progress percentage exists.
- First inference after boot pays one-time model init (~20 s).
- If the VLM server is down, requests fail with `vlm_server_unreachable` (503);
  nothing is cached between runs.
- Error messages may include underlying library exception text - fine for a
  localhost demo, not for exposing beyond loopback.
