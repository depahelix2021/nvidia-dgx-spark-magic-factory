#!/usr/bin/env bash
# kill-ports.sh — Free up specific ports by killing whatever is listening on them.
#
# Handles both Docker containers and host processes. Edit the PORTS array to
# target different ports. Originally written to clear ports 8080 and 5111
# during early development before the project settled on its final port range.

set -euo pipefail

PORTS=(8080 5111)

for port in "${PORTS[@]}"; do
  echo "=== Port $port ==="

  # 1) Kill Docker containers bound to this port
  container_ids=$(docker ps --format '{{.ID}} {{.Ports}}' 2>/dev/null \
    | grep ":${port}->" | awk '{print $1}') || true
  if [ -n "$container_ids" ]; then
    for cid in $container_ids; do
      echo "Stopping Docker container $cid (port $port)"
      docker stop "$cid" && docker rm -f "$cid" 2>/dev/null || true
    done
  fi

  # 2) Kill any remaining host processes on this port
  pids=$(lsof -ti :"$port" 2>/dev/null) || true
  if [ -n "$pids" ]; then
    for pid in $pids; do
      name=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
      echo "Killing PID $pid ($name) on port $port"
      kill -9 "$pid" 2>/dev/null || true
    done
  fi

  # 3) Verify
  remaining=$(lsof -ti :"$port" 2>/dev/null) || true
  if [ -z "$remaining" ]; then
    echo "Port $port is now free."
  else
    echo "WARNING: Port $port still in use by PID(s): $remaining"
  fi

  echo
done

echo "Done."
