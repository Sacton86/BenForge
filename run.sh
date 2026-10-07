#!/usr/bin/env bash
# ==============================================================================
# BenForge — Launcher Script
# Starts BenForge in compiled binary mode (if present) or via Python virtualenv.
# ==============================================================================

set -e

# Resolve the project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPILED_BIN="$SCRIPT_DIR/dist/BenForge_v1.0.0/BenForge_v1.0.0"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

# Check if user explicitly wants source/dev mode
if [[ "$1" == "--dev" || "$1" == "--source" ]]; then
    USE_SOURCE=1
    shift
else
    USE_SOURCE=0
fi

echo "=========================================================="
echo " Starting BenForge — 3D Pattern Unfolder & Fabrication"
echo "=========================================================="

if [[ "$USE_SOURCE" -eq 0 && -x "$COMPILED_BIN" ]]; then
    echo "Running compiled standalone binary: $COMPILED_BIN"
    exec "$COMPILED_BIN" "$@"
elif [[ -x "$VENV_PYTHON" ]]; then
    echo "Running via virtual environment Python (.venv)..."
    exec "$VENV_PYTHON" "$SCRIPT_DIR/app.py" "$@"
elif command -v python3 &>/dev/null; then
    echo "Running via system Python..."
    exec python3 "$SCRIPT_DIR/app.py" "$@"
else
    echo "Error: Neither compiled binary nor Python executable could be found." >&2
    exit 1
fi
