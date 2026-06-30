"""Sentence segmentation + chunk-packing tests, including the Portuguese fallback."""

from __future__ import annotations

from audiobook_generator.chunking import split_segments, supports_pysbd


def test_pysbd_language_support():
    assert supports_pysbd("en")
    assert supports_pysbd("es")
    assert supports_pysbd("de")
    # pysbd does NOT support Portuguese -> must report unsupported (regex fallback used).
    assert not supports_pysbd("pt")
    assert not supports_pysbd("pt-BR")


def test_empty_input():
    assert split_segments("") == []
    assert split_segments("   \n  ") == []


def test_chunks_respect_budget_and_preserve_content():
    text = " ".join(f"Sentence number {i}." for i in range(50))
    chunks = split_segments(text, "en", max_chars=80)
    assert len(chunks) > 1
    assert all(len(c) <= 80 for c in chunks)
    combined = " ".join(chunks)
    for i in range(50):
        assert f"Sentence number {i}." in combined


def test_long_sentence_becomes_its_own_chunk():
    long_sentence = "word " * 100  # ~500 chars, no sentence-ending punctuation
    chunks = split_segments(long_sentence.strip(), "en", max_chars=60)
    assert len(chunks) == 1
    assert chunks[0].startswith("word")


def test_portuguese_uses_regex_fallback_without_crashing():
    # This is the exact path that previously raised KeyError: 'pt'.
    chunks = split_segments("As armas e os barões assinalados. Que da ocidental praia.", "pt")
    assert len(chunks) >= 1
    assert "barões" in " ".join(chunks)


def test_portuguese_abbreviation_rejoined_by_packer():
    chunks = split_segments("Bom dia, Sr. Silva. Como vai?", "pt", max_chars=200)
    assert chunks == ["Bom dia, Sr. Silva. Como vai?"]
