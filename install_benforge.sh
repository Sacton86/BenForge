#!/usr/bin/env bash
# ==============================================================================
# BenForge — one-shot installer / updater (Linux)
#
# Run it to install BenForge fresh, or run it again later to update to the
# newest version. It performs four clearly announced steps:
#   STEP 1/4  Install system prerequisites (git, python3, venv, tk)  [apt]
#   STEP 2/4  Clone the repo (or fast-forward it if already present)
#   STEP 3/4  Create a Python virtual environment and install dependencies
#   STEP 4/4  Download the matching Blender engine if one isn't available
#
# Everything printed to the screen is also saved to a timestamped log file.
# If anything fails, the script stops, prints exactly which step and command
# failed, and tells you where the log is so you can send it for support.
#
# Quick start (one line):
#   curl -fsSL https://raw.githubusercontent.com/Sacton86/BenForge/main/install_benforge.sh | bash
#
# Install location defaults to ~/BenForge. Override with:
#   BENFORGE_DIR=/opt/benforge bash install_benforge.sh
# ==============================================================================
set -Eeuo pipefail

SCRIPT_VERSION="1.1"
REPO_URL="https://github.com/Sacton86/BenForge.git"
INSTALL_DIR="${BENFORGE_DIR:-$HOME/BenForge}"
BLENDER_VER="4.1.1"
BLENDER_URL="https://download.blender.org/release/Blender4.1/blender-${BLENDER_VER}-linux-x64.tar.xz"

# ---- logging: mirror all output to a timestamped log file --------------------
LOG="${TMPDIR:-/tmp}/benforge-install-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

# ---- pretty printers ---------------------------------------------------------
c_cyan='\033[1;36m'; c_grn='\033[1;32m'; c_yel='\033[1;33m'; c_red='\033[1;31m'; c_rst='\033[0m'
STEP_CURRENT="startup"
step()  { STEP_CURRENT="$1"; printf "\n${c_cyan}========================================================\n STEP %s\n========================================================${c_rst}\n" "$*"; }
info()  { printf "${c_cyan}   -> %s${c_rst}\n" "$*"; }
ok()    { printf "${c_grn}   [OK] %s${c_rst}\n" "$*"; }
warn()  { printf "${c_yel}   !  %s${c_rst}\n" "$*"; }

# ---- failure handler: report step, line, command, and log path ---------------
on_error() {
    local rc=$?
    printf "\n${c_red}########################################################${c_rst}\n"
    printf "${c_red}  INSTALL FAILED${c_rst}\n"
    printf "${c_red}  Step   : %s${c_rst}\n" "$STEP_CURRENT"
    printf "${c_red}  Line   : %s${c_rst}\n" "${BASH_LINENO[0]:-?}"
    printf "${c_red}  Command: %s${c_rst}\n" "${BASH_COMMAND}"
    printf "${c_red}  Exit   : %s${c_rst}\n" "$rc"
    printf "${c_red}########################################################${c_rst}\n"
    printf "\n${c_yel}A full log was saved to:\n   %s\n${c_rst}" "$LOG"
    printf "${c_yel}Please send that file (or copy everything printed above)\nto report the problem.${c_rst}\n\n"
    exit "$rc"
}
trap on_error ERR

die() { STEP_CURRENT="${STEP_CURRENT}"; printf "${c_red}   ERROR: %s${c_rst}\n" "$*"; false; }

SUDO=""
[ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO="sudo"

# ---- environment banner (useful for bug reports) -----------------------------
printf "${c_cyan}============================================================${c_rst}\n"
printf "${c_cyan} BenForge Installer / Updater  (script v%s)${c_rst}\n" "$SCRIPT_VERSION"
printf "${c_cyan}============================================================${c_rst}\n"
echo   "   Date        : $(date)"
echo   "   User        : $(id -un) (uid $(id -u))"
echo   "   Machine     : $(uname -srm)"
echo   "   Distro      : $( (. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}") || echo unknown)"
echo   "   Python      : $(python3 --version 2>&1 || echo 'not found')"
echo   "   Install dir : $INSTALL_DIR"
echo   "   Log file    : $LOG"
[ -n "$SUDO" ] && info "Elevated steps will use 'sudo' (you may be prompted for your password)."

# =============================================================== STEP 1/4
step "1/4  System prerequisites"
if command -v apt-get >/dev/null 2>&1; then
    info "Updating package lists and installing: git python3 python3-venv python3-pip python3-tk xz-utils curl"
    $SUDO apt-get update -y
    $SUDO apt-get install -y git python3 python3-venv python3-pip python3-tk xz-utils curl
    ok "System packages installed."
else
    warn "This is not an apt-based system, so packages can't be auto-installed."
    warn "Please ensure these are installed: git python3 python3-venv python3-tk tar xz curl"
    for c in git python3 curl tar; do
        if command -v "$c" >/dev/null 2>&1; then ok "found: $c"; else die "required command '$c' is missing"; fi
    done
fi

# =============================================================== STEP 2/4
step "2/4  Download / update BenForge source"
if [ -d "$INSTALL_DIR/.git" ]; then
    info "Existing install found in $INSTALL_DIR — fetching latest..."
    git -C "$INSTALL_DIR" fetch --tags origin
    if git -C "$INSTALL_DIR" pull --ff-only; then
        ok "Updated to the latest version."
    else
        warn "Could not fast-forward (you may have local changes in $INSTALL_DIR)."
        warn "Keeping the current version. Stash/commit your changes and re-run to update."
    fi
else
    info "Cloning $REPO_URL into $INSTALL_DIR ..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    ok "Repository cloned."
fi
cd "$INSTALL_DIR"
info "Now at commit: $(git rev-parse --short HEAD)  ($(git log -1 --format=%s))"

# =============================================================== STEP 3/4
step "3/4  Python environment & dependencies"
if [ ! -d .venv ]; then
    info "Creating virtual environment in .venv ..."
    python3 -m venv .venv
    ok "Virtual environment created."
else
    info "Reusing existing .venv"
fi
info "Upgrading pip..."
./.venv/bin/python -m pip install --upgrade pip >/dev/null
info "Installing runtime dependency: customtkinter"
./.venv/bin/python -m pip install --upgrade customtkinter
./.venv/bin/python -c "import customtkinter, tkinter" \
    && ok "Python dependencies ready (customtkinter + tkinter import cleanly)." \
    || die "customtkinter/tkinter failed to import after install"

# =============================================================== STEP 4/4
step "4/4  Blender unfolding engine"
if [ -x "$INSTALL_DIR/engine/blender_linux/blender" ]; then
    ok "Bundled Blender engine already present (engine/blender_linux)."
elif command -v blender >/dev/null 2>&1; then
    ok "Using system Blender on PATH: $(command -v blender)"
else
    info "No Blender found. Downloading Blender ${BLENDER_VER} (~298 MB, one time)..."
    mkdir -p "$INSTALL_DIR/engine"
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    info "Downloading from $BLENDER_URL"
    curl -fL# "$BLENDER_URL" -o "$tmp/blender.tar.xz"
    ok "Download complete ($(du -h "$tmp/blender.tar.xz" | cut -f1))."
    info "Extracting engine (this takes a moment)..."
    tar -xf "$tmp/blender.tar.xz" -C "$tmp"
    rm -rf "$INSTALL_DIR/engine/blender_linux"
    mv "$tmp/blender-${BLENDER_VER}-linux-x64" "$INSTALL_DIR/engine/blender_linux"
    [ -x "$INSTALL_DIR/engine/blender_linux/blender" ] || die "Blender engine was not set up correctly"
    ok "Blender engine installed into engine/blender_linux."
fi

chmod +x "$INSTALL_DIR/run.sh" 2>/dev/null || true

# =============================================================== DONE
printf "\n${c_grn}============================================================${c_rst}\n"
printf "${c_grn} BenForge is installed and ready.${c_rst}\n"
printf "${c_grn}============================================================${c_rst}\n"
echo   "   Version  : $(git rev-parse --short HEAD)"
echo   "   Location : $INSTALL_DIR"
echo   "   Log file : $LOG"
printf "\n   Launch it with:\n      ${c_cyan}%s/run.sh${c_rst}\n" "$INSTALL_DIR"
printf "\n   Re-run this installer any time to update to the latest version.\n\n"
