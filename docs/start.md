# start.sh — Documentation

## ptr d0010001 — Header

Bash script with strict mode (set -euo pipefail). Resolves its own directory for all relative paths.

## ptr d0010002 — Startup banner

Prints version and informs user that all output goes to the web UI after startup. Terminal will be quiet.

## ptr d0010003 — Python discovery

Searches for Python 3.10+ by trying python3.12, python3.11, python3.10, python3 in order. Validates the version by running a Python one-liner. Exits with error if no suitable Python found.

## ptr d0010004 — Virtual environment

Creates a venv in `.venv/` if it doesn't exist. Activates it, upgrades pip, installs requirements.txt (all quietly).

## ptr d0010005 — Environment file

Loads `.env` if present. Falls back to `../env/.env` (copies it locally if found). Uses `set -a` to export all variables.

## ptr d0010006 — Permission fix

If any files in `data/` are owned by a different user (e.g., from a previous sudo run), fixes ownership with `sudo chown -R`. This is why sudo is preferred.

## ptr d0010007 — Duplicate instance check

If `.pid` file exists and the PID is still alive, assumes already running and opens the browser instead via `show.sh`. Cleans up stale PID files.

## ptr d0010008 — Browser auto-open

After a 2-second delay (in background), tries xdg-open, then firefox, then macOS open to launch the harness URL.

## ptr d0010009 — Background launch

Runs `python app.py --port $PORT` in background, redirecting all output to `data/logs/startup.log`. Writes PID to `.pid`. Waits 1 second and checks if the process is still alive. Registers with the svc registry on success, or drops the registration on failure.
