"""Qualitative eval on a handful of dataset samples (gitignored eval_samples/).

Runs each image through the REAL API, then checks whether key reference fields
(invoice number / date, from the dataset's stored parsed_data annotations) appear
in the recognized text. Reference annotations are precomputed strings parsed
defensively (json.loads + ast.literal_eval - never eval) and used ONLY as a
comparison reference; they are not ground truth.

Usage:
    uv run --project backend python scripts/eval_dataset.py [--samples eval_samples] [--rows /tmp/ds_rows.json]
"""

from __future__ import annotations

import argparse
import ast
import json
import time
import urllib.request
from pathlib import Path

API = "http://localhost:8000/api/ocr"


def reference_fields(parsed_data: str) -> dict[str, str]:
    """Safely extract a few reference fields from the stored annotation string."""
    try:
        outer = json.loads(parsed_data)
        inner = outer.get("json", "")
        # inner is a Python-repr dict (single quotes); literal_eval is safe (no eval)
        data = ast.literal_eval(inner) if isinstance(inner, str) else inner
        header = data.get("header", {}) if isinstance(data, dict) else {}
        return {k: str(v) for k, v in header.items() if v and k in ("invoice_no", "invoice_date")}
    except Exception:
        return {}


def run(image: Path) -> dict:
    req = urllib.request.Request(
        API,
        data=_multipart(image.read_bytes(), image.name),
        headers={"Content-Type": "multipart/form-data; boundary=ocrpoc"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.loads(resp.read())
    wall = time.perf_counter() - t0
    return {"wall_s": round(wall, 1), "body": body}


def _multipart(data: bytes, filename: str) -> bytes:
    part = (
        f"--ocrpoc\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode()
    return part + data + b"\r\n--ocrpoc--\r\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=Path, default=Path("eval_samples"))
    ap.add_argument("--rows", type=Path, default=Path("/tmp/ds_rows.json"))
    args = ap.parse_args()

    refs: dict[str, dict[str, str]] = {}
    if args.rows.exists():
        for row in json.loads(args.rows.read_text()).get("rows", []):
            refs[str(row["row"]["id"])] = reference_fields(row["row"].get("parsed_data", ""))

    images = sorted(args.samples.glob("ds_*.jpg"))
    if not images:
        raise SystemExit(f"no ds_*.jpg found in {args.samples}")

    summary = []
    for img in images:
        ds_id = img.stem.removeprefix("ds_")
        out = run(img)
        body = out["body"]
        if not body.get("success"):
            print(f"{img.name}: ERROR {body.get('error')}")
            summary.append({"image": img.name, "error": body.get("error")})
            continue
        data = body["data"]
        full_text = "\n".join(b["content"] for b in data["blocks"])
        ref = refs.get(ds_id, {})
        checks = {k: str(v) in full_text for k, v in ref.items()}
        row = {
            "image": img.name,
            "wall_s": out["wall_s"],
            "api_elapsed_ms": body["meta"]["elapsed_ms"],
            "blocks": len(data["blocks"]),
            "labels": sorted({b["label"] for b in data["blocks"]}),
            "reference_fields": ref,
            "reference_found_in_ocr": checks,
        }
        summary.append(row)
        print(f"{img.name}: {row['blocks']} blocks, api {row['api_elapsed_ms']/1000:.1f}s, refs {checks}")

    Path("docs/eval_summary.json").write_text(json.dumps(summary, indent=2))
    print("wrote docs/eval_summary.json")


if __name__ == "__main__":
    main()
