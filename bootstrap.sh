#!/usr/bin/env bash
#
# bootstrap.sh — install the external prerequisites for audiobook-generator and sync the project.
#
# Handles the things `uv sync` cannot install itself:
#   * uv            (the package manager / runner)
#   * ffmpeg/ffprobe (system binaries used for audio encoding & chapters)
# Then runs `uv sync`, which installs Python 3.13 and all PyPI dependencies into .venv.
#
# Supported: macOS (Homebrew) and Linux (apt / dnf / yum / pacman / zypper). Unix only.
#
# Usage:
#   ./bootstrap.sh
#
set -euo pipefail

# ---- pretty output --------------------------------------------------------
info() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }

cd "$(dirname "$0")"

# ---- detect OS ------------------------------------------------------------
OS="$(uname -s)"
case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)
        err "Unsupported OS: $OS. This script supports macOS and Linux only."
        exit 1
        ;;
esac
info "Detected platform: $PLATFORM"

# ---- sudo helper (Linux package installs) ---------------------------------
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    if have sudo; then
        SUDO="sudo"
    fi
fi

# ---- ensure uv ------------------------------------------------------------
UV_FRESHLY_INSTALLED=0
ensure_uv() {
    if have uv; then
        info "uv already installed ($(uv --version))"
        return
    fi
    UV_FRESHLY_INSTALLED=1
    info "Installing uv via the official installer..."
    if ! have curl && ! have wget; then
        err "Need curl or wget to install uv. Install one and re-run."
        exit 1
    fi
    if have curl; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    else
        wget -qO- https://astral.sh/uv/install.sh | sh
    fi
    # The installer drops uv in one of these; make it available for the rest of this run.
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! have uv; then
        err "uv installed but not on PATH. Open a new shell (or add ~/.local/bin to PATH) and re-run."
        exit 1
    fi
    info "uv installed ($(uv --version))"
}

# ---- ensure ffmpeg --------------------------------------------------------
install_ffmpeg_macos() {
    if ! have brew; then
        err "Homebrew is required to auto-install ffmpeg on macOS."
        err "Install it from https://brew.sh then re-run, or install ffmpeg yourself."
        exit 1
    fi
    brew install ffmpeg
}

install_ffmpeg_linux() {
    if have apt-get; then
        $SUDO apt-get update -y && $SUDO apt-get install -y ffmpeg
    elif have dnf; then
        $SUDO dnf install -y ffmpeg || {
            warn "ffmpeg may need RPM Fusion: https://rpmfusion.org/Configuration"
            exit 1
        }
    elif have yum; then
        $SUDO yum install -y ffmpeg || {
            warn "ffmpeg may need RPM Fusion: https://rpmfusion.org/Configuration"
            exit 1
        }
    elif have pacman; then
        $SUDO pacman -Sy --noconfirm ffmpeg
    elif have zypper; then
        $SUDO zypper install -y ffmpeg
    else
        err "No supported package manager found (apt/dnf/yum/pacman/zypper)."
        err "Install ffmpeg manually and re-run."
        exit 1
    fi
}

ensure_ffmpeg() {
    if have ffmpeg && have ffprobe; then
        info "ffmpeg already installed ($(ffmpeg -version | head -1))"
        return
    fi
    info "Installing ffmpeg..."
    if [ "$PLATFORM" = "macos" ]; then
        install_ffmpeg_macos
    else
        install_ffmpeg_linux
    fi
    if ! have ffmpeg || ! have ffprobe; then
        err "ffmpeg/ffprobe still not found after install."
        exit 1
    fi
    info "ffmpeg installed ($(ffmpeg -version | head -1))"
}

# ---- run ------------------------------------------------------------------
ensure_uv
ensure_ffmpeg

info "Syncing project (installs Python 3.13 + dependencies into .venv)..."
uv sync

info "Done. Try it:"
printf '    uv run python -m audiobook_generator --file documents/book.pdf --pages 1-3\n'
if [ "$UV_FRESHLY_INSTALLED" -eq 1 ]; then
    printf '\n'
    warn "uv was installed this run — open a new terminal (or 'source ~/.bashrc') so it stays on PATH."
fi
