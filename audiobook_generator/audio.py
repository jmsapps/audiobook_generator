"""ffmpeg-backed audio operations: WAV -> page file, and pages -> single .m4b w/ chapters.

All outputs are written via temp files and atomically moved into place.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .state import atomic_write


class FfmpegError(RuntimeError):
    pass


def check_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run(
                [tool, "-version"], check=True, capture_output=True
            )
        except (OSError, subprocess.CalledProcessError) as e:
            raise FfmpegError(
                f"{tool} not found on PATH. Install ffmpeg (e.g. `brew install ffmpeg`)."
            ) from e


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise FfmpegError(
            f"ffmpeg failed ({' '.join(cmd[:3])} ...):\n"
            + proc.stderr.decode("utf-8", "replace")[-2000:]
        )


def duration_seconds(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise FfmpegError(proc.stderr.decode("utf-8", "replace"))
    try:
        return float(proc.stdout.decode().strip())
    except ValueError:
        return 0.0


def is_valid_audio(path: Path) -> bool:
    """A finished page file must exist, be non-empty, and have a positive duration."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        return duration_seconds(path) > 0.0
    except FfmpegError:
        return False


def encode_page(src_wav: Path, dest: Path, fmt: str) -> None:
    """Encode a synthesized WAV into the page's final ``mp3`` or ``wav`` file."""
    if fmt == "wav":
        codec = ["-c:a", "pcm_s16le", "-f", "wav"]
    elif fmt == "mp3":
        codec = ["-c:a", "libmp3lame", "-q:a", "4", "-f", "mp3"]
    else:
        raise ValueError(f"Unsupported format {fmt!r}")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(src_wav), *codec, "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise FfmpegError(proc.stderr.decode("utf-8", "replace")[-2000:])
    with atomic_write(dest, "wb") as fh:
        fh.write(proc.stdout)


def _build_chapters_metadata(durations: list[tuple[str, float]]) -> str:
    """ffmetadata with one chapter per page (title, start/end in ms)."""
    lines = [";FFMETADATA1"]
    start_ms = 0
    for title, dur in durations:
        end_ms = start_ms + int(dur * 1000)
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={title}",
        ]
        start_ms = end_ms
    return "\n".join(lines) + "\n"


def combine_to_m4b(
    page_files: list[tuple[int, Path]], dest: Path, book_title: str
) -> None:
    """Concatenate per-page audio into a single ``.m4b`` with one chapter per page."""
    if not page_files:
        raise FfmpegError("No page audio files to combine.")

    durations = [(f"Page {n}", duration_seconds(p)) for n, p in page_files]
    metadata = _build_chapters_metadata(durations)

    # concat demuxer list + metadata file, both in the destination dir.
    dest.parent.mkdir(parents=True, exist_ok=True)
    list_path = dest.parent / ".combine_list.txt"
    meta_path = dest.parent / ".combine_meta.txt"
    list_path.write_text(
        "".join(f"file '{p.resolve()}'\n" for _, p in page_files), encoding="utf-8"
    )
    meta_path.write_text(metadata, encoding="utf-8")
    try:
        tmp_out = dest.parent / (dest.name + ".tmp.m4b")
        _run([
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-i", str(meta_path),
            "-map_metadata", "1",
            "-metadata", f"title={book_title}",
            "-c:a", "aac", "-b:a", "64k",
            "-f", "mp4",
            str(tmp_out),
        ])
        tmp_out.replace(dest)
    finally:
        list_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
