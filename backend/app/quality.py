"""OCR quality heuristics -> quality flags stored on the document.

The VLM recognition path exposes no per-character confidence (recorded in
docs/VALIDATION.md), so quality is inferred from cheap proxies on the
normalized blocks. Flags are advisory: they route human review, they never
change content. Arithmetic field validation joins later with extraction.
"""

from __future__ import annotations

import re
from typing import Any

# a run of 4+ of the same character is almost always misread (IIII, l111, ...)
_REPEATED = re.compile(r"(.)\1{3,}")
# cells per row of model-generated table HTML
_ROW_CELLS = re.compile(r"<t[dh]\b", re.IGNORECASE)

# multi-word text that is this sparse relative to its bbox area likely failed
# to read (single-word blocks are exempt: stamps and labels are legitimately
# short, and indistinguishable from a failed one-word read)
_MIN_CHARS_PER_1000PX2 = 0.5
# below this share of letters+digits (and length >= 8), text is mostly noise
_MIN_ALNUM_SHARE = 0.5


def quality_flags(blocks: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    for b in blocks:
        content = str(b.get("content") or "")
        if _is_garbled(content):
            flags.append(f"garbled:block-{b['id']}")
        if _is_sparse(b):
            flags.append(f"sparse:block-{b['id']}")
        if b.get("label") == "table" or "<table" in content.lower():
            ragged = _ragged_rows(content)
            if ragged:
                flags.append(f"ragged_table:block-{b['id']}:{ragged}")
    return flags


def _is_garbled(content: str) -> bool:
    if len(content) < 8:
        return False
    if _REPEATED.search(content):
        return True
    alnum = sum(c.isalnum() for c in content)
    return alnum / len(content) < _MIN_ALNUM_SHARE


def _is_sparse(block: dict[str, Any]) -> bool:
    content = str(block.get("content") or "")
    if block.get("label") in ("table",) or "<table" in content.lower():
        return False  # tables legitimately have sparse text per pixel
    if len(content.split()) < 2:
        return False  # single word: stamp/label or a failed read - not decidable
    bbox = block.get("bbox") or [0, 0, 0, 0]
    area = max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    if area <= 0:
        return False
    return len(content.strip()) / (area / 1000) < _MIN_CHARS_PER_1000PX2


def _ragged_rows(table_html: str) -> int:
    """Rows whose cell count differs from the table's own majority count."""
    rows = [
        len(_ROW_CELLS.findall(row))
        for row in re.findall(r"<tr\b.*?</tr>", table_html, re.IGNORECASE | re.DOTALL)
    ]
    rows = [n for n in rows if n > 0]
    if len(rows) < 3:  # too few rows to speak of a majority
        return 0
    majority = max(set(rows), key=rows.count)
    return sum(1 for n in rows if n != majority)
