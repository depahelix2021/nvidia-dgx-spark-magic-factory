#!/usr/bin/env bash
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIDFILE="$DIR/.pid"
PORT="${PORT:-7711}"

echo "✨ NVIDIA DGX Spark Magic Factory — stopping"

# ptr e0010002
CHAT_PID_FILE="$DIR/chat/.chat.pid"
if [ -f "$CHAT_PID_FILE" ]; then
    CHAT_PID=$(cat "$CHAT_PID_FILE")
    if kill -0 "$CHAT_PID" 2>/dev/null; then
        echo "  Stopping Magic Factory Chat (PID $CHAT_PID)..."
        kill "$CHAT_PID" 2>/dev/null
        sleep 1
        kill -0 "$CHAT_PID" 2>/dev/null && kill -9 "$CHAT_PID" 2>/dev/null
        echo "  Magic Factory Chat stopped."
    fi
    rm -f "$CHAT_PID_FILE"
fi
"$DIR/bin/svc" drop chat

# ptr e0010003
if command -v docker &>/dev/null; then
    for name in open-webui openwebui; do
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${name}$"; then
            echo "  Stopping Docker container: $name"
            docker stop "$name" --time 10 2>/dev/null
            echo "  Stopped $name."
        fi
    done
    for cname in $(docker ps --format '{{.Names}}' 2>/dev/null | grep '^openwebui-'); do
        echo "  Stopping Docker container: $cname"
        docker stop "$cname" --time 10 2>/dev/null
        echo "  Stopped $cname."
    done
fi
"$DIR/bin/svc" drop open-webui

# ptr e0010004
stopped=false

if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "  Sending SIGTERM to harness PID $PID..."
        kill "$PID"
        for i in $(seq 1 10); do
            kill -0 "$PID" 2>/dev/null || { echo "  Harness stopped."; rm -f "$PIDFILE"; stopped=true; break; }
            sleep 0.5
        done
        if [ "$stopped" = false ]; then
            echo "  Still running after 5s, sending SIGKILL..."
            kill -9 "$PID" 2>/dev/null
            rm -f "$PIDFILE"
            stopped=true
            echo "  Killed."
        fi
    else
        echo "  PID $PID from .pid file is not running (stale)."
        rm -f "$PIDFILE"
    fi
fi

if [ "$stopped" = false ]; then
    PID=$(lsof -ti :"$PORT" 2>/dev/null | head -1)
    if [ -n "$PID" ]; then
        echo "  Found process $PID listening on port $PORT, stopping..."
        kill "$PID"
        sleep 1
        kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
        echo "  Stopped."
        stopped=true
    fi
fi

if [ "$stopped" = false ]; then
    PID=$(pgrep -f "app.py --port $PORT" 2>/dev/null | head -1)
    if [ -n "$PID" ]; then
        echo "  Found process $PID via pgrep, stopping..."
        kill "$PID"
        sleep 1
        kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
        echo "  Stopped."
        stopped=true
    fi
fi

if [ "$stopped" = false ]; then
    echo "  No running Magic Factory harness found."
fi
"$DIR/bin/svc" drop harness

echo "  Done."
exit 0
