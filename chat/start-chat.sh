#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT="$(dirname "$DIR")"
PORT="${CHAT_PORT:-7722}"

echo "✨ Magic Factory Chat"

# Load .env from parent if available
if [ -f "$PARENT/.env" ]; then
    set -a; . "$PARENT/.env"; set +a
fi

MODEL="${SPARK_MODEL:-qwen3-coder-next}"

# Check if already running
PIDFILE="$DIR/.chat.pid"
if [ -f "$PIDFILE" ]; then
    OLD_PID=$(cat "$PIDFILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "  Already running (PID $OLD_PID). Kill with: kill $OLD_PID"
        exit 1
    fi
    rm -f "$PIDFILE"
fi

# No venv needed — zero external dependencies (stdlib only)
python3 "$DIR/chat.py" --model "$MODEL" --port "$PORT" &
CHAT_PID=$!
echo "$CHAT_PID" > "$PIDFILE"

sleep 1
if kill -0 "$CHAT_PID" 2>/dev/null; then
    echo "  Running (PID $CHAT_PID). Terminal is yours."
    echo "  Stop:  kill $CHAT_PID"
else
    echo "  ERROR: Failed to start."
    rm -f "$PIDFILE"
    exit 1
fi
