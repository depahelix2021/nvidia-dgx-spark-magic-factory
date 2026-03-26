# CLAUDE.md — NVIDIA DGX Spark Magic Factory

## What this project is

Long-running build harness for NVIDIA DGX Spark local LLM setup. Runs a Flask web UI on port 7711 that orchestrates installing Ollama, pulling models, launching Open WebUI (Docker, port 7733), and Magic Factory Chat (stdlib Python, port 7722). Designed to run for days unattended.

## Architecture

- **app.py** — Main Flask application. Event bus (SSE), step runner, build registry, Claude integration, security scanner. All output goes to the web UI via broadcast(), nothing to terminal.
- **bin/svc** — Python CLI for the service registry (services.json). Tracks what's running, syncs with reality, opens browsers.
- **chat/chat.py** — Zero-dependency chat UI. Talks to Ollama at localhost:11434. Single file with embedded HTML/CSS/JS.
- **templates/index.html** — Harness web UI. Three views: Steps, Builds, Logs. SSE for real-time updates. Auto-opens service tabs when they pass verification.
- **static/style.css** — Industrial control room aesthetic. Dark theme, monospace, amber/green/red signals.
- **bin/start.sh / stop.sh / restart.sh / show.sh / uninstall.sh** — Lifecycle shell scripts.
- **extras/** — Bonus utility scripts (cleanup, kill-ports, NoMachine setup).

## Key patterns

- All state under `data/` — logs, builds, research. Immutable once written (append-only).
- SSE event bus: `broadcast()` sends to all connected clients. Events logged to `data/logs/session_*.jsonl`.
- Security: all commands scanned against blocklist before execution. Claude-suggested commands auto-applied if safe, require human approval if blocked.
- Loop detection: 2+ identical errors or 5+ total attempts triggers escalation to Claude Opus.
- Build isolation: each build gets its own port, Docker container name, venv. GPU, Ollama, and models are shared.

## Commands

All should be run with `sudo` (see docs/commands.md for why):
```
sudo bin/start.sh        # Start the harness
sudo bin/stop.sh         # Stop everything
sudo bin/restart.sh      # Stop + start
sudo bin/show.sh         # Open running services in browser
sudo bin/uninstall.sh    # Full removal
```

## Ports

- 7711 — Harness web UI (Flask)
- 7722 — Magic Factory Chat
- 7733 — Open WebUI (Docker)
- 7750-7769 — Build port pool
- 11434 — Ollama API

## Documentation convention

English documentation is extracted from code into the `docs/` directory (e.g., `docs/app.md` documents `app.py`). Code files contain only `ptr <uuid>` marker comments that cross-reference the documentation. This keeps code clean and documentation maintainable.

## Environment

- Target: DGX Spark (ARM64/aarch64, Ubuntu 24.04, Blackwell GPU, 128GB RAM)
- Python 3.10+, Flask, python-dotenv
- Docker for Open WebUI
- Optional: ANTHROPIC_API_KEY for Claude-assisted debugging
