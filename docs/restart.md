# restart.sh — Documentation

## ptr f0010001 — Overview

Restart script with strict mode. Calls stop.sh (tolerates failure if nothing is running), then exec's into start.sh. The exec replaces the shell process so there's no lingering parent. Works whether the app is currently running or not.
