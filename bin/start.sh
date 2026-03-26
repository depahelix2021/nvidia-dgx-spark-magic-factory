#!/usr/bin/env bash
# ✨ NVIDIA DGX Spark Magic Factory
# Copyright 2026 Chris Morley / Lantern Light AI (https://www.lanternlight.ai)
# chris.morley@lanternlight.ai — Available for contracts & 100% remote work
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$DIR/.venv"
PORT="${PORT:-7711}"

# ptr d0010002
echo "✨ NVIDIA DGX Spark Magic Factory"
echo "  All output goes to the web UI. Terminal will be quiet after startup."
echo ""

# ptr d0010003
PY=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')")
        maj=${ver%%.*}; min=${ver#*.}
        if [ "$maj" -ge 3 ] && [ "$min" -ge 10 ]; then PY="$cmd"; break; fi
    fi
done
[ -z "$PY" ] && { echo "ERROR: Python 3.10+ required"; exit 1; }

# ptr d0010004
[ ! -d "$VENV" ] && "$PY" -m venv "$VENV"
. "$VENV/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$DIR/requirements.txt"

# ptr d0010005
if [ ! -f "$DIR/.env" ] && [ -f "$DIR/../env/.env" ]; then
    cp "$DIR/../env/.env" "$DIR/.env"
    echo "  Copied .env from ../env/.env"
fi
[ -f "$DIR/.env" ] && { set -a; . "$DIR/.env"; set +a; }

# ptr d0010006
if find "$DIR/data" -not -user "$(id -u)" -print -quit 2>/dev/null | grep -q .; then
    echo "  Fixing file permissions in data/ (requires sudo)..."
    sudo chown -R "$(id -u):$(id -g)" "$DIR/data"
fi

# ptr d0010007
if [ -f "$DIR/.pid" ]; then
    OLD_PID=$(cat "$DIR/.pid")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "  Already running (PID $OLD_PID). Opening in browser..."
        exec "$DIR/bin/show.sh"
    fi
    rm -f "$DIR/.pid"
fi

echo "  Open: http://localhost:$PORT"
echo "  Logs: $DIR/data/logs/"
echo "  Stop: bin/stop.sh"
echo ""

# ptr d0010008
# Open browser via D-Bus portal — works with snap Firefox under both sudo and non-sudo.
( sleep 2
  URL="http://localhost:$PORT"
  if [ "$(id -u)" = "0" ]; then
      REAL_USER="${SUDO_USER:-}"
      if [ -n "$REAL_USER" ]; then
          REAL_UID=$(id -u "$REAL_USER")
          sudo -u "$REAL_USER" \
              DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$REAL_UID/bus" \
              XDG_RUNTIME_DIR="/run/user/$REAL_UID" \
              gdbus call --session \
                  --dest org.freedesktop.portal.Desktop \
                  --object-path /org/freedesktop/portal/desktop \
                  --method org.freedesktop.portal.OpenURI.OpenURI \
                  "" "$URL" {} &>/dev/null
      fi
  else
      gdbus call --session \
          --dest org.freedesktop.portal.Desktop \
          --object-path /org/freedesktop/portal/desktop \
          --method org.freedesktop.portal.OpenURI.OpenURI \
          "" "$URL" {} &>/dev/null
  fi
) &

mkdir -p "$DIR/data/logs"

# ptr d0010009
LOG="$DIR/data/logs/startup.log"
python "$DIR/app.py" --port "$PORT" >"$LOG" 2>&1 &
APP_PID=$!
echo "$APP_PID" > "$DIR/.pid"

sleep 1
if kill -0 "$APP_PID" 2>/dev/null; then
    echo "  Running (PID $APP_PID). Terminal is yours."
    "$DIR/bin/svc" set harness "$PORT" "$APP_PID"
else
    echo "  ERROR: Failed to start. Check $LOG"
    rm -f "$DIR/.pid"
    "$DIR/bin/svc" drop harness
    exit 1
fi
