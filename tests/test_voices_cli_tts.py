"""Voice URL mapping, default-voice selection, page-range parsing, backend factory."""

from __future__ import annotations

import pytest

from audiobook_generator.cli import _parse_pages
from audiobook_generator.tts import get_backend
from audiobook_generator.tts.piper_backend import PiperBackend
from audiobook_generator.tts.pyttsx3_backend import Pyttsx3Backend
from audiobook_generator.voices import _voice_url_path, default_voice


def test_voice_url_path_mapping():
    assert (
        _voice_url_path("pt_BR-faber-medium")
        == "pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
    )
    assert (
        _voice_url_path("en_US-amy-medium") == "en/en_US/amy/medium/en_US-amy-medium.onnx"
    )


def test_voice_url_path_rejects_bad_id():
    with pytest.raises(ValueError):
        _voice_url_path("solo")          # 1 part
    with pytest.raises(ValueError):
        _voice_url_path("two-parts")     # 2 parts, need at least 3


def test_default_voice_per_language():
    assert default_voice("pt") == "pt_BR-faber-medium"
    assert default_voice("pt-BR") == "pt_BR-faber-medium"
    assert default_voice("en") == "en_US-amy-medium"


def test_default_voice_unknown_language_raises():
    with pytest.raises(ValueError):
        default_voice("zz")


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("1-3", [1, 2, 3]),
        ("3,5,9", [3, 5, 9]),
        ("1-3,7", [1, 2, 3, 7]),
        ("5-3", [3, 4, 5]),     # reversed range is normalized
        ("2", [2]),
        ("", None),            # empty -> all pages
        (None, None),
    ],
)
def test_parse_pages(spec, expected):
    assert _parse_pages(spec) == expected


def test_get_backend_factory():
    assert isinstance(get_backend("piper", voice=None, language="en"), PiperBackend)
    assert isinstance(get_backend("pyttsx3", voice=None, language="en"), Pyttsx3Backend)
    with pytest.raises(ValueError):
        get_backend("bogus", voice=None, language="en")


def test_piper_backend_voice_id_uses_language_default():
    b = get_backend("piper", voice=None, language="pt")
    assert b.voice_id() == "piper:pt_BR-faber-medium"
    b2 = get_backend("piper", voice="en_US-ryan-high", language="en")
    assert b2.voice_id() == "piper:en_US-ryan-high"
