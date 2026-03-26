#!/bin/bash
# cleanup.sh — Nuclear option: kill ALL Python/Flask processes and remove ALL Docker containers/images.
#
# Use this when things are stuck and you want a completely clean slate.
# WARNING: This kills all Flask processes and removes all Docker containers and images
# on the system, not just Magic Factory ones. Use bin/stop.sh for targeted cleanup.

echo "=== Killing Python/Flask processes ==="
pids=$(ps aux | grep -i '[p]ython.*flask\|[p]ython.*app\.py\|[f]lask run' | awk '{print $2}')
if [ -n "$pids" ]; then
    echo "Found Flask processes: $pids"
    kill $pids 2>/dev/null
    sleep 1
    # Force kill any remaining
    for pid in $pids; do
        if kill -0 "$pid" 2>/dev/null; then
            echo "Force killing PID $pid"
            kill -9 "$pid"
        fi
    done
    echo "Flask processes killed."
else
    echo "No Flask processes found."
fi

echo ""
echo "=== Stopping and removing Docker containers ==="
containers=$(docker ps -aq 2>/dev/null)
if [ -n "$containers" ]; then
    echo "Stopping containers..."
    docker stop $containers
    echo "Removing containers..."
    docker rm $containers
    echo "Containers removed."
else
    echo "No Docker containers found."
fi

echo ""
echo "=== Removing Docker images ==="
images=$(docker images -q 2>/dev/null)
if [ -n "$images" ]; then
    echo "Removing images..."
    docker rmi -f $images
    echo "Images removed."
else
    echo "No Docker images found."
fi

echo ""
echo "=== Cleanup complete ==="
