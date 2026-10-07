#!/usr/bin/env bash
# ==============================================================================
# BenForge — one-shot installer / updater (Linux)
#
# Run it to install BenForge fresh, or run it again later to update to the
# newest version. It will:
#   1. Install system prerequisites (git, python3, venv, tk)      [apt systems]
#   2. Clone the repo (or fast-forward it if already present)
#   3. Create a Python virtual environment and install dependencies
#   4. Download the matching Blender engine if one isn't available
#
# Quick start (one line):
#   curl -fsSL https://raw.githubusercontent.com/Sacton86/BenForge/main/install_benforge.sh | bash
#
# Install location defaults to ~/BenForge. Override with:
#   BENFORGE_DIR=/opt/benforge bash install_benforge.sh
# ==============================================================================
set -euo pipefail

REPO_URL="https://github.com/Sacton86/BenForge.git"
INSTALL_DIR="${BENFORGE_DIR:-$HOME/BenForge}"
BLENDER_VER="4.1.1"
BLENDER_URL="https://download.blender.org/release/Blender4.1/blender-${BLENDER_VER}-linux-x64.tar.xz"

info()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn()  { printf '\033[1;33m!  %s\033[0m\n' "$*"; }
die()   { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

SUDO=""
[ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO="sudo"

# ------------------------------------------------------------------ 1. OS deps
if command -v apt-get >/dev/null 2>&1; then
    info "Installing system packages (git, python3, venv, pip, tk, xz, curl)..."
    $SUDO apt-get update -y
    $SUDO apt-get install -y git python3 python3-venv python3-pip python3-tk xz-utils curl
else
    warn "Non-apt system detected. Please make sure these are installed yourself:"
    warn "  git, python3, python3-venv, python3-tk, tar, xz, curl"
    for c in git python3 curl tar; do
        command -v "$c" >/dev/null 2>&1 || die "Required command '$c' not found."
    done
fi

# ------------------------------------------------------------- 2. Clone/update
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Updating existing BenForge in $INSTALL_DIR ..."
    git -C "$INSTALL_DIR" fetch --tags origin
    if ! git -C "$INSTALL_DIR" pull --ff-only; then
        warn "Could not fast-forward (you may have local changes)."
        warn "Fix or stash them in $INSTALL_DIR, then re-run. Continuing with current version."
    fi
else
    info "Cloning BenForge into $INSTALL_DIR ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# ------------------------------------------------------------- 3. Python setup
info "Setting up Python environment (.venv)..."
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip >/dev/null
# customtkinter is the only runtime dependency; tkinter ships with python3-tk.
./.venv/bin/python -m pip install --upgrade customtkinter

# --------------------------------------------------------- 4. Blender engine
if [ -x "$INSTALL_DIR/engine/blender_linux/blender" ]; then
    info "Blender engine already present (engine/blender_linux)."
elif command -v blender >/dev/null 2>&1; then
    info "Using system Blender found on PATH: $(command -v blender)"
else
    info "Downloading Blender ${BLENDER_VER} engine (~298 MB, one time)..."
    mkdir -p "$INSTALL_DIR/engine"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    curl -fL# "$BLENDER_URL" -o "$tmp/blender.tar.xz" || die "Blender download failed."
    info "Extracting Blender engine..."
    tar -xf "$tmp/blender.tar.xz" -C "$tmp"
    rm -rf "$INSTALL_DIR/engine/blender_linux"
    mv "$tmp/blender-${BLENDER_VER}-linux-x64" "$INSTALL_DIR/engine/blender_linux"
    [ -x "$INSTALL_DIR/engine/blender_linux/blender" ] || die "Blender engine not set up correctly."
fi

chmod +x "$INSTALL_DIR/run.sh" 2>/dev/null || true

info "BenForge is ready."
printf '\n  Launch it with:\n    \033[1m%s/run.sh\033[0m\n\n' "$INSTALL_DIR"
printf '  (Re-run this script any time to update to the latest version.)\n\n'
