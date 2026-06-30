"""Manifest, hashing, and atomic-write tests."""

from __future__ import annotations

import pytest

from audiobook_generator.state import Manifest, atomic_write, params_hash, text_hash


def test_text_hash_is_stable_and_distinct():
    assert text_hash("hello") == text_hash("hello")
    assert text_hash("hello") != text_hash("world")


def test_params_hash_is_order_independent():
    assert params_hash(a=1, b=2) == params_hash(b=2, a=1)
    assert params_hash(voice="amy") != params_hash(voice="ryan")


def test_atomic_write_creates_file(tmp_path):
    p = tmp_path / "sub" / "out.txt"
    with atomic_write(p, "w", encoding="utf-8") as fh:
        fh.write("content")
    assert p.read_text() == "content"


def test_atomic_write_leaves_original_on_error(tmp_path):
    p = tmp_path / "out.txt"
    p.write_text("original")
    with pytest.raises(RuntimeError):
        with atomic_write(p, "w", encoding="utf-8") as fh:
            fh.write("partial")
            raise RuntimeError("boom")
    assert p.read_text() == "original"
    # No leftover temp files in the directory.
    assert [x.name for x in tmp_path.iterdir()] == ["out.txt"]


def test_manifest_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    m = Manifest(path=path, source_pdf="x.pdf", total_pages=3)
    rec = m.page(1)
    rec.text_hash = "abc"
    rec.audio_done = True
    rec.audio_params = "p1"
    m.combined_done = True
    m.combined_hash = "h1"
    m.save()

    loaded = Manifest.load(path)
    assert loaded.total_pages == 3
    assert loaded.source_pdf == "x.pdf"
    assert loaded.combined_done is True
    assert loaded.combined_hash == "h1"
    assert loaded.page(1).audio_done is True
    assert loaded.page(1).text_hash == "abc"
    assert loaded.page(1).audio_params == "p1"


def test_manifest_load_missing_returns_empty(tmp_path):
    m = Manifest.load(tmp_path / "nope.json")
    assert m.total_pages == 0
    assert m.pages == {}
