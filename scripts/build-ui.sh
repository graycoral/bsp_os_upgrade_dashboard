#!/usr/bin/env bash
set -Eeuo pipefail
usage() { echo 'Usage: bash scripts/build-ui.sh [all|dashboard|gui-test] [--skip-install]'; }
target=all
skip_install=false
if [[ $# -gt 0 && "$1" != --* ]]; then target="$1"; shift; fi
case "$target" in all|dashboard|gui-test) ;; *) usage >&2; exit 2 ;; esac
for arg in "$@"; do
  case "$arg" in
    --skip-install) skip_install=true ;;
    --help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
stage='checking build tools'
trap 'status=$?; printf "[build-ui] Failed while %s (exit %s).\n" "$stage" "$status" >&2; exit "$status"' ERR
printf '[build-ui] Starting %s UI build.\n' "$target"
for tool in node npm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf '[build-ui] Missing %s. Install Node.js 22.12+ and npm, then retry.\n' "$tool" >&2
    exit 1
  fi
  printf '[build-ui] %s version\n' "$tool"
  "$tool" --version
done
cd "$(dirname "${BASH_SOURCE[0]}")/.."
case "$target" in
  dashboard) apps=(apps/web) ;;
  gui-test) apps=(apps/gui-test) ;;
  all) apps=(apps/web apps/gui-test) ;;
esac
for app in "${apps[@]}"; do
  if ! "$skip_install"; then
    stage="installing dependencies for $app"
    printf '[build-ui] Installing dependencies for %s. Registry/proxy requests may take time.\n' "$app"
    npm ci --prefix "$app" --loglevel=info --foreground-scripts
  else
    printf '[build-ui] Reusing installed dependencies for %s.\n' "$app"
  fi
  stage="building $app"
  printf '[build-ui] Building %s.\n' "$app"
  npm run build --prefix "$app"
  printf '[build-ui] Finished %s.\n' "$app"
done
if [[ "$target" != gui-test ]]; then echo 'Dashboard UI: apps/web/dist'; fi
if [[ "$target" != dashboard ]]; then echo 'Standalone GUI Test UI: apps/gui-test/static'; fi
