#!/bin/sh
# Register as a foreground child of the company plugin supervisor. All arguments
# are global plugin.py options. Stop only the child handle returned at startup.
set -eu
source_root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd -P)
entry="$source_root/apps/agent-monitor/plugin.py"
if [ -f "$source_root/../PLUGIN_PACKAGE.json" ]; then
    entry="$source_root/../plugin.py"
fi
exec "${BSP_PLUGIN_PYTHON:-python3}" -B "$entry" "$@" connect --watch --json
