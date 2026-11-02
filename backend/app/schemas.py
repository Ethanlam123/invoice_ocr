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
    reviewed: bool = False  # a human correction is stored for this block


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


class DocumentSummary(BaseModel):
    id: int
    filename: str
    doc_type: str
    page_count: int
    quality_flags: list[str]
    created_at: str


class DocumentListData(BaseModel):
    documents: list[DocumentSummary]


class BlockCorrection(BaseModel):
    corrected_content: str


class ErrorOut(BaseModel):
    code: str
    message: str


class Envelope(BaseModel):
    success: bool
    data: OcrData | DocumentListData | None = None
    error: ErrorOut | None = None
    meta: dict[str, Any] | None = None
