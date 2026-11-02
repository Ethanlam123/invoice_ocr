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


def _block_from(b: dict[str, Any], id_: int, page: int | None = None) -> dict[str, Any]:
    order = b.get("block_order")
    content = str(b.get("block_content") or "")
    label = str(b.get("block_label") or "unknown")
    block = {
        "id": id_,
        "order": int(order) if order is not None else id_,
        "label": label,
        "bbox": _bbox_list(b["block_bbox"]),
        "content": content,
        "content_html": sanitize_table_html(content) if is_table_block(label, content) else None,
    }
    if page is not None:
        block["page"] = page
        block["page_end"] = page
    return block


def normalize_blocks(res: dict[str, Any]) -> list[dict[str, Any]]:
    """parsing_res_list -> ordered block dicts. `id` is the pipeline block_id and
    is the stable key for left/right selection sync (text may repeat)."""
    out: list[dict[str, Any]] = []
    for b in res.get("parsing_res_list") or []:
        out.append(_block_from(b, int(b.get("block_id", len(out)))))
    out.sort(key=lambda b: b["order"])
    return out


def normalize_document(page_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Multi-page per-page results -> ordered blocks with page tags.

    Engine merge contract (restructure_pages): a table merged across pages
    keeps the full HTML on its owner page; continuation fragments are emptied
    (content "") and carry global_group_id = owner's global_block_id. Fragments
    are not emitted as list rows; their geometry reaches the viewer through
    the owner's page_bboxes so every page of a span can draw its own rect.
    """
    out: list[dict[str, Any]] = []
    span_end: dict[int, int] = {}  # owner global id -> last page of the merge
    fragments: dict[int, list[tuple[int, Any]]] = {}  # owner id -> [(page, bbox)]
    for page_no, res in enumerate(page_results):
        for b in res.get("parsing_res_list") or []:
            if b.get("global_block_id") is None or b.get("global_group_id") is None:
                # without global ids, per-page block_id restarts per page and
                # ids collide; fail loudly instead of breaking selection sync
                raise ValueError(
                    "multi-page results must carry global_block_id/global_group_id "
                    "(engine restructure_pages contract)"
                )
            gid, grp = int(b["global_block_id"]), int(b["global_group_id"])
            if grp != gid:
                # continuation fragment of an earlier block: record span + bbox
                span_end[grp] = max(span_end.get(grp, 0), page_no)
                fragments.setdefault(grp, []).append((page_no, b["block_bbox"]))
                continue
            out.append(_block_from(b, gid, page=page_no))
    for block in out:
        end = span_end.get(block["id"])
        if end is None:
            continue
        block["page_end"] = end
        frag_pages = sorted(fragments.get(block["id"], []))
        block["page_bboxes"] = [{"page": block["page"], "bbox": block["bbox"]}] + [
            {"page": p, "bbox": _bbox_list(bb)} for p, bb in frag_pages
        ]
    out.sort(key=lambda b: (b["page"], b["order"]))
    return out


def document_markdown(page_results: list[dict[str, Any]]) -> str:
    return "\n\n".join(t for t in (markdown_text(r) for r in page_results) if t)


def markdown_text(res: dict[str, Any]) -> str:
    md = res.get("markdown")
    if isinstance(md, dict):
        return str(md.get("text") or "")
    return str(md) if md else ""
