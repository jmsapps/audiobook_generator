"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import Config, run


def _parse_pages(spec: str | None, default_count_hint: int | None = None) -> list[int] | None:
    """Parse '1-10' / '3,5,9' / '1-3,7' into a sorted unique list. None = all."""
    if not spec:
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
            if start > end:
                start, end = end, start
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part))
    return sorted(p for p in pages if p > 0)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audiobook-generator",
        description="Turn a PDF into an audiobook, offline, one page at a time, resumable.",
    )
    p.add_argument("--file", required=True, help="Path to the source PDF (e.g. documents/sherlock.pdf)")
    p.add_argument("-l", "--language", default="en", help="Language code (default: en; sets default voice)")
    p.add_argument("--voice", default=None, help="Override TTS voice id (e.g. af_heart)")
    p.add_argument(
        "--backend",
        default="kokoro",
        choices=["piper", "pyttsx3", "kokoro"],
        help="TTS backend",
    )
    p.add_argument("--pages", default=None, help="Page range, e.g. '1-10' or '3,5,9' (default: all)")
    p.add_argument("--format", dest="fmt", default="mp3", choices=["mp3", "wav"], help="Page audio format")
    p.add_argument(
        "--length-scale",
        type=float,
        default=1.25,
        help="Speech pacing for synthesis; higher is slower (default: 1.25)",
    )
    p.add_argument(
        "--pause-ms",
        type=int,
        default=250,
        help="Silence to insert between narration chunks, in milliseconds (default: 250)",
    )
    p.add_argument("--transcribe-only", action="store_true", help="Stop after extracting text")
    p.add_argument("--from-transcripts", action="store_true", help="Skip extraction; build audio from existing .txt")
    p.add_argument("--combine", action="store_true", help="Build a single .m4b with per-page chapters")
    p.add_argument("--force", action="store_true", help="Ignore checkpoints and redo everything")
    p.add_argument("--documents-dir", default="documents")
    p.add_argument("--transcriptions-dir", default="transcriptions")
    p.add_argument("--audiobooks-dir", default="audiobooks")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    pdf_path = Path(args.file)
    if not pdf_path.is_absolute() and not pdf_path.exists():
        # Allow bare filename relative to the documents dir.
        candidate = Path(args.documents_dir) / args.file
        if candidate.exists():
            pdf_path = candidate
    if not pdf_path.exists():
        print(f"error: PDF not found: {args.file}", file=sys.stderr)
        return 2
    if pdf_path.suffix.lower() != ".pdf":
        print(f"error: not a .pdf file: {pdf_path}", file=sys.stderr)
        return 2
    if args.length_scale <= 0:
        print("error: --length-scale must be greater than 0", file=sys.stderr)
        return 2
    if args.pause_ms < 0:
        print("error: --pause-ms must be greater than or equal to 0", file=sys.stderr)
        return 2

    book = pdf_path.stem

    from . import pdf_extract

    total = pdf_extract.page_count(str(pdf_path))
    selected = _parse_pages(args.pages)
    pages = selected if selected is not None else list(range(1, total + 1))

    cfg = Config(
        pdf_path=pdf_path,
        book=book,
        language=args.language,
        backend_name=args.backend,
        voice=args.voice,
        fmt=args.fmt,
        length_scale=args.length_scale,
        pause_ms=args.pause_ms,
        pages=pages,
        transcribe_only=args.transcribe_only,
        from_transcripts=args.from_transcripts,
        combine=args.combine,
        force=args.force,
        transcriptions_dir=Path(args.transcriptions_dir),
        audiobooks_dir=Path(args.audiobooks_dir),
    )

    try:
        failed = run(cfg)
    except KeyboardInterrupt:
        print("\nInterrupted. Re-run the same command to resume where it left off.", file=sys.stderr)
        return 130
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
