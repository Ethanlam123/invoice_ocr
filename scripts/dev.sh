#!/usr/bin/env bash
# Start all three local processes for the Invoice OCR Viewer.
# Usage: scripts/dev.sh  (each service logs to its own file under /tmp)
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${VLM_MODEL_NAME:-mlx-community/PaddleOCR-VL-1.6-4bit}"
VLM_PORT="${VLM_PORT:-8111}"

echo "1/3 MLX-VLM server (model: $MODEL, port $VLM_PORT)"
uv run --project vlm-server mlx_vlm.server --port "$VLM_PORT" --model "$MODEL" \
  > /tmp/invoice-ocr-vlm.log 2>&1 &

echo "2/3 FastAPI backend (port 8000) - waits for VLM"
(cd backend && uv run uvicorn app.main:app --port 8000) \
  > /tmp/invoice-ocr-backend.log 2>&1 &

echo "3/3 Next.js frontend (port 3000)"
(cd frontend && npm run dev) > /tmp/invoice-ocr-frontend.log 2>&1 &

trap 'kill 0' EXIT INT TERM
echo "ready: http://localhost:3000 (logs in /tmp/invoice-ocr-*.log)"
wait
