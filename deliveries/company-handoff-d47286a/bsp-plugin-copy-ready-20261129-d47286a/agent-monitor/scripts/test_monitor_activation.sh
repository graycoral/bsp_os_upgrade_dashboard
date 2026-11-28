#!/usr/bin/env bash
# T-323 local regression, copied package smoke and mock Chromium checks.
set -euo pipefail

root=$(cd -- "$(dirname -- "$0")/.." && pwd)

usage() {
    printf '%s\n' 'Usage: bash scripts/test_monitor_activation.sh [python|package|browser|browser-monitor ...]' \
        'Default: Python, fresh package, and full browser. Set BSP_TEST_PYTHON to override .venv/bin/python.' \
        'Package requires both prebuilt UIs. Browser requires installed Node, Playwright, and Chromium.' \
        'Use browser-monitor to run only the T-323 browser scenario.' \
        'Use package --package DIRECTORY to test an already exported full package.'
}

provided_package=''
if [[ ${1:-} == package && ${2:-} == --package ]]; then
    if [[ $# -ne 3 || -z $3 ]]; then
        usage >&2
        exit 2
    fi
    provided_package=$3
    if [[ $provided_package != /* ]]; then
        provided_package="$PWD/$provided_package"
    fi
    set -- package
fi
cd "$root"

if [[ $# -eq 0 ]]; then
    set -- python package browser
fi
selected=' '
for stage in "$@"; do
    case "$stage" in
        python|package|browser|browser-monitor) ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
    if [[ $selected == *" $stage "* ]]; then
        printf 'Stage specified twice: %s\n' "$stage" >&2
        exit 2
    fi
    selected+="$stage "
done

python=${BSP_TEST_PYTHON:-"$root/.venv/bin/python"}
if ! command -v "$python" >/dev/null; then
    printf 'Test interpreter unavailable: %s\n' "$python" >&2
    exit 2
fi
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}

mkdir -p .local-reports
reports=$(mktemp -d ".local-reports/$(date +%Y%m%d)-monitor-activation.XXXXXX")
printf 'T-323 logs: %s\n' "$reports"
result=0

run_stage() {
    local name=$1 status=0
    shift
    "$@" >"$reports/$name.log" 2>&1 || status=$?
    printf '%s exit %s · %s/%s.log\n' "$name" "$status" "$reports" "$name"
    if [[ $result -eq 0 ]]; then
        result=$status
    fi
}

run_browser() {
    if ! command -v node >/dev/null || ! command -v npx >/dev/null ||
            [[ ! -x apps/web/node_modules/.bin/playwright ]]; then
        printf '%s\n' 'Browser stage requires Node, npx, and local Playwright.' >&2
        return 2
    fi
    npm_config_offline=true npm_config_yes=false "$python" scripts/test_connector_browser.py "$@"
}

for stage in "$@"; do
    case "$stage" in
        python)
            run_stage python-monitor "$python" -m pytest -q -rs \
                tests/test_monitor_activation.py tests/test_agent_monitor_manager.py \
                tests/test_agent_monitor_lifecycle.py tests/test_plugin_delivery.py \
                tests/test_direct_connector_unit4.py
            run_stage python-connector "$python" -m pytest -q -rs \
                tests/test_connector_monitor_link.py tests/test_ssh_bind_probe.py \
                tests/test_direct_connector_unit2.py backend/gui_test/tests/test_connector_web.py \
                backend/gui_test/tests/test_connector_server_port.py
            ;;
        package)
            if [[ -n $provided_package ]]; then
                run_stage package "$python" -IB scripts/test_monitor_activation_package.py "$reports" --package "$provided_package"
            else
                run_stage package "$python" -IB scripts/test_monitor_activation_package.py "$reports"
            fi
            ;;
        browser)
            run_stage browser run_browser
            ;;
        browser-monitor)
            run_stage browser-monitor run_browser --grep 'Agent Monitor action follows'
            ;;
    esac
done
exit "$result"
