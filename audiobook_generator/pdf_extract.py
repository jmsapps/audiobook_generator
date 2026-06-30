"""Layout-adaptive, per-page PDF text extraction using PyMuPDF.

Reading order is recovered with a recursive **XY-cut**: the page's text blocks are repeatedly
split along the widest full-width horizontal gap (separating stacked bands like a chapter header,
body, footer) or the widest vertical gap (separating columns), choosing whichever gap is more
significant. This adapts to whatever layout a page actually has — one column, two/three columns,
headers that straddle the column gap, sidebars — without hardcoding a column count. Thresholds
scale with the page's typical line height, so it works regardless of font size.

Text is then cleaned for narration: drop-cap letters are rejoined to their word, words hyphenated
across line breaks are merged, table-of-contents dot leaders are removed, and bare page-number
lines are dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import fitz  # PyMuPDF


@dataclass
class _Block:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def h(self) -> float:
        return self.y1 - self.y0


def page_count(pdf_path: str) -> int:
    with fitz.open(pdf_path) as doc:
        return doc.page_count


def _line_unit(blocks: list[_Block], page_height: float) -> float:
    """Estimate a single text-line height (the unit gap thresholds scale from).

    Multi-line paragraph blocks inflate the mean/median, so we use a low percentile of block
    heights, which tracks the single-line blocks (headers, short lines, drop-cap rows).
    """
    heights = sorted(b.h for b in blocks if b.h > 0)
    if not heights:
        return 12.0
    idx = max(0, int(0.2 * (len(heights) - 1)))
    return max(6.0, heights[idx])


def _max_gap(intervals: list[tuple[float, float]]) -> tuple[float, int, list[int]]:
    """Largest gap between sorted 1-D intervals.

    Returns (gap_size, split_index, order) where `order` is the indices sorted by interval start
    and the split puts order[:split_index] before the gap and order[split_index:] after.
    """
    order = sorted(range(len(intervals)), key=lambda i: intervals[i][0])
    best_gap, best_k = 0.0, 0
    running = intervals[order[0]][1]
    for k in range(1, len(order)):
        lo, hi = intervals[order[k]]
        gap = lo - running
        if gap > best_gap:
            best_gap, best_k = gap, k
        running = max(running, hi)
    return best_gap, best_k, order


def _xy_cut(blocks: list[_Block], unit: float) -> list[_Block]:
    """Recursively order blocks into reading order via alternating horizontal/vertical cuts."""
    if len(blocks) <= 1:
        return list(blocks)

    h_gap, h_k, h_order = _max_gap([(b.y0, b.y1) for b in blocks])
    v_gap, v_k, v_order = _max_gap([(b.x0, b.x1) for b in blocks])

    h_min = 0.5 * unit   # full-width whitespace band that stacks sections vertically
    v_min = 1.2 * unit   # whitespace gutter that separates columns (wider than a line)

    can_h = h_gap >= h_min and 0 < h_k < len(blocks)
    can_v = v_gap >= v_min and 0 < v_k < len(blocks)

    # Prefer the more significant cut; on ties cut horizontally (read top-to-bottom first).
    if can_h and (not can_v or h_gap >= v_gap):
        top = [blocks[i] for i in h_order[:h_k]]
        bottom = [blocks[i] for i in h_order[h_k:]]
        return _xy_cut(top, unit) + _xy_cut(bottom, unit)
    if can_v:
        left = [blocks[i] for i in v_order[:v_k]]
        right = [blocks[i] for i in v_order[v_k:]]
        return _xy_cut(left, unit) + _xy_cut(right, unit)

    return sorted(blocks, key=lambda b: (round(b.y0, 1), b.x0))


def _merge_drop_caps(blocks: list[_Block], unit: float) -> list[_Block]:
    """Rejoin an oversized single-letter drop cap to the line it begins.

    A drop cap is a 1-char block much taller than a line; its letter is prepended to the nearest
    block that starts to its right and overlaps it vertically (the first line of the paragraph).
    """
    result = list(blocks)
    caps = [
        b for b in result
        if len(b.text.strip()) == 1 and b.text.strip().isalpha() and b.h > 1.6 * unit
    ]
    for cap in caps:
        candidates = [
            b for b in result
            if b is not cap
            and b.x0 >= cap.x1 - 2
            and b.x0 - cap.x1 < 4 * unit   # same column, immediately to the right
            and b.y1 >= cap.y0
            and b.y0 <= cap.y1
        ]
        if not candidates:
            continue
        # The drop cap's line is the block directly to its right (nearest x0), tie-break by y.
        target = min(candidates, key=lambda b: (b.x0, abs(b.y0 - cap.y0)))
        target.text = cap.text.strip() + target.text.lstrip()
        result.remove(cap)
    return result


_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_DOT_LEADERS = re.compile(r"\s*\.(?:\s*\.){3,}")  # 4+ dots (TOC leaders); keeps "..." ellipsis
_WS = re.compile(r"[ \t]+")
_MULTI_NL = re.compile(r"\n{3,}")
# Bare page-number line, e.g. "42" or "- 42 -". Arabic only: matching roman numerals here would
# wrongly delete real words that wrap onto their own line ("mix", "did", "I").
_PAGE_NUM_LINE = re.compile(r"^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$")


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)        # "exam-\nple" -> "example"
    text = _DOT_LEADERS.sub(" ", text)             # drop TOC dot leaders
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if not _PAGE_NUM_LINE.match(ln)]  # drop bare page numbers
    text = "\n".join(lines)
    text = _WS.sub(" ", text)
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


def extract_page_text(pdf_path: str, page_number: int) -> str:
    """Extract cleaned, reading-order text for a single 1-based page number."""
    with fitz.open(pdf_path) as doc:
        page = doc.load_page(page_number - 1)
        page_height = page.rect.height
        raw = page.get_text("blocks")  # (x0,y0,x1,y1,text,block_no,block_type)

    blocks = [
        _Block(b[0], b[1], b[2], b[3], b[4])
        for b in raw
        if len(b) >= 5 and isinstance(b[4], str) and b[4].strip()
    ]
    if not blocks:
        return ""

    unit = _line_unit(blocks, page_height)
    ordered = _xy_cut(blocks, unit)
    ordered = _merge_drop_caps(ordered, unit)
    return _clean("\n".join(b.text.strip() for b in ordered if b.text.strip()))
