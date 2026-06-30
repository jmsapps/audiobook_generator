"""TTS backend interface.

A backend turns a list of text chunks into one WAV file. Concatenation, MP3 encoding and chapter
stitching all happen downstream in ``audio.py``, so backends only need to produce WAV audio.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TtsBackend(ABC):
    #: short id used in params hashing / CLI
    name: str = "base"

    @abstractmethod
    def voice_id(self) -> str:
        """A stable string identifying the active voice (for invalidation hashing)."""

    @abstractmethod
    def synthesize(self, chunks: list[str], out_wav: Path) -> None:
        """Synthesize all chunks and write a single WAV to ``out_wav`` (atomically)."""
