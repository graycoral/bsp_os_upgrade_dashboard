#!/usr/bin/env bash
# T-324. Only disposable profiles, mock boards and loopback services are used.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
python=${BSP_TEST_PYTHON:-"$root/.venv/bin/python"}
mkdir -p .local-reports
report=$(mktemp -d ".local-reports/$(date +%Y%m%d)-multi-plugin.XXXXXX")
export QT_QPA_PLATFORM=${QT_QPA_PLATFORM:-offscreen}
run() {
    local stage=$1 rc=0
    shift
    "$@" >"$report/$stage.log" 2>&1 || rc=$?
    printf '%s exit %s · %s/%s.log\n' "$stage" "$rc" "$report" "$stage"
    if [[ $rc != 0 ]]; then exit "$rc"; fi
}
case "${1:-all}" in
    feature|regression|package|browser|all) stage=${1:-all} ;;
    *) echo 'Usage: test_multi_plugin_ownership.sh [all|feature|regression|browser|package [copied-package]]' >&2; exit 2 ;;
esac
if [[ "$stage" == feature || "$stage" == all ]]; then
    run ownership "$python" -m pytest -q tests/test_multi_plugin*.py
fi
if [[ "$stage" == regression || "$stage" == all ]]; then
    run compatibility "$python" -m pytest -q tests/test_connector_run_replay.py tests/test_connector_observation.py \
        tests/test_company_connector_delivery.py tests/test_monitor_activation.py tests/test_connector_monitor_link.py \
        tests/test_plugin_delivery.py tests/test_agent_monitor_delivery.py tests/test_direct_connector_unit*.py
fi
if [[ "$stage" == browser || "$stage" == all ]]; then
    run browser "$python" scripts/test_connector_browser.py
fi
if [[ "$stage" == package || "$stage" == all ]]; then
    args=(package)
    if [[ -n "${2:-}" ]]; then args+=(--package "$2"); fi
    run package bash scripts/test_monitor_activation.sh "${args[@]}"
    if [[ -n "${2:-}" ]]; then
        supplied=$(cd -- "$2" && pwd)
        run pristine "$python" -IB "$supplied/plugin.py" verify "$supplied" --pristine
        # Run the delivered source and tests in a disposable copy.
        fixture=$(mktemp -d "${TMPDIR:-/tmp}/bsp-multi-plugin.XXXXXX")
        trap 'rm -rf -- "$fixture"' EXIT
        cp -R "$supplied" "$fixture/plugin"
        (
            cd "$fixture/plugin/agent-monitor"
            log="$root/$report/delivered-ownership.log"
            rc=0
            PYTHONDONTWRITEBYTECODE=1 "$python" -m pytest -q -p no:cacheprovider tests/test_multi_plugin*.py >"$log" 2>&1 || rc=$?
            printf 'delivered-ownership exit %s · %s\n' "$rc" "$log"
            exit "$rc"
        )
    fi
fi
