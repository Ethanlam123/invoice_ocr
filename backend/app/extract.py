"""Common-field extraction (regex over normalized blocks) + arithmetic checks.

Phase 2 by plan: deterministic rules first, measured on the sample set; a
local LLM extractor is a later, measurement-gated swap. Fields land in
documents.extracted (JSONB); validation failures mark the field
needs_review and merge flags into quality_flags. Amounts are NEVER
auto-corrected.

Scope limits (measured/deliberate): US number format only (1,234.56),
currency inferred from an ISO code or the symbol next to the total
($ -> USD, £ -> GBP, EUR symbols, ¥ -> JPY), one currency per document.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_MONEY = (
    # thousands groups may use space (measured: "$ 1 606,67" on mychen76)
    r"(?P<val>[0-9]{1,3}(?:[., ][0-9]{3})+(?:[.,][0-9]{1,2})?"
    r"|[0-9]+[.,][0-9]{1,2}|[0-9]+)"
)
_SYM = (r"(?P<sym>HK\$|US\$|CA\$|AU\$|NZ\$|NT\$|S\$|[$£€¥]"
        r"|USD|EUR|GBP|HKD|JPY|CNY|TWD|AUD|CAD|SGD)?")


def _parse_amount(raw: str) -> float:
    """US (1,234.56) and EU (1.234,56 / '7,50') number formats.

    shortcut: a lone separator followed by exactly 3 digits is treated as
    thousands ("7,500" EU-decimal ambiguity accepted); measured on mychen76
    where every amount is EU-style with 2 decimals.
    """
    cleaned = raw.replace(" ", "")
    if "." in cleaned and "," in cleaned:
        dec = "." if cleaned.rfind(".") > cleaned.rfind(",") else ","
        other = "," if dec == "." else "."
        int_part, frac = cleaned.rsplit(dec, 1)
        return float(int_part.replace(other, "") + "." + frac)
    if "." in cleaned or "," in cleaned:
        sep = "." if "." in cleaned else ","
        head, frac = cleaned.rsplit(sep, 1)
        if len(frac) == 3:  # thousands, not decimals
            return float(head.replace(sep, "") + frac)
        return float(head.replace(sep, "") + "." + frac)
    return float(cleaned)
_AFTER = r"\s*[:\s]+\s*"  # separator between label and value (may cross lines)
# money labels must have their value on the same line: a table header like
# "Gross worth" is followed on the next line by item quantities (measured)
_AFTER_MONEY = r"[ \t:]+"

# doc_type -> field -> regex patterns (first match in reading order wins).
# Named groups: val = the value, sym = optional currency marker for money.
# \b on every label: without it "Subtotal" feeds the total field (measured).
_SCHEMAS: dict[str, dict[str, tuple[str, ...]]] = {
    "invoice": {
        "invoice_no": (
            r"invoice\s*(?:no|number|num|#|id)?\s*[:#]\s*"
            r"(?P<val>[A-Za-z0-9][A-Za-z0-9/-]*)",
        ),
        "issue_date": (
            r"date\s*(?:of\s*issue)?\s*[:]\s*"
            r"(?P<val>[0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})",
            r"(?P<val>[0-9]{4}-[0-9]{2}-[0-9]{2})",
        ),
        "due_date": (
            r"due\s*date\s*[:]\s*(?P<val>[0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{2,4})",
        ),
        "subtotal": (rf"\bsub\s*-?\s*total\b{_AFTER_MONEY}{_SYM}\s*{_MONEY}",),
        "discount": (rf"\bdiscount\b{_AFTER_MONEY}{_SYM}\s*{_MONEY}",),
        "shipping": (rf"\bshipping\b{_AFTER_MONEY}{_SYM}\s*{_MONEY}",),
        "tax": (
            rf"\b(?:tax|vat|gst)\b(?:[ \t]*(?:amount|amt|@[^:\n]*?|\([^)\n]*\)))?"
            rf"{_AFTER_MONEY}{_SYM}\s*{_MONEY}",
        ),
        "total": (
            # pattern order is priority: a gross-total line beats an earlier
            # plain-total line (mychen76 prints the net total first)
            rf"\bgross\s*(?:worth|total|amount)\b{_AFTER_MONEY}{_SYM}\s*{_MONEY}",
            rf"\b(?:grand\s*total|total\s*due|amount\s*due|balance\s*due|total)\b"
            rf"{_AFTER_MONEY}{_SYM}\s*{_MONEY}",
        ),
    },
}

_SYMBOL_CURRENCY = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY",
                    "HK$": "HKD", "US$": "USD", "CA$": "CAD", "AU$": "AUD",
                    "NZ$": "NZD", "NT$": "TWD", "S$": "SGD",
                    "USD": "USD", "EUR": "EUR", "GBP": "GBP", "HKD": "HKD",
                    "JPY": "JPY", "CNY": "CNY", "TWD": "TWD", "AUD": "AUD",
                    "CAD": "CAD", "SGD": "SGD"}
_MONEY_FIELDS = ("subtotal", "discount", "shipping", "tax", "total")
# both day-first and month-first: the check catches OCR garble (13/45), it
# does not decide which of two valid readings is meant
_DATE_FORMATS = ("%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y", "%d-%m-%Y",
                 "%Y-%m-%d", "%d/%m/%y", "%m/%d/%y")
_TOLERANCE = 0.02  # cents-level OCR jitter plus rounding; money stays flagged, never fixed

_TAGS = re.compile(r"<[^>]+>")
_ROWS = re.compile(r"<tr\b.*?</tr>", re.IGNORECASE | re.DOTALL)
_CELLS = re.compile(r"<t[dh]\b.*?</t[dh]>", re.IGNORECASE | re.DOTALL)


def extract_document(
    blocks: list[dict[str, Any]], doc_type: str
) -> tuple[dict[str, Any], list[str]]:
    """Blocks -> (extracted fields, quality flags). Pure; no writes."""
    schema = _SCHEMAS.get(doc_type)
    if not schema:
        return {}, []
    extracted = _extract_fields(blocks, schema)
    flags = _validate_dates(extracted)
    flags += _validate_total(extracted)
    flags += _validate_line_items(blocks, extracted)
    _mark_needs_review(extracted, flags)
    return extracted, flags


def _plain_text(content: str) -> str:
    """Table HTML flattened to text: </tr> becomes a newline (row boundary -
    keeps a header like 'Gross worth' off the same line as item quantities),
    other tags become spaces so 'Subtotal</td><td>2,850.00' stays matchable.
    Trailing spaces are stripped per line: a leftover space before the
    newline would let the same-line rule cross rows anyway."""
    if "<" in content:
        with_rows = re.sub(r"</tr\s*>", "\n", content, flags=re.IGNORECASE)
        flattened = _TAGS.sub(" ", with_rows)
        return re.sub(r"[ \t]+\n", "\n", flattened)
    return content


def _extract_fields(
    blocks: list[dict[str, Any]], schema: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    """entry = {value, block id (None when the match spans blocks), symbol?}."""
    texts = [(b["id"], _plain_text(str(b.get("content") or ""))) for b in blocks]
    # measured on real samples (mychen76): the label and the value often land
    # in separate blocks ("Date of issue:" then "07/06/2014"), so fields not
    # found in a single block get one pass over the joined text (block=None)
    joined = (None, "\n".join(text for _, text in texts))
    out: dict[str, Any] = {}
    for field, patterns in schema.items():
        # pattern order is priority, then reading order within a pattern
        for pattern in patterns:
            for block_id, text in [*texts, joined]:
                m = re.search(pattern, text, re.IGNORECASE)
                if not m or m.group("val") is None:
                    continue
                entry: dict[str, Any] = {"value": m.group("val").strip(), "block": block_id}
                if field in _MONEY_FIELDS:
                    entry["value"] = _parse_amount(m.group("val"))
                    sym = m.group("sym")
                    entry["symbol"] = sym.strip() if sym else None
                out[field] = entry
                break
            if field in out:
                break
    _assign_currency(out)
    return out


def _assign_currency(extracted: dict[str, Any]) -> None:
    """One currency per document, taken from the total (fall back to any money field)."""
    for field in ("total", "tax", "subtotal"):
        entry = extracted.get(field)
        if entry and entry.get("symbol"):
            extracted["currency"] = {
                "value": _SYMBOL_CURRENCY.get(entry["symbol"], entry["symbol"]),
                "block": entry["block"],
            }
            return


def _validate_dates(extracted: dict[str, Any]) -> list[str]:
    flags = []
    for field in ("issue_date", "due_date"):
        entry = extracted.get(field)
        if not entry:
            continue
        raw = str(entry["value"])
        if not any(_parse_date(raw, f) for f in _DATE_FORMATS):
            flags.append(f"date_invalid:{field}")
    return flags


def _parse_date(raw: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(raw, fmt)
    except ValueError:
        return None


def _validate_total(extracted: dict[str, Any]) -> list[str]:
    """subtotal - discount + shipping + tax == total (only when checkable).

    shortcut: flags assume no other charge types (fees, multi-rate tax);
    those invoices will flag - accepted until measurement says otherwise.
    """
    total = extracted.get("total")
    subtotal = extracted.get("subtotal")
    if not total or not subtotal:
        return []
    amount = lambda f: extracted[f]["value"] if f in extracted else 0.0  # noqa: E731
    if "tax" in extracted:
        expected = subtotal["value"] - amount("discount") + amount("shipping") + amount("tax")
        if abs(expected - total["value"]) > _TOLERANCE:
            return ["math:total_mismatch"]
        return []
    if abs(subtotal["value"] - total["value"]) > _TOLERANCE:
        return ["math:tax_missing"]  # total differs but no tax was extracted
    return []


def _validate_line_items(blocks: list[dict[str, Any]], extracted: dict[str, Any]) -> list[str]:
    """qty x unit price == amount per row (tables with a recognizable header),
    and items sum == subtotal when three or more rows parsed."""
    flags: list[str] = []
    items_sum: list[float] = []
    for b in blocks:
        content = str(b.get("content") or "")
        if not (b.get("label") == "table" or "<table" in content.lower()):
            continue
        rows = [
            [_TAGS.sub("", cell).strip() for cell in _CELLS.findall(row)]
            for row in _ROWS.findall(content)
        ]
        header = _header_map(rows[0]) if rows else {}
        if not all(k in header for k in ("qty", "price", "amount")):
            continue
        for i, cells in enumerate(rows[1:], start=1):
            qty = _number(cells[header["qty"]]) if header["qty"] < len(cells) else None
            price = _number(cells[header["price"]]) if header["price"] < len(cells) else None
            line = _number(cells[header["amount"]]) if header["amount"] < len(cells) else None
            if line is None:
                continue
            items_sum.append(line)
            if qty is None or price is None:
                continue
            if abs(qty * price - line) > _TOLERANCE:
                flags.append(f"math:line_item:block-{b['id']}:row-{i}")
    subtotal = extracted.get("subtotal")
    if subtotal and len(items_sum) >= 3:
        if abs(sum(items_sum) - subtotal["value"]) > _TOLERANCE * len(items_sum):
            flags.append("math:items_sum")
    return flags


def _header_map(header_cells: list[str]) -> dict[str, int]:
    low = [c.lower() for c in header_cells]
    out: dict[str, int] = {}
    for i, cell in enumerate(low):
        if "qty" in cell or "quantity" in cell:
            out["qty"] = i
        elif "price" in cell or "rate" in cell:
            out["price"] = i
        elif "amount" in cell or "line total" in cell or cell == "total":
            out["amount"] = i
    return out


_NUMBER_CELL = re.compile(
    r"[#$£€¥HKUSCANZT]*\$?\s*"
    r"(-?[0-9]{1,3}(?:[.,][0-9]{3})+(?:[.,][0-9]{1,2})?|-?[0-9]+[.,][0-9]{1,2}|-?[0-9]+)"
)


def _number(cell: str) -> float | None:
    m = _NUMBER_CELL.fullmatch(cell.strip())
    return _parse_amount(m.group(1)) if m else None


def _mark_needs_review(extracted: dict[str, Any], flags: list[str]) -> None:
    for flag in flags:
        if flag.startswith("date_invalid:"):
            field = flag.split(":", 1)[1]
            if field in extracted:
                extracted[field]["needs_review"] = True
        elif flag.startswith("math:"):
            for field in _MONEY_FIELDS + ("currency",):
                if field in extracted:
                    extracted[field]["needs_review"] = True
