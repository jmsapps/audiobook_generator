"""Audio encode/validate/combine tests. Skipped if ffmpeg/ffprobe are unavailable."""

from __future__ import annotations

import shutil
import wave

import pytest

from audiobook_generator import audio

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)


def _silent_wav(path, seconds=0.2, rate=22050):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))


def test_encode_page_to_mp3_is_valid(tmp_path):
    wav = tmp_path / "in.wav"
    _silent_wav(wav)
    mp3 = tmp_path / "out.mp3"
    audio.encode_page(wav, mp3, "mp3")
    assert audio.is_valid_audio(mp3)
    assert audio.duration_seconds(mp3) > 0


def test_is_valid_audio_rejects_empty(tmp_path):
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    assert not audio.is_valid_audio(empty)
    assert not audio.is_valid_audio(tmp_path / "missing.mp3")


def test_combine_to_m4b_with_chapters(tmp_path):
    p1, p2 = tmp_path / "p1.mp3", tmp_path / "p2.mp3"
    for wav_secs, dest in ((0.2, p1), (0.3, p2)):
        wav = dest.with_suffix(".wav")
        _silent_wav(wav, wav_secs)
        audio.encode_page(wav, dest, "mp3")

    out = tmp_path / "book.m4b"
    audio.combine_to_m4b([(1, p1), (2, p2)], out, book_title="book")
    assert audio.is_valid_audio(out)
