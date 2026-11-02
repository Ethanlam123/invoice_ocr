"""Upload validation and EXIF normalization.

The pipeline and the viewer must see the same pixels, so we EXIF-transpose the
image once here and re-encode to PNG. All downstream coordinates (block_bbox)
and the data URL served to the frontend refer to this normalized image.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Protocol

from PIL import Image, ImageOps

from . import config


class ImageValidationError(ValueError):
    """Raised when an upload fails validation. `code` maps to an API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class NormalizedImage:
    png: bytes
    width: int
    height: int


class AsyncReader(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


async def read_upload_capped(file: AsyncReader) -> bytes:
    """Read an upload in chunks, rejecting oversized bodies before buffering
    them fully into memory (the multipart body has no server-side cap)."""
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1 << 20):
        total += len(chunk)
        if total > config.MAX_FILE_BYTES:
            raise ImageValidationError(
                "file_too_large",
                f"File exceeds {config.MAX_FILE_BYTES // (1024 * 1024)} MB limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def is_pdf(data: bytes) -> bool:
    """PDF uploads are detected by magic bytes, like image format detection."""
    return data.startswith(config.PDF_MAGIC)


def render_pdf_pages(data: bytes) -> list[NormalizedImage]:
    """Render PDF bytes to per-page PNGs (no EXIF step: PDF pages have none).

    The rendered pages are both the pipeline input and the viewer images, so
    block_bbox coordinates keep the same guarantee as image uploads.
    """
    import pypdfium2 as pdfium

    try:
        doc = pdfium.PdfDocument(data)
        page_count = len(doc)
        if page_count == 0:
            raise ImageValidationError("undecodable", "PDF has no pages.")
        if page_count > config.MAX_PDF_PAGES:
            raise ImageValidationError(
                "too_many_pages",
                f"PDF has {page_count} pages; limit is {config.MAX_PDF_PAGES}.",
            )
        pages: list[NormalizedImage] = []
        for page in doc:
            img = page.render(scale=config.PDF_RENDER_DPI / 72).to_pil().convert("RGB")
            width, height = img.size
            if min(width, height) < config.MIN_SIDE:
                raise ImageValidationError(
                    "too_small",
                    f"PDF page renders to {width}x{height}px at {config.PDF_RENDER_DPI} DPI; "
                    f"minimum side is {config.MIN_SIDE}px.",
                )
            if width * height > config.MAX_PIXELS:
                raise ImageValidationError(
                    "too_many_pixels",
                    f"PDF page renders to {width * height:,} pixels at "
                    f"{config.PDF_RENDER_DPI} DPI; limit is {config.MAX_PIXELS:,}.",
                )
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            pages.append(NormalizedImage(png=buf.getvalue(), width=width, height=height))
        return pages
    except ImageValidationError:
        raise
    except Exception as exc:
        raise ImageValidationError("undecodable", f"PDF cannot be rendered: {exc}") from exc


def load_normalized(data: bytes) -> NormalizedImage:
    """Validate raw upload bytes and return an EXIF-normalized PNG.

    Validation is by actual decode, never by filename or extension.
    """
    if len(data) > config.MAX_FILE_BYTES:
        raise ImageValidationError(
            "file_too_large",
            f"File exceeds {config.MAX_FILE_BYTES // (1024 * 1024)} MB limit.",
        )

    try:
        img = Image.open(io.BytesIO(data))
        fmt, (width, height) = img.format, img.size
    except Exception as exc:
        raise ImageValidationError("undecodable", "File is not a decodable image.") from exc

    if fmt not in config.ALLOWED_FORMATS:
        raise ImageValidationError(
            "unsupported_format", f"Unsupported image format '{fmt}'. Upload JPG or PNG."
        )
    if min(width, height) < config.MIN_SIDE:
        raise ImageValidationError(
            "too_small",
            f"Image is too small ({width}x{height}); minimum side is {config.MIN_SIDE}px.",
        )
    if width * height > config.MAX_PIXELS:
        raise ImageValidationError(
            "too_many_pixels",
            f"Image has {width * height:,} pixels; limit is {config.MAX_PIXELS:,}.",
        )

    try:
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
    except Exception as exc:
        raise ImageValidationError("undecodable", "Image data is corrupt or truncated.") from exc

    return NormalizedImage(png=buf.getvalue(), width=img.width, height=img.height)
