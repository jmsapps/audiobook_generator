"""Pipeline orchestration: resume/skip, hash invalidation, error isolation, circuit breaker."""

from __future__ import annotations

from conftest import make_config

import audiobook_generator.pipeline as pipeline


def _pages_dir(tmp_path):
    return tmp_path / "audiobooks" / "book" / "pages"


def test_fresh_run_synthesizes_all(patched, tmp_path):
    cfg = make_config(tmp_path, pages=[1, 2, 3])
    rc = pipeline.run(cfg)
    assert rc == 0
    assert len(patched.Backend.calls) == 3
    for n in (1, 2, 3):
        assert (_pages_dir(tmp_path) / f"page_{n:04d}.mp3").exists()
        assert (tmp_path / "transcriptions" / "book" / f"page_{n:04d}.txt").exists()


def test_rerun_skips_completed_pages(patched, tmp_path):
    cfg = make_config(tmp_path, pages=[1, 2, 3])
    pipeline.run(cfg)
    assert len(patched.Backend.calls) == 3
    pipeline.run(cfg)  # resume: everything is up to date
    assert len(patched.Backend.calls) == 3  # no new synthesis


def test_editing_transcript_resynthesizes_only_that_page(patched, tmp_path):
    cfg = make_config(tmp_path, pages=[1, 2, 3])
    pipeline.run(cfg)
    assert len(patched.Backend.calls) == 3

    edited = tmp_path / "transcriptions" / "book" / "page_0002.txt"
    edited.write_text("Completely different text now.", encoding="utf-8")

    pipeline.run(cfg)
    assert len(patched.Backend.calls) == 4  # only page 2 re-synthesized


def test_changing_voice_invalidates_audio(patched, tmp_path):
    pipeline.run(make_config(tmp_path, pages=[1]))
    assert len(patched.Backend.calls) == 1
    # Different voice -> different params hash -> re-synthesize.
    pipeline.run(make_config(tmp_path, pages=[1], voice="en_US-ryan-high"))
    assert len(patched.Backend.calls) == 2


def test_transcribe_only_writes_no_audio(patched, tmp_path):
    cfg = make_config(tmp_path, pages=[1, 2], transcribe_only=True)
    rc = pipeline.run(cfg)
    assert rc == 0
    assert (tmp_path / "transcriptions" / "book" / "page_0001.txt").exists()
    assert not _pages_dir(tmp_path).exists()
    assert patched.Backend.calls == []


def test_empty_page_text_skips_audio(patched, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline.pdf_extract, "extract_page_text", lambda p, n: "")
    cfg = make_config(tmp_path, pages=[1])
    rc = pipeline.run(cfg)
    assert rc == 0
    assert patched.Backend.calls == []
    assert not (_pages_dir(tmp_path) / "page_0001.mp3").exists()


def test_page_error_is_isolated_and_others_succeed(patched, tmp_path, monkeypatch):
    def extract(p, n):
        if n == 2:
            raise ValueError("bad page")
        return f"Page {n} text."

    monkeypatch.setattr(pipeline.pdf_extract, "extract_page_text", extract)
    cfg = make_config(tmp_path, pages=[1, 2, 3])
    rc = pipeline.run(cfg)

    assert rc == 1  # one failure
    assert (_pages_dir(tmp_path) / "page_0001.mp3").exists()
    assert not (_pages_dir(tmp_path) / "page_0002.mp3").exists()
    assert (_pages_dir(tmp_path) / "page_0003.mp3").exists()


def test_circuit_breaker_aborts_after_consecutive_failures(patched, tmp_path, monkeypatch):
    attempts = {"n": 0}

    class Raiser:
        def voice_id(self):
            return "r"

        def synthesize(self, chunks, out_wav):
            attempts["n"] += 1
            raise RuntimeError("nope")

    monkeypatch.setattr(pipeline, "get_backend", lambda *a, **k: Raiser())
    monkeypatch.setattr(pipeline.pdf_extract, "page_count", lambda p: 20)

    cfg = make_config(tmp_path, pages=list(range(1, 21)))
    rc = pipeline.run(cfg)

    assert rc == pipeline.ABORT_AFTER_CONSECUTIVE
    # Stopped early rather than attempting all 20 pages.
    assert attempts["n"] == pipeline.ABORT_AFTER_CONSECUTIVE


def test_combine_builds_m4b_on_success(patched, tmp_path):
    cfg = make_config(tmp_path, pages=[1, 2, 3, 4, 5], combine=True)
    rc = pipeline.run(cfg)
    assert rc == 0
    assert (tmp_path / "audiobooks" / "book" / "book.m4b").exists()


def test_combine_skipped_when_a_page_failed(patched, tmp_path, monkeypatch):
    def extract(p, n):
        if n == 3:
            raise ValueError("bad")
        return f"Page {n}."

    monkeypatch.setattr(pipeline.pdf_extract, "extract_page_text", extract)
    cfg = make_config(tmp_path, pages=[1, 2, 3], combine=True)
    rc = pipeline.run(cfg)

    assert rc == 1
    assert not (tmp_path / "audiobooks" / "book" / "book.m4b").exists()
