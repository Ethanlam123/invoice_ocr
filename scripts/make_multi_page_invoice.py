"""Generate a two-page invoice PDF whose item table spans both pages.

Layout follows what the engine's cross-page merge requires
(paddlex merge_table.can_merge_tables): on page 2 the table must be the
first significant block (only header/page-number labels allowed above),
must not repeat the header row, and both tables share the same x-extent
and column count. The totals block sits BELOW the continued table, which
is allowed (only blocks before the table are checked).

Run from the repo root:
  uv run --project backend python scripts/make_multi_page_invoice.py
Writes samples/multi_page_invoice.pdf (ours, committable).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

A4_150 = (1240, 1754)  # A4 at 150 DPI, matches config.PDF_RENDER_DPI
REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

TABLE_X0, TABLE_X1 = 80, 1160
COLS = (80, 460, 760)  # x positions: item, qty, price
P1_ROWS = [
    ("Widget Alpha", "3", "120.00"),
    ("Widget Beta", "1", "340.00"),
    ("Gadget Gamma", "5", "88.50"),
    ("Part Delta", "2", "45.00"),
    ("Part Epsilon", "8", "12.25"),
    ("Service Zeta", "1", "900.00"),
    ("Assembly Eta", "4", "310.00"),
    ("Calibration Theta", "2", "75.00"),
]
P2_ROWS = [
    ("Shipping Iota", "1", "60.00"),
    ("Handling Kappa", "1", "25.00"),
    ("Warranty Lambda", "3", "40.00"),
    ("Inspection Mu", "1", "150.00"),
]


def draw_header(d: ImageDraw.ImageDraw, page_no: int) -> None:
    d.text((80, 60), "ACME SUPPLY LTD.", font=ImageFont.truetype(BOLD, 40), fill="black")
    d.text((80, 120), "Invoice INV-2026-0417", font=ImageFont.truetype(BOLD, 26), fill="black")
    d.text((80, 160), f"Date: 2026-11-01     Page {page_no} of 2",
           font=ImageFont.truetype(REG, 20), fill="black")


def draw_table(d: ImageDraw.ImageDraw, rows: list[tuple[str, str, str]], y: int,
               with_header: bool) -> int:
    body = ImageFont.truetype(REG, 20)
    head = ImageFont.truetype(BOLD, 20)
    if with_header:
        for x, cell in zip(COLS, ("Item", "Qty", "Price")):
            d.text((x, y), cell, font=head, fill="black")
        d.line((TABLE_X0, y + 30, TABLE_X1, y + 30), fill="black", width=2)
        y += 42
    for row in rows:
        for x, cell in zip(COLS, row):
            d.text((x, y), cell, font=body, fill="black")
        d.line((TABLE_X0, y + 28, TABLE_X1, y + 28), fill="black", width=1)
        y += 36
    return y


def main() -> None:
    p1 = Image.new("RGB", A4_150, "white")
    d1 = ImageDraw.Draw(p1)
    draw_header(d1, 1)
    d1.text((80, 240), "Bill To: Demo Customer, 1 Sample Street, Sample City",
            font=ImageFont.truetype(REG, 20), fill="black")
    # table starts low and runs to the bottom edge: continues on page 2
    draw_table(d1, P1_ROWS, y=1180, with_header=True)

    p2 = Image.new("RGB", A4_150, "white")
    d2 = ImageDraw.Draw(p2)
    # page 2 starts directly with the continued rows (no header, nothing above)
    y = draw_table(d2, P2_ROWS, y=70, with_header=False)
    d2.text((80, y + 80), "Subtotal: 3975.50", font=ImageFont.truetype(REG, 20), fill="black")
    d2.text((80, y + 115), "Total Due: 3975.50", font=ImageFont.truetype(BOLD, 24), fill="black")
    d2.text((80, y + 180), "Thank you for your business.",
            font=ImageFont.truetype(REG, 20), fill="black")

    out = Path(__file__).resolve().parent.parent / "samples" / "multi_page_invoice.pdf"
    p1.save(out, save_all=True, append_images=[p2], format="PDF", resolution=150)
    print(f"wrote {out} (2 pages, table spans both)")


if __name__ == "__main__":
    main()
