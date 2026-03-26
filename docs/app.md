# app.py — Documentation

## ptr a0010001 — Module overview

NVIDIA DGX Spark Magic Factory is a long-running build harness for DGX Spark LLM setup.

Architecture:
- Runs for days. All output goes to the web UI, nothing to terminal.
- Each build attempt runs inside a Docker container for isolation.
- Builds are archived immutably. Old builds are never modified.
- Periodic health checks re-test existing builds.
- Duplicate builds are detected via SHA256 checksums.
- Claude-suggested commands require human approval.
- All commands are security-scanned before execution.

## ptr a0010002 — Paths

All data lives under `data/`. Subdirectories:
- `data/logs/` — Session event logs (append-only JSONL)
- `data/builds/` — Exported build artifacts (immutable)
- `data/research/` — Claude advice transcripts
- `data/step_timings.json` — Historical step durations for time estimates

## ptr a0010003 — Timing system

`_save_timing(step_id, duration)` records step durations. Keeps last 5 runs per step for averaging. `_estimate_duration(step_id)` returns the average, used by progress bars in the frontend.

## ptr a0010004 — Model config

`MODEL_NAME` defaults to `qwen3-coder-next` (from SPARK_MODEL env var). `MIN_OLLAMA_VERSION` is `0.15.5`, required for MoE/SSM model support.

## ptr a0010005 — Logging

All Python logging is redirected to the event system via `UILogHandler`, not stdout. This includes Flask/werkzeug request logs. The terminal stays quiet after startup — everything goes to the web UI.

## ptr a0010006 — Suppressing Flask terminal output

werkzeug's stream handler is replaced with UILogHandler so no HTTP request logs appear on the terminal.

## ptr a0010007 — Event bus

`_clients` is a list of `queue.Queue` objects, one per connected SSE client. `_events` is the in-memory log (last 10,000 non-output events).

`broadcast(event_type, data)` sends an event to all SSE clients, appends to in-memory log, and flushes to disk (session JSONL file). High-frequency `step_output` events are sent to clients but skipped from disk/memory logging to avoid bloat.

## ptr a0010008 — Immutable file persistence

`persist_file(directory, prefix, ext, content)` writes content to a timestamped, never-overwritten file. Guards against clock collisions by appending a UUID suffix if the path already exists.

## ptr a0010009 — Security scanning

`VALID_ID` — regex for step IDs: lowercase alpha start, alphanumeric/underscore, max 64 chars.

`BLOCKED_PATTERNS` — regex patterns that cause commands to be blocked:
- curl/wget piped to bash/sh (except known-safe installers)
- `rm -rf /`, `mkfs`, `dd if=`, `chmod 777 /`
- Writing to `/etc/`
- eval(), base64 decode piped to shell
- Netcat listeners, nohup+disown, `/dev/tcp/`
- Python socket imports via command line

`SAFE_DOMAINS` — hosts that are allowed in curl/wget URLs without warning (localhost, ghcr.io, ollama.com, docker.io, etc.)

`SAFE_PIPE_PATTERNS` — specific curl|sh URLs that are known-safe official installers (ollama, docker, uv, pyenv).

`scan_command(cmd)` returns a list of warnings. Warnings prefixed with "BLOCKED:" prevent execution entirely. Warnings prefixed with "WARNING:" are informational but allow execution.

## ptr a001000a — SHA256 utilities

`sha256(text)` — hash a string. `file_sha256(path)` — hash a file in 8KB chunks.

## ptr a001000b — Build registry

`BuildRegistry` manages immutable build records on disk.

Isolation strategy for coexisting builds on a single DGX Spark:

Fully isolated per build:
- Python venvs (`data/builds/<id>/venv/`)
- Docker container names (`open-webui-<build_id_short>`)
- Ports (allocated from pool 7750-7769, stored in manifest)
- Install/teardown scripts

Shared (one version, all builds use it):
- Ollama binary (system-wide, backward compatible)
- Ollama models (stored in `~/.ollama/models`, models coexist fine)
- GPU memory (only one large model loaded at a time)
- CUDA/driver stack

Only one build is "active" at a time (has its model loaded and UI running). Switching builds: teardown active, setup new. Health checks run on active only.

## ptr a001000c — Port allocation

`_allocate_port()` finds an unused port in the 7750-7769 pool by checking existing build manifests.

## ptr a001000d — Build creation and duplicate detection

`create_build()` creates a new build directory with install.sh, teardown.sh, and manifest.json. The install script is hashed (excluding the timestamp line) for duplicate detection. If a build with the same hash already exists, it's flagged as a duplicate.

## ptr a001000e — Health check recording

`record_health_check()` appends a health check result to a build's manifest (append-only). Detects degradation pattern: if previous check passed but current one failed, marks build as "degraded" and broadcasts an alert.

## ptr a001000f — Build activation

`activate_build()` makes a build the active one. Only one build can be active (using the GPU/ports). Deactivates any currently active build first. `deactivate_build()` reverses this.

## ptr a0010010 — Step execution

`_results` — dict of step_id to last result. `_running` — set of currently running step IDs. `_attempt_history` — dict of step_id to list of failed attempt records. `_step_overrides` — dict of step_id to Claude-suggested replacement commands. `_pending_overrides` — commands awaiting human approval.

`MAX_SAME_ERROR = 2` — triggers loop detection after 2 identical errors. `MAX_ATTEMPTS = 5` — hard cap on retries.

## ptr a0010011 — Error fingerprinting

`error_fingerprint(stderr)` normalizes error text for comparison: lowercases, replaces numbers with N, replaces paths, extracts the last line containing error keywords. Used to detect repeated identical failures.

## ptr a0010012 — Loop detection

`detect_loop(step_id)` checks attempt history for loop patterns:
- Max attempts reached (5)
- Same error fingerprint repeated 2+ times
- Same command repeated 2+ times

Returns `{"looping": True/False, "reason": ..., "attempts": N}`.

## ptr a0010013 — Command runner

`run_command(step_id, command, timeout)` runs a shell command with streaming output. Flow:

1. Security scan — blocked commands are rejected immediately
2. Environment setup — injects Ollama PATH from breadcrumb, adds common install locations
3. Spawns subprocess with streaming stdout/stderr via selectors
4. Broadcasts `step_output` events throttled to ~4/sec (0.25s interval)
5. Sends heartbeat events if no output for 1+ second
6. On completion, saves timing data and records attempt history for failures
7. Triggers loop detection on failure

Output is capped: stdout last 8000 chars, stderr last 4000 chars.

## ptr a0010014 — Service URL and registration mappings

`_STEP_URLS` maps step IDs to their web URLs (used by frontend for auto-open). `_STEP_SVC` maps step IDs to service registry entries (name + port).

## ptr a0010015 — Service registration

`_register_svc(name, port)` calls the `bin/svc` CLI to register a service in services.json. Best-effort, ignores failures.

## ptr a0010016 — Browser opener (server-side, legacy)

`_open_browser(url)` opens a URL in the default browser. Tries xdg-open, firefox, then macOS open. Deduplicates per session. Note: browser auto-open is now handled by the frontend via SSE step_verified events; this function remains but is no longer called for service steps.

## ptr a0010017 — Step verification

`verify_step(step_id, verify_cmd, expect)` runs the verification command and checks for expected output. Updates `_results` with verified status. Broadcasts `step_verified` event. On pass, registers service in svc registry if applicable.

## ptr a0010018 — Build steps definition

`build_steps()` returns the ordered list of setup steps. Each step has: id, name, description, command, verify command, expected output, category, and optional teardown command.

Categories: `preflight` (detect_arch, detect_gpu, check_memory, check_docker, check_ollama, upgrade_ollama), `model` (pull_model, test_generate), `ui` (start_openwebui, verify_e2e, start_chat).

Notable step details:
- **check_ollama**: Searches multiple locations, installs if not found, writes breadcrumb to /tmp/.ollama_path, starts service if needed
- **upgrade_ollama**: Version comparison using `sort -V`, upgrades via official installer, restarts service
- **pull_model**: Checks memory before pulling, warns if <30GB free
- **start_openwebui**: Docker container with host networking, waits up to 3 min for health endpoint
- **start_chat**: Kills any existing instance, launches chat.py in background

## ptr a0010019 — Claude helper

System prompt configures Claude as a DGX Spark setup expert (ARM64, Ubuntu 24.04, CUDA 13.0, sm_121 Blackwell, 128GB RAM). Key instruction: never suggest commands identical to previous failed attempts.

`claude_ask()` sends step failure info to Claude. Uses Sonnet for routine fixes, Opus for loop escalation (needs creative thinking). Includes attempt history and loop info.

If Claude's response contains `NEW_COMMAND:`, the command is security-scanned:
- Safe commands are auto-applied as overrides
- Blocked commands are put in `_pending_overrides` for human approval

All Claude responses are persisted to `data/research/`.

## ptr a001001a — Health check loop

Background thread that runs every 6-12 hours (randomized). Picks a random healthy/new build and runs the e2e verification steps. Records results in the build manifest. Detects degradation (was passing, now failing).

## ptr a001001b — Flask application and routes

Flask app serves:
- `GET /` — Main web UI (index.html template)
- `GET /api/steps` — Current step states with results, overrides, loop info
- `POST /api/run/<step_id>` — Start running a step (threaded)
- `POST /api/verify/<step_id>` — Run verification for a step
- `POST /api/ask-claude/<step_id>` — Get Claude's advice for a failed step
- `POST /api/approve/<step_id>` — Approve a blocked Claude suggestion
- `POST /api/reject/<step_id>` — Reject a blocked Claude suggestion
- `POST /api/reset/<step_id>` — Reset a single step to initial state
- `POST /api/reset-all` — Reset all steps to startup state
- `POST /api/autorun` — Auto-run all steps sequentially (Go button)
- `POST /api/autorun/stop` — Stop autorun after current step
- `POST /api/export` — Export verified steps as build (install.sh + teardown.sh)
- `GET /api/builds` — List all builds
- `GET /api/builds/active` — Get the active build
- `POST /api/builds/<id>/activate` — Make a build active
- `POST /api/builds/<id>/deactivate` — Deactivate a build
- `GET /api/builds/<id>` — Build detail
- `GET /api/builds/<id>/<install|teardown>` — Download build scripts
- `GET /api/events` — SSE stream (queue per client, 25s ping, 500 event buffer)
- `GET /api/logs` — Return last 1000 events from up to 5 most recent session logs
- `GET /api/integrity` — SHA256 hashes of all tool files

## ptr a001001c — Autorun worker

`_autorun_worker()` walks through every step sequentially: run, wait, verify. On failure, asks Claude once. If Claude provides an override, retries once. Stops on first verification failure. Checks `_autorun_active` flag between each operation for early stop.

## ptr a001001d — Build export

`api_export()` generates install.sh and teardown.sh from verified steps. Teardown runs in reverse order. Supports `--keep-models`, `--keep-images`, `--dry-run` flags.

## ptr a001001e — SSE stream

`api_events()` creates a Queue per client, appends to `_clients`, yields events as `data: {JSON}\n\n`. Sends ping every 25 seconds if idle. Client queues are capped at 500 events.

## ptr a001001f — Main entry point

`main()` does:
1. Parse --port argument (default 7711)
2. Redirect sys.stdout/stderr to the event system via UIWriter (so print() goes to web UI)
3. Start health check background thread
4. Create werkzeug server bound to 127.0.0.1 (localhost only)
5. Serve forever
