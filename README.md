# Audiobook Generator

Turn a PDF into an audiobook — **fully offline, open source, free to run**. It works through the
PDF **one page at a time**, writing an editable text transcription per page, then narrating each
page to audio. The whole pipeline is **resumable**: rerun the command at any point and it picks up
exactly where it left off, and re-narrates only pages whose text you've changed.

```
documents/<book>.pdf
   → transcriptions/<book>/page_0001.txt      (layout-aware text, editable)
   → audiobooks/<book>/pages/page_0001.mp3     (one audio file per page)
   → audiobooks/<book>/<book>.m4b              (optional single file w/ chapters)
```

## Requirements

- macOS or Linux
- [`uv`](https://docs.astral.sh/uv/) (manages Python 3.13 + dependencies)
- `ffmpeg`/`ffprobe` on your `PATH`

## Setup

The bootstrap script detects your OS and installs the external prerequisites (`uv` and `ffmpeg`),
then syncs the project:

```bash
./bootstrap.sh
```

Or, if you already have `uv` and `ffmpeg`:

```bash
uv sync          # creates .venv and installs everything
```

## Usage

```bash
# English (default), produce per-page MP3s
uv run python -m audiobook_generator --file documents/book.pdf

# Portuguese
uv run python -m audiobook_generator --file documents/livro.pdf --language pt

# A page range, then stitch into a single .m4b with one chapter per page
uv run python -m audiobook_generator --file documents/book.pdf --pages 1-20 --combine
```

### Options

| Flag | Default | Meaning |
|------|---------|---------|
| `--file` | (required) | PDF under `documents/` (or any path) |
| `-l, --language` | `en` | Sets the default voice (e.g. `pt` → `pt_BR-faber-medium`) |
| `--voice` | per-language | Override the Piper voice id, e.g. `pt_BR-faber-medium` |
| `--backend` | `piper` | `piper` (neural, local) or `pyttsx3` (OS voices) |
| `--pages` | all | `1-10` or `3,5,9` |
| `--format` | `mp3` | `mp3` or `wav` |
| `--length-scale` | `1.25` | Speech pacing; higher is slower |
| `--pause-ms` | `250` | Silence between narration chunks, in milliseconds |
| `--transcribe-only` | off | Stop after extracting text |
| `--from-transcripts` | off | Skip extraction; (re)build audio from existing `.txt` |
| `--combine` | off | Build a single `.m4b` with per-page chapters |
| `--force` | off | Ignore checkpoints and redo everything |

## How resume works

Progress lives in `audiobooks/<book>/state.json` and is always reconciled against the files on
disk. Each output is written atomically, so a crash never leaves a half-file that looks finished.
The manifest stores a hash of each page's transcription and the synthesis parameters — so editing
`transcriptions/<book>/page_0007.txt` (or changing `--voice`) re-narrates just the affected pages
and rebuilds the combined file.

## Tests

```bash
uv run pytest
```

Unit tests cover reading-order (XY-cut), drop-cap merging, text cleanup, sentence chunking
(including the Portuguese fallback), the resume/skip and hash-invalidation logic, and per-page
error handling. Audio tests that shell out to ffmpeg are skipped automatically if it isn't
installed. No tests require network access or model downloads.

## Layout-aware extraction

Text is extracted with PyMuPDF using an adaptive reading-order pass that discovers however many
columns/regions a page has, rather than assuming a fixed layout — so multi-column pages aren't
scrambled. Scanned/image-only pages (which need OCR) are out of scope for now.

## Licensing note

Uses **PyMuPDF (AGPL-3.0)** for extraction. Fine for local/personal/open-source use; review the
license before redistributing inside closed-source software.
