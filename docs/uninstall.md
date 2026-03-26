# uninstall.sh — Documentation

## ptr g0010001 — Header and confirmation

Bash script with `set -uo pipefail` (no -e). Uses ANSI color codes for terminal output. Shows what will be removed and requires the user to type "YES" to proceed. States that Docker and NVIDIA drivers will NOT be removed.

## ptr g0010002 — Phase 1: Stop all running processes

Runs stop.sh first for graceful shutdown. Then belt-and-suspenders: kills anything on ports 7711, 7722, 7733, and 7750-7769 (build pool) via lsof. Also pgrep's for any lingering app.py or chat.py processes from this project directory.

## ptr g0010003 — Phase 2: Remove Open WebUI

If Docker is available:
- Removes containers: `open-webui`, `openwebui`, and any build-specific containers matching `openwebui-*` or `open-webui-*` patterns
- Removes Docker volume `open-webui`
- Removes all Docker images containing `open-webui`
- Prunes dangling Docker images left by pulls

## ptr g0010004 — Phase 3: Remove Ollama

Finds Ollama binary (checks /tmp/.ollama_path breadcrumb first, then PATH). Deletes all models while service is still running. Stops and disables the systemd service. Kills any remaining ollama processes. Removes the binary from all known locations (/usr/local/bin, /usr/bin, /snap/bin, ~/.local/bin, ~/bin, /opt/ollama/bin). Removes systemd service files and reloads daemon. Removes ~/.ollama (all model data) and /usr/share/ollama (system-level installs). Removes the `ollama` system user and group if they exist. Cleans up breadcrumb files.

## ptr g0010005 — Phase 4: Clean up local files

Removes: Python venv (`.venv/`), data directory (`data/` — logs, builds, research), PID files, `__pycache__` directories, `.env` file.

## ptr g0010006 — Verification

Checks that everything was actually removed:
- Is `ollama` still on PATH?
- Does `~/.ollama` still exist?
- Are any open-webui containers or images left in Docker?
- Do local data directories still exist?
- Is anything still listening on ports 7711, 7722, 7733?

Prints a summary of what was and wasn't removed. Notes that Docker itself and NVIDIA drivers were not removed, and the script directory itself must be manually deleted.
