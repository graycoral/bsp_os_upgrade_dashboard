"""Tests for Direct Connector Unit 2: SSH -R decoupled lifecycle, diagnostics, DPAPI bridge, and settings CAS."""
import json
import os
from pathlib import Path
import socket
import sys
import time

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.connector import emergency
from backend.gui_test.connector.ssh_tunnel import (
    SshTunnelSupervisor,
    build_ssh_r_argv,
    classify_ssh_stderr_line,
    is_forward_success_line,
    preflight_ssh,
)
from backend.gui_test.connector.supervisor import Manager
from backend.gui_test.core.models import TestError
from backend.gui_test.execution import launch
from backend.gui_test.execution.connector_runs import BridgeTokenStore
from backend.gui_test.execution.host import Host, create_app
from backend.gui_test.execution.source_snapshots import receive_archive
import zipfile


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _make_source_zip(tmp_path: Path):
    src = tmp_path / 'tc_src'
    src.mkdir(parents=True, exist_ok=True)
    (src / 'tc_pass.py').write_text("print('RESULT: PASS')\n", encoding='utf-8')
    (src / 'tc_catalog.json').write_text(
        json.dumps([{'id': 'TC-1', 'path': 'tc_pass.py', 'kind': 'Single', 'timeout': 30}]),
        encoding='utf-8',
    )
    zip_path = tmp_path / 'src.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.write(src / 'tc_pass.py', 'tc_pass.py')
        zf.write(src / 'tc_catalog.json', 'tc_catalog.json')
    return zip_path


def _make_host_and_client(tmp_path: Path):
    home = tmp_path / 'winhome'
    runtime = home / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    cfg_path = home / 'windows-runner.json'
    cfg = {
        'python': sys.executable,
        'boards': [{'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}],
        'board_names': {'B1': 'Board One'},
        'serial_transport': 'native',
        '_setup': {'server': '127.0.0.1', 'account': 'bsp', 'ssh_port': 22, 'remote_runner_port': 8771},
    }
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    host = Host(cfg, runtime, ports=lambda: {'COM3'}, config_path=cfg_path)
    app = create_app(host)
    return home, runtime, cfg_path, host, app


def test_ssh_argv_forbids_strict_host_key_checking_no_and_uses_verbose(tmp_path):
    key = tmp_path / 'id_ed25519'
    key.write_text('dummy', encoding='utf-8')
    argv = build_ssh_r_argv(
        'ssh',
        {'server': 'linux.example', 'account': 'bsp', 'ssh_key': str(key)},
        actual_local_runner_port=8772,
        remote_runner_port=8771,
        ssh_port=2222,
    )
    assert 'StrictHostKeyChecking=no' not in argv
    assert 'LogLevel=VERBOSE' in argv
    assert 'ExitOnForwardFailure=yes' in argv
    assert '127.0.0.1:8771:127.0.0.1:8772' in argv


def test_ssh_stderr_classification_and_forward_detection():
    assert is_forward_success_line('debug1: Allocated port 8771 for remote forward to 127.0.0.1:8772', 8771)
    assert is_forward_success_line('All remote forwarding requests succeeded', 8771)
    assert not is_forward_success_line('OpenSSH_9.0p1, debug1: Connecting...', 8771)

    code, fatal = classify_ssh_stderr_line('Permission denied (publickey,password).')
    assert fatal and code == 'SSH_AUTH_FAILED'
    code, fatal = classify_ssh_stderr_line('Error: remote port forwarding failed for listen port 8771')
    assert not fatal and code == 'SSH_REMOTE_PORT_BUSY'
    code, fatal = classify_ssh_stderr_line('ssh: connect to host 10.0.0.5 port 22: Connection timed out')
    assert not fatal and code == 'SSH_TIMEOUT'


def test_ssh_tunnel_supervisor_bind_verify_fatal_halt_and_dash_isolation(tmp_path):
    fake_ssh = tmp_path / 'fake_ssh.py'
    fake_ssh.write_text(
        """
import os, sys, time
mode = os.environ.get('FAKE_SSH_MODE', 'ok')
is_dash = '-L' in sys.argv
if is_dash and os.environ.get('FAKE_DASH_FAIL') == '1':
    sys.stderr.write('bind [127.0.0.1]:8766: Address already in use\\n')
    sys.stderr.flush()
    sys.exit(255)
if mode == 'fatal_auth':
    sys.stderr.write('Permission denied (publickey).\\n')
    sys.stderr.flush()
    sys.exit(255)
if mode == 'hang_no_bind':
    sys.stderr.write('debug1: Connecting to linux...\\n')
    sys.stderr.flush()
    time.sleep(5)
    sys.exit(0)
sys.stderr.write('debug1: Allocated port 8771 for remote forward to 127.0.0.1:8772\\n')
sys.stderr.flush()
time.sleep(5)
""",
        encoding='utf-8',
    )

    def spawn_fake(mode, dash_fail='0'):
        env = dict(os.environ, FAKE_SSH_MODE=mode, FAKE_DASH_FAIL=dash_fail)
        return lambda argv, **kw: __import__('subprocess').Popen(
            [sys.executable, '-B', str(fake_ssh), *argv],
            stdin=__import__('subprocess').DEVNULL,
            stdout=__import__('subprocess').PIPE,
            stderr=__import__('subprocess').PIPE,
            env=env,
        )

    # 1. Successful -R bind + isolated -L port busy still yields CONNECTED!
    sup = SshTunnelSupervisor(
        tmp_path / 'rt1',
        {'server': '127.0.0.1', 'account': 'bsp', 'ssh_port': 22},
        actual_local_runner_port=8772,
        remote_runner_port=8771,
        local_dashboard_port=8766,
        remote_dashboard_port=8766,
        popen=spawn_fake('ok', dash_fail='1'),
        preflight_fn=lambda *a, **kw: {'ok': True, 'code': None, 'fatal': False, 'warnings': [], 'ssh_path': 'ssh'},
        stability_window=0.05,
        bind_timeout=3.0,
    )
    sup.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            snap = sup.snapshot()
            if snap['ssh_state'] == 'CONNECTED':
                break
            time.sleep(0.05)
        snap = sup.snapshot()
        assert snap['ssh_state'] == 'CONNECTED'
        assert snap['tunnel']['optional_dashboard_forward'] == 'LOCAL_DASHBOARD_FORWARD_SKIPPED'
    finally:
        sup.stop()

    # 2. Fatal auth error halts in AUTH_OR_CONFIG_ERROR without spinning infinitely.
    sup_bad = SshTunnelSupervisor(
        tmp_path / 'rt2',
        {'server': '127.0.0.1', 'account': 'bsp', 'ssh_port': 22},
        actual_local_runner_port=8772,
        remote_runner_port=8771,
        popen=spawn_fake('fatal_auth'),
        preflight_fn=lambda *a, **kw: {'ok': True, 'code': None, 'fatal': False, 'warnings': [], 'ssh_path': 'ssh'},
        stability_window=0.05,
        bind_timeout=2.0,
    )
    sup_bad.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            snap = sup_bad.snapshot()
            if snap['ssh_state'] == 'AUTH_OR_CONFIG_ERROR':
                break
            time.sleep(0.05)
        snap = sup_bad.snapshot()
        assert snap['ssh_state'] == 'AUTH_OR_CONFIG_ERROR'
        assert snap['ssh_diagnostic']['code'] == 'SSH_AUTH_FAILED'
    finally:
        sup_bad.stop()

    # 3. Missing Allocated port line does NOT prematurely mark CONNECTED.
    sup_hang = SshTunnelSupervisor(
        tmp_path / 'rt3',
        {'server': '127.0.0.1', 'account': 'bsp', 'ssh_port': 22},
        actual_local_runner_port=8772,
        remote_runner_port=8771,
        popen=spawn_fake('hang_no_bind'),
        preflight_fn=lambda *a, **kw: {'ok': True, 'code': None, 'fatal': False, 'warnings': [], 'ssh_path': 'ssh'},
        stability_window=0.05,
        bind_timeout=0.35,
    )
    sup_hang.start()
    try:
        time.sleep(0.2)
        assert sup_hang.snapshot()['ssh_state'] != 'CONNECTED'
    finally:
        sup_hang.stop()


def test_preflight_ssh_detects_missing_key_and_invalid_host(tmp_path):
    res_cfg = preflight_ssh({'server': '', 'account': 'bsp'})
    assert res_cfg['ok'] is False and res_cfg['code'] == 'SSH_CONFIG_INCOMPLETE' and res_cfg['fatal'] is True

    res_key = preflight_ssh({'server': '127.0.0.1', 'account': 'bsp', 'ssh_key': str(tmp_path / 'missing_key')}, which=lambda *_: 'ssh')
    assert res_key['ok'] is False and res_key['code'] == 'SSH_KEY_NOT_FOUND' and res_key['fatal'] is True


def test_host_dpapi_bridge_peer_hello_lru_diagnostics_and_settings_cas(tmp_path):
    home, runtime, cfg_path, host, app = _make_host_and_client(tmp_path)
    try:
        bridge = BridgeTokenStore(home / 'manager-bridge', windows=False)
        token = bridge.ensure()

        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            # Origin header rejected by non-browser middleware.
            r_origin = client.get('/v1/identity', headers={'Origin': 'http://evil.example'})
            assert r_origin.status_code == 403

            ident = client.get('/v1/identity').json()
            assert ident['schema_version'] == 'direct-connector-v1'
            assert ident['service'] == 'bsp-board-connector'
            assert 'connector-runs-v1' in ident['capabilities']
            assert ident['manager_attached'] is False

            # Unauthorized manager heartbeat -> 403.
            r_bad_mgr = client.post(
                '/v1/internal/manager-heartbeat',
                headers={'X-Manager-Token': 'wrong-token'},
                json={'manager_pid': os.getpid()},
            )
            assert r_bad_mgr.status_code == 403

            # Headless verify-connection -> MANAGER_NOT_ATTACHED warning, putty/restart -> 501.
            assert client.post('/v1/control/putty').status_code == 501
            assert client.post('/v1/control/restart').status_code == 501
            v_headless = client.post('/v1/control/verify-connection').json()
            assert v_headless['ssh_diagnostic']['code'] == 'MANAGER_NOT_ATTACHED'

            # Valid manager heartbeat attaches Manager and marks CONNECTED when ssh_state=CONNECTED.
            hb = client.post(
                '/v1/internal/manager-heartbeat',
                headers={'X-Manager-Token': token},
                json={
                    'manager_pid': os.getpid(),
                    'local_port': 8772,
                    'remote_runner_port': 8771,
                    'ssh_snapshot': {'ssh_state': 'CONNECTED', 'tunnel': {'remote_runner_port': 8771, 'actual_local_runner_port': 8772}},
                },
            )
            assert hb.status_code == 200 and hb.json()['manager_attached'] is True
            assert client.get('/v1/identity').json()['manager_attached'] is True

            # Peer hello LRU cap = 16 + mismatch warning exposed.
            for idx in range(20):
                hello = client.post(
                    '/v1/peer/hello',
                    json={
                        'peer_type': 'plugin',
                        'peer_instance_id': f'plugin-{idx}',
                        'peer_version': '1.0',
                        'target_port': 8771,
                        'expected_runner_id': host.identity if idx < 19 else 'f' * 32,
                        'linux_host': 'linux-dev',
                        'client_status': 'MISMATCH' if idx == 19 else 'OK',
                        'client_issue': {'code': 'RUNNER_CHANGED', 'message': 'mismatch'} if idx == 19 else None,
                    },
                )
                assert hello.status_code == 200
                assert hello.json()['overall_connection_state'] == 'CONNECTED'
            diag = client.get('/v1/diagnostics/connection').json()
            assert diag['overall_connection_state'] == 'CONNECTED'
            assert len(diag['peers']['recent']) == 16
            assert any(w['client_status'] == 'MISMATCH' for w in diag['peer_warnings'])
            assert diag['peers']['agent_monitor']['client_status'] == 'OPTIONAL_OFFLINE'

            # Readiness (missing COM) NEVER degrades overall_connection_state when transport is CONNECTED.
            host.ports = lambda: set()
            diag2 = client.get('/v1/diagnostics/connection').json()
            assert diag2['overall_connection_state'] == 'CONNECTED'
            assert diag2['readiness']['execution_ready'] is False
            assert diag2['readiness']['com_port']['ready'] is False

            # Control settings CAS + Windows offline dirty tracking + ack-sync.
            s0 = client.get('/v1/control/settings').json()
            bad_cas = client.put(
                '/v1/control/settings',
                json={'expected_revision': 'stale-rev', 'source': 'linux', 'patch': {'board_names': {'B1': 'X'}}},
            )
            assert bad_cas.status_code == 409
            assert bad_cas.json()['code'] == 'SETTINGS_REVISION_CONFLICT'
            assert bad_cas.json()['current_revision'] == s0['revision']

            win_edit = client.put(
                '/v1/control/settings',
                json={
                    'expected_revision': s0['revision'],
                    'source': 'windows',
                    'patch': {'timeouts': {'default_seconds': 720, 'overrides': {'TC-1': 90}}},
                },
            ).json()
            assert win_edit['sync_state']['dirty_on_windows'] is True
            assert win_edit['manager_reload']['queued'] is True
            ack = client.post(
                '/v1/settings/ack-sync',
                json={
                    'expected_runner_id': host.identity,
                    'expected_windows_revision': win_edit['revision'],
                    'base_linux_revision': 'linux-rev-1',
                },
            ).json()
            assert ack['acknowledged'] is True
            assert ack['sync_state']['dirty_on_windows'] is False
    finally:
        host.close()


def test_manager_reattaches_host_keeps_ssh_on_host_restart_and_emergency_cleans_v2_files(tmp_path, monkeypatch):
    fake_proc_id = {'pid': os.getpid(), 'creation_time': 'mac-test'}
    monkeypatch.setattr(launch, 'process_identity', lambda pid: fake_proc_id if pid == os.getpid() else None)
    import backend.gui_test.connector.supervisor as sup_mod
    monkeypatch.setattr(sup_mod, 'process_identity', lambda pid: fake_proc_id if pid == os.getpid() else None)
    import backend.gui_test.connector.ssh_tunnel as tunnel_mod
    monkeypatch.setattr(tunnel_mod, 'process_identity', lambda pid: fake_proc_id if pid == os.getpid() else None)

    home = tmp_path / 'winhome'
    runtime = home / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    cfg = {
        'python': sys.executable,
        'boards': [{'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}],
        'serial_transport': 'native',
        '_setup': {'server': '127.0.0.1', 'account': 'bsp', 'ssh_port': 22, 'remote_runner_port': 8771},
    }
    (home / 'windows-runner.json').write_text(json.dumps(cfg), encoding='utf-8')
    host = Host(cfg, runtime, ports=lambda: {'COM3'}, config_path=home / 'windows-runner.json')
    port = _free_port()

    import threading, uvicorn
    app = create_app(host)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, access_log=False, log_level='warning'))
    srv_thread = threading.Thread(target=server.run, daemon=True)
    srv_thread.start()
    cleanup_bridge = lambda: None
    try:
        import httpx
        bridged = False
        for _ in range(20):
            try:
                if httpx.get(f'http://127.0.0.1:{port}/v1/identity', timeout=0.2).status_code == 200:
                    break
            except Exception as exc:
                if 'Operation not permitted' in str(exc):
                    bridged = True
                    break
                time.sleep(0.05)
        if bridged:
            tc = TestClient(app, base_url=f'http://127.0.0.1:{port}', client=('127.0.0.1', 5000))
            real_client, real_get = httpx.Client, httpx.get

            def _handler(req: httpx.Request) -> httpx.Response:
                if getattr(server, 'should_exit', False) or req.url.port != port:
                    raise httpx.ConnectError('Connection refused', request=req)
                hdrs = {k: v for k, v in req.headers.items() if k.lower() != 'host'}
                r = tc.request(req.method, req.url.raw_path.decode('ascii'), headers=hdrs, content=req.read())
                return httpx.Response(r.status_code, headers=dict(r.headers), content=r.content, request=req)

            monkeypatch.setattr(httpx, 'Client', lambda *a, **kw: real_client(*a, **{**kw, 'transport': kw.get('transport') or httpx.MockTransport(_handler)}))
            monkeypatch.setattr(httpx, 'get', lambda url, **kw: httpx.Client(**kw).get(url))
        launch.write_host_active(
            runtime,
            {
                'version': 2,
                'launch_id': 'a' * 32,
                'owner': launch.process_identity(os.getpid()),
                'runner': launch.process_identity(os.getpid()),
                'runner_id': host.identity,
                'runner_port': port,
                'local_state': 'READY',
                'manager_attached': True,
                'started_at': time.time(),
            },
        )
        fake_ssh = tmp_path / 'fake_ssh_ok.py'
        fake_ssh.write_text(
            "import sys, time\nsys.stderr.write('Allocated port 8771 for remote forward to 127.0.0.1:%s\\n' % "
            "sys.argv[-1].split(':')[-1] if False else 'Allocated port 8771 for remote forward to 127.0.0.1:8772\\n')\n"
            "sys.stderr.flush()\ntime.sleep(5)\n",
            encoding='utf-8',
        )
        orig_builder = Manager._build_ssh_supervisor

        def fake_builder(self, setup, local_runner_port, remote_runner_port, local_dashboard_port, remote_dashboard_port):
            return SshTunnelSupervisor(
                self.runtime,
                setup,
                actual_local_runner_port=local_runner_port,
                remote_runner_port=remote_runner_port,
                popen=lambda argv, **kw: __import__('subprocess').Popen(
                    [sys.executable, '-B', str(fake_ssh)],
                    stdin=__import__('subprocess').DEVNULL,
                    stdout=__import__('subprocess').PIPE,
                    stderr=__import__('subprocess').PIPE,
                ),
                preflight_fn=lambda *a, **kw: {'ok': True, 'code': None, 'fatal': False, 'warnings': [], 'ssh_path': 'ssh'},
                stability_window=0.05,
                bind_timeout=3.0,
            )

        Manager._build_ssh_supervisor = fake_builder
        try:
            mgr = Manager(home)
            try:
                assert mgr.host_url == f'http://127.0.0.1:{port}'
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    if mgr.probe().get('state') == 'CONNECTED':
                        break
                    time.sleep(0.05)
                probed = mgr.probe()
                assert probed['state'] == 'CONNECTED'
                assert probed['stages']['agent_monitor'] == 'OPTIONAL_OFFLINE'

                # Simulate Manager restart: new Manager reattaches to same running Host via DPAPI token!
                mgr.close()
                mgr2 = Manager(home)
                try:
                    assert mgr2.host_url == f'http://127.0.0.1:{port}'
                    assert httpx.get(f'http://127.0.0.1:{port}/v1/identity', timeout=1.0).json()['manager_attached'] is True
                    # Restart Host only -> SSH supervisor stays preserved!
                    ssh_obj_before = mgr2.ssh_supervisor
                    restarted_ports = []
                    mgr2._stop_host_only = lambda: restarted_ports.append('stopped')
                    mgr2._spawn_host_process = lambda p, allow_fallback=False: {
                        'runner_port': p,
                        'runner_id': host.identity,
                        'runner_url': f'http://127.0.0.1:{p}',
                    }
                    res = mgr2.restart_host()
                    assert res['restarted'] is True and res['ssh_preserved'] is True
                    assert mgr2.ssh_supervisor is ssh_obj_before
                    assert restarted_ports == ['stopped']
                finally:
                    mgr2.close()
            finally:
                mgr.close()
        finally:
            Manager._build_ssh_supervisor = orig_builder
    finally:
        server.should_exit = True
        srv_thread.join(timeout=3.0)
        cleanup_bridge()
        host.close()

    # Verify emergency force_stop inspects v2 receipt files cleanly.
    dummy = __import__('subprocess').Popen([sys.executable, '-B', '-c', 'import time; time.sleep(30)'])
    try:
        dummy_id = {'pid': dummy.pid, 'creation_time': 'mac-dummy'}
        monkeypatch.setattr(launch, 'process_identity', lambda pid: dummy_id if pid == dummy.pid else None)
        import backend.gui_test.execution.force_stop as fs_mod
        monkeypatch.setattr(fs_mod, 'process_identity', lambda pid: dummy_id if pid == dummy.pid else None)

        class _FakePinned:
            def __init__(self, ident): self.identity = ident
            def close(self): pass
            def stop(self):
                if dummy.poll() is None:
                    dummy.terminate()
                    dummy.wait(timeout=3)
        monkeypatch.setattr(fs_mod, 'PinnedProcess', _FakePinned)
        monkeypatch.setattr(fs_mod, 'force_owned', lambda owners, cb, phase: ([o for o in owners if (_FakePinned(o).stop(), True)][:] if True else []) and dummy.poll() is not None)
        launch.write_host_active(
            runtime,
            {
                'version': 2,
                'launch_id': 'b' * 32,
                'owner': dummy_id,
                'runner': dummy_id,
                'runner_id': host.identity,
                'runner_port': port,
                'local_state': 'READY',
                'manager_attached': False,
                'started_at': time.time(),
            },
        )
        launch.write_ssh_tunnel(
            runtime,
            {
                'version': 2,
                'transport': dummy_id,
                'dashboard_transport': None,
                'remote_runner_port': 8771,
                'remote_dashboard_port': None,
                'local_dashboard_port': None,
                'ssh_port': 22,
                'ssh_state': 'CONNECTED',
                'last_error_code': None,
                'connected_since': time.time(),
                'reconnect_attempts': 0,
            },
        )
        res = emergency.force_stop(home)
        assert res['state'] == 'FORCE_STOPPED'
        assert (runtime / 'force-stop.json').exists()
        assert dummy.poll() is not None
    finally:
        if dummy.poll() is None:
            dummy.kill()
            dummy.wait(timeout=3)


def test_ssh_supervisor_update_config_resumes_from_auth_error_and_manager_verify(tmp_path, monkeypatch):
    import subprocess
    from backend.gui_test.connector.ssh_tunnel import SshTunnelSupervisor
    from backend.gui_test.connector import supervisor as sup_mod

    fake_ssh = tmp_path / 'fake_ssh.py'
    fake_ssh.write_text(
        "import os, sys, time\n"
        "mode = os.environ.get('FAKE_SSH_MODE', 'ok')\n"
        "if mode == 'fatal_auth':\n"
        "    sys.stderr.write('Permission denied (publickey).\\n')\n"
        "    sys.stderr.flush()\n"
        "    sys.exit(255)\n"
        "sys.stderr.write('debug1: remote forward success for: listen 127.0.0.1:8771\\n')\n"
        "sys.stderr.flush()\n"
        "time.sleep(10)\n",
        encoding='utf-8',
    )

    state = {'mode': 'fatal_auth'}

    def spawn(argv, **kwargs):
        env = dict(os.environ, FAKE_SSH_MODE=state['mode'])
        return subprocess.Popen([sys.executable, str(fake_ssh)], **dict(kwargs, env=env))

    sup = SshTunnelSupervisor(
        tmp_path / 'rt',
        {'server': '127.0.0.1', 'account': 'bsp', 'ssh_port': 22},
        actual_local_runner_port=8772,
        remote_runner_port=8771,
        popen=spawn,
        preflight_fn=lambda *a, **kw: {'ok': True, 'code': None, 'fatal': False, 'warnings': [], 'ssh_path': 'ssh'},
        stability_window=0.05,
        bind_timeout=2.0,
    )
    sup.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and sup.snapshot()['ssh_state'] != 'AUTH_OR_CONFIG_ERROR':
            time.sleep(0.05)
        assert sup.snapshot()['ssh_state'] == 'AUTH_OR_CONFIG_ERROR'

        # Saving updated settings while in AUTH_OR_CONFIG_ERROR must wake and resume retries.
        state['mode'] = 'ok'
        sup.update_config({'server': '127.0.0.1', 'account': 'bsp-fixed', 'ssh_port': 22})
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and sup.snapshot()['ssh_state'] != 'CONNECTED':
            time.sleep(0.05)
        assert sup.snapshot()['ssh_state'] == 'CONNECTED'
    finally:
        sup.stop()

    # Manager.reconnect_ssh returns snapshot & Manager.verify_connection reads /linux-diagnostics when -L is CONNECTED.
    home = tmp_path / 'mgr_home'
    home.mkdir()
    (home / 'windows-runner.json').write_text(json.dumps({
        '_setup': {'server': '10.0.0.5', 'account': 'bsp', 'ssh_port': 22, 'remote_runner_port': 8771, 'remote_dashboard_port': 8766, 'dashboard_port': 18766},
        'boards': [],
    }), encoding='utf-8')
    mgr = sup_mod.Manager(home)
    try:
        class FakeSup:
            def reconnect(self): return None
            def snapshot(self):
                return {
                    'ssh_state': 'CONNECTED',
                    'tunnel': {'optional_dashboard_forward': 'CONNECTED', 'local_dashboard_port': 18766},
                    'ssh_diagnostic': {'code': 'CONNECTED'},
                }
        mgr.ssh_supervisor = FakeSup()
        monkeypatch.setattr(sup_mod, 'preflight_ssh', lambda *a, **k: {'ok': True, 'code': None, 'fatal': False, 'warnings': [], 'ssh_path': 'ssh'})
        rec_snap = mgr.reconnect_ssh()
        assert isinstance(rec_snap, dict) and rec_snap['ssh_state'] == 'CONNECTED'

        seen_urls = []
        seen_headers = []
        import httpx
        real_client = httpx.Client
        def mock_client(**kw):
            def handler(req):
                seen_urls.append(str(req.url))
                seen_headers.append(dict(req.headers))
                return httpx.Response(200, json={'listening': True, 'target_port': 8771})
            return real_client(transport=httpx.MockTransport(handler))
        monkeypatch.setattr(httpx, 'Client', mock_client)
        res = mgr.verify_connection(check_linux=True)
        assert res['linux_diagnostics'] == {'listening': True, 'target_port': 8771}
        assert any('/api/v1/gui-test/live/connector/direct/linux-diagnostics' in u for u in seen_urls)
        assert any(h.get('x-bsp-service') == 'plugin' for h in seen_headers)
    finally:
        mgr.close()


def test_emergency_force_stop_allows_manager_ssh_lock_when_transport_is_none_and_not_connected(tmp_path, monkeypatch):
    import subprocess
    import backend.gui_test.execution.force_stop as fs_mod

    for ssh_state in ('NOT_CONFIGURED', 'AUTH_OR_CONFIG_ERROR', 'RECONNECTING'):
        home = tmp_path / f'case_{ssh_state}'
        runtime = home / 'runtime'
        runtime.mkdir(parents=True, exist_ok=True)
        holder_script = home / 'hold_locks.py'
        ready_flag = runtime / 'locks_ready'
        holder_script.write_text(
            "import sys, time\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from backend.gui_test.execution.launch import LaunchLock\n"
            "rt = Path(sys.argv[2])\n"
            "with LaunchLock(rt / 'connector-manager.lock'), LaunchLock(rt / 'ssh-tunnel.lock'):\n"
            "    (rt / 'locks_ready').write_text('1', encoding='utf-8')\n"
            "    time.sleep(30)\n",
            encoding='utf-8',
        )
        repo_root = str(Path(__file__).resolve().parents[1])
        dummy = subprocess.Popen([sys.executable, '-B', str(holder_script), repo_root, str(runtime)])
        try:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not ready_flag.exists():
                time.sleep(0.05)
            assert ready_flag.exists()

            dummy_id = {'pid': dummy.pid, 'creation_time': 'mac-mgr-holder'}
            monkeypatch.setattr(launch, 'process_identity', lambda pid: dummy_id if pid == dummy.pid else None)
            monkeypatch.setattr(fs_mod, 'process_identity', lambda pid: dummy_id if pid == dummy.pid else None)

            class _FakePinned:
                def __init__(self, ident):
                    self.identity = ident
                def close(self):
                    pass
                def stop(self):
                    if dummy.poll() is None:
                        dummy.terminate()
                        dummy.wait(timeout=3)

            monkeypatch.setattr(fs_mod, 'PinnedProcess', _FakePinned)
            monkeypatch.setattr(
                fs_mod,
                'force_owned',
                lambda owners, cb, phase: [(_FakePinned(o).stop(), o)[1] for o in owners],
            )
            (runtime / 'connector-manager.json').write_text(
                json.dumps({'owner': dummy_id, 'port': 8773}),
                encoding='utf-8',
            )
            launch.write_ssh_tunnel(
                runtime,
                {
                    'version': 2,
                    'transport': None,
                    'dashboard_transport': None,
                    'remote_runner_port': 8771,
                    'remote_dashboard_port': None,
                    'local_dashboard_port': None,
                    'ssh_port': 22,
                    'ssh_state': ssh_state,
                    'last_error_code': 'SSH_AUTH_FAILED' if ssh_state == 'AUTH_OR_CONFIG_ERROR' else None,
                    'connected_since': None,
                    'reconnect_attempts': 1 if ssh_state == 'RECONNECTING' else 0,
                },
            )
            res = emergency.force_stop(home)
            assert res['state'] == 'FORCE_STOPPED'
            assert dummy.poll() is not None
        finally:
            if dummy.poll() is None:
                dummy.kill()
                dummy.wait(timeout=3)

    # Guard: ssh_state == 'CONNECTED' with transport=None must still block.
    blocked_home = tmp_path / 'case_connected_no_transport'
    blocked_rt = blocked_home / 'runtime'
    blocked_rt.mkdir(parents=True, exist_ok=True)
    with launch.LaunchLock(blocked_rt / 'ssh-tunnel.lock'):
        mgr_id = {'pid': os.getpid(), 'creation_time': 'mac-self'}
        monkeypatch.setattr(launch, 'process_identity', lambda pid: mgr_id if pid == os.getpid() else None)
        (blocked_rt / 'connector-manager.json').write_text(json.dumps({'owner': mgr_id, 'port': 8773}), encoding='utf-8')
        launch.write_ssh_tunnel(
            blocked_rt,
            {
                'version': 2,
                'transport': None,
                'dashboard_transport': None,
                'remote_runner_port': 8771,
                'remote_dashboard_port': None,
                'local_dashboard_port': None,
                'ssh_port': 22,
                'ssh_state': 'CONNECTED',
                'last_error_code': None,
                'connected_since': time.time(),
                'reconnect_attempts': 0,
            },
        )
        with pytest.raises(RuntimeError, match='FORCE_STOP_BLOCKED'):
            emergency.force_stop(blocked_home)


def test_manager_restart_host_fallback_port_updates_ssh_supervisor_config(tmp_path):
    home = tmp_path / 'mgr_fallback'
    home.mkdir()
    (home / 'windows-runner.json').write_text(json.dumps({
        '_setup': {
            'server': '10.0.0.5',
            'account': 'bsp',
            'ssh_port': 22,
            'remote_runner_port': 8771,
            'remote_dashboard_port': 8766,
            'dashboard_port': 18766,
        },
        'boards': [],
    }), encoding='utf-8')
    mgr = Manager(home)
    try:
        mgr.local_runner_port = 8772
        calls = []

        class _FakeSshSup:
            actual_local_runner_port = 8772

            def update_config(self, setup_cfg, **kwargs):
                calls.append((setup_cfg, kwargs))
                self.actual_local_runner_port = kwargs['actual_local_runner_port']

            def snapshot(self):
                return {'ssh_state': 'CONNECTED', 'tunnel': {}}

        mgr.ssh_supervisor = _FakeSshSup()
        mgr._stop_host_only = lambda: None
        mgr._send_bridge_heartbeat = lambda: None

        def fake_spawn(port, *, allow_fallback=True):
            if not allow_fallback:
                raise TestError('port busy', 'HOST_START_FAILED', 500)
            mgr.local_runner_port = 18772
            return {'runner_port': 18772, 'runner_id': 'a' * 32, 'runner_url': 'http://127.0.0.1:18772'}

        mgr._spawn_host_process = fake_spawn
        res = mgr.restart_host()
        assert res['restarted'] is True
        assert res['runner_port'] == 18772
        assert len(calls) == 1
        assert calls[0][1]['actual_local_runner_port'] == 18772
        assert calls[0][1]['remote_runner_port'] == 8771
        assert calls[0][1]['remote_dashboard_port'] == 8766
        assert calls[0][1]['local_dashboard_port'] == 18766
    finally:
        mgr.close()
