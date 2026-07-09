"""Piper TTS backend — fast, local, neural, multilingual (incl. pt_BR/pt_PT).

Each text chunk is synthesized to int16 PCM and appended to a single WAV. WAV format is taken from
the first audio chunk the model emits, so we don't hardcode sample rate/width/channels.
"""

from __future__ import annotations

import wave
from pathlib import Path

from .. import voices
from ..state import atomic_write
from .base import TtsBackend


class PiperBackend(TtsBackend):
    name = "piper"

    def __init__(
        self, *, voice: str | None, language: str, length_scale: float, pause_ms: int
    ) -> None:
        self._voice_id = voice or voices.default_voice(language)
        self._length_scale = length_scale
        self._pause_ms = pause_ms
        self._voice = None  # lazily loaded so --transcribe-only needs no model

    def voice_id(self) -> str:
        return f"piper:{self._voice_id}"

    def _load(self):
        if self._voice is None:
            from piper import PiperVoice

            onnx, config = voices.ensure_voice(self._voice_id)
            self._voice = PiperVoice.load(str(onnx), config_path=str(config))
        return self._voice

    def synthesize(self, chunks: list[str], out_wav: Path) -> None:
        from piper.config import SynthesisConfig

        voice = self._load()
        syn_config = SynthesisConfig(length_scale=self._length_scale)
        with atomic_write(out_wav, "wb") as fh:
            with wave.open(fh, "wb") as wav:
                fmt_set = False
                for i, chunk_text in enumerate(chunks):
                    if not chunk_text.strip():
                        continue
                    for audio in voice.synthesize(chunk_text, syn_config=syn_config):
                        if not fmt_set:
                            wav.setnchannels(audio.sample_channels)
                            wav.setsampwidth(audio.sample_width)
                            wav.setframerate(audio.sample_rate)
                            fmt_set = True
                        wav.writeframes(audio.audio_int16_bytes)
                    if fmt_set and self._pause_ms > 0 and i < len(chunks) - 1:
                        frames = int(wav.getframerate() * self._pause_ms / 1000)
                        wav.writeframes(b"\x00" * frames * wav.getnchannels() * wav.getsampwidth())
                if not fmt_set:
                    # Nothing synthesized (all-empty input): emit a valid silent WAV.
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(22050)
