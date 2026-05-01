#!/usr/bin/env bash
# Meshgram relay — launcher for Linux / macOS.
# Mirrors run_relay.bat: checks python, deps, lists serial ports, runs.
set -euo pipefail
cd "$(dirname "$0")"

echo
echo " ================================================================"
echo "   MESHTASTIC <--> TELEGRAM   public relay"
echo " ================================================================"
echo

# 1. Python 3.10+
if ! command -v python3 >/dev/null 2>&1; then
    echo " [X]  python3 not found. Install Python 3.10+:"
    echo "      Ubuntu/Debian:  sudo apt install python3 python3-venv python3-pip"
    echo "      Fedora:         sudo dnf install python3 python3-pip"
    echo "      Arch:           sudo pacman -S python python-pip"
    exit 1
fi
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
echo " [OK] python3 $PYV"

[ -f "relay.py" ] || { echo " [X]  relay.py not found next to this script"; exit 1; }
echo " [OK] relay.py"

# 2. Token check (skip if .env exists with a non-placeholder token)
if [ -f ".env" ] && grep -q "^BOT_TOKEN=" .env && ! grep -q "PASTE_BOT_TOKEN_HERE\|PASTE_RELAY_BOT_TOKEN_HERE" .env; then
    echo " [OK] BOT_TOKEN set in .env"
else
    if grep -q "PASTE_RELAY_BOT_TOKEN_HERE" relay.py 2>/dev/null; then
        echo " [!]  TOKEN NOT SET"
        echo "      Either edit relay.py (find PASTE_RELAY_BOT_TOKEN_HERE)"
        echo "      OR create .env from .env.example and put your @BotFather token there."
        exit 1
    fi
fi

# 3. Deps via venv (recommended) or system pip
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo " [..] Creating venv $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if ! python -c 'import meshtastic, telegram' >/dev/null 2>&1; then
    echo " [..] Installing dependencies..."
    python -m pip install --quiet --upgrade pip
    python -m pip install -r ../requirements.txt
fi
echo " [OK] dependencies"

# 4. Serial ports
echo
echo " Available serial devices:"
python - <<'PY' || true
import os, glob
patterns = ['/dev/ttyUSB*', '/dev/ttyACM*', '/dev/serial/by-id/*']
seen = []
for p in patterns:
    for path in glob.glob(p):
        if path not in seen:
            seen.append(path)
            print(f"   {path}")
if not seen:
    print("   (none found — check USB cable / dialout group membership)")
PY
echo
echo "   Enter:  full path (e.g. /dev/ttyUSB0), 'a' = auto-detect, 'q' = quit"
read -r -p "   Your choice: " port

case "$port" in
    q|Q) exit 0 ;;
    a|A|"") PORT_ARG="" ;;
    *) PORT_ARG="--port $port" ;;
esac

# 5. Run
echo
echo " ================================================================"
echo "   Starting relay.py $PORT_ARG"
echo "   Press Ctrl+C to stop"
echo " ================================================================"
echo
# shellcheck disable=SC2086
exec python relay.py $PORT_ARG
