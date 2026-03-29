#!/usr/bin/env bash
# ============================================================
#  Mimir's Memory Hub — macOS / Linux launcher
#  First run: automatically creates a virtual environment
#  and installs all dependencies.
# ============================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$DIR/venv"

# ── First-time setup ─────────────────────────────────────────────────
if [ ! -d "$VENV" ]; then
    echo ""
    echo " ============================================================"
    echo "  Mimir's Memory Hub - First Time Setup"
    echo " ============================================================"
    echo ""

    # Check Python 3.10+
    if ! command -v python3 &>/dev/null; then
        echo " ERROR: python3 not found."
        echo " Install Python 3.10+ from https://www.python.org or via your package manager:"
        echo "   macOS:   brew install python"
        echo "   Ubuntu:  sudo apt install python3 python3-venv"
        exit 1
    fi

    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

    if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
        echo " ERROR: Python 3.10 or newer is required (found $PY_VER)."
        exit 1
    fi

    echo " Python $PY_VER found."
    echo " Creating virtual environment..."
    python3 -m venv "$VENV"

    echo " Installing packages (this may take a minute)..."
    "$VENV/bin/pip" install -r "$DIR/requirements.txt" --quiet

    echo ""
    echo " ============================================================"
    echo "  Setup complete!"
    echo " ============================================================"
    echo ""
fi

# ── Launch ───────────────────────────────────────────────────────────
echo " ============================================================"
echo "  Mimir's Memory Hub"
echo "  Starting at http://127.0.0.1:19009"
echo "  Press Ctrl+C to stop."
echo " ============================================================"
echo ""

cd "$DIR"
"$VENV/bin/python" -m playground
