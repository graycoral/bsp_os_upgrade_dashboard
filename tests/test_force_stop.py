"""Explicit emergency commands: fake OS process objects only, never live services."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from backend.gui_test.execution import force_stop as force
from backend.gui_test.connector import emergency
from scripts import board_connector as boot

ROOT = Path(__file__).resolve().parents[1]


def identity(pid, created='100'):
    return {'pid': pid, 'creation_time': created}


@pytest.fixture
def processes(monkeypatch):
    live = {900001: identity(900001), 900002: identity(900002, '101')}
    parents = {900002: 900001}
    events, handles = [], []
    monkeypatch.setattr(emergency, 'discover_windows_processes', lambda home: {})
    monkeypatch.setattr(force, 'WINDOWS', True)
    monkeypatch.setattr(force, '_process_parents', lambda: dict(parents))
    monkeypatch.setattr(force, '_created_before', lambda a, b: int(a['creation_time']) <= int(b['creation_time']))
    monkeypatch.setattr(force, 'process_identity', lambda pid: live.get(pid))

    class Handle:
        def __init__(self, value):
            self.identity = value
            handles.append(self)
            events.append(('pin', value['pid']))

        def pause(self): events.append(('pause', self.identity['pid']))
        def alive(self): return live.get(self.identity['pid']) == self.identity
        def kill(self):
            events.append(('kill', self.identity['pid']))
            live.pop(self.identity['pid'], None)
        def close(self): events.append(('close', self.identity['pid']))

    monkeypatch.setattr(force, 'PinnedProcess', Handle)
    return SimpleNamespace(live=live, parents=parents, events=events, handles=handles, Handle=Handle)


def test_generation_pins_cover_post_kill_windows_child_and_keep_handles_open(processes, monkeypatch):
    original = processes.Handle.kill
    def kill(handle):
        if handle.identity['pid'] == 900001:
            # Born after the initial snapshot, just before the parent's exact
            # process object exits. Windows retains the original PPID.
            processes.live[900003] = identity(900003, '102')
            processes.parents[900003] = 900001
        original(handle)
    monkeypatch.setattr(processes.Handle, 'kill', kill)
    checkpoints = []
    result = force.force_owned([identity(900001)], lambda values: checkpoints.append(list(values)))
    assert {v['pid'] for v in result} == {900001, 900002, 900003}
    assert not processes.live
    first_close = next(i for i, e in enumerate(processes.events) if e[0] == 'close')
    assert all(e[0] != 'kill' for e in processes.events[first_close:])
    assert {v['pid'] for v in checkpoints[-1]} == {900001, 900002, 900003}


def test_recycled_owner_pid_and_older_orphan_are_never_killed(processes):
    processes.live[900004] = identity(900004, '50')
    processes.parents[900004] = 900001
    result = force.force_owned([identity(900001), identity(900005, 'old')], lambda _: None)
    assert {v['pid'] for v in result} == {900001, 900002}
    assert processes.live == {900004: identity(900004, '50')}
    processes.live[900006] = identity(900006, '999')
    assert force.force_owned([identity(900006, '1')], lambda _: None) == []
    assert processes.live[900006] == identity(900006, '999')


def test_checkpoint_failure_releases_all_pins_before_any_kill(processes):
    def fail(_): raise OSError('receipt disk full')
    with pytest.raises(OSError, match='disk full'):
        force.force_owned([identity(900001)], fail)
    assert not any(e[0] == 'kill' for e in processes.events)
    assert sum(e[0] == 'close' for e in processes.events) == len(processes.handles)


def test_partial_kill_persists_pending_targets_and_retry_checks_generations(processes, tmp_path, monkeypatch):
    original = processes.Handle.kill
    def fail_child(handle):
        if handle.identity['pid'] == 900002: raise PermissionError('fixture denied')
        original(handle)
    monkeypatch.setattr(processes.Handle, 'kill', fail_child)
    path = tmp_path / 'force-stop.json'
    with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING'):
        force.stop_recorded(path, [identity(900001)])
    saved = json.loads(path.read_text())
    assert saved['state'] == 'FORCE_STOP_PENDING'
    assert {v['pid'] for v in saved['targets']} == {900001, 900002}
    with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING'):
        force.require_force_complete(path)
    monkeypatch.setattr(processes.Handle, 'kill', original)
    result = force.stop_recorded(path, [])
    assert result['state'] == 'FORCE_STOPPED'
    assert not processes.live and result['execution_state'] == 'UNKNOWN'
    force.require_force_complete(path)


def test_refuses_caller_ancestor_before_opening_any_handle(processes, monkeypatch):
    monkeypatch.setattr(force.os, 'getpid', lambda: 900001)
    with pytest.raises(ValueError, match='상위'):
        force.force_owned([identity(900001)], lambda _: None)
    assert not processes.handles


def test_reused_child_from_discovery_snapshot_is_rechecked_after_pin(processes, monkeypatch):
    calls = 0
    def parents():
        nonlocal calls
        calls += 1
        if calls <= 2:
            return {900002: 900001}
        # By the time the child is pinned it belongs to an unrelated parent.
        return {900002: 800000}
    monkeypatch.setattr(force, '_process_parents', parents)
    force.force_owned([identity(900001)], lambda _: None)
    assert processes.live == {900002: identity(900002, '101')}
    assert ('kill', 900002) not in processes.events


def test_post_exit_discovery_failure_saves_late_child_and_never_claims_complete(processes, tmp_path, monkeypatch):
    original = processes.Handle.kill
    def kill(handle):
        if handle.identity['pid'] == 900001:
            for pid in (900003, 900004):
                processes.live[pid] = identity(pid, '102')
                processes.parents[pid] = 900001
        original(handle)
    monkeypatch.setattr(processes.Handle, 'kill', kill)
    def inspect(pid):
        if pid == 900004: raise PermissionError('post-exit discovery denied')
        return processes.live.get(pid)
    monkeypatch.setattr(force, 'process_identity', inspect)
    path = tmp_path / 'force-stop.json'
    with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING'):
        force.stop_recorded(path, [identity(900001)])
    saved = json.loads(path.read_text())
    assert identity(900003, '102') in saved['targets']
    assert saved['tree_unverified'] is True
    monkeypatch.setattr(force, 'process_identity', lambda pid: processes.live.get(pid))
    with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING'):
        force.stop_recorded(path, [])
    assert 900003 not in processes.live
    assert 900004 in processes.live
    assert json.loads(path.read_text())['state'] == 'FORCE_STOP_PENDING'


def test_interruption_after_kill_keeps_durable_scan_phase_before_any_termination(processes, tmp_path, monkeypatch):
    path = tmp_path / 'force-stop.json'
    original = processes.Handle.kill
    def interrupt(handle):
        saved = json.loads(path.read_text())
        assert saved['post_exit_scan_pending'] == handle.identity
        assert saved['termination_started'] is True
        processes.live[900003] = identity(900003, '102')
        processes.parents[900003] = 900001
        original(handle)
        raise KeyboardInterrupt('command interrupted before final child scan')
    monkeypatch.setattr(processes.Handle, 'kill', interrupt)
    with pytest.raises(KeyboardInterrupt):
        force.stop_recorded(path, [identity(900001)])
    assert json.loads(path.read_text())['post_exit_scan_pending'] == identity(900001)
    monkeypatch.setattr(processes.Handle, 'kill', original)
    with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING'):
        force.stop_recorded(path, [])
    assert 900003 in processes.live
    assert json.loads(path.read_text())['tree_unverified'] is True


def test_linux_failed_attempt_resumes_paused_object_and_kill_uses_pidfd(monkeypatch):
    monkeypatch.setattr(force, 'WINDOWS', False)
    # Linux signals are synthetic in this test, including on Windows CI.
    for name, number in [('SIGKILL', 9), ('SIGCONT', 18)]:
        monkeypatch.setattr(force.signal, name, number, raising=False)
    calls = []
    monkeypatch.setattr(force.signal, 'pidfd_send_signal', lambda fd, number: calls.append((fd, number)), raising=False)
    monkeypatch.setattr(force.os, 'close', lambda fd: calls.append(('close', fd)))
    handle = object.__new__(force.PinnedProcess)
    handle.handle = 101; handle.paused = True
    monkeypatch.setattr(handle, 'alive', lambda: True)
    handle.kill()
    handle.close()
    assert calls == [(101, force.signal.SIGKILL), (101, force.signal.SIGCONT), ('close', 101)]


def test_cli_launch_holds_same_emergency_barrier_until_children_are_recorded(tmp_path, monkeypatch):
    from scripts import setup_runtime as setup
    from backend.gui_test.execution.launch import LaunchLock
    w = setup.Wizard(root=tmp_path / 'source', windows=True, home=tmp_path / 'home')
    w.python.parent.mkdir(parents=True, exist_ok=True); w.python.touch()
    setup.save_json(w.config, {'_setup': {'server': 'fixture.invalid', 'account': 'fixture'}})
    monkeypatch.setattr(w, 'environment', lambda: {})
    def start(_):
        with pytest.raises(RuntimeError):
            with LaunchLock(w.runtime / 'connector-start.lock'):
                pytest.fail('emergency command overlapped an unrecorded CLI launch')
    monkeypatch.setattr(w, '_windows_start', start)
    w.start()


def test_linux_tree_pauses_all_discovered_children_before_first_kill(processes, monkeypatch):
    monkeypatch.setattr(force, 'WINDOWS', False)
    force.force_owned([identity(900001)], lambda _: None)
    first_kill = next(i for i, e in enumerate(processes.events) if e[0] == 'kill')
    assert {pid for event, pid in processes.events[:first_kill] if event == 'pause'} == {900001, 900002}


def test_orphan_ssh_is_stopped_using_saved_generation_without_manager(processes, tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'; runtime.mkdir()
    (runtime / 'connector-manager.json').write_text(json.dumps({'owner': identity(900010)}))
    (runtime / 'active-endpoints.json').write_text(json.dumps({
        'owner': identity(900010), 'runner': identity(900001),
        'transport': identity(900002, '101'), 'phase': 'ssh_running'}))
    (tmp_path / 'windows-runner.json').write_text('{"boards":[]}')
    db = runtime / 'executions.db'; db.write_bytes(b'preserve unknown evidence')
    result = emergency.force_stop(tmp_path)
    assert result['state'] == 'FORCE_STOPPED'
    assert not processes.live and db.read_bytes() == b'preserve unknown evidence'
    assert (tmp_path / 'windows-runner.json').read_text() == '{"boards":[]}'


def test_stale_legacy_ssh_receipt_does_not_block_owned_host_stop(processes, tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'active-endpoints.json').write_text(json.dumps({
        'owner': identity(900010), 'phase': 'ssh_running'}))
    (runtime / 'host-active.json').write_text(json.dumps({'runner': identity(900001)}))
    other = identity(900009, '300')
    processes.live[other['pid']] = other
    from backend.gui_test.execution import launch
    monkeypatch.setattr(launch, '_windows_process_snapshot', lambda: {other['pid']: (900008, 'ssh.exe')})
    monkeypatch.setattr(launch, 'process_identity', processes.live.get)
    assert emergency.force_stop(tmp_path)['state'] == 'FORCE_STOPPED'
    assert processes.live == {other['pid']: other}
    assert emergency.force_stop(tmp_path)['state'] == 'FORCE_STOPPED'


def test_uncertain_legacy_ssh_is_preserved_but_known_host_is_stopped(processes, tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'active-endpoints.json').write_text(json.dumps({
        'owner': identity(900010), 'phase': 'ssh_running'}))
    (runtime / 'host-active.json').write_text(json.dumps({'runner': identity(900001)}))
    from backend.gui_test.execution import launch
    candidate = identity(900009, '105')
    processes.live[candidate['pid']] = candidate
    table = {candidate['pid']: (900010, 'ssh.exe')}
    monkeypatch.setattr(launch, '_windows_process_snapshot', lambda: table.copy())
    monkeypatch.setattr(launch, 'process_identity', processes.live.get)
    for _ in range(2):
        with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING.*SSH'):
            emergency.force_stop(tmp_path)
        assert json.loads((runtime / 'force-stop.json').read_text())['state'] == 'FORCE_STOP_PENDING'
        assert processes.live == {candidate['pid']: candidate}
    table.clear()
    assert emergency.force_stop(tmp_path)['state'] == 'FORCE_STOPPED'


def test_legacy_receipt_skips_ssh_of_reused_parent_pid(processes, tmp_path, monkeypatch):
    from backend.gui_test.execution import launch
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'active-endpoints.json').write_text(json.dumps({
        'owner': identity(900010), 'phase': 'ssh_starting'}))
    processes.live.update({900010: identity(900010, '200'), 900011: identity(900011, '210')})
    monkeypatch.setattr(launch, '_windows_process_snapshot', lambda: {900011: (900010, 'SSH.EXE')})
    monkeypatch.setattr(launch, 'process_identity', processes.live.get)
    assert emergency.force_stop(tmp_path)['state'] == 'FORCE_STOPPED'
    assert not processes.handles


@pytest.mark.skipif(os.name != 'nt', reason='Windows Toolhelp snapshot')
def test_windows_snapshot_reports_this_process_and_parent():
    from backend.gui_test.execution import launch
    parent, image = launch._windows_process_snapshot()[os.getpid()]
    assert parent == os.getppid()
    assert image.lower().endswith('.exe')


def test_legacy_inspection_failure_stays_pending_until_complete_scan(processes, tmp_path, monkeypatch):
    from backend.gui_test.execution import launch
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'active-endpoints.json').write_text(json.dumps({
        'owner': identity(900010), 'phase': 'ssh_running'}))
    def denied():
        raise PermissionError('mock discovery failure')
    monkeypatch.setattr(launch, '_windows_process_snapshot', denied)
    monkeypatch.setattr(launch, 'process_identity', processes.live.get)
    with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING.*SSH'):
        emergency.force_stop(tmp_path)
    with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING'):
        force.require_force_complete(runtime / 'force-stop.json')
    monkeypatch.setattr(launch, '_windows_process_snapshot', lambda: {})
    assert emergency.force_stop(tmp_path)['state'] == 'FORCE_STOPPED'
    force.require_force_complete(runtime / 'force-stop.json')


def test_connector_force_command_dispatches_without_install_or_gui(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(boot, 'os', SimpleNamespace(name='nt'))
    for name in ('prepare', 'prepare_public_tools', 'browser_files'):
        monkeypatch.setattr(boot, name, lambda *a, **k: pytest.fail('force stop installed or opened GUI'))
    homes = []
    monkeypatch.setattr(emergency, 'force_stop', lambda home: homes.append(home) or {'state': 'FORCE_STOPPED'})
    assert boot.main(['--force-stop', '--home', str(tmp_path)]) == 0
    assert homes == [tmp_path]
    assert json.loads(capsys.readouterr().out)['state'] == 'FORCE_STOPPED'
    with pytest.raises(SystemExit):
        boot.main(['--force-stop', '--import-profile', 'private.json'])
    with pytest.raises(SystemExit):
        boot.main(['--force-stop', '--server-port', '8765'])


def test_delivered_script_stops_active_host_and_children_offline(tmp_path, processes, monkeypatch, capsys):
    script = tmp_path / 'stop-board-connector.py'
    shutil.copyfile(ROOT / 'deliveries' / 'connector-recovery' / script.name, script)
    spec = importlib.util.spec_from_file_location('standalone_recovery', script)
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)
    monkeypatch.setattr(recovery, 'WINDOWS', True)
    monkeypatch.setattr(recovery, '_process_parents', lambda: dict(processes.parents))
    monkeypatch.setattr(recovery, '_created_before', force._created_before)
    monkeypatch.setattr(recovery, 'process_identity', processes.live.get)
    monkeypatch.setattr(recovery, 'PinnedProcess', processes.Handle)
    home = tmp_path / 'profile'
    runtime = home / 'runtime'
    runtime.mkdir(parents=True)
    (runtime / 'host-active.json').write_text(json.dumps({'runner': identity(900001)}))
    foreign = identity(900009)
    processes.live[foreign['pid']] = foreign
    monkeypatch.setattr(sys, 'argv', [str(script), '--home', str(home)])

    assert recovery.main() == 0
    assert 'FORCE_STOPPED' in capsys.readouterr().out
    assert processes.live == {foreign['pid']: foreign}
    marker = json.loads((runtime / 'force-stop.json').read_text())
    assert {entry['pid'] for entry in marker['targets']} == {900001, 900002}
    assert marker['execution_state'] == 'UNKNOWN'


def test_active_receipt_accepts_optional_ssh_generation_without_relaxing_v1_schema():
    from backend.gui_test.execution.launch import _startup
    value = {'version': 1, 'launch_id': 'a' * 32, 'runner_id': 'b' * 32,
             'owner': identity(900001), 'runner': identity(900002), 'runner_port': 8771,
             'dashboard_port': 8766, 'remote_runner_port': 8771, 'remote_dashboard_port': 8766,
             'ssh_port': 22, 'phase': 'ssh_running', 'runner_url': 'http://127.0.0.1:8771',
             'dashboard_url': 'http://127.0.0.1:8766'}
    assert _startup(dict(value), active=True) == value
    assert _startup(value | {'transport': identity(900003)}, active=True)['transport'] == identity(900003)
    for extra in ({'transport': {'pid': 900003}}, {'unexpected': True}):
        with pytest.raises(ValueError):
            _startup(value | extra, active=True)


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'apps/agent-monitor'))
    spec = importlib.util.spec_from_file_location('force_monitor_tests', ROOT / 'apps/agent-monitor/manage.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    # Test Linux manager logic with the same exclusive-lock semantics on every
    # test host; the real Agent Monitor service remains POSIX-only.
    from backend.gui_test.execution.launch import LaunchLock
    monkeypatch.setattr(module, 'lock', LaunchLock)
    return module


def test_monitor_force_uses_receipts_preserves_db_and_bypasses_safe_stop(processes, monitor, tmp_path, monkeypatch):
    monitor.atomic(tmp_path / 'service.json', {'owner': identity(900001), 'children': {'worker': identity(900002, '101')}})
    monkeypatch.setattr(monitor, 'has_work', lambda _: pytest.fail('emergency command used normal-stop gate'))
    db = tmp_path / 'dashboard.db'; db.write_bytes(b'reserved and UNKNOWN remain')
    assert monitor.force_stop(tmp_path)['state'] == 'FORCE_STOPPED'
    assert not processes.live and db.read_bytes() == b'reserved and UNKNOWN remain'


def test_monitor_old_live_receipt_never_guesses_process_from_port(processes, monitor, tmp_path, monkeypatch):
    monitor.atomic(tmp_path / 'service.json', {'instance': 'old'})
    monkeypatch.setattr(monitor, 'active', lambda _: True)
    with pytest.raises(RuntimeError, match='OS 소유권'):
        monitor.force_stop(tmp_path)
    assert not processes.handles


def test_monitor_force_dispatch_has_no_install_or_runtime_binding(monitor, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(monitor, 'bind_runtime', lambda *a: pytest.fail('force stop rebound runtime'))
    monkeypatch.setattr(monitor, 'prepare', lambda *a: pytest.fail('force stop installed'))
    monkeypatch.setattr(monitor, 'force_stop', lambda _: {'state': 'FORCE_STOPPED'})
    assert monitor.main(['force-stop', '--home', str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)['state'] == 'FORCE_STOPPED'


def test_manager_restart_preserves_owned_ssh_until_explicit_stop(processes, tmp_path, monkeypatch):
    from backend.gui_test.execution import launch
    from backend.gui_test.connector.ssh_tunnel import SshTunnelSupervisor
    import time

    runtime = tmp_path / 'runtime'
    owned = identity(900002, '101')
    manual = identity(900009, '106')
    processes.live[manual['pid']] = manual
    processes.parents.clear()  # The original SSH parent has already exited.
    monkeypatch.setattr(launch, 'process_identity', processes.live.get)
    launch.write_ssh_tunnel(runtime, {
        'version': 2, 'transport': owned, 'dashboard_transport': None,
        'remote_runner_port': 18771, 'remote_dashboard_port': None, 'local_dashboard_port': None,
        'ssh_port': 2222, 'ssh_state': 'CONNECTED', 'last_error_code': None,
        'connected_since': 1.0, 'reconnect_attempts': 0,
    })
    supervisor = SshTunnelSupervisor(
        runtime, {'server': 'lab.example', 'account': 'lab'}, actual_local_runner_port=18772,
        preflight_fn=lambda *a, **kw: {'ok': False, 'code': 'SSH_AUTH_FAILED',
                                       'fatal': True, 'summary': 'test authentication error'},
    )
    supervisor.start()
    try:
        deadline = time.monotonic() + 2
        while supervisor.snapshot()['ssh_state'] != 'AUTH_OR_CONFIG_ERROR':
            assert time.monotonic() < deadline
            time.sleep(0.02)
    finally:
        supervisor.stop()
    assert json.loads((runtime / 'ssh-tunnel.json').read_text())['transport'] is None
    result = emergency.force_stop(tmp_path)
    assert result['state'] == 'FORCE_STOPPED'
    assert owned['pid'] not in processes.live, 'previous Manager lost its live SSH generation'
    assert processes.live[manual['pid']] == manual


def test_recorded_endpoints_checked_after_stop_without_claiming_reused_pid(processes, tmp_path, monkeypatch):
    from backend.gui_test.connector import ssh_ownership, ssh_tunnel
    from backend.gui_test.execution import launch

    monkeypatch.setattr(launch, 'process_identity', processes.live.get)
    runtime = tmp_path / 'runtime'
    old = ssh_ownership.endpoint({'server': 'old.example', 'account': 'lab'}, 2222, 18771)
    current = ssh_ownership.endpoint({'server': 'new.example', 'account': 'lab'}, 22, 8771)
    owned, reused = processes.live.values()
    processes.parents.clear()
    ssh_ownership.update(runtime, target=old, processes=[owned])
    ssh_ownership.update(runtime, target=current, processes=[reused])
    replacement = identity(reused['pid'], '500')
    processes.live[reused['pid']] = replacement
    other_home = tmp_path / 'another'
    shutil.copytree(runtime, other_home / 'runtime')
    with pytest.raises(ValueError, match='profile'):
        emergency.force_stop(other_home)
    assert not processes.handles

    def probe(target):
        assert processes.live == {replacement['pid']: replacement}
        return {'state': 'BUSY' if target == current else 'FREE', 'server': target['server']}
    monkeypatch.setattr(ssh_tunnel, 'probe_remote_listener', probe)
    result = emergency.force_stop(tmp_path)
    assert result['state'] == 'FORCE_STOPPED' and result['targets'] == [owned]
    assert result['remote_ports'] == [{'state': 'BUSY', 'server': 'new.example'},
                                      {'state': 'FREE', 'server': 'old.example'}]
    assert result == json.loads((runtime / 'force-stop.json').read_text())
    force.require_force_complete(runtime / 'force-stop.json')
    assert ssh_ownership.read(runtime)['owners'] == []
    assert emergency.force_stop(tmp_path)['remote_ports'] == result['remote_ports'][:1]


@pytest.mark.parametrize('existing', ['owned', 'manual', 'other_port', 'dashboard', 'reused_pid'])
def test_before_start_identity_explains_owned_or_manual_tunnel(processes, tmp_path, monkeypatch, existing):
    import time
    from backend.gui_test.connector import ssh_ownership, ssh_tunnel
    from backend.gui_test.execution import launch

    cfg = {'server': 'linux', 'account': 'lab'}
    target = ssh_ownership.endpoint(cfg, 2222, 8771)
    runtime = tmp_path / 'runtime'
    monkeypatch.setattr(launch, 'process_identity', processes.live.get)
    if existing != 'manual':
        saved = dict(target, remote_runner_port=18771) if existing == 'other_port' else target
        ssh_ownership.update(runtime, target=saved, processes=[identity(900001)],
                             forward='-L' if existing == 'dashboard' else '-R')
    if existing == 'reused_pid':
        processes.live[900001] = identity(900001, '300')
    supervisor = ssh_tunnel.SshTunnelSupervisor(
        runtime, cfg, actual_local_runner_port=18771, ssh_port=2222,
        preflight_fn=lambda *a, **kw: {'ok': True, 'ssh_path': 'fixture'},
        popen=lambda *a, **kw: pytest.fail('duplicate primary SSH'),
    )
    monkeypatch.setattr(supervisor, '_runner_id', lambda: 'current-host')
    monkeypatch.setattr(ssh_tunnel, 'probe_remote_identity', lambda *a: (True, ''))
    supervisor.start()
    try:
        deadline = time.monotonic() + 2
        while (snap := supervisor.snapshot())['ssh_diagnostic']['code'] != 'SSH_REMOTE_PORT_BUSY':
            assert time.monotonic() < deadline
            time.sleep(.02)
        detail = snap['ssh_diagnostic']['detail']
        if existing == 'owned':
            assert 'PID 900001' in detail and '--force-stop' in detail
        else:
            assert '수동 터널' in detail and '--force-stop' not in detail
        assert snap['ssh_state'] == 'RECONNECTING' and not processes.handles
    finally:
        supervisor.stop()


def test_force_stop_finds_processes_after_receipts_disappear(processes, tmp_path, monkeypatch):
    from backend.gui_test.execution import launch
    # The original Manager has exited. Python Host and SSH are independent roots.
    processes.parents.clear()
    manual = identity(900009, '105')
    processes.live[manual['pid']] = manual
    owned = list(processes.live.values())[:2]
    def discover(home):
        assert home == tmp_path
        return {role: [proc] for role, proc in zip(('host', 'ssh'), owned)
                if processes.live.get(proc['pid']) == proc}
    monkeypatch.setattr(emergency, 'discover_windows_processes', discover, raising=False)
    monkeypatch.setattr(launch, 'process_identity', processes.live.get)
    result = emergency.force_stop(tmp_path)
    assert result['state'] == 'FORCE_STOPPED'
    assert processes.live == {manual['pid']: manual}
    assert set(p['pid'] for p in result['targets']) == {p['pid'] for p in owned}


def test_process_scan_requires_product_role_and_exact_profile(tmp_path):
    from backend.gui_test.connector.windows_processes import process_role, tag_transport
    home = tmp_path / 'bsp-dashboard windows'
    other = tmp_path / 'bsp-dashboard windows 2'
    py = 'python.exe'
    manager = [py, '-B', '-m', 'backend.gui_test.connector.supervisor', '--home', str(home)]
    assert process_role(py, manager, home) == 'manager'
    assert process_role('python3.12.exe', manager, home) == 'manager'
    assert process_role(py, manager, other) is None
    host = [py, '-B', '-m', 'backend.gui_test.execution.host', '--config', str(home / 'windows-runner.json'),
            '--runtime', str(home / 'runtime')]
    assert process_role(py, host, home) == 'host'
    assert process_role(py, host[:-1] + [str(other / 'runtime')], home) is None
    ui = [py, '-X', 'utf8', '-B', '-m', 'backend.gui_test.connector', '--home=' + str(home)]
    assert process_role('pythonw.exe', ui, home) == 'ui'
    private = str(home / 'connector-environments' / ('env-' + 'a' * 32) / 'Scripts/python.exe')
    assert process_role(py, [private, 'worker.py'], home, private) == 'profile_python'
    assert process_role(py, [private, 'worker.py'], other, private) is None
    assert process_role(py, manager[:-1] + [str(other)], home, private) is None
    assert process_role(py, [py, 'worker.py', str(home)], home, str(ROOT / '.venv/Scripts/python.exe')) is None
    launcher = [py, str(ROOT / 'scripts/board_connector.py'), '--home', str(home)]
    assert process_role(py, launcher, home) == 'launcher'
    for unrelated in (launcher + ['--force-stop'], [py, '-c', 'pass', *manager[2:]],
                      [py, str(home / 'tc.py'), *manager[2:]], manager + ['--home', str(other)]):
        assert process_role(py, unrelated, home) is None
    for direction in ('-R', '-L'):
        manual = ['ssh.exe', '-NT', direction, '127.0.0.1:8771:127.0.0.1:8772', 'lab@linux']
        tagged = tag_transport(manual, home)
        assert process_role('ssh.exe', tagged, home) == 'ssh'
        assert process_role('ssh.exe', tagged, other) is None
        assert process_role('ssh.exe', manual, home) is None


def test_cim_snapshot_pid_reuse_is_not_adopted(tmp_path, monkeypatch):
    from backend.gui_test.connector import windows_processes as win
    from backend.gui_test.execution import launch
    monkeypatch.setattr(win, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setattr(launch, '_windows_process_snapshot', lambda: {900001: (1, 'python.exe')})
    generations = iter([identity(900001), identity(900001, '500')])
    monkeypatch.setattr(launch, 'process_identity', lambda pid: next(generations))
    monkeypatch.setattr(win, '_command_rows', lambda: [{'ProcessId': 900001, 'Name': 'python.exe', 'CommandLine': 'fixture'}])
    monkeypatch.setattr(win, '_split_command', lambda _: ['python.exe', '-B', '-m', 'backend.gui_test.connector.supervisor',
                                                          '--home', str(tmp_path)])
    assert win.discover_windows_processes(tmp_path) == {}


def test_process_scan_failure_stops_known_targets_and_retries(processes, tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.mkdir()
    (runtime / 'host-active.json').write_text(json.dumps({'runner': identity(900001)}))
    def unavailable(_):
        raise RuntimeError('CIM unavailable')
    monkeypatch.setattr(emergency, 'discover_windows_processes', unavailable)
    with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING'):
        emergency.force_stop(tmp_path)
    assert not processes.live
    with pytest.raises(RuntimeError, match='FORCE_STOP_PENDING'):
        force.require_force_complete(runtime / 'force-stop.json')
    monkeypatch.setattr(emergency, 'discover_windows_processes', lambda home: {})
    assert emergency.force_stop(tmp_path)['state'] == 'FORCE_STOPPED'


def test_packaged_cli_launcher_matches_its_effective_profile(tmp_path):
    from backend.gui_test.connector.windows_processes import process_role
    from scripts.build_connector_bundle import _launcher
    home = tmp_path / 'profile'
    bundle = tmp_path / 'cli'
    script = bundle / 'src/scripts/setup_runtime.py'
    script.parent.mkdir(parents=True)
    script.touch()
    (bundle / 'bundle.json').write_text('{"mode":"editable"}')
    exe = str(bundle / 'runtime/python.exe')
    cmd = _launcher('scripts.setup_runtime', 'run').decode('ascii').splitlines()[2]
    args = [exe, *cmd.split('" ')[1].split(' %*')[0].split(), '--home', str(home)]
    assert process_role('python.exe', args, home, exe) == 'launcher'
    assert process_role('python.exe', args, tmp_path / 'other', exe) is None
    assert process_role('python.exe', args, home, str(tmp_path / 'unrelated/python.exe')) is None
