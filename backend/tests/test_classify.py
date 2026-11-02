"""Phase 1 heuristics: rule classifier + OCR quality flags."""

from __future__ import annotations

from app.classify import classify
from app.quality import quality_flags


def _block(id_: int, label: str, content: str, bbox: list[float] | None = None):
    return {"id": id_, "order": id_, "label": label, "content": content,
            "bbox": bbox or [0, 0, 100, 20], "content_html": None}


# ---- classify ----

def test_classify_invoice_from_title() -> None:
    assert classify([_block(0, "title", "INVOICE")]) == ("invoice", 1.0)


def test_classify_cjk_keywords() -> None:
    assert classify([_block(0, "title", "區域發票")])[0] == "invoice"
    assert classify([_block(0, "title", "電子收據")])[0] == "receipt"
    assert classify([_block(0, "title", "訂購單")])[0] == "purchase_order"


def test_classify_purchase_order_beats_invoice_words() -> None:
    # a PO often mentions invoices; the heading decides
    blocks = [_block(0, "title", "Purchase Order"), _block(1, "text", "invoice ref")]
    assert classify(blocks) == ("purchase_order", 1.0)


def test_classify_falls_back_to_first_text_block() -> None:
    assert classify([_block(0, "text", "ACME Corp"), _block(1, "text", "Receipt #12")]) == (
        "receipt", 1.0,
    )


def test_classify_unknown_when_no_keyword() -> None:
    assert classify([_block(0, "title", "ACME Corp"), _block(1, "text", "hello")]) == (
        "unknown", 0.0,
    )


# ---- quality flags ----

def test_flag_repeated_character_runs() -> None:
    flags = quality_flags([_block(3, "text", "Total IIII 4O0.00")])
    assert "garbled:block-3" in flags


def test_flag_low_alphanumeric_share() -> None:
    flags = quality_flags([_block(1, "text", "!!@@##$$%%^^")])
    assert "garbled:block-1" in flags


def test_flag_sparse_text_block() -> None:
    # multi-word text in a 400x300 px box: far below the density floor
    flags = quality_flags([_block(5, "text", "Total due", bbox=[0, 0, 400, 300])])
    assert "sparse:block-5" in flags


def test_single_word_blocks_not_flagged_sparse() -> None:
    # stamps/labels are legitimately short; indistinguishable from a failed
    # one-word read, so they stay unflagged
    flags = quality_flags([_block(4, "text", "PAID", bbox=[0, 0, 300, 100])])
    assert flags == []


def test_normal_blocks_have_no_flags() -> None:
    flags = quality_flags([_block(0, "title", "INVOICE", bbox=[0, 0, 200, 40]),
                           _block(1, "text", "Thank you for your business.", bbox=[0, 0, 300, 30])])
    assert flags == []


def test_flag_ragged_table_rows() -> None:
    html = ("<table><tr><td>a</td><td>b</td></tr>"
            "<tr><td>c</td><td>d</td></tr>"
            "<tr><td>e</td></tr>"
            "<tr><td>f</td><td>g</td></tr></table>")
    flags = quality_flags([_block(2, "table", html)])
    assert "ragged_table:block-2:1" in flags  # 1 row deviates from the 2-cell majority


def test_consistent_table_not_flagged_and_not_sparse() -> None:
    html = ("<table><tr><td>a</td><td>b</td></tr>"
            "<tr><td>c</td><td>d</td></tr></table>")
    flags = quality_flags([_block(2, "table", html, bbox=[0, 0, 500, 500])])
    assert flags == []
