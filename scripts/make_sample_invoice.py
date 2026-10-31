"""Generate a synthetic test invoice PNG (ours, committable - no third-party data).

Creates a realistic single-page invoice with a table, duplicate text ("Hong Kong"
appears in two address blocks), and punctuation-heavy notes, for OCR pipeline testing.

Usage: uv run --project backend python scripts/make_sample_invoice.py [out.png]
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1240, 1600
INK = (24, 24, 27)
MUTED = (90, 90, 95)
LINE = (180, 180, 185)
ACCENT = (30, 90, 180)

FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]
BOLD_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def load(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/invoice_sample.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    f_title = load(BOLD_PATHS, 58)
    f_head = load(BOLD_PATHS, 26)
    f_body = load(FONT_PATHS, 26)
    f_small = load(FONT_PATHS, 20)

    # Header
    d.text((80, 70), "INVOICE", font=f_title, fill=INK)
    d.text((80, 140), "Invoice # INV-2026-0042", font=f_body, fill=MUTED)
    for i, line in enumerate(["Date: 2026-10-31", "Due Date: 2026-11-14", "Terms: Net 14"]):
        d.text((830, 80 + i * 36), line, font=f_body, fill=INK)

    # Parties (duplicate city text on purpose: selection-sync test)
    d.text((80, 260), "FROM", font=f_head, fill=ACCENT)
    for i, line in enumerate(
        ["Acme Consulting Ltd.", "123 Harbour Road", "Wan Chai, Hong Kong", "billing@acme.example"]
    ):
        d.text((80, 300 + i * 34), line, font=f_body, fill=INK)

    d.text((660, 260), "BILL TO", font=f_head, fill=ACCENT)
    for i, line in enumerate(
        ["Globex Corporation", "55 King Street", "Tsim Sha Tsui, Hong Kong", "ap@globex.example"]
    ):
        d.text((660, 300 + i * 34), line, font=f_body, fill=INK)

    # Table
    y0 = 500
    rows = [
        ("Description", "Qty", "Unit Price", "Amount"),
        ("Document parsing service", "1", "4,500.00", "4,500.00"),
        ("OCR pipeline integration", "2", "1,200.00", "2,400.00"),
        ("R&D support retainer", "1", "800.00", "800.00"),
        ("Q&A session package", "3", "300.00", "900.00"),
    ]
    col_x = [80, 720, 880, 1060]
    row_h = 52

    d.rectangle([80, y0, 1160, y0 + row_h], fill=(238, 240, 244))
    for cx in [720, 880, 1060, 1160]:
        d.line([(cx, y0), (cx, y0 + row_h * len(rows))], fill=LINE, width=2)
    for r, row in enumerate(rows):
        y = y0 + r * row_h
        d.line([(80, y), (1160, y)], fill=LINE, width=2)
        for c, cell in enumerate(row):
            font = f_head if r == 0 else f_body
            fill = INK if r > 0 else (60, 60, 65)
            align_right = c > 0
            x = col_x[c] + (10 if not align_right else 0)
            if align_right:
                tw = d.textlength(cell, font=font)
                x = (1160 if c == 3 else col_x[c + 1] - 12) - tw
            d.text((x, y + 12), cell, font=font, fill=fill)
    d.line([(80, y0 + row_h * len(rows)), (1160, y0 + row_h * len(rows))], fill=LINE, width=2)

    # Totals
    ty = y0 + row_h * len(rows) + 40
    for label, value in [("Subtotal", "8,600.00"), ("Tax (10%)", "860.00")]:
        d.text((850, ty), label, font=f_body, fill=MUTED)
        d.text((1020, ty), value, font=f_body, fill=INK)
        ty += 40
    d.text((850, ty), "TOTAL", font=f_head, fill=INK)
    d.text((1010, ty), "HKD 9,460.00", font=f_head, fill=INK)

    # Notes with punctuation / entity-like text (XSS-rendering test)
    ny = ty + 80
    d.text((80, ny), "Notes", font=f_head, fill=ACCENT)
    d.text(
        (80, ny + 38),
        "Payment by bank transfer. Quote <b>INV-2026-0042</b> & ref #A-1024/7.",
        font=f_body,
        fill=INK,
    )
    d.text((80, ny + 74), "Late fee: 1.5% <per month> on overdue amounts.", font=f_body, fill=INK)

    # Footer
    d.text((80, H - 120), "Thank you for your business.", font=f_body, fill=INK)
    d.text((80, H - 86), "Acme Consulting Ltd. - Document Processing & AI Solutions", font=f_small, fill=MUTED)
    d.text((80, H - 58), "Page 1 of 1", font=f_small, fill=MUTED)

    img.save(out, "PNG")
    print(f"wrote {out} ({W}x{H})")


if __name__ == "__main__":
    main()
