#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export BSP_PORT="${BSP_PORT:-8766}"
if [[ $# -gt 0 ]]; then
  if [[ $# -eq 2 && "$1" == "--port" && "$2" =~ ^[0-9]+$ ]]; then
    export BSP_PORT="$2"
  else
    echo 'Usage: bash run.sh [--port PORT]' >&2
    exit 2
  fi
fi
exec bash scripts/start.sh
