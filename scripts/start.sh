#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  echo 'Create the environment: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.lock'
  exit 1
fi
if [[ ! -f apps/web/dist/index.html ]]; then
  echo 'Build the UI: npm ci --prefix apps/web && npm run build --prefix apps/web'
  exit 1
fi
# Separate worker lifetime: for persistent Linux jobs run this worker under your service manager.
.venv/bin/python -m backend.worker.main --runtime .runtime &
worker_pid=$!
trap 'kill -INT "$worker_pid" 2>/dev/null || true' EXIT
.venv/bin/python scripts/serve.py --runtime .runtime --port "${BSP_PORT:-8765}"
