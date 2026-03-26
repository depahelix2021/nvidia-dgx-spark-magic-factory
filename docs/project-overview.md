# Project Overview

**NVIDIA DGX Spark Magic Factory** is a long-running build harness for setting up local LLMs on an NVIDIA DGX Spark system (ARM64, Blackwell GPU, 128GB RAM).

## What It Does

A Flask web UI (port 7711) orchestrates:
- Installing **Ollama** (local LLM runtime, port 11434)
- Pulling LLM models
- Launching **Open WebUI** via Docker (port 7733)
- Launching **Magic Factory Chat**, a zero-dependency Python chat UI (port 7722)

## Key Components

| File | Purpose |
|------|---------|
| `app.py` | Flask app with SSE event bus, step runner, build registry, security scanner |
| `chat/chat.py` | Standalone chat UI that talks to Ollama — single file, no dependencies |
| `bin/svc` | CLI tool for the service registry (`services.json`) |
| `templates/index.html` | Web UI with Steps, Builds, and Logs views |
| `bin/start.sh / stop.sh / restart.sh` | Lifecycle scripts |
| `bin/show.sh` | Opens running services in browser |
| `bin/uninstall.sh` | Full removal |
| `extras/` | Bonus utility scripts (cleanup, kill-ports, NoMachine setup) |

## Design

- All state is append-only under `data/`
- Real-time updates via Server-Sent Events (SSE)
- Each build is isolated with its own port, container, and venv
- Optional Claude API integration for automated debugging
