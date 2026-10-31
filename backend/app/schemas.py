"""API response models (envelope per project conventions)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BlockOut(BaseModel):
    id: int
    order: int
    label: str
    bbox: list[float]
    content: str
    content_html: str | None = None


class ImageOut(BaseModel):
    width: int
    height: int
    mime: str
    data_url: str


class OcrData(BaseModel):
    image: ImageOut
    blocks: list[BlockOut]
    markdown: str
    raw: dict[str, Any]


class ErrorOut(BaseModel):
    code: str
    message: str


class Envelope(BaseModel):
    success: bool
    data: OcrData | None = None
    error: ErrorOut | None = None
    meta: dict[str, Any] | None = None
