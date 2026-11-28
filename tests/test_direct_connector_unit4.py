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

    out_dir = tmp_path / 'win-connector'
    res_export = subprocess.run(
        [
            sys.executable, str(plugin_py), '--home', str(home), '--runtime', str(rt),
            'connect', 'export', '--server', 'linux.test', '--account', 'bsp',
            '--ssh-port', '2222', '--remote-runner-port', '8771', '--output', str(out_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert res_export.returncode == 0, res_export.stderr
    assert out_dir.is_dir()
    prof = json.loads((out_dir / 'connector-connection.json').read_text(encoding='utf-8'))
    parsed = parse_bootstrap(prof)
    assert parsed.format == 'gui-test-connector-bootstrap-v2'
    assert parsed.endpoint.server == 'linux.test'
    assert parsed.endpoint.remote_runner_port == 8771
    assert parsed.endpoint.remote_dashboard_port is None


def test_plugin_cli_reuses_saved_windows_bootstrap_ssh_profile(tmp_path):
    plugin_py = ROOT / 'apps' / 'agent-monitor' / 'plugin.py'
    home, runtime = tmp_path / 'home', tmp_path / 'runtime'
    shared = SharedSettingsStore(runtime)
    shared.save_preferences({'preferred_connector_port': 8871, 'expected_runner_id': 'a' * 32})
    initial_preferences = shared.read_preferences()

    def plugin(*args, connector_port=None, plugin_runtime=runtime):
        command = [sys.executable, str(plugin_py), '--home', str(home), '--runtime', str(plugin_runtime)]
        if connector_port is not None:
            command += ['--connector-port', str(connector_port)]
        return subprocess.run([*command, *args], capture_output=True, text=True, check=False)

    out = tmp_path / 'missing'
    missing = plugin('connect', 'export', '--output', str(out))
    assert missing.returncode != 0
    assert 'connect profile --server HOST --account USER' in missing.stderr
    assert not out.exists()

    saved = plugin('connect', 'profile', '--server', 'linux.test', '--account', 'bsp', '--ssh-port', '2222')
    assert saved.returncode == 0, saved.stderr
    assert shared.read_preferences() == initial_preferences
    invalid = plugin('connect', 'profile', '--server', '127.0.0.1', '--account', 'bsp')
    assert invalid.returncode != 0
    assert 'Windows-reachable Linux SSH' in invalid.stderr

    isolated = plugin('connect', 'export', '--output', str(out), plugin_runtime=tmp_path / 'isolated')
    assert isolated.returncode != 0
    assert not out.exists()
    incomplete = plugin('connect', 'export', '--output', str(out), '--server', 'other.test')
    assert incomplete.returncode != 0
    assert 'Supply --server and --account together' in incomplete.stderr
    assert not out.exists()

    reused = tmp_path / 'reused'
    exported = plugin('connect', 'export', '--output', str(reused))
    assert exported.returncode == 0, exported.stderr
    assert (reused / 'start-board-connector.bat').is_file()
    profile = parse_bootstrap(json.loads((reused / 'connector-connection.json').read_text(encoding='utf-8')))
    assert profile.endpoint.model_dump() == {
        'server': 'linux.test', 'account': 'bsp', 'ssh_port': 2222,
        'remote_runner_port': 8871, 'remote_dashboard_port': None,
    }
    assert profile.expected_runner_id == 'a' * 32

    overridden = tmp_path / 'overridden'
    exported = plugin('connect', 'export', '--output', str(overridden), '--server', 'another.test',
                      '--account', 'other', '--remote-runner-port', '8873',
                      '--remote-dashboard-port', '8765', connector_port=8872)
    assert exported.returncode == 0, exported.stderr
    profile = parse_bootstrap(json.loads((overridden / 'connector-connection.json').read_text(encoding='utf-8')))
    assert profile.endpoint.model_dump() == {
        'server': 'another.test', 'account': 'other', 'ssh_port': 22,
        'remote_runner_port': 8873, 'remote_dashboard_port': 8765,
    }
    assert shared.read_bootstrap_ssh() == {'server': 'linux.test', 'account': 'bsp', 'ssh_port': 2222}

    cli_port = tmp_path / 'cli-port'
    exported = plugin('connect', 'export', '--output', str(cli_port), '--ssh-port', '3222', connector_port=8872)
    assert exported.returncode == 0, exported.stderr
    profile = parse_bootstrap(json.loads((cli_port / 'connector-connection.json').read_text(encoding='utf-8')))
    assert profile.endpoint.remote_runner_port == 8872
    assert profile.endpoint.ssh_port == 3222


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
            assert dc.test_status()['has_projection'] is False
            execute_direct(dc, ['test', 'list'], emit=lambda _: None)
            ts_data = dc.test_status()
            assert ts_data['has_projection'] is True
            assert [i['tc_id'] for i in ts_data['items']] == ['t1.py']

            # 3. DirectConnectorClient run + KeyboardInterrupt detach does NOT cancel run!
            run = dc.start_run(patterns=['t1.py'])
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
            run2 = dc.start_run(patterns=['t1.py'])
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
            out_dir = tmp_path / 'bundle-dir'
            emitted = []
            assert execute_direct(
                dc,
                ['connect', 'export', '--server', 'linux-build.internal', '--account', 'bsp', '--output', str(out_dir)],
                source_root=Path(__file__).resolve().parents[1],
                emit=emitted.append,
            ) == 0
            prof = json.loads((out_dir / 'connector-connection.json').read_text(encoding='utf-8'))
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
        with pytest.raises(TestError, match='Linux 공통 서버'):
            actions.shared({'expected_revision': shared0['revision'], 'integration': {'installer_path': '/images/flash.bat'}})
        saved_t = actions.shared({'expected_revision': shared0['revision'], 'integration': {'installer_path': '', 'flash_profile': ''},
                                  'timeouts': {'default_seconds': 333, 'overrides': {}}})
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


def test_discover_to_preview_run_without_metadata_timeout_falls_back_to_600s(tmp_path):
    from backend.gui_test.core.discovery import discover

    rt = tmp_path / 'rt'
    tc_root = tmp_path / 'tcs'
    tc_root.mkdir()
    (tc_root / 'plain_tc.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')

    catalog = discover(tc_root)
    assert catalog['tests'][0]['timeout'] == 120
    assert catalog['tests'][0]['timeout_explicit'] is False

    store = SharedSettingsStore(rt)
    s0 = store.read()
    store.save({
        'expected_revision': s0['revision'],
        'integration': s0['integration'] | {'tc_root': str(tc_root), 'source_roots': [str(tmp_path)]},
        'timeouts': {'default_seconds': None, 'overrides': {}},
    })

    dc = DirectConnectorClient(runtime_dir=rt, connector_port=8771)
    try:
        preview = dc.preview_run(patterns=['plain_tc.py'])
        assert len(preview['tests']) == 1
        step = preview['tests'][0]
        assert step['metadata_timeout_s'] is None
        assert step['effective_timeout_s'] == 600

        proj, _ = dc.build_tc_projection()
        assert len(proj['items']) == 1
        item = proj['items'][0]
        assert item['source_timeout_s'] is None
        assert item['effective_timeout_s'] == 600
    finally:
        dc.close()


def test_direct_connect_watch_emits_transitions_and_exits_cleanly(tmp_path):
    from backend.gui_test.standalone.plugin_commands import execute_direct

    rt = tmp_path / 'rt'
    dc = DirectConnectorClient(runtime_dir=rt, connector_port=8771)
    states = iter([
        (False, None),
        (True, 'a' * 32),
        (True, 'a' * 32),
        (False, None),
    ])

    def fake_diagnose():
        reachable, _ = next(states, (False, None))
        return {'linux_diagnostics': {'reachable': reachable}, 'report': {'connected': reachable}}

    dc.diagnose = fake_diagnose
    dc.inventory = lambda: {'runner_id': 'a' * 32, 'boards': []}
    try:
        events = []
        last = dc.watch_connection(interval=0.01, on_change=events.append, max_iterations=4)
        assert [e['event'] for e in events] == ['DISCONNECTED', 'CONNECTED', 'DISCONNECTED']
        assert last['connected'] is False

        # KeyboardInterrupt during execute_direct(['connect', '--watch']) exits cleanly with code 0.
        def raise_interrupt(*, on_change=None, **_kwargs):
            raise KeyboardInterrupt

        dc.watch_connection = lambda **kw: (kw['on_change']({'event': 'CONNECTED', 'connected': True}) if kw.get('on_change') else None) or {'event': 'CONNECTED'}
        emitted = []
        assert execute_direct(dc, ['connect', '--watch'], emit=emitted.append) == 0
        assert emitted == [{'event': 'CONNECTED', 'connected': True}]
    finally:
        dc.close()


def test_direct_defaults_glob_board_selection_and_streaming_installer(tmp_path, monkeypatch):
    rt = tmp_path / 'rt'
    tc_root = tmp_path / 'tcs'
    (tc_root / 'eth').mkdir(parents=True)
    (tc_root / 'usb').mkdir(parents=True)
    (tc_root / 'eth' / 't_eth.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
    (tc_root / 'usb' / 't_usb.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')

    inst_dir = tmp_path / 'inst'
    inst_dir.mkdir()
    inst_bat = inst_dir / 'flash.bat'
    inst_bat.write_text('@echo off\n', encoding='utf-8')
    (inst_dir / 'flash.bin').write_bytes(b'ABCD' * 2048)

    store = SharedSettingsStore(rt)
    s0 = store.read()
    store.save({
        'expected_revision': s0['revision'],
        'integration': s0['integration'] | {
            'tc_root': str(tc_root),
            'source_roots': [str(tmp_path)],
            'installer_roots': [str(tmp_path)],
            'global_defaults': ['eth/*.py'],
            'module_defaults': {'usb_mod': ['usb/*.py']},
            'connection': {'a': {'host': 'WINPC', 'board_id': 'B2', 'com': 'COM9'}},
        },
        'timeouts': {'default_seconds': None, 'overrides': {}},
    })

    dc = DirectConnectorClient(runtime_dir=rt, connector_port=8771, chunk_bytes=4096)
    try:
        # 1. global_defaults + glob matching
        p_global = dc.preview_run()
        assert [t['path'] for t in p_global['tests']] == ['eth/t_eth.py']

        # 2. module_defaults override
        p_mod = dc.preview_run(module='usb_mod')
        assert [t['path'] for t in p_mod['tests']] == ['usb/t_usb.py']

        # 3. shared['connection'] and active-board fallback
        inv = {
            'boards': [
                {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3', 'detected': False, 'state': 'DISCONNECTED'},
                {'host': 'WINPC', 'board_id': 'B2', 'com': 'COM9', 'detected': True, 'state': 'CONNECTED'},
            ]
        }
        conn, _ = dc._resolve_connection_and_command(p_global['tests'], inv)
        assert conn['a']['board_id'] == 'B2'

        # Without shared connection, active/detected board B2 is preferred over disconnected B1
        s1 = store.read()
        integ = dict(s1['integration'])
        integ.pop('connection', None)
        store.save({'expected_revision': s1['revision'], 'integration': integ, 'timeouts': {'default_seconds': None, 'overrides': {}}})
        conn2, _ = dc._resolve_connection_and_command(p_global['tests'], inv)
        assert conn2['a']['board_id'] == 'B2'

        # 4. sync_installer_snapshot streams without Path.read_bytes()
        monkeypatch.setattr(Path, 'read_bytes', lambda self: (_ for _ in ()).throw(AssertionError('read_bytes must not be called')))
        reqs = []

        def fake_request(method, path, **kwargs):
            reqs.append((method, path, kwargs.get('headers')))
            if method == 'GET':
                return {'state': 'EMPTY', 'offset': 0}
            return {'state': 'READY', 'offset': 999999}

        dc._request = fake_request
        res = dc.sync_installer_snapshot(inst_bat)
        assert res['uploaded'] is True
        assert res['chunks'] >= 1
    finally:
        dc.close()


def test_execute_direct_auto_analyzes_and_follows_retry_and_reprepare(tmp_path):
    from backend.gui_test.standalone.plugin_commands import execute_direct

    rt = tmp_path / 'rt'
    tc_root = tmp_path / 'tcs'
    tc_root.mkdir()
    (tc_root / 't1.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')

    dc = DirectConnectorClient(runtime_dir=rt, connector_port=8771)
    try:
        dc.start_run = lambda **kw: {'run_id': 'r1', 'state': 'QUEUED', 'tc_root': str(kw.get('tc_root'))}
        watch_calls = []
        states = iter([
            {'run_id': 'r1', 'state': 'PAUSED', 'pause_reason': 'FAILURE_STOP_LATCH'},
            {'run_id': 'r1', 'state': 'PAUSED', 'pause_reason': 'FAILURE_STOP_LATCH'},
            {'run_id': 'r2', 'state': 'COMPLETED', 'outcome': 'PASSED'},
        ])

        def fake_watch(run_id):
            watch_calls.append(run_id)
            return next(states)

        decisions = iter([
            {'analysis': {'decision': {'enforced_verdict': 'RETRY'}}, 'run': {'run_id': 'r1', 'state': 'QUEUED'}, 'child_run': None},
            {'analysis': {'decision': {'enforced_verdict': 'REPREPARE'}}, 'run': {'run_id': 'r1', 'state': 'COMPLETED'}, 'child_run': {'run_id': 'r2'}},
        ])
        analyze_calls = []

        def fake_analyze(**kw):
            analyze_calls.append(kw.get('run_id'))
            return next(decisions)

        dc.watch_run = fake_watch
        dc.analyze_once = fake_analyze
        emitted = []
        rc = execute_direct(dc, ['test', 'run', '--tc-root', str(tc_root)], emit=emitted.append)
        assert rc == 0
        assert watch_calls == ['r1', 'r1', 'r2']
        assert analyze_calls == ['r1', 'r1']
        assert emitted[-1]['run_id'] == 'r2'
        assert emitted[-1]['outcome'] == 'PASSED'
    finally:
        dc.close()


def test_single_run_retry_allowed_when_unused_second_board_is_disconnected(tmp_path):
    from backend.gui_test.execution.host import Host
    from backend.gui_test.execution.connector_runs import ConnectorEngine
    from backend.gui_test.core.models import digest

    runtime = tmp_path / 'winrt'
    runtime.mkdir()
    cfg = {
        'python': sys.executable,
        'boards': [
            {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'},
            {'host': 'WINPC', 'board_id': 'B2', 'com': 'COM4'},
        ],
        'serial_transport': 'native',
    }
    # Only COM3 is physically connected; COM4 is disconnected.
    host = Host(cfg, runtime, ports=lambda: {'COM3'})
    engine = ConnectorEngine(host, cfg)
    try:
        # Prepare minimal source snapshot
        from backend.gui_test.execution import source_snapshots
        tc_bytes = b"print('Test Result: FAIL'); import sys; sys.exit(1)\n"
        manifest = source_snapshots.manifest({'t_fail.py': tc_bytes}, {'kind': 'local'}, {})
        snap_id = manifest['snapshot_id']
        zpath = tmp_path / 'src.zip'
        with zipfile.ZipFile(zpath, 'w') as zf:
            zf.writestr(source_snapshots.MANIFEST, json.dumps(manifest, sort_keys=True))
            zf.writestr('t_fail.py', tc_bytes)
        source_snapshots.receive_archive(zpath, snap_id, host.runtime / 'source-snapshots')

        req = {
            'execution_mode': 'tc_only',
            'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
            'source_snapshot_id': snap_id,
            'source_revision': manifest['source_revision'],
            'command_snapshot': {
                'name': 'default',
                'revision': 'c1',
                'template': {
                    'single': ['python', '{tc_path}', '--com', '{com_a}'],
                    'dual': ['python', '{tc_path}', '--a', '{com_a}', '--b', '{com_b}'],
                },
            },
            'tests': [{'step_index': 0, 'tc_id': 't_fail.py', 'path': 't_fail.py', 'kind': 'Single', 'effective_timeout_s': 10}],
            'timeout_settings_snapshot': {},
            'failure_policy': {'mode': 'fail-stop-analysis-v1', 'max_retry_chain': 3, 'stop_on_same_cause': True, 'verifier_required': True},
            'origin': {'client': 'plugin', 'session_id': 's1'},
        }
        run, status_code = engine.create_run(req, idempotency_key='single-b2-off')
        assert status_code == 201
        deadline = time.time() + 10.0
        while time.time() < deadline:
            cur = engine.get_run(run['run_id'])
            if cur['state'] == 'PAUSED':
                break
            time.sleep(0.05)
        assert cur['pause_reason'] == 'FAILURE_STOP_LATCH'

        pending = engine.list_analyses(status='PENDING', run_id=run['run_id'])
        assert len(pending) == 1
        claimed = engine.claim_analysis(pending[0]['analysis_id'], {'lease_owner': 'plugin', 'lease_ttl_s': 60})
        dec = engine.decide_analysis(
            pending[0]['analysis_id'],
            {
                'lease_token': claimed['lease_token'],
                'expected_evidence_revision': claimed['evidence_revision'],
                'verdict': 'RETRY',
                'cause_key': 'transient_glitch',
                'summary': 'Retry on B1 even though B2 is disconnected',
                'verifier_status': 'PASSED',
            },
        )
        assert dec['analysis']['decision']['enforced_verdict'] == 'RETRY'
    finally:
        engine.close()


def test_efficiency_fixes_watch_stream_skip_rerun_headers_bridge_cache_and_ready_skip(tmp_path, monkeypatch):
    from backend.gui_test.connector.direct_proxy import DirectConnectorProxy
    from backend.gui_test.execution.connector_runs import BridgeTokenStore
    import zipfile as zf_mod

    # 1. watch_run skips streams already marked eof=True
    rt = tmp_path / 'rt'
    dc = DirectConnectorClient(runtime_dir=rt, connector_port=8771)
    try:
        poll_count = {'n': 0}
        log_calls = []

        def fake_get_run(run_id):
            poll_count['n'] += 1
            state = 'RUNNING' if poll_count['n'] == 1 else 'COMPLETED'
            return {'run_id': run_id, 'state': state, 'attempts': [{'attempt_id': 'a1', 'phase': 'TC'}]}

        def fake_read_logs(run_id, aid, *, stream='stdout', offset=0, limit=65536):
            log_calls.append((aid, stream, offset))
            if stream == 'stdout':
                return {'text': 'line1\n' if offset == 0 else '', 'next_offset': 6, 'total_bytes': 6, 'eof': True}
            return {'text': '', 'next_offset': 0, 'total_bytes': 0, 'eof': False}

        dc.get_run = fake_get_run
        dc.read_logs = fake_read_logs
        res = dc.watch_run('r1', poll_interval_s=0.0)
        assert res['state'] == 'COMPLETED'
        # stdout was eof=True on poll 1, so poll 2 must NOT re-fetch stdout
        assert [c for c in log_calls if c[1] == 'stdout'] == [('a1', 'stdout', 0)]
        assert len([c for c in log_calls if c[1] == 'stderr']) == 2
    finally:
        dc.close()

    # 2. DirectConnectorProxy.rerun_run forwards Idempotency-Key header without TypeError
    captured = {}

    class _FakeResp:
        status_code = 201
        def json(self):
            return {'run_id': 'b' * 32, 'state': 'QUEUED'}

    class _FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def request(self, method, url, json=None, headers=None):
            captured['method'] = method
            captured['url'] = url
            captured['headers'] = headers
            return _FakeResp()

    proxy = DirectConnectorProxy(manager=type('M', (), {'runtime': rt})(), client_factory=_FakeClient)
    rerun_res = proxy.rerun_run('a' * 32, idempotency_key='idem-123')
    assert rerun_res['run_id'] == 'b' * 32
    assert captured['headers'] == {'Idempotency-Key': 'idem-123'}

    # 3. BridgeTokenStore caches token by (mtime_ns, size)
    tok_dir = tmp_path / 'tok'
    bts = BridgeTokenStore(tok_dir, windows=False)
    tok = 't' * 40
    bts.save(tok)
    monkeypatch.setattr(Path, 'read_bytes', lambda self: (_ for _ in ()).throw(AssertionError('must hit cache')))
    assert bts.load() == tok

    # 4. sync_installer_snapshot skips ZipFile creation when Host already reports READY
    inst_dir = tmp_path / 'inst'
    inst_dir.mkdir()
    bat = inst_dir / 'flash.bat'
    bat.write_text('@echo off\n', encoding='utf-8')
    (inst_dir / 'flash.bin').write_bytes(b'IMG')
    store = SharedSettingsStore(rt)
    s0 = store.read()
    store.save({
        'expected_revision': s0['revision'],
        'integration': s0['integration'] | {'installer_roots': [str(tmp_path)]},
        'timeouts': {'default_seconds': None, 'overrides': {}},
    })
    dc2 = DirectConnectorClient(runtime_dir=rt, connector_port=8771)
    try:
        dc2._request = lambda method, path, **kw: {'state': 'READY', 'archive_size': 123}
        monkeypatch.setattr(zf_mod, 'ZipFile', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('must not zip when READY')))
        out = dc2.sync_installer_snapshot(bat)
        assert out['uploaded'] is False and out['total_bytes'] == 123
    finally:
        dc2.close()



def test_direct_settings_explicit_import_is_revision_checked_and_rejects_file_sync(tmp_path):
    from backend.gui_test.core.models import TestError

    client = DirectConnectorClient(runtime_dir=tmp_path / 'runtime')
    draft = tmp_path / 'shared-settings.json'
    commands = lambda op: execute_direct(client, ['settings', *op], emit=lambda value: None)
    try:
        baseline = client.store.read()
        for detail in ('sync', 'push'):
            with pytest.raises(ValueError, match='unavailable'):
                commands(['file', detail, '--file', str(draft)])
        with pytest.raises(FileNotFoundError):
            commands(['import', '--file', str(draft)])
        assert client.store.read() == baseline
        assert commands(['export', '--file', str(draft)]) == 0
        payload = json.loads(draft.read_text())
        payload['timeouts']['default_seconds'] = 150
        draft.write_text(json.dumps(payload))
        assert commands(['import', '--file', str(draft)]) == 0
        committed = client.store.read()
        assert committed['timeouts']['default_seconds'] == 150
        with pytest.raises(TestError, match='Shared settings changed'):
            commands(['import', '--file', str(draft)])
        assert client.store.read() == committed
        assert json.loads(draft.read_text()) == payload
    finally:
        client.close()


def test_flash_request_combines_manual_settings_and_plugin_arguments(tmp_path):
    from types import SimpleNamespace

    saved = {'installer_path': '/images/selected/app.bat', 'flash_profile': 'manual'}
    client = SimpleNamespace(store=SimpleNamespace(read=lambda: {'integration': saved}),
                             preview_run=lambda **kw: kw, start_run=lambda **kw: kw)
    def execute(*args):
        result = []
        execute_direct(client, ['test', *args], emit=result.append)
        return result[0]

    assert execute('preview')['installer'] is None
    manual = execute('run', '--flash', '--no-follow')
    assert manual['installer'] == Path(saved['installer_path']) and manual['flash_profile'] == 'manual'
    assert execute('preview', '--flash', '--installer', '/new/install.bat')['installer'] == Path('/new/install.bat')
    assert execute('preview', '--flash', '--flash-profile', 'override')['flash_profile'] == 'override'
    saved.clear()
    with pytest.raises(ValueError, match='Linux 설치 BAT'):
        execute('run', '--flash', '--no-follow')
    with pytest.raises(ValueError, match='explicit --flash'):
        execute('preview', '--installer', '/new/install.bat')


def test_plugin_published_flash_settings_flow_between_dashboard_and_direct_cli(tmp_path):
    from fastapi.testclient import TestClient
    from backend.api.main import create_app

    root = tmp_path.resolve()
    direct = DirectConnectorClient(home=root, runtime_dir=root)
    file = root / 'settings.json'
    file.write_text(json.dumps({'installer_roots': ['/images'], 'installer_path': '/images/build/flash.bat',
                                'flash_profile': 'company'}))
    try:
        execute_direct(direct, ['settings', 'save', '--file', str(file)], emit=lambda _: None)
        with TestClient(create_app(root), client=('127.0.0.1', 1234)) as browser:
            url = '/api/v1/gui-test/live/integration/settings'
            config = browser.get(url).json()
            assert config['integration']['flash_profile'] == 'company'
            assert config['integration']['installer_path'] == '/images/build/flash.bat'
            manual = dict(config['integration'], installer_path='/images/manual/flash.bat', flash_profile='manual')
            body = {'expected_revision': config['revision'], 'integration': manual,
                    'timeouts': {k: v for k, v in config['timeouts'].items() if k != 'revision'}}
            assert browser.put(url, headers={'X-Bsp-Client':'dashboard', 'Origin':'http://testserver'}, json=body).status_code == 200
        direct.preview_run = lambda **options: options
        results = []
        execute_direct(direct, ['test', 'preview', '--flash'], emit=results.append)
        assert results[0]['installer'] == Path('/images/manual/flash.bat') and results[0]['flash_profile'] == 'manual'
    finally:
        direct.close()


def test_connect_delivers_linux_tc_path_without_dashboard_or_watch(tmp_path):
    import socket
    from types import SimpleNamespace
    from backend.gui_test.connector.supervisor import Manager
    host, port, server, thread = _start_live_host(tmp_path)
    client = DirectConnectorClient(runtime_dir=tmp_path / 'linux', connector_port=port)
    try:
        shared = client.store.read()
        root = '/company/tests/linux-tcs'
        client.store.save({'expected_revision': shared['revision'],
                           'integration': dict(shared['integration'], tc_root=root, source_roots=['/company/tests']),
                           'timeouts': {k:v for k,v in shared['timeouts'].items() if k != 'revision'}})
        started = time.time() - 1
        assert client.diagnose()['reachable']
        mgr = object.__new__(Manager)
        mgr.home = tmp_path / 'winhome'
        mgr.runtime = mgr.home / 'runtime'
        mgr.host_url = client.url
        mgr.host_runner_id = host.identity
        mgr.error = ''
        mgr.storage_cache = {}
        mgr.storage_checked = time.monotonic()
        mgr.console_cursor = 0
        mgr.console_epoch = ''
        settings = {'server': socket.gethostname(), 'account':'lab', 'remote_runner_port':port}
        mgr.settings = SimpleNamespace(read=lambda: {'_setup': settings})
        tunnel = {'server': settings['server'], 'account':'lab', 'remote_runner_port': port,
                  'connected_since': time.time(), 'transport_started_at': started, 'optional_dashboard_forward': 'NOT_CONFIGURED'}
        mgr.ssh_supervisor = SimpleNamespace(snapshot=lambda: {'ssh_state':'CONNECTED','tunnel':tunnel})
        value = mgr._probe_direct(None)
        assert value['state'] == 'CONNECTED'
        assert value.get('shared_settings', {}).get('integration', {}).get('tc_root') == root
        assert value['shared_settings']['read_only'] is True
        assert '플러그인 연결 보고' in value['shared_settings']['settings_source']
        from backend.gui_test.connector.web_actions import ManagerActions
        mgr.cached = value
        actions = ManagerActions(mgr)
        manual = actions.shared()
        assert manual == value['shared_settings']
        assert value['test_status']['tc_root'] == root and value['test_status']['has_projection'] is False
        monitor = DirectConnectorClient(runtime_dir=tmp_path / 'monitor', connector_port=port, peer_type='agent_monitor')
        try:
            assert monitor.diagnose()['reachable']
            both = mgr._probe_direct(None)
            assert both['shared_settings']['settings_source'].startswith('Agent Monitor 연결 보고')
            assert both['shared_settings']['integration']['tc_root'] == ''
            assert both['plugin_receipt']['state'] == 'CONNECTED'
            assert both['plugin_receipt']['settings']['integration']['tc_root'] == root
        finally:
            monitor.close()
        tunnel['transport_started_at'] = time.time() + 1
        later = mgr._probe_direct(None)
        assert later['state'] == 'CONNECTED' and not later.get('shared_settings')
        assert later['plugin_receipt'] is None
        with pytest.raises(TestError) as pending:
            actions.shared()
        assert pending.value.code == 'SHARED_SETTINGS_PENDING'
    finally:
        client.close()
        server.should_exit = True
        thread.join(5)


def test_shared_get_uses_live_dashboard_forward_and_rejects_reused_pid(tmp_path, monkeypatch):
    import httpx
    from backend.gui_test.connector import shared_control
    from backend.gui_test.execution import launch
    from backend.gui_test.connector.settings import Settings

    ssh = {'pid': 51, 'creation_time': '100'}
    dash = {'pid': 52, 'creation_time': '101'}
    current = {51:ssh, 52:dash}
    info = {'ssh_state':'CONNECTED', 'transport':ssh, 'dashboard_transport':dash, 'local_dashboard_port':28766}
    monkeypatch.setattr(launch, 'read_ssh_tunnel', lambda _: info)
    monkeypatch.setattr(launch, 'read_active', lambda _: pytest.fail('used stale legacy receipt'))
    monkeypatch.setattr(launch, 'process_identity', current.get)
    monkeypatch.setattr(Settings, 'read', lambda _: {})
    actual = httpx.Client
    def respond(req):
        assert str(req.url) == 'http://127.0.0.1:28766/api/v1/gui-test/live/integration/settings'
        return httpx.Response(200, json={'revision':'r1','timeouts':{},'integration':{'tc_root':'/srv/board-tcs'}})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: actual(transport=httpx.MockTransport(respond), **kwargs))
    assert shared_control.request(tmp_path, 'settings', direct=True)['integration']['tc_root'] == '/srv/board-tcs'
    current[52] = dict(dash, creation_time='202')
    with pytest.raises(TestError) as exc:
        shared_control.request(tmp_path, 'settings', direct=True)
    assert exc.value.code == 'CONNECTOR_DISCONNECTED'


@pytest.mark.parametrize('code,status,allow_ssh', [
    ('CONNECTOR_DISCONNECTED', 409, True),
    ('SHARED_UNAVAILABLE', 503, True),
    ('SERVICE_IDENTITY_MISMATCH', 409, False),
    ('FORBIDDEN', 403, False),
])
def test_manual_load_with_unusable_dashboard_forward(tmp_path, monkeypatch, code, status, allow_ssh):
    from types import SimpleNamespace
    from backend.gui_test.connector import shared_control
    from backend.gui_test.connector.supervisor import Manager
    from backend.gui_test.connector.web_actions import ManagerActions

    manager = object.__new__(Manager)
    manager.home, manager.host_runner_id = tmp_path, 'board-host'
    manager.cached = {}
    manager.settings = SimpleNamespace(read=lambda: {})
    tunnel = {'server': 'lab', 'remote_dashboard_port': 9876, 'optional_dashboard_forward': 'CONNECTED'}
    preview = {'read_only': True, 'revision':'linux', 'integration':{'tc_root':'/srv/tc'}, 'timeouts':{}}
    def unavailable(*args, **kwargs):
        raise TestError('forward error', code, status)
    def remote_read(*, refresh):
        assert refresh and allow_ssh
        return preview
    monkeypatch.setattr(shared_control, 'request', unavailable)
    manager.ssh_supervisor = SimpleNamespace(snapshot=lambda: {'ssh_state':'CONNECTED', 'tunnel':tunnel},
                                             read_linux_settings=remote_read)
    if allow_ssh:
        assert ManagerActions(manager).shared() == preview
    else:
        with pytest.raises(TestError) as error:
            ManagerActions(manager).shared()
        assert (error.value.code, error.value.status) == (code, status)


def test_plugin_settings_show_names_database_even_when_tc_source_is_empty(tmp_path):
    from backend.gui_test.standalone.plugin_commands import execute_direct
    client = DirectConnectorClient(runtime_dir=tmp_path / 'separate runtime', home=tmp_path / 'login')
    try:
        output = []
        assert execute_direct(client, ['settings','show'], emit=output.append) == 0
        assert output[0]['settings_db_path'] == str(client.store.path)
        assert output[0]['tc_root_state'] == 'UNSET'
        assert output[0]['shared_settings']['integration']['tc_root'] == ''
        current = client.store.read()
        client.store.save({'expected_revision':current['revision'], 'integration':{'tc_root':'/srv/tcs',
                           'source_roots':['/srv/tcs']}, 'timeouts':{}})
        assert execute_direct(client, ['settings','show'], emit=output.append) == 0
        assert output[-1]['tc_root_state'] == 'SET' and output[-1]['shared_settings']['integration']['tc_root'] == '/srv/tcs'
    finally:
        client.close()


@pytest.mark.parametrize('peer_type,label', [('plugin', 'Linux 플러그인'), ('agent_monitor', 'Agent Monitor')])
def test_settings_peer_source_and_plugin_receipt(tmp_path, peer_type, label):
    from types import SimpleNamespace
    from backend.gui_test.connector.supervisor import Manager, plugin_receipt
    mgr = object.__new__(Manager)
    mgr.home = tmp_path
    mgr.settings = SimpleNamespace(read=lambda: {})
    started = time.time() - 10
    tunnel = {'server': 'linux', 'remote_runner_port': 8771, 'transport_started_at': started}
    report = {'revision': 'saved', 'integration': {'tc_root': '/from-plugin'}, 'timeouts': {'default_seconds': 300}}
    peer = {'peer_type': peer_type, 'client_status': 'OK', 'stale': False, 'linux_host': 'linux',
            'expected_runner_id': 'r', 'target_port': 8771, 'observed_at': started + 1,
            'linux_diagnostics': {'active_shared_revision': 'saved', 'shared_execution_settings': report}}
    diag = {'peers': {'recent': [peer]}}
    shared = mgr._direct_shared_settings(tunnel, diag, 'r')['shared_settings']
    assert shared['settings_source'].startswith(label)
    receipt = plugin_receipt(tunnel, diag, 'r')
    if peer_type == 'agent_monitor':
        assert receipt is None
        return
    assert receipt['state'] == 'CONNECTED' and receipt['settings']['integration']['tc_root'] == '/from-plugin'
    assert receipt['settings'] == report  # Omitted fields must not appear as values sent by the plugin.
    peer['linux_diagnostics']['active_shared_revision'] = 'other'
    assert plugin_receipt(tunnel, diag, 'r')['settings'] == report
    assert 'shared_settings' not in mgr._direct_shared_settings(tunnel, diag, 'r')
    peer['stale'] = True
    assert plugin_receipt(tunnel, diag, 'r')['state'] == 'STALE'
    peer['observed_at'] = started - 1
    assert plugin_receipt(tunnel, diag, 'r') is None
