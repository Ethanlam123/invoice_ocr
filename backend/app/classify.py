"""Rule-based document-type classification (Phase 1; local Jev is a later,
measurement-gated swap behind the same interface).

Input is normalized blocks; title and leading text blocks carry the document
self-identification ("INVOICE", "RECEIPT", ...). Rules give a hard 1.0/0.0
confidence: they only fire on an explicit keyword, never a guess.
"""

from __future__ import annotations

from typing import Any

# (doc_type, keywords matched against the uppercased heading text)
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("purchase_order", ("PURCHASE ORDER", "PURCHASE REQUEST", "訂購單", "订购单")),
    ("receipt", ("RECEIPT", "收據", "收据")),
    ("invoice", ("INVOICE", "發票", "发票")),
]

# purchase_order is checked first: invoices often contain the word "receipt"
# ("receipt of payment") but a PO heading says "purchase order".


def classify(blocks: list[dict[str, Any]]) -> tuple[str, float]:
    """Blocks -> (doc_type, confidence). 'unknown' when no keyword fires."""
    # heading-class blocks first, then leading text: measured on real samples
    # (mychen76), the self-identifying line lands in header/title/paragraph_title
    # or a leading text block depending on the layout
    # shortcut: first 3 text blocks only; deep-body keywords would misclassify
    heading_parts = [
        str(b["content"])
        for b in blocks
        if b["label"] in ("title", "paragraph_title", "header")
    ]
    texts = [str(b["content"]) for b in blocks if b["label"] == "text"]
    heading = " ".join(heading_parts + texts[:3]).upper()
    for doc_type, keywords in _RULES:
        if any(k in heading for k in keywords):
            return doc_type, 1.0
    return "unknown", 0.0
