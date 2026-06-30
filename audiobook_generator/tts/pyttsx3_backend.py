"""pyttsx3 fallback backend — uses the OS speech engine (macOS ``say`` / SAPI / espeak).

No model download, works fully offline, but lower quality than Piper. The native driver may emit
AIFF (macOS), so we synthesize to a temp file and transcode to WAV with ffmpeg to keep the
backend's "produce a WAV" contract.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from ..state import atomic_write
from .base import TtsBackend


class Pyttsx3Backend(TtsBackend):
    name = "pyttsx3"

    def __init__(self, *, voice: str | None, language: str) -> None:
        self._voice = voice
        self._language = language

    def voice_id(self) -> str:
        return f"pyttsx3:{self._voice or self._language or 'default'}"

    def _make_engine(self):
        import pyttsx3

        engine = pyttsx3.init()
        if self._voice:
            engine.setProperty("voice", self._voice)
        return engine

    def synthesize(self, chunks: list[str], out_wav: Path) -> None:
        text = "\n".join(c.strip() for c in chunks if c.strip())
        if not text:
            text = " "

        fd, raw = tempfile.mkstemp(suffix=".aiff")
        os.close(fd)
        raw_path = Path(raw)
        try:
            engine = self._make_engine()
            engine.save_to_file(text, str(raw_path))
            engine.runAndWait()
            # Transcode whatever the driver produced into a clean WAV.
            with atomic_write(out_wav, "wb") as fh:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(raw_path), "-f", "wav", "-"],
                    check=True,
                    stdout=fh,
                    stderr=subprocess.DEVNULL,
                )
        finally:
            raw_path.unlink(missing_ok=True)
