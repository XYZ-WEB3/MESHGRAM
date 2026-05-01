#!/usr/bin/env bash
# Meshgram relay GUI — launcher for Linux / macOS.
# Setups venv on first run, then `python gui.py`.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "[X] python3 not found. See run_relay.sh for install hints."
    exit 1
fi

# Headless? GUI требует X11 / Wayland. Если их нет — direct relay лучше.
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo "[!] DISPLAY/WAYLAND_DISPLAY не задан. PyQt6-GUI здесь не запустится."
    echo "    Если ты на сервере — используй run_relay.sh (CLI), не GUI."
    echo "    Если по SSH — убедись что включён X11-forwarding (ssh -X)."
    exit 1
fi

VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if ! python -c 'import PyQt6, meshtastic, telegram, serial' >/dev/null 2>&1; then
    echo "[..] Installing dependencies..."
    python -m pip install --quiet --upgrade pip
    python -m pip install -r ../requirements.txt
fi

exec python gui.py
