#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ $# -eq 0 && -n "${BSP_PORT:-}" ]]; then
  set -- --port "$BSP_PORT"
fi
select_python() {
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys;raise SystemExit(not ((3,11)<=sys.version_info[:2]<(3,14)))' >/dev/null 2>&1; then
      monitor_python="$candidate"
      return 0
    fi
  done
  return 1
}
if ! select_python; then
  bash "$root/scripts/bootstrap-prerequisites.sh"
  select_python || { echo 'Supported Python remains unavailable.' >&2; exit 1; }
fi
exec "$monitor_python" "$root/apps/agent-monitor/manage.py" start --runtime "${BSP_RUNTIME:-$root/.runtime}" "$@"
