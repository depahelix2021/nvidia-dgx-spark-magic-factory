#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "✨ NVIDIA DGX Spark Magic Factory — services"
echo ""

# ptr f0020001
"$DIR/bin/svc" open
