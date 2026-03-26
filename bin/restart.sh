#!/usr/bin/env bash
set -euo pipefail
# ptr f0010001

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "✨ NVIDIA DGX Spark Magic Factory — restarting"
echo ""

# ptr f0010002
# Snapshot which services were running before we stop everything
HAD_CHAT=false
HAD_WEBUI=false
curl -sf http://localhost:7722/ -o /dev/null 2>&1 && HAD_CHAT=true
curl -sf http://localhost:7733/health -o /dev/null 2>&1 && HAD_WEBUI=true

"$DIR/bin/stop.sh" || true

echo ""
echo "  Starting..."
echo ""

"$DIR/bin/start.sh"

# ptr f0010003
# Load env for SPARK_MODEL
[ -f "$DIR/.env" ] && { set -a; . "$DIR/.env"; set +a; }
MODEL="${SPARK_MODEL:-qwen3-coder-next}"

# Relaunch Open WebUI if it was running
if [ "$HAD_WEBUI" = true ]; then
    echo "  Restarting Open WebUI..."
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^open-webui$'; then
        echo "  Open WebUI already running."
    else
        docker start open-webui 2>/dev/null || \
            docker run -d --network=host \
                -e OLLAMA_BASE_URL=http://127.0.0.1:11434 \
                -e PORT=7733 \
                -e WEBUI_SECRET_KEY="${WEBUI_SECRET_KEY:-$(python3 -c "import secrets; print(secrets.token_hex(32))")}" \
                -v open-webui:/app/backend/data \
                --name open-webui --restart unless-stopped \
                ghcr.io/open-webui/open-webui:main
        for i in $(seq 1 36); do
            curl -sf http://localhost:7733/health -o /dev/null 2>/dev/null && break
            sleep 5
        done
    fi
    if curl -sf http://localhost:7733/health -o /dev/null 2>/dev/null; then
        echo "  Open WebUI is up."
        "$DIR/bin/svc" set open-webui 7733
    else
        echo "  WARN: Open WebUI did not come back up."
    fi
fi

# Relaunch Magic Factory Chat if it was running
if [ "$HAD_CHAT" = true ]; then
    echo "  Restarting Magic Factory Chat..."
    CHAT_DIR="$DIR/chat"
    if [ -f "$CHAT_DIR/chat.py" ]; then
        if [ -f "$CHAT_DIR/.chat.pid" ]; then
            kill "$(cat "$CHAT_DIR/.chat.pid")" 2>/dev/null || true
            rm -f "$CHAT_DIR/.chat.pid"
        fi
        python3 "$CHAT_DIR/chat.py" --model "$MODEL" --port 7722 >/dev/null 2>&1 &
        CHAT_PID=$!
        echo "$CHAT_PID" > "$CHAT_DIR/.chat.pid"
        sleep 2
        if curl -sf http://localhost:7722/ -o /dev/null 2>&1; then
            echo "  Magic Factory Chat is up (PID $CHAT_PID)."
            "$DIR/bin/svc" set chat 7722 "$CHAT_PID"
        else
            echo "  WARN: Magic Factory Chat did not come back up."
        fi
    else
        echo "  WARN: chat/chat.py not found, skipping."
    fi
fi

# ptr f0010004
# Open all running services in Firefox
sleep 1
"$DIR/bin/svc" open
