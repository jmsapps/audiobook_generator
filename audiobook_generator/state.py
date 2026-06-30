"""Checkpoint manifest + atomic write helpers.

The manifest (``state.json``, stored next to the audio output) is the source of truth for
"what is done", but it is always reconciled against files actually on disk so the two cannot
silently disagree. Every output file is written atomically (``*.tmp`` then ``os.replace``) so a
crash mid-write never leaves a partial file that looks complete.

Stages per page: ``extract`` -> ``synthesize`` -> ``combine``.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

MANIFEST_VERSION = 1


def text_hash(text: str) -> str:
    """Stable short hash of transcription text, used for invalidation."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def params_hash(**parts: Any) -> str:
    """Hash of synthesis parameters (voice/backend/format) for invalidation."""
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@contextmanager
def atomic_write(path: Path, mode: str = "w", **kwargs: Any) -> Iterator[Any]:
    """Write to a temp file in the same dir, then atomically replace the target.

    Yields the open file handle. On any exception the temp file is removed and the
    destination is left untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        with open(tmp_path, mode, **kwargs) as fh:
            yield fh
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


@dataclass
class PageRecord:
    """Per-page progress, keyed by 1-based page number in the manifest."""

    text_hash: str | None = None        # hash of the transcription text on disk
    audio_params: str | None = None     # params_hash used to produce the page audio
    audio_done: bool = False            # page audio file written & valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_hash": self.text_hash,
            "audio_params": self.audio_params,
            "audio_done": self.audio_done,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PageRecord":
        return cls(
            text_hash=d.get("text_hash"),
            audio_params=d.get("audio_params"),
            audio_done=bool(d.get("audio_done", False)),
        )


@dataclass
class Manifest:
    path: Path
    source_pdf: str = ""
    total_pages: int = 0
    combined_hash: str | None = None    # hash of inputs the .m4b was built from
    combined_done: bool = False
    pages: dict[int, PageRecord] = field(default_factory=dict)

    # ---- load / save ---------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        if not path.exists():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        pages = {
            int(k): PageRecord.from_dict(v) for k, v in data.get("pages", {}).items()
        }
        return cls(
            path=path,
            source_pdf=data.get("source_pdf", ""),
            total_pages=data.get("total_pages", 0),
            combined_hash=data.get("combined_hash"),
            combined_done=bool(data.get("combined_done", False)),
            pages=pages,
        )

    def save(self) -> None:
        payload = {
            "version": MANIFEST_VERSION,
            "source_pdf": self.source_pdf,
            "total_pages": self.total_pages,
            "combined_hash": self.combined_hash,
            "combined_done": self.combined_done,
            "pages": {str(k): v.to_dict() for k, v in sorted(self.pages.items())},
        }
        with atomic_write(self.path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)

    # ---- accessors -----------------------------------------------------

    def page(self, n: int) -> PageRecord:
        return self.pages.setdefault(n, PageRecord())
