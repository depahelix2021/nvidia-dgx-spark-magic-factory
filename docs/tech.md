Technologies Used — NVIDIA DGX Spark Magic Factory

Languages
  Python 3.10+
  Bash
  HTML / CSS / JavaScript

Frameworks & Libraries
  Flask (web UI and SSE event bus)
  Anthropic SDK (Claude API integration)
  python-dotenv (environment config)
  Docker SDK for Python
  APScheduler (task scheduling)

Infrastructure
  Docker (runs Open WebUI)
  Ollama (local LLM serving)
  Open WebUI (chat frontend, containerized)

Platform
  Ubuntu 24.04 (ARM64/aarch64)
  NVIDIA DGX Spark (Blackwell GPU, 128GB RAM)

Protocols & Patterns
  Server-Sent Events (SSE) for real-time UI updates
  JSONL for append-only logging
  REST API (Flask routes, Ollama API on port 11434)
