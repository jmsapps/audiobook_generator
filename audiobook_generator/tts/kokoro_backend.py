"""Kokoro TTS backend.

Kokoro is a small open-weight neural TTS model. Its Python package downloads model weights and
voice tensors lazily, so this backend imports Kokoro only when synthesis is requested.
"""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

from ..state import atomic_write
from .base import TtsBackend


DEFAULT_VOICES = {
    "a": "af_heart",  # American English
    "b": "bf_emma",  # British English
    "e": "ef_dora",  # Spanish
    "f": "ff_siwis",  # French
    "h": "hf_alpha",  # Hindi
    "i": "if_sara",  # Italian
    "p": "pf_dora",  # Brazilian Portuguese
    "j": "jf_alpha",  # Japanese
    "z": "zf_xiaobei",  # Mandarin Chinese
}

LANG_CODES = {
    "en": "a",
    "en-us": "a",
    "en_us": "a",
    "en-gb": "b",
    "en_gb": "b",
    "en-uk": "b",
    "en_uk": "b",
    "pt": "p",
    "pt-br": "p",
    "pt_br": "p",
    "es": "e",
    "fr": "f",
    "fr-fr": "f",
    "fr_fr": "f",
    "hi": "h",
    "it": "i",
    "ja": "j",
    "zh": "z",
    "zh-cn": "z",
    "zh_cn": "z",
}


class KokoroBackend(TtsBackend):
    name = "kokoro"
    sample_rate = 24000

    def __init__(
        self, *, voice: str | None, language: str, length_scale: float, pause_ms: int
    ) -> None:
        self._lang_code = self._lang_code_for(language)
        self._voice = voice or DEFAULT_VOICES[self._lang_code]
        self._speed = 1.0 / length_scale
        self._pause_ms = pause_ms
        self._pipeline = None

    def voice_id(self) -> str:
        return f"kokoro:{self._lang_code}:{self._voice}"

    @staticmethod
    def _lang_code_for(language: str) -> str:
        normalized = (language or "en").lower()
        try:
            return LANG_CODES[normalized]
        except KeyError as e:
            supported = ", ".join(sorted(LANG_CODES))
            raise ValueError(
                f"Kokoro does not have a default for language {language!r}; "
                f"use one of: {supported}"
            ) from e

    def _load(self):
        if self._pipeline is None:
            try:
                from kokoro import KPipeline
            except ImportError as e:
                raise RuntimeError(
                    "Kokoro backend requires the optional Kokoro package. "
                    "Install it with `uv sync`."
                ) from e

            self._pipeline = KPipeline(
                lang_code=self._lang_code,
                repo_id="hexgrad/Kokoro-82M",
            )
        return self._pipeline

    @staticmethod
    def _audio_to_int16_bytes(audio: Any) -> bytes:
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()

        import numpy as np

        samples = np.asarray(audio, dtype=np.float32)
        samples = np.clip(samples, -1.0, 1.0)
        return (samples * 32767.0).astype("<i2").tobytes()

    def synthesize(self, chunks: list[str], out_wav: Path) -> None:
        pipeline = self._load()
        with atomic_write(out_wav, "wb") as fh:
            with wave.open(fh, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.sample_rate)

                for i, chunk_text in enumerate(chunks):
                    if not chunk_text.strip():
                        continue
                    chunk_wrote = False
                    for result in pipeline(
                        chunk_text,
                        voice=self._voice,
                        speed=self._speed,
                        split_pattern=None,
                    ):
                        if result.audio is None:
                            continue
                        wav.writeframes(self._audio_to_int16_bytes(result.audio))
                        chunk_wrote = True
                    if chunk_wrote and self._pause_ms > 0 and i < len(chunks) - 1:
                        frames = int(self.sample_rate * self._pause_ms / 1000)
                        wav.writeframes(b"\x00" * frames * wav.getnchannels() * wav.getsampwidth())
