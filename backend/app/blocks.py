"""Normalize PaddleOCRVL pipeline output to viewer blocks.

Pipeline result shape (from res.save_to_json, numpy already converted to lists):
    parsing_res_list: [{block_id, block_order, block_label, block_bbox, block_content}, ...]
    markdown: {text: str, ...}

block_content of `table` blocks is model-generated HTML - untrusted, sanitized
with nh3 before it is ever sent to a browser. Everything else is plain text and
is rendered as text nodes by the frontend (React-escaped).
"""

from __future__ import annotations

from typing import Any

import nh3

# Allowlist for model-generated table HTML. Nothing else survives cleaning.
_TABLE_TAGS = {
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "colgroup", "col",
}
_TABLE_ATTRS = {
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "col": {"span"},
    "colgroup": {"span"},
    "table": {"border"},
}


def _bbox_list(bbox: Any) -> list[float]:
    """numpy array or list -> plain float list (rounded to shrink JSON)."""
    if hasattr(bbox, "tolist"):
        bbox = bbox.tolist()
    return [round(float(v), 2) for v in bbox]


def sanitize_table_html(content: str) -> str:
    """Strip everything except a safe table subset; keeps escaped text content."""
    return nh3.clean(content, tags=_TABLE_TAGS, attributes=_TABLE_ATTRS, strip_comments=True)


def is_table_block(label: str, content: str) -> bool:
    return label == "table" or "<table" in content.lower()


def normalize_blocks(res: dict[str, Any]) -> list[dict[str, Any]]:
    """parsing_res_list -> ordered block dicts. `id` is the pipeline block_id and
    is the stable key for left/right selection sync (text may repeat)."""
    out: list[dict[str, Any]] = []
    for b in res.get("parsing_res_list") or []:
        block_id = int(b.get("block_id", len(out)))
        order = b.get("block_order")
        content = str(b.get("block_content") or "")
        label = str(b.get("block_label") or "unknown")
        is_table = is_table_block(label, content)
        out.append(
            {
                "id": block_id,
                "order": int(order) if order is not None else block_id,
                "label": label,
                "bbox": _bbox_list(b["block_bbox"]),
                "content": content,
                "content_html": sanitize_table_html(content) if is_table else None,
            }
        )
    out.sort(key=lambda b: b["order"])
    return out


def markdown_text(res: dict[str, Any]) -> str:
    md = res.get("markdown")
    if isinstance(md, dict):
        return str(md.get("text") or "")
    return str(md) if md else ""
