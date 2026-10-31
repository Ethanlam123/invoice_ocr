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
