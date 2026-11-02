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
    page: int = 0
    page_end: int = 0  # > page when the block spans pages (merged table)
    # present only on spanning blocks: one bbox per page (owner first)
    page_bboxes: list[dict[str, Any]] | None = None


class PageOut(BaseModel):
    index: int
    width: int
    height: int
    mime: str
    data_url: str


class OcrData(BaseModel):
    pages: list[PageOut]
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
