"""Unit 1 tests: shared-settings.db, recovery.py, bootstrap-v2, and Linux diagnostics."""
import importlib.util
import json
import os
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from backend.gui_test.connector.bootstrap import bootstrap_profile, import_profile
from backend.gui_test.core.connector_bootstrap import (
    FORMAT as FORMAT_V1,
    FORMAT_V2,
    build_bootstrap_v2,
    load_profile,
    service_headers,
    verify_service,
    write_profile,
)
from backend.gui_test.core.connector_diagnostics import (
    audit_linux_ssh_prereqs,
    diagnose_connector_endpoint,
    linux_local_diagnostics,
    scan_loopback_listeners,
)
from backend.gui_test.core.models import TestError
from backend.gui_test.core.shared_settings_store import SharedSettingsStore, resolve_runtime_dir
from backend.gui_test.core.store import Store
from backend.gui_test.runtime import make_manager

ROOT = Path(__file__).resolve().parents[1]


def _load_recovery():
    path = ROOT / 'apps' / 'agent-monitor' / 'recovery.py'
    spec = importlib.util.spec_from_file_location('agent_monitor_recovery_u1', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_runtime_dir_precedence(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    assert resolve_runtime_dir(home=home) == (home / 'runtime').resolve()
    custom = tmp_path / 'custom-runtime'
    (home / 'runtime-location.json').write_text(json.dumps({'path': str(custom)}))
    assert resolve_runtime_dir(home=home) == custom.resolve()
    explicit = tmp_path / 'explicit-runtime'
    assert resolve_runtime_dir(home=home, runtime=explicit) == explicit.resolve()


def test_shared_settings_store_migration_and_cas_and_tofu(tmp_path):
    runtime = tmp_path / 'rt'
    old_db = Store(runtime / 'gui-test-dashboard-windows' / 'runs.db')
    tc_root = tmp_path / 'tc'
    tc_root.mkdir()
    with old_db.transaction() as c:
        c.execute("INSERT INTO documents VALUES('shared-settings','current',?)",
                  (json.dumps({'source_roots': [str(tc_root)], 'tc_root': str(tc_root)}),))
        c.execute("INSERT INTO documents VALUES('execution-timeouts','current',?)",
                  (json.dumps({'default_seconds': 45, 'source_revision': '', 'overrides': {}}),))
    (runtime / 'gui-test.json').write_text(json.dumps({'runner': 'windows-http', 'url': 'http://127.0.0.1:8788'}))

    store = SharedSettingsStore(runtime)
    with sqlite3.connect(store.path) as c:
        assert c.execute('PRAGMA journal_mode').fetchone()[0].lower() == 'delete'
    cur = store.read()
    assert cur['integration']['tc_root'] == str(tc_root)
    assert cur['timeouts']['default_seconds'] == 45
    prefs = store.read_preferences()
    assert prefs['preferred_connector_port'] == 8788
    assert prefs['expected_runner_id'] is None

    # CAS mismatch raises 409
    updated = store.save({
        'expected_revision': cur['revision'],
        'integration': {**cur['integration'], 'installer_roots': [str(tmp_path)]},
        'timeouts': {'default_seconds': 90, 'source_revision': '', 'overrides': {}},
    })
    assert updated['timeouts']['default_seconds'] == 90
    with pytest.raises(TestError) as err:
        store.save({
            'expected_revision': cur['revision'],
            'integration': cur['integration'],
            'timeouts': {'default_seconds': 30, 'source_revision': '', 'overrides': {}},
        })
    assert err.value.status == 409

    # TOFU pinning & rebind
    rid1 = '1' * 32
    rid2 = '2' * 32
    pinned = store.pin_runner_if_unset(rid1)
    assert pinned['pinned'] == 'tofu' and pinned['expected_runner_id'] == rid1
    assert store.pin_runner_if_unset(rid1)['pinned'] == 'matched'
    with pytest.raises(TestError) as rerr:
        store.pin_runner_if_unset(rid2)
    assert rerr.value.code == 'RUNNER_CHANGED'
    store.rebind_runner(rid2)
    assert store.read_preferences()['expected_runner_id'] == rid2


def test_shared_settings_store_multiprocess_flock_cas(tmp_path):
    runtime = tmp_path / 'rt'
    store = SharedSettingsStore(runtime)
    code = (
        "import sys\n"
        "from backend.gui_test.core.shared_settings_store import SharedSettingsStore\n"
        "from backend.gui_test.core.models import TestError\n"
        "s = SharedSettingsStore(sys.argv[1])\n"
        "cur = s.read()\n"
        "try:\n"
        "    s.save({'expected_revision': cur['revision'], 'integration': cur['integration'], "
        "'timeouts': {'default_seconds': int(sys.argv[2]), 'source_revision': '', 'overrides': {}}})\n"
        "    print('OK')\n"
        "except TestError as e:\n"
        "    print(e.code)\n"
    )
    p1 = subprocess.Popen([sys.executable, '-c', code, str(runtime), '111'], cwd=ROOT, stdout=subprocess.PIPE, text=True)
    p2 = subprocess.Popen([sys.executable, '-c', code, str(runtime), '222'], cwd=ROOT, stdout=subprocess.PIPE, text=True)
    out1 = p1.communicate(timeout=15)[0].strip()
    out2 = p2.communicate(timeout=15)[0].strip()
    assert p1.returncode == 0 and p2.returncode == 0
    assert {out1, out2} == {'OK', 'SETTINGS_CHANGED'} or {out1, out2} == {'OK'}


def test_recovery_preserves_shared_settings_db_on_reset(tmp_path):
    recovery = _load_recovery()
    runtime = tmp_path / 'rt'
    manager = make_manager(runtime, 'integration')
    cur = manager.shared_settings.read()
    root_dir = tmp_path / 'tc_src'
    root_dir.mkdir()
    saved = manager.shared_settings.save({
        'expected_revision': cur['revision'],
        'integration': {**cur['integration'], 'source_roots': [str(root_dir)], 'tc_root': str(root_dir)},
        'timeouts': {'default_seconds': 321, 'source_revision': '', 'overrides': {}},
    })
    assert saved['timeouts']['default_seconds'] == 321

    report = recovery.inspect(runtime)
    assert report['compatible'] is True
    assert report['adoptable'] is True
    assert any(d['path'] == 'shared-settings.db' and d['schema_version'] == '1' for d in report['databases'])

    plan = recovery.reset_plan(runtime)
    recovery.clear_runtime_records(runtime, plan)
    reopened = SharedSettingsStore(runtime).read()
    assert reopened['integration']['tc_root'] == str(root_dir)
    assert reopened['timeouts']['default_seconds'] == 321


def test_bootstrap_v2_export_import_and_v1_compat(tmp_path):
    v2 = build_bootstrap_v2(server='linux-build.internal', account='bspdev', ssh_port=2222,
                            remote_runner_port=8771, remote_dashboard_port=None, expected_runner_id=None)
    assert v2['format'] == FORMAT_V2
    assert v2['endpoint']['remote_dashboard_port'] is None
    path = tmp_path / 'bootstrap-v2.json'
    write_profile(path, v2)
    loaded = load_profile(path)
    assert loaded.format == FORMAT_V2
    assert service_headers(v2) == {'X-Bsp-Service': 'plugin'}
    verify_service(v2, {'status': 'ok'})

    # Reject loopback / symlink / duplicate keys / oversized
    bad = tmp_path / 'bad.json'
    bad.write_text('{"format": "gui-test-connector-bootstrap-v2", "format": "gui-test-connector-bootstrap-v2"}')
    with pytest.raises(ValueError, match='Duplicate'):
        load_profile(bad)
    with pytest.raises(ValueError):
        build_bootstrap_v2(server='127.0.0.1', account='bspdev')
    link = tmp_path / 'link.json'
    link.symlink_to(path)
    with pytest.raises(ValueError, match='symbolic links'):
        load_profile(link)

    # Import v2 into Windows home without Agent Monitor identity
    win_home = tmp_path / 'win'
    receipt = import_profile(win_home, path)
    assert receipt['state'] == 'IMPORTED'
    assert receipt['format'] == FORMAT_V2
    assert bootstrap_profile(win_home, path)['state'] == 'REUSED'

    # Active connector_runs in executions.db blocks import
    rt = win_home / 'runtime'
    rt.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(rt / 'executions.db') as c:
        c.execute('CREATE TABLE IF NOT EXISTS jobs(data TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS batches(data TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS connector_runs(run_id TEXT PRIMARY KEY, state TEXT, analysis_latched INTEGER)')
        c.execute("INSERT INTO connector_runs VALUES('run1', 'RUNNING', 0)")
    with pytest.raises(TestError) as err:
        import_profile(win_home, path)
    assert err.value.code == 'CONNECTOR_BUSY'

    # v1 still works
    v1_path = tmp_path / 'v1.json'
    v1 = {'format': FORMAT_V1, 'endpoint': {'server': 'linux.example', 'account': 'user', 'ssh_port': 22, 'remote_dashboard_port': 8766},
          'identity': {'runtime_id': 'rt1', 'package_version': '0.1.0'}}
    v1_path.write_text(json.dumps(v1))
    assert service_headers(v1)['X-Bsp-Runtime-Id'] == 'rt1'
    win_home_v1 = tmp_path / 'win_v1'
    res_v1 = import_profile(win_home_v1, v1_path)
    assert res_v1['identity']['runtime_id'] == 'rt1'


def test_linux_diagnostics_proc_ipv4_ipv6_uid0_and_ssh_audit(tmp_path, monkeypatch):
    proc = tmp_path / 'proc'
    (proc / 'net').mkdir(parents=True)
    port_8771 = f'{8771:04X}'
    port_8781 = f'{8781:04X}'
    # 1) uid=0 root listener on 8771 (IPv6 ::1), plus uid=1000 sshd on 8781 (IPv4 127.0.0.1)
    (proc / 'net' / 'tcp').write_text(
        '  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n'
        f'   0: 0100007F:{port_8781} 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 2002 1 0 100 0 0 10 -1\n'
    )
    (proc / 'net' / 'tcp6').write_text(
        '  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n'
        f'   0: 00000000000000000000000001000000:{port_8771} 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1001 1 0 100 0 0 10 -1\n'
    )
    # pid 10 (root) raises PermissionError on fd, pid 20 (user 1000) is sshd owning inode 2002
    (proc / '10' / 'fd').mkdir(parents=True)
    (proc / '20' / 'fd').mkdir(parents=True)
    (proc / '20' / 'comm').write_text('sshd\n')
    (proc / '20' / 'cmdline').write_bytes(b'sshd: bsp@notty\x00')
    (proc / '20' / 'fd' / '3').symlink_to('socket:[2002]')

    real_iterdir = Path.iterdir
    def guarded_iterdir(self):
        if self == proc / '10' / 'fd':
            raise PermissionError('root fd denied')
        return real_iterdir(self)
    monkeypatch.setattr(Path, 'iterdir', guarded_iterdir)

    scan = scan_loopback_listeners(8771, proc_root=proc, current_uid=1000)
    assert scan['listening'] is True
    assert scan['listener']['listener_owner_uid'] == 0
    assert scan['listener']['pid'] is None
    assert scan['listener']['comm'] == 'privileged_or_root_listener'
    assert scan['suspected_port_mismatch_ports'] == [8781]

    # SSH audit
    home = tmp_path / 'userhome'
    ssh = home / '.ssh'
    ssh.mkdir(parents=True)
    ssh.chmod(0o755)
    ak = ssh / 'authorized_keys'
    ak.write_text('ssh-ed25519 AAAA\n')
    ak.chmod(0o664)
    sshd_cfg = tmp_path / 'sshd_config'
    sshd_cfg.write_text('AllowTcpForwarding no\nPermitListen 8771\n')
    warnings = audit_linux_ssh_prereqs(home_dir=home, sshd_config_path=sshd_cfg)
    codes = {w['code'] for w in warnings}
    assert {'SSH_DIR_PERMISSIONS_TOO_OPEN', 'AUTHORIZED_KEYS_PERMISSIONS_TOO_OPEN',
            'SSHD_ALLOW_TCP_FORWARDING_NO', 'SSHD_PERMIT_LISTEN_RESTRICTED'} <= codes


def test_mutual_diagnostics_classifications(tmp_path):
    proc = tmp_path / 'proc'
    (proc / 'net').mkdir(parents=True)
    (proc / 'net' / 'tcp').write_text('sl local_address rem_address st tx rx tr tm retrnsmt uid timeout inode\n')
    (proc / 'net' / 'tcp6').write_text('')

    # 1) ECONNREFUSED -> CONNECTOR_TUNNEL_NOT_LISTENING
    def handler_refused(request):
        raise httpx.ConnectError('connection refused', request=request)
    rep1 = diagnose_connector_endpoint(
        8771, proc_root=proc, home_dir=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler_refused)),
    )
    assert rep1['code'] == 'CONNECTOR_TUNNEL_NOT_LISTENING'
    assert rep1['windows_checklist']

    # 2) Timeout / EOF -> STALE_SSH_TUNNEL
    def handler_stale(request):
        raise httpx.RemoteProtocolError('peer closed connection without sending complete message', request=request)
    rep2 = diagnose_connector_endpoint(
        8771, proc_root=proc, home_dir=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler_stale)),
    )
    assert rep2['code'] == 'STALE_SSH_TUNNEL'

    # 3) Other service (agent-monitor) on port 8771 -> PORT_OCCUPIED_BY_OTHER_SERVICE
    def handler_other(request):
        if request.url.path == '/v1/identity':
            return httpx.Response(404, json={'detail': 'Not Found'})
        if request.url.path == '/api/v1/health':
            return httpx.Response(200, json={'status': 'ok', 'managed_runtime': '/x'})
        return httpx.Response(404)
    rep3 = diagnose_connector_endpoint(
        8771, proc_root=proc, home_dir=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler_other)),
    )
    assert rep3['code'] == 'PORT_OCCUPIED_BY_OTHER_SERVICE'
    assert rep3['service_signature'] == 'agent-monitor'

    # 4) runner_id mismatch -> notifies peer/hello(MISMATCH)
    hellos = []
    def handler_mismatch(request):
        if request.url.path == '/v1/identity':
            return httpx.Response(200, json={'runner_id': 'b' * 32, 'capabilities': ['direct-connector-v1']})
        if request.url.path == '/v1/peer/hello':
            hellos.append(json.loads(request.content))
            return httpx.Response(200, json={'runner_id': 'b' * 32, 'overall_connection_state': 'CONNECTED'})
        if request.url.path == '/v1/diagnostics/connection':
            return httpx.Response(200, json={'overall_connection_state': 'CONNECTED', 'readiness': {'execution_ready': True}})
        return httpx.Response(404)
    rep4 = diagnose_connector_endpoint(
        8771, expected_runner_id='a' * 32, proc_root=proc, home_dir=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler_mismatch)),
    )
    assert rep4['code'] == 'RUNNER_CHANGED'
    assert rep4['peer_notified'] is True
    assert hellos and hellos[0]['client_status'] == 'MISMATCH'
    assert hellos[0]['client_issue']['code'] == 'RUNNER_CHANGED'

    # 5) Connected with hw warnings -> READY_WITH_HW_WARNINGS
    hellos.clear()
    def handler_ok_warn(request):
        if request.url.path == '/v1/identity':
            return httpx.Response(200, json={'runner_id': 'a' * 32, 'capabilities': ['direct-connector-v1']})
        if request.url.path == '/v1/peer/hello':
            hellos.append(json.loads(request.content))
            return httpx.Response(200, json={'runner_id': 'a' * 32, 'overall_connection_state': 'CONNECTED'})
        if request.url.path == '/v1/diagnostics/connection':
            return httpx.Response(200, json={'overall_connection_state': 'CONNECTED', 'readiness': {'execution_ready': False}})
        return httpx.Response(404)
    rep5 = diagnose_connector_endpoint(
        8771, expected_runner_id='a' * 32, proc_root=proc, home_dir=tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(handler_ok_warn)),
    )
    assert rep5['connected'] is True
    assert rep5['code'] == 'READY_WITH_HW_WARNINGS'
    assert hellos[0]['client_status'] == 'OK'
