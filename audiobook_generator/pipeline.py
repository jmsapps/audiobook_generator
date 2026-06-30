"""Per-page staged orchestration with resume + hash-based invalidation.

Stages, each independently checkpointed in ``state.json``:

    extract     PDF page -> transcriptions/<book>/page_NNNN.txt
    synthesize  transcription -> audiobooks/<book>/pages/page_NNNN.<fmt>
    combine     all page audio -> audiobooks/<book>/<book>.m4b   (optional)

Re-running always resumes from the first incomplete (page, stage). Editing a transcription (its
text hash changes) or changing voice/backend/format (its params hash changes) re-synthesizes only
the affected pages and invalidates the combined file.
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import audio, chunking, pdf_extract
from .state import Manifest, atomic_write, params_hash, text_hash
from .tts import get_backend

# Stop a long run early if this many pages fail in a row — almost always a systemic problem
# (bad --voice, no network for the model download, missing ffmpeg) rather than bad page content.
ABORT_AFTER_CONSECUTIVE = 5


@dataclass
class Config:
    pdf_path: Path
    book: str
    language: str
    backend_name: str
    voice: str | None
    fmt: str
    pages: list[int]
    transcribe_only: bool
    from_transcripts: bool
    combine: bool
    force: bool

    transcriptions_dir: Path
    audiobooks_dir: Path


def _page_txt(cfg: Config, n: int) -> Path:
    return cfg.transcriptions_dir / cfg.book / f"page_{n:04d}.txt"


def _page_audio(cfg: Config, n: int) -> Path:
    return cfg.audiobooks_dir / cfg.book / "pages" / f"page_{n:04d}.{cfg.fmt}"


def _combined(cfg: Config) -> Path:
    return cfg.audiobooks_dir / cfg.book / f"{cfg.book}.m4b"


def _process_page(cfg: Config, manifest: Manifest, n: int, box: dict, cur_params: str) -> None:
    """Run the extract + synthesize stages for one page. Raises on failure (caught by run())."""
    rec = manifest.page(n)
    txt_path = _page_txt(cfg, n)

    # ---- stage: extract ------------------------------------------------
    if cfg.from_transcripts:
        if not txt_path.exists():
            print(f"  page {n}: no transcription on disk, skipping (--from-transcripts)")
            return
        page_text = txt_path.read_text(encoding="utf-8")
    else:
        need_extract = cfg.force or not txt_path.exists() or rec.text_hash is None
        if need_extract:
            page_text = pdf_extract.extract_page_text(str(cfg.pdf_path), n)
            with atomic_write(txt_path, "w", encoding="utf-8") as fh:
                fh.write(page_text)
            print(f"  page {n}: extracted {len(page_text)} chars")
        else:
            page_text = txt_path.read_text(encoding="utf-8")

    new_hash = text_hash(page_text)
    if rec.text_hash != new_hash:
        # Text changed (fresh extract or hand-edit) -> downstream audio is stale.
        rec.text_hash = new_hash
        rec.audio_done = False
        manifest.combined_done = False
    manifest.save()

    if cfg.transcribe_only:
        return

    # ---- stage: synthesize ---------------------------------------------
    audio_path = _page_audio(cfg, n)
    up_to_date = (
        rec.audio_done
        and rec.audio_params == cur_params
        and audio.is_valid_audio(audio_path)
    )
    if up_to_date and not cfg.force:
        print(f"  page {n}: audio up to date, skipping")
        return

    if not page_text.strip():
        print(f"  page {n}: empty text, skipping audio")
        rec.audio_done = False
        manifest.save()
        return

    if box["backend"] is None:
        box["backend"] = get_backend(cfg.backend_name, voice=cfg.voice, language=cfg.language)
    backend = box["backend"]

    segments = chunking.split_segments(page_text, language=cfg.language)
    with tempfile.TemporaryDirectory() as td:
        wav_path = Path(td) / f"page_{n:04d}.wav"
        backend.synthesize(segments, wav_path)
        audio.encode_page(wav_path, audio_path, cfg.fmt)

    rec.audio_done = True
    rec.audio_params = cur_params
    manifest.combined_done = False  # a new/changed page invalidates the combined file
    manifest.save()
    print(f"  page {n}: synthesized -> {audio_path.name}")


def run(cfg: Config) -> int:
    """Run the pipeline. Returns the number of pages that failed (0 on full success)."""
    audio.check_ffmpeg()
    book_dir = cfg.audiobooks_dir / cfg.book
    manifest = Manifest.load(book_dir / "state.json")
    manifest.source_pdf = str(cfg.pdf_path)
    manifest.total_pages = pdf_extract.page_count(str(cfg.pdf_path))

    box = {"backend": None}  # built lazily; --transcribe-only needs no TTS model
    cur_params = params_hash(
        backend=cfg.backend_name, voice=cfg.voice or f"default:{cfg.language}", fmt=cfg.fmt
    )

    print(f"Book '{cfg.book}': {manifest.total_pages} pages total, "
          f"processing {len(cfg.pages)} page(s).")

    failures: list[int] = []
    consecutive = 0
    for n in cfg.pages:
        if n < 1 or n > manifest.total_pages:
            print(f"  page {n}: out of range, skipping")
            continue
        try:
            _process_page(cfg, manifest, n, box, cur_params)
            consecutive = 0
        except KeyboardInterrupt:
            raise
        except Exception as e:  # one bad page shouldn't kill the whole run
            failures.append(n)
            consecutive += 1
            print(f"  page {n}: ERROR ({type(e).__name__}: {e}) — skipping; "
                  f"will retry on re-run", file=sys.stderr)
            if consecutive >= ABORT_AFTER_CONSECUTIVE:
                print(f"Aborting after {consecutive} consecutive failures — this looks "
                      f"systemic (e.g. bad --voice, no network, or a backend problem) rather "
                      f"than page content. Fix it and re-run to resume.", file=sys.stderr)
                return len(failures)

    if failures:
        print(f"\n{len(failures)} page(s) failed: {failures}. "
              f"Re-run the same command to retry just those pages.", file=sys.stderr)

    # ---- stage: combine ------------------------------------------------
    if cfg.combine and not cfg.transcribe_only:
        if failures:
            # Don't stitch a book with known gaps; re-run to fill them, then it combines.
            print("Combine: skipped because some pages failed — re-run to finish, then combine.",
                  file=sys.stderr)
            return len(failures)

        page_files: list[tuple[int, Path]] = []
        for n in range(1, manifest.total_pages + 1):
            p = _page_audio(cfg, n)
            if audio.is_valid_audio(p):
                page_files.append((n, p))
        if not page_files:
            print("Combine: no valid page audio found yet, skipping .m4b.")
            return len(failures)

        inputs_hash = params_hash(
            pages=[n for n, _ in page_files], params=cur_params
        )
        dest = _combined(cfg)
        if manifest.combined_done and manifest.combined_hash == inputs_hash \
                and dest.exists() and not cfg.force:
            print(f"Combine: {dest.name} already up to date.")
            return len(failures)
        print(f"Combine: building {dest.name} from {len(page_files)} page(s)...")
        audio.combine_to_m4b(page_files, dest, book_title=cfg.book)
        manifest.combined_done = True
        manifest.combined_hash = inputs_hash
        manifest.save()
        print(f"Combine: wrote {dest}")

    return len(failures)
