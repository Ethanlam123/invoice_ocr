from __future__ import annotations

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
