"""TTS backends."""

from __future__ import annotations

from .base import TtsBackend


def get_backend(name: str, *, voice: str | None, language: str) -> TtsBackend:
    """Factory: build a TTS backend by name."""
    name = (name or "piper").lower()
    if name == "piper":
        from .piper_backend import PiperBackend

        return PiperBackend(voice=voice, language=language)
    if name == "pyttsx3":
        from .pyttsx3_backend import Pyttsx3Backend

        return Pyttsx3Backend(voice=voice, language=language)
    raise ValueError(f"Unknown TTS backend: {name!r} (expected 'piper' or 'pyttsx3')")
