"""Language -> default Piper voice, plus on-demand model download & caching.

Piper voice models are hosted in the ``rhasspy/piper-voices`` repository on Hugging Face. A voice
id like ``pt_BR-faber-medium`` maps deterministically to its files; we download the ``.onnx`` and
``.onnx.json`` once into the user cache and reuse them thereafter.
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# Known-good default voices per language. Override any time with --voice.
DEFAULT_VOICES: dict[str, str] = {
    "en": "en_US-amy-medium",
    "pt": "pt_BR-faber-medium",
    "es": "es_ES-davefx-medium",
    "fr": "fr_FR-siwis-medium",
    "de": "de_DE-thorsten-medium",
    "it": "it_IT-riccardo-x_low",
    "nl": "nl_NL-mls-medium",
}


def default_voice(language: str) -> str:
    lang = (language or "en").split("-")[0].lower()
    if lang not in DEFAULT_VOICES:
        raise ValueError(
            f"No default Piper voice for language {lang!r}. "
            f"Pass --voice explicitly (e.g. en_US-amy-medium). "
            f"Known defaults: {', '.join(sorted(DEFAULT_VOICES))}."
        )
    return DEFAULT_VOICES[lang]


def cache_dir() -> Path:
    base = os.environ.get("AUDIOBOOK_CACHE") or os.path.expanduser(
        "~/.cache/audiobook_generator"
    )
    d = Path(base) / "voices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _voice_url_path(voice: str) -> str:
    """e.g. 'pt_BR-faber-medium' -> 'pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx'."""
    parts = voice.split("-")
    if len(parts) < 3:
        raise ValueError(
            f"Voice id {voice!r} must look like '<lang_region>-<name>-<quality>', "
            f"e.g. 'en_US-amy-medium'."
        )
    lang_region, name, quality = parts[0], parts[1], "-".join(parts[2:])
    lang = lang_region.split("_")[0]
    return f"{lang}/{lang_region}/{name}/{quality}/{voice}.onnx"


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                fh.write(chunk)
    os.replace(tmp, dest)


def ensure_voice(voice: str) -> tuple[Path, Path]:
    """Return (onnx_path, config_path), downloading them into the cache if missing."""
    rel = _voice_url_path(voice)
    onnx = cache_dir() / f"{voice}.onnx"
    config = cache_dir() / f"{voice}.onnx.json"
    if not onnx.exists():
        _download(f"{_HF_BASE}/{rel}", onnx)
    if not config.exists():
        _download(f"{_HF_BASE}/{rel}.json", config)
    return onnx, config
