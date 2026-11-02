from __future__ import annotations

import pytest

from app.blocks import markdown_text, normalize_blocks, sanitize_table_html


class FakeNdarray:
    """Mimics numpy array exposing tolist()."""

    def __init__(self, vals: list[float]) -> None:
        self._vals = vals

    def tolist(self) -> list[float]:
        return list(self._vals)


def test_normalize_sorts_by_reading_order() -> None:
    res = {
        "parsing_res_list": [
            {
                "block_id": 1, "block_order": 1, "block_label": "text",
                "block_bbox": [1, 2, 3, 4], "block_content": "b",
            },
            {
                "block_id": 0, "block_order": 0, "block_label": "text",
                "block_bbox": FakeNdarray([5, 6, 7, 8]), "block_content": "a",
            },
        ]
    }
    blocks = normalize_blocks(res)
    assert [b["id"] for b in blocks] == [0, 1]
    assert blocks[0]["bbox"] == [5.0, 6.0, 7.0, 8.0]  # numpy-like bbox converted
    assert blocks[1]["bbox"] == [1.0, 2.0, 3.0, 4.0]


def test_duplicate_text_blocks_keep_distinct_ids() -> None:
    res = {
        "parsing_res_list": [
            {
                "block_id": 3, "block_order": 0, "block_label": "text",
                "block_bbox": [0, 0, 10, 10], "block_content": "Hong Kong",
            },
            {
                "block_id": 7, "block_order": 1, "block_label": "text",
                "block_bbox": [0, 20, 10, 30], "block_content": "Hong Kong",
            },
        ]
    }
    blocks = normalize_blocks(res)
    assert [b["id"] for b in blocks] == [3, 7]  # sync by id, never by text


def test_table_html_is_sanitized() -> None:
    dirty = (
        '<table onclick="steal()"><caption>ok</caption>'
        '<tr><th colspan="2">A</th></tr>'
        "<tr><td><script>alert(1)</script>safe&amp;text</td>"
        '<td><img src=x onerror="alert(2)">x</td></tr></table>'
    )
    cleaned = sanitize_table_html(dirty)
    assert "<table" in cleaned
    assert 'colspan="2"' in cleaned
    assert "<script" not in cleaned
    assert "<img" not in cleaned
    assert "onclick" not in cleaned
    assert "onerror" not in cleaned


def test_non_table_block_gets_no_html_field() -> None:
    res = {
        "parsing_res_list": [
            {
                "block_id": 0, "block_order": 0, "block_label": "text",
                "block_bbox": [0, 0, 1, 1], "block_content": "<b>not really html</b>",
            }
        ]
    }
    blocks = normalize_blocks(res)
    assert blocks[0]["content_html"] is None
    assert blocks[0]["content"] == "<b>not really html</b>"  # raw text, escaped client-side


def test_table_detected_by_content_even_if_label_differs() -> None:
    res = {
        "parsing_res_list": [
            {
                "block_id": 0, "block_order": 0, "block_label": "text",
                "block_bbox": [0, 0, 1, 1],
                "block_content": "<table><tr><td>x</td></tr></table>",
            }
        ]
    }
    assert normalize_blocks(res)[0]["content_html"] is not None


def test_markdown_text_variants() -> None:
    assert markdown_text({"markdown": {"text": "# hi"}}) == "# hi"
    assert markdown_text({"markdown": "plain"}) == "plain"
    assert markdown_text({}) == ""


def test_normalize_document_pages_order_and_ids() -> None:
    from app.blocks import normalize_document

    page0 = {"parsing_res_list": [
        {"block_id": 0, "block_order": 0, "block_label": "text",
         "block_bbox": [0, 0, 10, 10], "block_content": "a",
         "global_block_id": 0, "global_group_id": 0},
        {"block_id": 1, "block_order": None, "block_label": "table",
         "block_bbox": [0, 20, 10, 30], "block_content": "<table></table>",
         "global_block_id": 5, "global_group_id": 5},
    ]}
    page1 = {"parsing_res_list": [
        {"block_id": 0, "block_order": 0, "block_label": "text",
         "block_bbox": [0, 0, 10, 10], "block_content": "b",
         "global_block_id": 9, "global_group_id": 9},
    ]}
    blocks = normalize_document([page0, page1])
    assert [(b["id"], b["page"]) for b in blocks] == [(0, 0), (5, 0), (9, 1)]
    assert blocks[1]["order"] == 5  # order falls back to global id when null


def test_normalize_document_merges_cross_page_fragment_span() -> None:
    from app.blocks import normalize_document

    page0 = {"parsing_res_list": [
        {"block_id": 0, "block_order": 0, "block_label": "table",
         "block_bbox": [0, 0, 10, 10], "block_content": "<table><tr><td>full</td></tr></table>",
         "global_block_id": 5, "global_group_id": 5},
    ]}
    page1 = {"parsing_res_list": [
        # continuation fragment: emptied by the engine, group-linked to id 5
        {"block_id": 0, "block_order": 0, "block_label": "table",
         "block_bbox": [0, 0, 10, 10], "block_content": "",
         "global_block_id": 7, "global_group_id": 5},
    ]}
    blocks = normalize_document([page0, page1])
    assert len(blocks) == 1  # fragment not emitted
    assert blocks[0]["page"] == 0 and blocks[0]["page_end"] == 1


def test_document_markdown_joins_pages() -> None:
    from app.blocks import document_markdown

    md = document_markdown([{"markdown": {"text": "p1"}}, {"markdown": {"text": "p2"}}])
    assert md == "p1\n\np2"


def test_normalize_document_span_owner_carries_page_bboxes() -> None:
    from app.blocks import normalize_document

    page0 = {"parsing_res_list": [
        {"block_id": 0, "block_order": 0, "block_label": "table",
         "block_bbox": [1, 2, 3, 4], "block_content": "<table></table>",
         "global_block_id": 5, "global_group_id": 5},
    ]}
    page1 = {"parsing_res_list": [
        {"block_id": 0, "block_order": 0, "block_label": "table",
         "block_bbox": [5, 6, 7, 8], "block_content": "",
         "global_block_id": 7, "global_group_id": 5},
    ]}
    blocks = normalize_document([page0, page1])
    assert blocks[0]["page_bboxes"] == [
        {"page": 0, "bbox": [1, 2, 3, 4]},
        {"page": 1, "bbox": [5, 6, 7, 8]},
    ]


def test_normalize_document_requires_global_ids() -> None:
    from app.blocks import normalize_document

    missing = {"parsing_res_list": [
        {"block_id": 0, "block_order": 0, "block_label": "text",
         "block_bbox": [0, 0, 10, 10], "block_content": "x"},
    ]}
    with pytest.raises(ValueError, match="global_block_id"):
        normalize_document([missing])
