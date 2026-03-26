# stop.sh — Documentation

## ptr e0010001 — Header

Bash script with `set -uo pipefail` (no -e, so failures don't abort the whole script — we want to try stopping everything).

## ptr e0010002 — Stop Magic Factory Chat

Checks `chat/.chat.pid` for a running chat process. Sends SIGTERM, waits 1 second, then SIGKILL if still alive. Removes PID file. Drops from svc registry.

## ptr e0010003 — Stop Open WebUI Docker containers

If Docker is available, stops containers named `open-webui` or `openwebui`. Also catches build-specific containers matching `openwebui-*` pattern. Uses `--time 10` for graceful shutdown. Drops from svc registry.

## ptr e0010004 — Stop the harness process

Three-tier approach:
1. **PID file** — reads `.pid`, sends SIGTERM, waits up to 5 seconds (polling every 0.5s), then SIGKILL if needed
2. **Port fallback** — uses `lsof -ti :PORT` to find process listening on the port
3. **Process name fallback** — uses `pgrep -f "app.py --port PORT"` to find by command name

Drops from svc registry after stopping.
