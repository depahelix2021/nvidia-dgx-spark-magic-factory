#!/usr/bin/env bash
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${RED}${BOLD}✨ NVIDIA DGX Spark Magic Factory — FULL UNINSTALL${NC}"
echo ""
echo "This will completely remove:"
echo "  1. Magic Factory harness + Chat (processes, venv, data, pid files)"
echo "  2. Open WebUI (Docker container + volume + image)"
echo "  3. All Ollama models (including qwen3-coder-next)"
echo "  4. Ollama itself (binary, systemd service, stored models)"
echo ""
echo -e "${YELLOW}WARNING: This is destructive and cannot be undone.${NC}"
echo -e "${YELLOW}Docker itself and NVIDIA drivers will NOT be removed.${NC}"
echo ""
read -rp "Type YES to continue: " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
    echo "Aborted."
    exit 0
fi
echo ""

# ptr g0010002
echo -e "${BOLD}[1/4] Stopping all running processes...${NC}"

if [ -f "$DIR/bin/stop.sh" ]; then
    bash "$DIR/bin/stop.sh" 2>/dev/null || true
fi

for port in 7711 7722 7733 $(seq 7750 7769); do
    PID=$(lsof -ti :"$port" 2>/dev/null | head -1)
    if [ -n "$PID" ]; then
        echo "  Killing process $PID on port $port"
        kill -9 "$PID" 2>/dev/null || true
    fi
done

pgrep -f "$DIR/app.py" 2>/dev/null | while read -r p; do
    echo "  Killing app.py process $p"
    kill -9 "$p" 2>/dev/null || true
done
pgrep -f "$DIR/chat/chat.py" 2>/dev/null | while read -r p; do
    echo "  Killing chat.py process $p"
    kill -9 "$p" 2>/dev/null || true
done

echo -e "${GREEN}  Done.${NC}"
echo ""

# ptr g0010003
echo -e "${BOLD}[2/4] Removing Open WebUI...${NC}"

if command -v docker &>/dev/null; then
    for name in open-webui openwebui; do
        if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${name}$"; then
            echo "  Removing container: $name"
            docker rm -f "$name" 2>/dev/null || true
        fi
    done
    for pattern in '^openwebui-' '^open-webui-'; do
        for cname in $(docker ps -a --format '{{.Names}}' 2>/dev/null | grep "$pattern"); do
            echo "  Removing container: $cname"
            docker rm -f "$cname" 2>/dev/null || true
        done
    done

    if docker volume ls -q 2>/dev/null | grep -q '^open-webui$'; then
        echo "  Removing Docker volume: open-webui"
        docker volume rm open-webui 2>/dev/null || true
    fi

    IMAGES=$(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep 'open-webui' || true)
    if [ -n "$IMAGES" ]; then
        echo "  Removing Docker image(s):"
        echo "$IMAGES" | while read -r img; do
            echo "    $img"
            docker rmi -f "$img" 2>/dev/null || true
        done
    fi

    DANGLING=$(docker images -f "dangling=true" -q 2>/dev/null || true)
    if [ -n "$DANGLING" ]; then
        echo "  Pruning dangling Docker images..."
        docker image prune -f 2>/dev/null || true
    fi

    echo -e "${GREEN}  Done.${NC}"
else
    echo "  Docker not found, skipping."
fi
echo ""

# ptr g0010004
echo -e "${BOLD}[3/4] Removing Ollama and all models...${NC}"

OLLAMA_BIN=""
if [ -f /tmp/.ollama_path ]; then
    OLLAMA_BIN=$(tr -d '\n\r' < /tmp/.ollama_path)
fi
if [ -z "$OLLAMA_BIN" ] || [ ! -x "$OLLAMA_BIN" ]; then
    OLLAMA_BIN=$(command -v ollama 2>/dev/null || true)
fi

if [ -n "$OLLAMA_BIN" ] && [ -x "$OLLAMA_BIN" ]; then
    echo "  Deleting all Ollama models..."
    "$OLLAMA_BIN" list 2>/dev/null | tail -n +2 | awk '{print $1}' | while read -r model; do
        if [ -n "$model" ]; then
            echo "    Removing model: $model"
            "$OLLAMA_BIN" rm "$model" 2>/dev/null || true
        fi
    done
fi

echo "  Stopping Ollama service..."
if systemctl is-active ollama >/dev/null 2>&1; then
    sudo systemctl stop ollama 2>/dev/null || true
fi
if systemctl is-enabled ollama >/dev/null 2>&1; then
    sudo systemctl disable ollama 2>/dev/null || true
fi
pkill -f 'ollama serve' 2>/dev/null || true
pkill -f 'ollama' 2>/dev/null || true
sleep 1

for bin in /usr/local/bin/ollama /usr/bin/ollama /snap/bin/ollama "$HOME/.local/bin/ollama" "$HOME/bin/ollama" /opt/ollama/bin/ollama; do
    if [ -f "$bin" ] || [ -L "$bin" ]; then
        echo "  Removing binary: $bin"
        sudo rm -f "$bin" 2>/dev/null || rm -f "$bin" 2>/dev/null || true
    fi
done

for svc in /etc/systemd/system/ollama.service /usr/lib/systemd/system/ollama.service; do
    if [ -f "$svc" ]; then
        echo "  Removing systemd service: $svc"
        sudo rm -f "$svc" 2>/dev/null || true
    fi
done
sudo systemctl daemon-reload 2>/dev/null || true

if [ -d "$HOME/.ollama" ]; then
    echo "  Removing $HOME/.ollama/ (all model data)..."
    rm -rf "$HOME/.ollama"
fi

if [ -d /usr/share/ollama ]; then
    echo "  Removing /usr/share/ollama/..."
    sudo rm -rf /usr/share/ollama 2>/dev/null || true
fi

if id ollama &>/dev/null; then
    echo "  Removing 'ollama' system user..."
    sudo userdel ollama 2>/dev/null || true
fi
if getent group ollama &>/dev/null; then
    echo "  Removing 'ollama' system group..."
    sudo groupdel ollama 2>/dev/null || true
fi

rm -f /tmp/.ollama_path /tmp/ollama_serve.log 2>/dev/null || true

echo -e "${GREEN}  Done.${NC}"
echo ""

# ptr g0010005
echo -e "${BOLD}[4/4] Cleaning up Magic Factory local files...${NC}"

if [ -d "$DIR/.venv" ]; then
    echo "  Removing Python venv..."
    rm -rf "$DIR/.venv"
fi

if [ -d "$DIR/data" ]; then
    echo "  Removing data/ (logs, builds, research)..."
    rm -rf "$DIR/data"
fi

rm -f "$DIR/.pid" "$DIR/chat/.chat.pid" 2>/dev/null

find "$DIR" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

if [ -f "$DIR/.env" ]; then
    echo "  Removing .env"
    rm -f "$DIR/.env"
fi

echo -e "${GREEN}  Done.${NC}"
echo ""

# ptr g0010006
echo -e "${BOLD}Verifying cleanup...${NC}"
CLEAN=true

if command -v ollama &>/dev/null; then
    echo -e "  ${RED}WARNING: 'ollama' still on PATH: $(command -v ollama)${NC}"
    CLEAN=false
else
    echo -e "  ${GREEN}ollama binary: gone${NC}"
fi

if [ -d "$HOME/.ollama" ]; then
    echo -e "  ${RED}WARNING: ~/.ollama still exists${NC}"
    CLEAN=false
else
    echo -e "  ${GREEN}~/.ollama: gone${NC}"
fi

if command -v docker &>/dev/null; then
    OW_CONTAINERS=$(docker ps -a --format '{{.Names}}' 2>/dev/null | grep -c 'open.webui' || true)
    if [ "$OW_CONTAINERS" -gt 0 ]; then
        echo -e "  ${RED}WARNING: $OW_CONTAINERS open-webui container(s) still exist${NC}"
        CLEAN=false
    else
        echo -e "  ${GREEN}Open WebUI containers: gone${NC}"
    fi
    OW_IMAGES=$(docker images 2>/dev/null | grep -c 'open-webui' || true)
    if [ "$OW_IMAGES" -gt 0 ]; then
        echo -e "  ${RED}WARNING: $OW_IMAGES open-webui image(s) still exist${NC}"
        CLEAN=false
    else
        echo -e "  ${GREEN}Open WebUI images: gone${NC}"
    fi
fi

if [ -d "$DIR/.venv" ] || [ -d "$DIR/data" ]; then
    echo -e "  ${RED}WARNING: local data still exists${NC}"
    CLEAN=false
else
    echo -e "  ${GREEN}Local data (venv, data/): gone${NC}"
fi

for port in 7711 7722 7733; do
    if lsof -ti :"$port" &>/dev/null; then
        echo -e "  ${RED}WARNING: something still listening on port $port${NC}"
        CLEAN=false
    fi
done

echo ""
if [ "$CLEAN" = true ]; then
    echo -e "${GREEN}${BOLD}Uninstall complete. System is clean.${NC}"
else
    echo -e "${YELLOW}${BOLD}Uninstall finished with warnings (see above).${NC}"
fi
echo ""
echo "Removed:"
echo "  - All running Magic Factory processes"
echo "  - Open WebUI (containers, volumes, images)"
echo "  - Ollama (binary, service, all models, ~/.ollama)"
echo "  - Magic Factory local data (venv, logs, builds, pid files)"
echo ""
echo "NOT removed:"
echo "  - Docker itself"
echo "  - NVIDIA drivers / CUDA"
echo "  - This script directory (delete it yourself: rm -rf $DIR)"
echo ""
