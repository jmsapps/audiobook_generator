"""Shared fixtures/helpers for the test suite."""

from __future__ import annotations

import types

import pytest

from audiobook_generator.pipeline import Config


def make_config(tmp_path, **overrides) -> Config:
    """Build a Config rooted at tmp_path; override any field via kwargs."""
    defaults = dict(
        pdf_path=tmp_path / "book.pdf",
        book="book",
        language="en",
        backend_name="piper",
        voice=None,
        fmt="mp3",
        pages=[1, 2, 3],
        transcribe_only=False,
        from_transcripts=False,
        combine=False,
        force=False,
        transcriptions_dir=tmp_path / "transcriptions",
        audiobooks_dir=tmp_path / "audiobooks",
    )
    defaults.update(overrides)
    return Config(**defaults)


class FakeBackend:
    """TTS backend stand-in: records calls and writes a dummy wav. No model/network."""

    calls: list[list[str]] = []

    def __init__(self, **_):
        pass

    def voice_id(self) -> str:
        return "fake:voice"

    def synthesize(self, chunks, out_wav):
        FakeBackend.calls.append(list(chunks))
        out_wav.write_bytes(b"RIFFfakewav")


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Patch out ffmpeg, PDF reading, and the TTS backend so pipeline logic runs in isolation."""
    import audiobook_generator.pipeline as P

    FakeBackend.calls = []

    monkeypatch.setattr(P.audio, "check_ffmpeg", lambda: None)
    monkeypatch.setattr(P.audio, "is_valid_audio", lambda p: p.exists() and p.stat().st_size > 0)

    def fake_encode(src, dest, fmt):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"AUDIO")

    def fake_combine(page_files, dest, book_title):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"M4B")

    monkeypatch.setattr(P.audio, "encode_page", fake_encode)
    monkeypatch.setattr(P.audio, "combine_to_m4b", fake_combine)
    monkeypatch.setattr(P.pdf_extract, "page_count", lambda p: 5)
    monkeypatch.setattr(
        P.pdf_extract, "extract_page_text", lambda p, n: f"Page {n} text. Second sentence."
    )
    monkeypatch.setattr(P, "get_backend", lambda *a, **k: FakeBackend())

    return types.SimpleNamespace(Backend=FakeBackend)
