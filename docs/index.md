# templates/index.html — Documentation

## ptr h0010001 — Page structure

HTML5 page for the NVIDIA DGX Spark Magic Factory web UI. Uses IBM Plex Mono and Anybody fonts. Links to `/static/style.css`.

Layout:
- **Header** — Brand logo, navigation tabs (Steps/Builds/Logs), action buttons (Reset All, Export Build)
- **Main** — Three view sections, only one visible at a time
- **Live feed bar** — Fixed at bottom, shows real-time event stream

## ptr h0010002 — Steps view

Contains:
- **Go bar** — Large Go/Stop button for autorun, status text
- **Steps container** — Rendered dynamically by JavaScript

## ptr h0010003 — Builds and Logs views

Builds view: container for build cards (rendered by JS). Logs view: scrollable log content area.

## ptr h0010004 — Navigation

Click handlers on nav buttons toggle `.active` class between views. Builds and Logs views fetch data on activation.

## ptr h0010005 — Step loading and rendering

`loadSteps()` fetches from `/api/steps`, stores in `steps` array, calls `renderSteps()`.

`renderSteps()` groups steps by category (preflight/model/ui). Each step card shows:
- Step indicator (number, checkmark, X, or spinner)
- Name, description, attempt count, override indicator
- Action buttons: Run, Verify, Reset
- Command code block
- Progress bar (if running)
- Result display (if completed)
- Pending override approval UI (if blocked)
- Claude help buttons (if failed)
- Loop warning (if detected)

## ptr h0010006 — Step results

`renderResult(r)` shows: status label (VERIFIED/VERIFY FAILED/error/done), duration, exit code, stdout (last 3000 chars), stderr (last 2000 chars).

## ptr h0010007 — Pending override UI

`renderPending(stepId, p)` shows blocked Claude suggestions with security warnings and approve/reject buttons. Only shown for BLOCKED warnings.

## ptr h0010008 — Action handlers

- `runStep(id)` — POST /api/run/:id
- `verifyStep(id)` — POST /api/verify/:id
- `resetStep(id)` — POST /api/reset/:id
- `approveOverride(id)` — POST /api/approve/:id
- `rejectOverride(id)` — POST /api/reject/:id
- `askClaude(id)` — POST /api/ask-claude/:id, shows response in claude-advice div

## ptr h0010009 — Autorun (Go button)

`startAutorun()` POSTs to /api/autorun, updates button to Stop state. `stopAutorun()` POSTs to /api/autorun/stop. Button toggles between green Go and red Stop.

## ptr h001000a — Reset All

Clears all steps via POST /api/reset-all. Resets autorun state and Go button.

## ptr h001000b — Export

POSTs to /api/export. Shows build ID in feed. Reloads builds view.

## ptr h001000c — Builds view

`loadBuilds()` fetches from /api/builds. Each build card shows: ID, status (active/healthy/degraded/new), approach, timestamp, port, Docker container name, isolation details, health check history (dot indicators), actions (activate/deactivate, download install.sh/teardown.sh).

`activateBuild(id)` / `deactivateBuild(id)` — POST to activate/deactivate endpoints.

## ptr h001000d — Logs view

`loadLogs()` fetches from /api/logs. Renders each event with timestamp, session ID (last 6 chars), event type (color-coded), and data JSON.

## ptr h001000e — Progress bar

`updateProgressBar(stepId, data)` updates the progress bar for a running step:
- Elapsed time display (Xm Ys / ~Nm Ns left)
- Percentage fill based on estimated duration (capped at 95%)
- Indeterminate animation if no estimate
- Last output line display (red for stderr)

State is kept in `_stepProgress` dict and restored after re-renders.

## ptr h001000f — Auto-open services

`_SERVICE_URLS` maps step IDs to service URLs (start_openwebui to port 7733, start_chat to port 7722). `_openedServices` set prevents duplicate opens per page session. `autoOpenService(stepId)` calls `window.open(url, '_blank')` when a service step passes verification.

## ptr h0010010 — SSE connection

`connectSSE()` creates an EventSource to `/api/events`. Handles events:
- `ping` — ignored (keepalive)
- `step_output` — updates progress bar, skips feed
- `step_done` / `step_reset` — clears progress state
- `autorun_*` — updates Go button status text
- `step_verified` with passed=true — triggers autoOpenService
- State-changing events — triggers loadSteps() or loadBuilds()

Reconnects with 3-second delay on error. On open, loads initial steps.

## ptr h0010011 — Live feed

`addFeed(type, msg)` appends an event to the bottom feed bar. Color-coded by type (green for ok, red for errors, amber for warnings, blue for builds). Keeps max 200 items.

## ptr h0010012 — Utilities and initialization

`esc(s)` — HTML escapes a string via DOM textContent/innerHTML trick.

On load: calls `loadSteps()`, `connectSSE()`, adds "UI connected" feed entry.
