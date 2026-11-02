#!/usr/bin/env bash
# Start all three local processes for the Invoice OCR Viewer.
# Usage: scripts/dev.sh  (each service logs to its own file under /tmp)
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${VLM_MODEL_NAME:-mlx-community/PaddleOCR-VL-1.6-4bit}"
VLM_PORT="${VLM_PORT:-8111}"

# Bypass any system HTTP proxy for local services (httpx routes localhost
# through HTTP_PROXY otherwise and gets a 400 from the proxy).
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}localhost,127.0.0.1"
export no_proxy="$NO_PROXY"

# Persistence: Docker Postgres (scripts: docker run -d --name invoice-ocr-db
# -p 5433:5432 -e POSTGRES_DB=invoice_ocr -e POSTGRES_PASSWORD=postgres
# -v invoice-ocr-db-data:/var/lib/postgresql/data postgres:17-alpine).
export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@localhost:5433/invoice_ocr}"
docker start invoice-ocr-db >/dev/null 2>&1 || true  # no-op if already running / docker down

for port in "$VLM_PORT" 8000 3000; do
  if lsof -ti "tcp:$port" >/dev/null 2>&1; then
    echo "port $port is already in use - stop the running services first" >&2
    exit 1
  fi
done

echo "1/3 MLX-VLM server (model: $MODEL, port $VLM_PORT)"
uv run --project vlm-server mlx_vlm.server --port "$VLM_PORT" --model "$MODEL" \
  > /tmp/invoice-ocr-vlm.log 2>&1 &

echo "2/3 FastAPI backend (port 8000) - waits for VLM"
(cd backend && uv run uvicorn app.main:app --port 8000) \
  > /tmp/invoice-ocr-backend.log 2>&1 &

echo "3/3 Next.js frontend (port 3000)"
# .next does not survive unclean stops (this script's own trap): the
# turbopack cache crashes the next start, and macOS duplicates generated
# type files ("routes.d 2.ts") that break tsc - start clean every time.
rm -rf frontend/.next
(cd frontend && npm run dev) > /tmp/invoice-ocr-frontend.log 2>&1 &

trap 'kill 0' EXIT INT TERM
echo "ready: http://localhost:3000 (logs in /tmp/invoice-ocr-*.log)"
wait
