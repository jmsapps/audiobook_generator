"""Reading-order (XY-cut), drop-cap merge, and text-cleanup tests."""

from __future__ import annotations

from audiobook_generator.pdf_extract import (
    _Block,
    _clean,
    _line_unit,
    _merge_drop_caps,
    _xy_cut,
    extract_page_text,
    page_count,
)


def test_xy_cut_two_columns_with_spanning_header():
    # A centered header straddles the gutter; left column then right column below it.
    blocks = [
        _Block(255, 29, 363, 42, "HEADER"),
        _Block(65, 83, 300, 96, "L1"),
        _Block(65, 100, 300, 300, "L2"),
        _Block(320, 83, 556, 300, "R1"),
        _Block(320, 310, 556, 400, "R2"),
    ]
    order = [b.text for b in _xy_cut(blocks, 13.0)]
    assert order == ["HEADER", "L1", "L2", "R1", "R2"]


def test_xy_cut_single_block():
    assert [b.text for b in _xy_cut([_Block(0, 0, 10, 10, "X")], 13.0)] == ["X"]


def test_xy_cut_single_column_preserves_order():
    blocks = [
        _Block(65, 100, 300, 120, "first"),
        _Block(65, 140, 300, 160, "second"),
        _Block(65, 180, 300, 200, "third"),
    ]
    assert [b.text for b in _xy_cut(blocks, 13.0)] == ["first", "second", "third"]


def test_merge_drop_cap_joins_to_right_neighbor():
    cap = _Block(65, 85, 105, 127, "T")            # tall single letter
    line = _Block(106, 83, 300, 96, "o continues here")
    out = _merge_drop_caps([cap, line], 13.0)
    texts = [b.text for b in out]
    assert texts == ["To continues here"]


def test_merge_drop_cap_picks_same_column_not_other():
    cap = _Block(65, 85, 105, 127, "T")
    same_col = _Block(106, 83, 300, 96, "o the left")
    other_col = _Block(320, 86, 556, 300, "right column line")
    out = _merge_drop_caps([cap, same_col, other_col], 13.0)
    texts = [b.text for b in out]
    assert "To the left" in texts
    assert "right column line" in texts


def test_clean_removes_dot_leaders():
    assert _clean("Chapter One . . . . . . .") == "Chapter One"


def test_clean_keeps_ellipsis():
    assert "..." in _clean("Wait... what happens")


def test_clean_dehyphenates_across_linebreak():
    assert _clean("exam-\nple") == "example"


def test_clean_drops_bare_page_number():
    assert _clean("Body text here\n42") == "Body text here"


def test_clean_keeps_roman_looking_words():
    # Arabic-only page-number rule: must NOT delete real words like "mix"/"did".
    out = _clean("mix\nDid you know")
    assert "mix" in out
    assert "Did you know" in out


def test_line_unit_uses_low_percentile():
    blocks = [_Block(0, 0, 10, h, "x") for h in (10, 10, 10, 10, 40, 40, 80)]
    assert _line_unit(blocks, 792) == 10


def test_extract_real_pdf(tmp_path):
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Hello world.", fontsize=12)
    page.insert_text((72, 130), "This is a test sentence.", fontsize=12)
    pdf = tmp_path / "t.pdf"
    doc.save(pdf)
    doc.close()

    assert page_count(str(pdf)) == 1
    text = extract_page_text(str(pdf), 1)
    assert "Hello world." in text
    assert "test sentence" in text
