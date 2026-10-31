"""Run one real end-to-end PaddleOCR-VL inference and dump the result JSON.

Requires the MLX-VLM server to be running (scripts/dev.sh or manual start).
This is the live-model check - deliberately NOT part of the pytest suite.

Usage:
    uv run --project backend python scripts/run_real_inference.py <image> [--out result.json]
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

VLM_SERVER_URL = "http://localhost:8111/"
MODEL_NAME = "mlx-community/PaddleOCR-VL-1.6-4bit"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    from paddleocr import PaddleOCRVL

    t0 = time.perf_counter()
    pipeline = PaddleOCRVL(
        vl_rec_backend="mlx-vlm-server",
        vl_rec_server_url=VLM_SERVER_URL,
        vl_rec_api_model_name=MODEL_NAME,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
    )
    t_init = time.perf_counter() - t0

    t0 = time.perf_counter()
    result = next(iter(pipeline.predict(str(args.image))))
    t_infer = time.perf_counter() - t0

    # save_to_json converts numpy arrays to lists; reload for printing
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        tmp = Path(tf.name)
    try:
        result.save_to_json(str(tmp))
        data = json.loads(tmp.read_text())
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_bytes(tmp.read_bytes())
    finally:
        tmp.unlink(missing_ok=True)

    # paddleocr may wrap single-image results in {"res": {...}}
    res = data.get("res", data)
    blocks = res.get("parsing_res_list", [])
    print(f"pipeline init: {t_init:.1f}s | inference: {t_infer:.1f}s | blocks: {len(blocks)}")
    print(f"top-level keys: {sorted(res.keys())}")
    for b in blocks:
        bbox = b.get("block_bbox")
        content = str(b.get("block_content", "")).replace("\n", "\\n")
        print(
            f"  id={b.get('block_id')} order={b.get('block_order')} "
            f"label={b.get('block_label')!r} bbox={bbox} content={content[:70]!r}"
        )
    md = res.get("markdown", {})
    if isinstance(md, dict) and md.get("text"):
        print("--- markdown (first 500 chars) ---")
        print(md["text"][:500])


if __name__ == "__main__":
    main()
