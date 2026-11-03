#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -X utf8 scripts/setup_runtime.py "$@"
