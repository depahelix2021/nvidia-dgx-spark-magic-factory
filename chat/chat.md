# chat/chat.py — Documentation

## ptr c0010001 — Module overview

Magic Factory Chat is a zero-dependency local chat UI for Ollama models.

- Talks directly to Ollama at localhost:11434
- No auth, no Docker, no external services
- Streams responses token-by-token
- All conversations stay on your machine
- Single file, embedded HTML

Usage:
- `python chat.py` — default model
- `python chat.py --model qwen3-coder:30b` — specific model
- `python chat.py --port 7722` — custom port

## ptr c0010002 — Ollama helpers

`ollama_models()` lists available models from Ollama via `GET /api/tags`. Returns list of model name strings.

`ollama_stream(model, messages)` is a generator that yields content chunks from Ollama's `POST /api/chat` endpoint. Reads response byte-by-byte, parses newline-delimited JSON, extracts `message.content` fields. 600 second timeout.

## ptr c0010003 — Embedded HTML/CSS/JS

The entire chat UI is embedded as a raw string `HTML_PAGE`. Design: dark theme, JetBrains Mono + Space Grotesk fonts, minimal chrome. Features: auto-resize textarea, streaming response display with typing indicator, clear button, model name display, error banner, "100% local" badge.

CSS sections: header, chat area with scrollbar styling, message bubbles (user = blue-bordered, assistant = transparent), typing indicator (blinking cursor), welcome screen, input area with send button, error banner. Responsive for mobile.

JavaScript: `init()` fetches model info from `/api/info`, `sendMessage()` POSTs to `/api/chat` and reads the streaming response via ReadableStream, `appendMessage()` creates DOM elements, `clearChat()` resets state.

## ptr c0010004 — HTTP server

`ChatHandler` extends `BaseHTTPRequestHandler`. Request logging silenced.

Routes:
- `GET /` — Serves the embedded HTML page
- `GET /api/info` — Returns model name, available models, Ollama connectivity status. Resolves short model names (e.g., `qwen3-coder-next` to `qwen3-coder-next:latest`).
- `POST /api/chat` — Proxies to Ollama's streaming chat API. Uses HTTP chunked transfer encoding. Handles stream errors gracefully by appending error message to the response stream.

`send_json(data)` helper for JSON responses. `_ollama_ping()` checks if Ollama is responding.

## ptr c0010005 — Main entry point

Parses `--model` and `--port` arguments. Resolves model name against Ollama's model list. Prints startup info (model, Ollama host, available models, privacy note). Starts HTTPServer on 127.0.0.1. Handles KeyboardInterrupt for clean shutdown.
