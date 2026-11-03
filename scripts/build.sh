#!/usr/bin/env bash
set -euo pipefail
usage() { echo 'Usage: bash scripts/build.sh [all|dashboard|gui-test] [--skip-install]'; }
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
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if ! "$skip_install"; then npm ci --prefix apps/web; fi
if [[ "$target" != gui-test ]]; then
  npm run build --prefix apps/web
  echo 'Dashboard UI: apps/web/dist'
fi
if [[ "$target" != dashboard ]]; then
  npm run build:gui-test --prefix apps/web
  echo 'Standalone GUI Test UI: gui_test/static'
fi
