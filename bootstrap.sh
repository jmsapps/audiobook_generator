#!/usr/bin/env bash
#
# bootstrap.sh — install the external prerequisites for audiobook-generator and sync the project.
#
# Handles the things `uv sync` cannot install itself:
#   * uv            (the package manager / runner)
#   * ffmpeg/ffprobe (system binaries used for audio encoding & chapters)
#   * espeak-ng     (phonemizer used by the default Kokoro backend)
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

# ---- ensure system packages ----------------------------------------------
install_brew_package() {
    if ! have brew; then
        err "Homebrew is required to auto-install $1 on macOS."
        err "Install it from https://brew.sh then re-run, or install $1 yourself."
        exit 1
    fi
    brew install "$1"
}

install_linux_package() {
    if have apt-get; then
        $SUDO apt-get update -y && $SUDO apt-get install -y "$1"
    elif have dnf; then
        $SUDO dnf install -y "$1" || {
            [ "$1" = "ffmpeg" ] && warn "ffmpeg may need RPM Fusion: https://rpmfusion.org/Configuration"
            exit 1
        }
    elif have yum; then
        $SUDO yum install -y "$1" || {
            [ "$1" = "ffmpeg" ] && warn "ffmpeg may need RPM Fusion: https://rpmfusion.org/Configuration"
            exit 1
        }
    elif have pacman; then
        $SUDO pacman -Sy --noconfirm "$1"
    elif have zypper; then
        $SUDO zypper install -y "$1"
    else
        err "No supported package manager found (apt/dnf/yum/pacman/zypper)."
        err "Install $1 manually and re-run."
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
        install_brew_package ffmpeg
    else
        install_linux_package ffmpeg
    fi
    if ! have ffmpeg || ! have ffprobe; then
        err "ffmpeg/ffprobe still not found after install."
        exit 1
    fi
    info "ffmpeg installed ($(ffmpeg -version | head -1))"
}

ensure_espeak_ng() {
    if have espeak-ng; then
        info "espeak-ng already installed ($(espeak-ng --version | head -1))"
        return
    fi
    info "Installing espeak-ng..."
    if [ "$PLATFORM" = "macos" ]; then
        install_brew_package espeak-ng
    else
        install_linux_package espeak-ng
    fi
    if ! have espeak-ng; then
        err "espeak-ng still not found after install."
        exit 1
    fi
    info "espeak-ng installed ($(espeak-ng --version | head -1))"
}

# ---- run ------------------------------------------------------------------
ensure_uv
ensure_ffmpeg
ensure_espeak_ng

info "Syncing project (installs Python 3.13 + dependencies into .venv)..."
uv sync

info "Done. Try it:"
printf '    uv run python -m audiobook_generator --file documents/book.pdf --pages 1-3\n'
if [ "$UV_FRESHLY_INSTALLED" -eq 1 ]; then
    printf '\n'
    warn "uv was installed this run — open a new terminal (or 'source ~/.bashrc') so it stays on PATH."
fi
