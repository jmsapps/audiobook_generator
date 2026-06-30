"""Language-aware segmentation of a page's text into TTS-sized chunks.

Sentence boundaries come from ``pysbd`` when it supports the language, otherwise from a simple
regex splitter (``pysbd`` does not cover every language — e.g. Portuguese). Sentences are then
greedily packed into groups up to a character budget so long pages synthesize in bounded memory
while never splitting mid-sentence.
"""

from __future__ import annotations

import re

import pysbd

DEFAULT_MAX_CHARS = 800

# Source of truth for which languages pysbd can segment (varies by version). Anything not here
# falls back to the regex splitter below.
try:
    from pysbd.languages import LANGUAGE_CODES as _PYSBD_CODES

    _SUPPORTED = set(_PYSBD_CODES.keys())
except Exception:  # pragma: no cover - defensive
    _SUPPORTED = {"en"}

# Split after sentence-ending punctuation. Used for languages pysbd lacks (e.g. pt); the packer
# re-joins short fragments, so an occasional split after an abbreviation is harmless.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def _base_lang(language: str) -> str:
    return (language or "en").split("-")[0].lower()


def supports_pysbd(language: str) -> bool:
    return _base_lang(language) in _SUPPORTED


def _sentences(text: str, lang: str) -> list[str]:
    if lang in _SUPPORTED:
        seg = pysbd.Segmenter(language=lang, clean=False)
        return [s.strip() for s in seg.segment(text) if s.strip()]
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def split_segments(
    text: str, language: str = "en", max_chars: int = DEFAULT_MAX_CHARS
) -> list[str]:
    """Return a list of narration chunks, each <= ~max_chars, on sentence boundaries."""
    text = text.strip()
    if not text:
        return []

    lang = _base_lang(language)
    sentences: list[str] = []
    # Segment per paragraph so blank-line structure is preserved as natural pauses.
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        sentences.extend(_sentences(para.replace("\n", " "), lang))

    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        # A single sentence longer than the budget becomes its own chunk.
        if len(sentence) > max_chars and buf:
            chunks.append(buf)
            buf = ""
        if not buf:
            buf = sentence
        elif len(buf) + 1 + len(sentence) <= max_chars:
            buf = f"{buf} {sentence}"
        else:
            chunks.append(buf)
            buf = sentence
    if buf:
        chunks.append(buf)
    return chunks
