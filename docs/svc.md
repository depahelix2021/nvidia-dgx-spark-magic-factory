# svc — Documentation

## ptr b0010001 — Module overview

Service registry CLI. Keeps services.json in sync with what's actually running.

Usage:
- `./svc sync` — reconcile file with what's actually running
- `./svc set NAME PORT [PID]` — mark a service as expected-running
- `./svc drop NAME` — mark a service as stopped/uninstalled
- `./svc open` — open running+ready services in Firefox
- `./svc show` — print status table (no browser)

## ptr b0010002 — Known services

Three known services with their ports, PID files, and labels:
- **harness** (7711) — Magic Factory, PID in `.pid`
- **chat** (7722) — Magic Factory Chat, PID in `chat/.chat.pid`
- **open-webui** (7733) — Open WebUI, Docker container named `open-webui`

## ptr b0010003 — Helper functions

- `_load()` / `_save(data)` — Read/write services.json
- `_pid_alive(pid)` — Check if a process is alive via `os.kill(pid, 0)`. Returns True even if PermissionError (process exists but owned by another user)
- `_port_listening(port)` — TCP connect test to 127.0.0.1:port with 0.3s timeout
- `_http_ready(port)` — HTTP GET to `http://127.0.0.1:{port}/` with 0.8s timeout, passes if status < 500
- `_read_pid_file(path)` — Read PID from a file, returns int or None
- `_docker_running(name)` — Check if a Docker container is running by name. Also matches build-specific names (e.g., `openwebui-XXXX` matches `open-webui`)

## ptr b0010004 — Sync command

`cmd_sync()` reconciles services.json with reality. For each known service:
- Docker services: checks container running + port listening, then HTTP readiness
- Process services: checks PID file, falls back to lsof port ownership if PID doesn't match
- Also verifies unknown entries (e.g., build containers) by port

## ptr b0010005 — Set and drop commands

`cmd_set(name, port, pid)` registers a service as running. `cmd_drop(name)` marks it stopped (running=false, ready=false, pid=null).

## ptr b0010006 — Show command

`cmd_show()` runs sync then prints a status table with icons: lightning bolt (ready), hourglass (running), black square (stopped).

## ptr b0010007 — Open command

`cmd_open()` runs sync, then for each running service waits up to 6 seconds for HTTP readiness. Opens ready services in Firefox. Skips services that don't become ready.

## ptr b0010008 — Main dispatch

CLI argument dispatch: no args or "show" runs cmd_show, "sync" runs sync+show, "open" runs cmd_open, "set" and "drop" pass through arguments.
