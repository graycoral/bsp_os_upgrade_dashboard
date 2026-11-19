"""Tests for Direct Connector Unit 4: Plugin CLI decoupling, DirectConnectorClient, TC projection, watch detach, analysis & sync."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import zipfile

import pytest
import uvicorn

from backend.gui_test.core.connector_bootstrap import parse_bootstrap
from backend.gui_test.core.models import TestError
from backend.gui_test.core.shared_settings_store import SharedSettingsStore
from backend.gui_test.execution.host import Host, create_app
from backend.gui_test.standalone.direct_connector_client import DirectConnectorClient
from backend.gui_test.standalone.plugin_commands import execute_direct


ROOT = Path(__file__).resolve().parents[1]


def _free_port():
    import socket
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _start_live_host(tmp_path: Path):
    home = tmp_path / 'winhome'
    runtime = home / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    cfg = {
        'python': sys.executable,
        'boards': [{'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}],
        'serial_transport': 'native',
        '_setup': {'server': '127.0.0.1', 'account': 'bsp', 'ssh_port': 22, 'remote_runner_port': 8771},
    }
    cfg_path = home / 'windows-runner.json'
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    host = Host(cfg, runtime, ports=lambda: {'COM3'}, config_path=cfg_path)
    app = create_app(host)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, access_log=False, log_level='warning'))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    import httpx
    for _ in range(50):
        try:
            if httpx.get(f'http://127.0.0.1:{port}/v1/identity', timeout=1.0).status_code == 200:
                break
        except Exception:
            time.sleep(0.05)
    return host, port, server, t


def test_plugin_cli_port_conflict_and_local_connect_export_without_monitor(tmp_path):
    plugin_py = ROOT / 'apps' / 'agent-monitor' / 'plugin.py'
    rt = tmp_path / 'rt'
    home = tmp_path / 'home'
    res_conflict = subprocess.run(
        [sys.executable, str(plugin_py), '--home', str(home), '--runtime', str(rt), '--port', '8771', '--connector-port', '8771', 'status'],
        capture_output=True,
        text=True,
    )
    assert res_conflict.returncode != 0
    assert 'PORT_CONFLICT' in res_conflict.stderr

    out_zip = tmp_path / 'win-connector.zip'
    res_export = subprocess.run(
        [
            sys.executable, str(plugin_py), '--home', str(home), '--runtime', str(rt),
            'connect', 'export', '--server', 'linux.test', '--account', 'bsp',
            '--ssh-port', '2222', '--remote-runner-port', '8771', '--output', str(out_zip),
        ],
        capture_output=True,
        text=True,
    )
    assert res_export.returncode == 0, res_export.stderr
    assert out_zip.is_file()
    with zipfile.ZipFile(out_zip) as zf:
        prof = json.loads(zf.read('connector-connection.json'))
        parsed = parse_bootstrap(prof)
        assert parsed.format == 'gui-test-connector-bootstrap-v2'
        assert parsed.endpoint.server == 'linux.test'
        assert parsed.endpoint.remote_runner_port == 8771
        assert parsed.endpoint.remote_dashboard_port is None


def test_plugin_direct_connect_tc_projection_run_watch_detach_and_analysis(tmp_path):
    host, port, server, thread = _start_live_host(tmp_path)
    try:
        rt = tmp_path / 'linux_rt'
        home = tmp_path / 'linux_home'
        tc_root = tmp_path / 'tcs'
        tc_root.mkdir()
        fail_flag = tmp_path / 'fail.flag'
        fail_flag.write_text('PASS', encoding='utf-8')
        (tc_root / 't1.py').write_text(
            f"import time; time.sleep(0.15); txt=open({repr(str(fail_flag))}).read().strip(); print('LOG_LINE_1'); print('Test Result: ' + txt); exit(0 if txt=='PASS' else 1)\n",
            encoding='utf-8',
        )

        store = SharedSettingsStore(rt)
        s0 = store.read()
        store.save({
            'expected_revision': s0['revision'],
            'integration': s0['integration'] | {'tc_root': str(tc_root), 'source_roots': [str(tmp_path)]},
            'timeouts': {k: v for k, v in s0['timeouts'].items() if k != 'revision'},
        })
        store.save_command_profile('default', {'single': ['python', '{tc_path}', '--com', '{com_a}'], 'dual': ['python', '{tc_path}', '--a', '{com_a}', '--b', '{com_b}']})

        plugin_py = ROOT / 'apps' / 'agent-monitor' / 'plugin.py'
        # 1. Verify plugin.py CLI connects directly without Agent Monitor!
        cli_connect = subprocess.run(
            [sys.executable, str(plugin_py), '--home', str(home), '--runtime', str(rt), '--connector-port', str(port), 'connect'],
            capture_output=True,
            text=True,
        )
        assert cli_connect.returncode == 0, cli_connect.stderr
        conn_out = json.loads(cli_connect.stdout)
        assert conn_out['linux_diagnostics']['reachable'] is True
        assert conn_out['runner_id'] == host.identity
        # Agent Monitor port 8766 was NEVER started.
        assert not (home / 'service.json').exists()

        # 2. Verify test list pushed TC catalog projection to Windows Host!
        dc = DirectConnectorClient(home=home, runtime_dir=rt, connector_port=port)
        try:
            ts_data = dc.test_status()
            assert ts_data['has_projection'] is True
            assert [i['tc_id'] for i in ts_data['items']] == ['t1.py']

            # 3. DirectConnectorClient run + KeyboardInterrupt detach does NOT cancel run!
            run = dc.start_run()
            run_id = run['run_id']

            calls = [0]
            def fake_sleep(dt):
                calls[0] += 1
                if calls[0] >= 1:
                    raise KeyboardInterrupt()

            dc.sleep = fake_sleep
            detached = dc.watch_run(run_id)
            assert detached['detached'] is True and detached['cancelled'] is False
            dc.sleep = time.sleep
            final = dc.watch_run(run_id, timeout_s=5.0)
            assert final['state'] == 'COMPLETED' and final['outcome'] == 'PASSED'

            # 4. Trigger failure -> claim -> verify -> RETRY -> pass!
            fail_flag.write_text('FAIL', encoding='utf-8')
            run2 = dc.start_run()
            failed_state = dc.watch_run(run2['run_id'], timeout_s=5.0)
            assert failed_state['state'] == 'PAUSED' and failed_state['analysis_latched'] is True

            fail_flag.write_text('PASS', encoding='utf-8')
            dec = dc.analyze_once(
                run_id=run2['run_id'],
                analyzer=lambda item: {'verdict': 'RETRY', 'cause_key': 'transient:uart', 'summary': 'retry once'},
                verifier=lambda item, res: 'PASSED',
            )
            assert dec['analysis']['status'] == 'RETRY_READY'
            passed_after_retry = dc.watch_run(run2['run_id'], timeout_s=5.0)
            assert passed_after_retry['state'] == 'COMPLETED' and passed_after_retry['outcome'] == 'PASSED'

            # 5. Offline two-way settings sync (Windows edit -> Linux auto pull + dual conflict)
            win_edit = dc._request(
                'PUT',
                '/v1/control/settings',
                json_body={
                    'source': 'windows',
                    'patch': {'timeouts': {'default_seconds': 480, 'overrides': {}}},
                },
            )
            assert win_edit['sync_state']['dirty_on_windows'] is True
            diag_sync = dc.diagnose()
            assert diag_sync['settings_sync']['status'] == 'PULLED_FROM_WINDOWS'
            assert store.read_timeouts()['default_seconds'] == 480

            # Now Windows edits AND Linux edits -> conflict surfaced!
            dc._request(
                'PUT',
                '/v1/control/settings',
                json_body={'source': 'windows', 'patch': {'timeouts': {'default_seconds': 500, 'overrides': {}}}},
            )
            cur_t = store.read_timeouts()
            store.save_timeouts({'expected_revision': cur_t['revision'], 'default_seconds': 510, 'overrides': {}})
            with pytest.raises(TestError) as exc_info:
                dc.require_connected()
            assert exc_info.value.code == 'SETTINGS_SYNC_CONFLICT'
        finally:
            dc.close()
    finally:
        server.should_exit = True
        thread.join(timeout=3.0)
        host.close()


def test_runner_mismatch_triggers_peer_hello_mismatch_and_blocks(tmp_path):
    host, port, server, thread = _start_live_host(tmp_path)
    try:
        rt = tmp_path / 'rt'
        store = SharedSettingsStore(rt)
        store.rebind_runner('f' * 32)
        store.save_preferences({'preferred_connector_port': port})
        dc = DirectConnectorClient(runtime_dir=rt, connector_port=port)
        try:
            with pytest.raises(TestError) as exc:
                dc.require_connected()
            assert exc.value.code == 'RUNNER_CHANGED'
            diag = dc._request('GET', '/v1/diagnostics/connection')
            assert any(w['client_status'] == 'MISMATCH' for w in diag['peer_warnings'])
        finally:
            dc.close()
    finally:
        server.should_exit = True
        thread.join(timeout=3.0)
        host.close()


def test_direct_export_includes_pinned_runner_settings_export_and_offline_web_actions(tmp_path):
    from types import SimpleNamespace
    import zipfile
    from fastapi.testclient import TestClient
    from backend.gui_test.connector.supervisor import create_manager_app
    from backend.gui_test.standalone.plugin_commands import execute_direct
    from backend.gui_test.connector.web_actions import ManagerActions

    host, port, server, thread = _start_live_host(tmp_path)
    try:
        rt = tmp_path / 'rt'
        store = SharedSettingsStore(rt)
        store.rebind_runner(host.identity)
        dc = DirectConnectorClient(runtime_dir=rt, connector_port=port)
        try:
            out_zip = tmp_path / 'bundle.zip'
            emitted = []
            assert execute_direct(
                dc,
                ['connect', 'export', '--server', 'linux-build.internal', '--account', 'bsp', '--output', str(out_zip)],
                source_root=Path(__file__).resolve().parents[1],
                emit=emitted.append,
            ) == 0
            with zipfile.ZipFile(out_zip) as zf:
                prof = json.loads(zf.read('connector-connection.json'))
            assert prof['format'] == 'gui-test-connector-bootstrap-v2'
            assert prof['expected_runner_id'] == host.identity

            exp_file = tmp_path / 'exported-settings.json'
            assert execute_direct(dc, ['settings', 'export', '--file', str(exp_file)], emit=emitted.append) == 0
            assert json.loads(exp_file.read_text(encoding='utf-8'))['format'] == 'gui-test-shared-settings-v1'
        finally:
            dc.close()

        # Windows Web UI ManagerActions & Manager HTTP routes (/shared-settings, /storage-policy) offline fallback edit Host directly.
        fake_mgr = SimpleNamespace(home=tmp_path / 'win_home', runtime=tmp_path / 'win_home' / 'runtime', host_url=f'http://127.0.0.1:{port}')
        actions = ManagerActions(fake_mgr)
        shared0 = actions.shared()
        assert shared0['offline_direct'] is True
        saved_t = actions.shared({'expected_revision': shared0['revision'], 'timeouts': {'default_seconds': 333, 'overrides': {}}})
        assert saved_t['timeouts']['default_seconds'] == 333
        assert saved_t['sync_state']['dirty_on_windows'] is True

        st0 = actions.storage()
        saved_s = actions.storage({'expected_revision': st0['revision'], 'enabled': True, 'max_age_seconds': 7200, 'max_bytes': 1024 * 1024 * 1024})
        assert saved_s['max_age_seconds'] == 7200
        assert saved_s['sync_state']['dirty_on_windows'] is True

        # Verify create_manager_app HTTP endpoints (used by Qt Client) also use ManagerActions fallback when Agent Monitor is offline.
        mgr_token = 'm' * 48
        mgr_app = create_manager_app(fake_mgr, mgr_token)
        with TestClient(mgr_app, base_url='http://127.0.0.1:8773', client=('127.0.0.1', 5000)) as mclient:
            auth_hdr = {'Authorization': 'Bearer ' + mgr_token}
            r_sh = mclient.get('/shared-settings', headers=auth_hdr)
            assert r_sh.status_code == 200 and r_sh.json()['offline_direct'] is True
            r_sh_save = mclient.post(
                '/shared-settings',
                headers=auth_hdr,
                json={'expected_revision': r_sh.json()['revision'], 'timeouts': {'default_seconds': 444, 'overrides': {}}},
            )
            assert r_sh_save.status_code == 200 and r_sh_save.json()['timeouts']['default_seconds'] == 444
            r_sp = mclient.get('/storage-policy', headers=auth_hdr)
            assert r_sp.status_code == 200 and r_sp.json()['max_age_seconds'] == 7200
    finally:
        server.should_exit = True
        thread.join(timeout=3.0)
        host.close()
