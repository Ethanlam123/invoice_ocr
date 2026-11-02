from __future__ import annotations

import io

import pytest
from PIL import Image

from app import config
from app.images import ImageValidationError, load_normalized

from .conftest import png_bytes


def test_valid_png_normalizes() -> None:
    img = load_normalized(png_bytes(200, 150))
    assert (img.width, img.height) == (200, 150)
    assert img.png[:8] == b"\x89PNG\r\n\x1a\n"  # re-encoded as PNG


def test_exif_orientation_is_transposed() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 CW for display
    buf = io.BytesIO()
    Image.new("RGB", (400, 200), (9, 99, 199)).save(buf, format="JPEG", exif=exif)
    img = load_normalized(buf.getvalue())
    assert (img.width, img.height) == (200, 400)  # display orientation


def test_random_bytes_rejected() -> None:
    with pytest.raises(ImageValidationError) as ei:
        load_normalized(b"definitely not an image")
    assert ei.value.code == "undecodable"


def test_truncated_png_rejected() -> None:
    whole = png_bytes(300, 200)
    with pytest.raises(ImageValidationError) as ei:
        load_normalized(whole[: len(whole) // 2])
    assert ei.value.code == "undecodable"


def test_non_allowed_format_rejected() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (300, 200)).save(buf, format="GIF")
    with pytest.raises(ImageValidationError) as ei:
        load_normalized(buf.getvalue())
    assert ei.value.code == "unsupported_format"


def test_too_small_rejected() -> None:
    with pytest.raises(ImageValidationError) as ei:
        load_normalized(png_bytes(20, 20))
    assert ei.value.code == "too_small"


def test_too_many_pixels_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_PIXELS", 1000)
    with pytest.raises(ImageValidationError) as ei:
        load_normalized(png_bytes(200, 150))
    assert ei.value.code == "too_many_pixels"


def test_file_too_large_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_FILE_BYTES", 10)
    with pytest.raises(ImageValidationError) as ei:
        load_normalized(png_bytes(200, 150))
    assert ei.value.code == "file_too_large"


def _pdf(pages: list[tuple[int, int]]) -> bytes:
    imgs = [Image.new("RGB", size, "white") for size in pages]
    buf = io.BytesIO()
    imgs[0].save(buf, save_all=True, append_images=imgs[1:], format="PDF", resolution=150)
    return buf.getvalue()


def test_is_pdf_magic() -> None:
    from app.images import is_pdf

    assert is_pdf(b"%PDF-1.4 ...") is True
    assert is_pdf(png_bytes(60, 60)) is False
    assert is_pdf(b"") is False


def test_render_pdf_pages_dims_and_png() -> None:
    from app.images import render_pdf_pages

    pages = render_pdf_pages(_pdf([(300, 400), (300, 400)]))
    assert len(pages) == 2
    assert (pages[0].width, pages[0].height) == (300, 400)
    assert pages[0].png.startswith(b"\x89PNG")  # inference input is PNG
    assert (pages[1].width, pages[1].height) == (300, 400)


def test_render_pdf_page_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.images import render_pdf_pages

    monkeypatch.setattr(config, "MAX_PDF_PAGES", 2)
    with pytest.raises(ImageValidationError) as ei:
        render_pdf_pages(_pdf([(60, 60)] * 3))
    assert ei.value.code == "too_many_pages"


def test_render_pdf_corrupt_rejected() -> None:
    from app.images import render_pdf_pages

    with pytest.raises(ImageValidationError) as ei:
        render_pdf_pages(b"%PDF-1.4 not really a pdf")
    assert ei.value.code == "undecodable"


def test_render_pdf_too_small_page_rejected() -> None:
    from app.images import render_pdf_pages

    with pytest.raises(ImageValidationError) as ei:
        render_pdf_pages(_pdf([(20, 30)]))
    assert ei.value.code == "too_small"


def test_render_pdf_pixel_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.images import render_pdf_pages

    monkeypatch.setattr(config, "MAX_PIXELS", 1000)
    with pytest.raises(ImageValidationError) as ei:
        render_pdf_pages(_pdf([(600, 800)]))
    assert ei.value.code == "too_many_pixels"
