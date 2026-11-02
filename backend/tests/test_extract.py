"""Phase 2: regex field extraction + arithmetic validation."""

from __future__ import annotations

from app.extract import extract_document


def _block(id_: int, label: str, content: str):
    return {"id": id_, "order": id_, "label": label, "content": content,
            "bbox": [0, 0, 100, 20], "content_html": None}


def test_extracts_core_fields_from_text_blocks() -> None:
    blocks = [
        _block(0, "text", "Invoice # INV-2026-0042"),
        _block(1, "text", "Date of issue: 31/10/2026"),
        _block(2, "text", "Total: $3,975.50"),
    ]
    extracted, flags = extract_document(blocks, "invoice")
    assert extracted["invoice_no"] == {"value": "INV-2026-0042", "block": 0}
    assert extracted["issue_date"]["value"] == "31/10/2026"
    assert extracted["total"]["value"] == 3975.5
    assert extracted["currency"]["value"] == "USD"
    assert flags == []


def test_extracts_money_from_flattened_table_html() -> None:
    blocks = [
        _block(0, "text", "Invoice no: 61356291"),
        _block(1, "table",
               "<table><tr><td>Subtotal</td><td>2,850.00</td></tr>"
               "<tr><td>Tax</td><td>142.50</td></tr>"
               "<tr><td>Total</td><td>2,992.50</td></tr></table>"),
    ]
    extracted, flags = extract_document(blocks, "invoice")
    assert extracted["subtotal"]["value"] == 2850.0
    assert extracted["tax"]["value"] == 142.5
    assert extracted["total"]["value"] == 2992.5
    assert flags == []  # 2850 + 142.50 == 2992.50


def test_tampered_total_flags_mismatch_and_needs_review() -> None:
    blocks = [
        _block(0, "text", "Subtotal: 100.00"),
        _block(1, "text", "Tax: 8.50"),
        _block(2, "text", "Total: 999.00"),  # wrong on purpose
    ]
    extracted, flags = extract_document(blocks, "invoice")
    assert flags == ["math:total_mismatch"]
    assert extracted["total"]["needs_review"] is True
    assert extracted["subtotal"]["needs_review"] is True


def test_tax_missing_when_total_exceeds_subtotal_without_tax() -> None:
    blocks = [_block(0, "text", "Subtotal: 100.00"), _block(1, "text", "Total: 108.50")]
    extracted, flags = extract_document(blocks, "invoice")
    assert flags == ["math:tax_missing"]
    assert extracted["total"]["needs_review"] is True


def test_discount_and_shipping_enter_the_check() -> None:
    blocks = [
        _block(0, "text", "Subtotal: 200.00"),
        _block(1, "text", "Discount: 20.00"),
        _block(2, "text", "Shipping: 10.00"),
        _block(3, "text", "Tax: 8.50"),
        _block(4, "text", "Total: 198.50"),  # 200 - 20 + 10 + 8.50
    ]
    _, flags = extract_document(blocks, "invoice")
    assert flags == []


def test_line_item_math_flags_bad_row() -> None:
    html = (
        "<table><tr><th>Item</th><th>Qty</th><th>Unit Price</th><th>Amount</th></tr>"
        "<tr><td>A</td><td>3</td><td>10.00</td><td>30.00</td></tr>"
        "<tr><td>B</td><td>2</td><td>5.00</td><td>90.00</td></tr>"  # wrong: 2x5 != 90
        "</table>"
    )
    blocks = [_block(0, "table", html)]
    extracted, flags = extract_document(blocks, "invoice")
    assert "math:line_item:block-0:row-2" in flags
    assert extracted == {} or "total" not in extracted  # no totals present, no total check


def test_items_sum_checked_against_subtotal() -> None:
    html = (
        "<table><tr><th>Qty</th><th>Price</th><th>Amount</th></tr>"
        "<tr><td>1</td><td>10.00</td><td>10.00</td></tr>"
        "<tr><td>2</td><td>10.00</td><td>20.00</td></tr>"
        "<tr><td>3</td><td>10.00</td><td>30.00</td></tr>"
        "</table>"
    )
    blocks = [_block(0, "table", html), _block(1, "text", "Subtotal: 70.00")]
    _, flags = extract_document(blocks, "invoice")
    assert "math:items_sum" in flags  # 10+20+30 = 60 != 70


def test_invalid_date_flagged_for_review() -> None:
    blocks = [_block(0, "text", "Date of issue: 13/45/2026")]
    extracted, flags = extract_document(blocks, "invoice")
    assert flags == ["date_invalid:issue_date"]
    assert extracted["issue_date"]["needs_review"] is True


def test_unknown_doc_type_extracts_nothing() -> None:
    extracted, flags = extract_document([_block(0, "text", "Total: 5.00")], "unknown")
    assert extracted == {} and flags == []


def test_tables_without_qty_price_amount_header_skipped() -> None:
    html = ("<table><tr><th>Item</th><th>Qty</th></tr>"
            "<tr><td>A</td><td>3</td></tr></table>")
    _, flags = extract_document([_block(0, "table", html)], "invoice")
    assert flags == []


def test_label_and_value_in_separate_blocks() -> None:
    # mychen76 layout: the label block and the value block are distinct
    blocks = [
        _block(0, "text", "Date of issue:"),
        _block(1, "text", "09/06/2012"),
    ]
    extracted, _ = extract_document(blocks, "invoice")
    assert extracted["issue_date"]["value"] == "09/06/2012"
    assert extracted["issue_date"]["block"] is None  # matched across blocks


def test_tax_with_rate_parenthesis() -> None:
    blocks = [
        _block(0, "text", "Subtotal: 8,600.00"),
        _block(1, "text", "Tax (10%): HK$860.00"),
        _block(2, "text", "Total: 9,460.00"),
    ]
    extracted, flags = extract_document(blocks, "invoice")
    assert extracted["tax"]["value"] == 860.0
    assert extracted["currency"]["value"] == "HKD"
    assert flags == []


def test_eu_decimal_comma_amounts() -> None:
    # mychen76 annotations: "$7,50" means 7.50, "$ 1606,67" means 1606.67
    blocks = [_block(0, "text", "Total: $7,50")]
    extracted, _ = extract_document(blocks, "invoice")
    assert extracted["total"]["value"] == 7.5

    blocks = [_block(0, "text", "Total: $ 1606,67")]
    extracted, _ = extract_document(blocks, "invoice")
    assert extracted["total"]["value"] == 1606.67

    blocks = [_block(0, "text", "Total: 1.606,67")]
    extracted, _ = extract_document(blocks, "invoice")
    assert extracted["total"]["value"] == 1606.67

    blocks = [_block(0, "text", "Total: 1,606.67")]
    extracted, _ = extract_document(blocks, "invoice")
    assert extracted["total"]["value"] == 1606.67

    # space as thousands separator (mychen76: "$ 1 606,67")
    blocks = [_block(0, "text", "Total: $ 1 606,67")]
    extracted, _ = extract_document(blocks, "invoice")
    assert extracted["total"]["value"] == 1606.67


def test_gross_total_label_preferred() -> None:
    blocks = [
        _block(0, "text", "Total: 100.00"),
        _block(1, "text", "Gross Total: 108.50"),
    ]
    extracted, _ = extract_document(blocks, "invoice")
    assert extracted["total"]["value"] == 108.5


def test_table_header_gross_worth_does_not_eat_item_quantity() -> None:
    # regression (measured on mychen76): the "Gross worth" column header is
    # followed on the NEXT row by item quantities; only same-line values count
    html = (
        "<table><tr><th>Qty</th><th>Net price</th><th>Gross worth</th></tr>"
        "<tr><td>1</td><td>7,50</td><td>8,25</td></tr>"
        "<tr><td>Total</td><td></td><td>8,25</td></tr></table>"
    )
    extracted, _ = extract_document([_block(0, "table", html)], "invoice")
    assert extracted["total"]["value"] == 8.25
