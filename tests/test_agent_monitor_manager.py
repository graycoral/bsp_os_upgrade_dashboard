"""No network/installation/process side effects: manager lifecycle ownership contracts."""
import importlib.util
import json
import os
import sqlite3
import subprocess
import signal
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name == 'nt', reason='Agent Monitor service runs on Linux/POSIX')


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'apps/agent-monitor'))
    spec = importlib.util.spec_from_file_location('agent_monitor_manager_tests', ROOT / 'apps/agent-monitor/manage.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_service_lock_is_exclusive_and_released_after_failure(manager, tmp_path):
    path = tmp_path / 'service.lock'
    with pytest.raises(ValueError):
        with manager.lock(path):
            assert manager.active(tmp_path)
            with pytest.raises(RuntimeError):
                with manager.lock(path): pytest.fail('second owner entered')
            raise ValueError('simulated owner failure')
    assert not manager.active(tmp_path)


@pytest.mark.parametrize('changed', ['managed_instance', 'managed_release', 'managed_runtime', 'worker_running', None])
def test_status_requires_matching_release_runtime_instance_and_worker(manager, tmp_path, monkeypatch, changed):
    receipt = {'instance': 'owned-instance', 'release': 'owned-release', 'runtime': str(tmp_path / 'runtime'), 'port': 18766}
    manager.atomic(tmp_path / 'service.json', receipt)
    value = {'managed_instance': receipt['instance'], 'managed_release': receipt['release'],
             'managed_runtime': receipt['runtime'], 'worker_running': True}
    if changed: value[changed] = False if changed == 'worker_running' else 'foreign'
    monkeypatch.setattr(manager, 'health', lambda port: value)
    with manager.lock(tmp_path / 'service.lock'):
        result = manager.status(tmp_path)
    assert result['state'] == ('READY' if changed is None else 'STARTING')
    if changed in {'managed_instance', 'managed_release', 'managed_runtime'}: assert result['health'] is None
    assert manager.status(tmp_path) == {'state': 'STOPPED'}


def test_running_other_port_cannot_be_replaced_or_trigger_install(manager, tmp_path, monkeypatch):
    monkeypatch.setattr(manager, 'active', lambda home: True)
    monkeypatch.setattr(manager, 'status', lambda home: {'state': 'READY', 'url': 'http://127.0.0.1:8766'})
    monkeypatch.setattr(manager, 'prepare', lambda *a, **k: pytest.fail('unexpected installation'))
    with pytest.raises(RuntimeError, match='포트'): manager.start(tmp_path, port=18766)


def test_stop_request_is_pinned_to_owned_supervisor_instance(manager, tmp_path):
    manager.atomic(tmp_path / 'service.json', {'instance': 'current-supervisor'})
    with manager.lock(tmp_path / 'service.lock'):
        assert manager.stop(tmp_path) == {'state': 'STOP_REQUESTED'}
        assert json.loads((tmp_path / 'stop-request.json').read_text()) == {'instance': 'current-supervisor'}
    assert manager.stop(tmp_path) == {'state': 'STOPPED'}


@pytest.mark.parametrize('state,blocks', [('QUEUED', True), ('RUNNING', True), ('PAUSED', True), ('UNKNOWN', True),
                                       ('COMPLETED', False), ('CANCELLED', False)])
def test_pending_or_unresolved_run_defers_shutdown_without_changing_db(manager, tmp_path, state, blocks):
    runtime = tmp_path / 'runtime'; runtime.mkdir(); db = runtime / 'runs.db'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, data TEXT)')
        c.execute('INSERT INTO runs VALUES (?,?)', ('run-one', json.dumps({'state': state})))
    before = db.read_bytes()
    assert manager.has_work(runtime) is blocks
    assert db.read_bytes() == before


def test_reservations_and_unknown_bsp_layout_conservatively_block_shutdown(manager, tmp_path):
    runtime = tmp_path / 'runtime'; runtime.mkdir(); db = runtime / 'dashboard.db'
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE reservations (id TEXT)'); c.execute("INSERT INTO reservations VALUES('held')")
    assert manager.has_work(runtime)
    with sqlite3.connect(db) as c:
        c.execute('DELETE FROM reservations'); c.execute('CREATE TABLE jobs (id TEXT)'); c.execute("INSERT INTO jobs VALUES('unknown-layout')")
    assert manager.has_work(runtime)


def fake_install(manager, tmp_path, monkeypatch):
    events = []
    def export(source, destination, include_ui):
        destination.mkdir(parents=True); (destination / 'requirements.lock').write_text('fixture==1')
        return {'release': 'a' * 64}
    monkeypatch.setattr(manager, 'export', export)
    monkeypatch.setattr(manager, 'verify', lambda path, **kwargs: {'release': 'a' * 64})
    monkeypatch.setattr(manager, 'valid_environment', lambda path: (Path(path) / '.venv/bin/python').is_file())
    def run(argv, **kwargs):
        events.append(argv)
        if argv[1:3] == ['-m', 'venv']:
            path = Path(argv[3]) / 'bin/python'; path.parent.mkdir(parents=True); path.write_text('fake interpreter')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(manager.subprocess, 'run', run)
    return events


def test_healthy_content_release_reuses_environment_without_pip_and_active_update_is_deferred(manager, tmp_path, monkeypatch):
    events = fake_install(manager, tmp_path, monkeypatch)
    source = tmp_path / 'source'; source.mkdir(); home = tmp_path / 'home'
    first = manager.prepare(source, home)
    assert first['state'] == 'INSTALLED' and len(events) == 2
    events.clear()
    second = manager.prepare(source, home)
    assert second['state'] == 'REUSED' and events == []
    previous = {'release': 'previous', 'path': str(home / 'releases/previous')}
    manager.atomic(home / 'current.json', previous)
    with manager.lock(home / 'service.lock'):
        held = manager.prepare(source, home)
    assert held['state'] == 'UPDATE_PENDING' and events == []
    assert json.loads((home / 'current.json').read_text()) == previous


def test_t254_preparation_reports_stages_and_keeps_stdout_clean(manager, tmp_path, monkeypatch, capsys):
    fake_install(manager, tmp_path, monkeypatch)
    result = manager.prepare(tmp_path / 'source', tmp_path / 'home')
    assert result['state'] == 'INSTALLED'
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'Python 가상환경 준비 시작' in captured.err
    assert 'Python 패키지 설치 시작' in captured.err
    assert 'Python 패키지 설치 완료' in captured.err
    assert str(tmp_path / 'home/install.log') in captured.err


def test_failed_preparation_preserves_existing_pointer_and_runtime(manager, tmp_path, monkeypatch):
    fake_install(manager, tmp_path, monkeypatch)
    home = tmp_path / 'home'; previous = {'release': 'previous', 'path': '/existing'}
    manager.atomic(home / 'current.json', previous)
    manager.atomic(home / 'runtime/kept.json', {'state': 'UNKNOWN'})
    def failed(argv, **kwargs): raise subprocess.CalledProcessError(7, argv)
    monkeypatch.setattr(manager.subprocess, 'run', failed)
    with pytest.raises(subprocess.CalledProcessError): manager.prepare(tmp_path / 'source', home)
    assert json.loads((home / 'current.json').read_text()) == previous
    assert json.loads((home / 'runtime/kept.json').read_text()) == {'state': 'UNKNOWN'}
    assert not list(home.glob('.install-*'))


def test_t254_quiet_install_reports_wait_without_exposing_log(manager, tmp_path, capsys):
    log = tmp_path / 'install.log'
    manager.install_step([sys.executable, '-c', 'import time; time.sleep(10.1); print("private fixture detail")'],
                         tmp_path, log, 'Python 패키지 설치')
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'Python 패키지 설치 시작' in captured.err
    assert '진행 중 · 10초 경과' in captured.err
    assert 'Python 패키지 설치 완료' in captured.err
    assert str(log) in captured.err
    assert 'private fixture detail' not in captured.err
    assert 'private fixture detail' in log.read_text()


def test_t254_failed_install_reports_exit_and_preserves_local_log(manager, tmp_path, capsys):
    log = tmp_path / 'install.log'
    with pytest.raises(subprocess.CalledProcessError) as error:
        manager.install_step([sys.executable, '-c', 'print("private fixture error"); raise SystemExit(7)'],
                             tmp_path, log, 'Python 패키지 설치')
    assert error.value.returncode == 7
    captured = capsys.readouterr()
    assert captured.out == ''
    assert '종료 코드 7' in captured.err
    assert '완료' not in captured.err
    assert 'private fixture error' not in captured.err
    assert 'private fixture error' in log.read_text()


def test_t254_interrupted_install_stops_child_and_releases_lock(manager, tmp_path):
    pidfile = tmp_path / 'installer.pid'
    child = f'from pathlib import Path; import os,time; Path({str(pidfile)!r}).write_text(str(os.getpid())); time.sleep(60)'
    command = (
        f'import sys; sys.path.insert(0, {str(Path(manager.__file__).parent)!r}); import manage; '
        f'home=manage.Path({str(tmp_path)!r}); '
        f'\nwith manage.lock(home/"install.lock"):\n'
        f' manage.install_step([sys.executable,"-c",{child!r}],home,home/"install.log","fixture install")'
    )
    with subprocess.Popen([sys.executable, '-c', command], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          start_new_session=True) as owner:
        try:
            deadline = time.monotonic() + 5
            while not pidfile.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            assert pidfile.exists()
            installer_pid = int(pidfile.read_text())
            owner.send_signal(signal.SIGINT)
            stdout, stderr = owner.communicate(timeout=5)
            assert owner.returncode != 0
            assert stdout == b''
            assert '중단' in stderr.decode()
            with pytest.raises(ProcessLookupError): os.kill(installer_pid, 0)
            with manager.lock(tmp_path / 'install.lock'):
                pass
        finally:
            if owner.poll() is None:
                os.killpg(owner.pid, signal.SIGKILL)
                owner.wait()


def restart_fixture(manager, tmp_path, monkeypatch):
    state = {'running': True, 'events': []}
    candidate = {'release': 'new-release', 'path': str(tmp_path / 'new'), 'state': 'UPDATE_PENDING'}
    manager.atomic(tmp_path / 'service.json', {'instance': 'old-instance', 'port': 18767})
    monkeypatch.setattr(manager, 'active', lambda home: state['running'])
    monkeypatch.setattr(manager, 'status', lambda home: {
        'state': 'READY', 'url': 'http://127.0.0.1:18767',
        'release': 'old-release' if state['running'] else 'new-release'})
    monkeypatch.setattr(manager, 'prepare', lambda *args: state['events'].append('prepare') or candidate)
    def stop(home):
        state['events'].append('stop')
        state['running'] = False
        return {'state': 'STOP_REQUESTED'}
    monkeypatch.setattr(manager, 'stop', stop)
    monkeypatch.setattr(manager, 'activate', lambda *args: state['events'].append('activate') or True)
    def spawn(argv, **kwargs):
        state['events'].append('launch')
        assert argv[0] == str(tmp_path / 'new/.venv/bin/python')
        assert argv[-2:] == ['--release', 'new-release']
        return SimpleNamespace(poll=lambda: None)
    monkeypatch.setattr(manager.subprocess, 'Popen', spawn)
    return state


def test_restart_prepares_before_stop_then_launches_selected_release(manager, tmp_path, monkeypatch):
    state = restart_fixture(manager, tmp_path, monkeypatch)
    result = manager.start(tmp_path, source=tmp_path / 'source', port=18767, restart=True)
    assert result['release'] == 'new-release'
    assert state['events'] == ['prepare', 'stop', 'activate', 'launch']


def test_existing_start_explains_reuse_without_installing(manager, tmp_path, monkeypatch, capsys):
    state = restart_fixture(manager, tmp_path, monkeypatch)
    result = manager.start(tmp_path, port=18767)
    assert result['release'] == 'old-release' and state['events'] == []
    assert './run.sh restart' in capsys.readouterr().err


def test_restart_install_failure_keeps_existing_service(manager, tmp_path, monkeypatch):
    state = restart_fixture(manager, tmp_path, monkeypatch)
    def fail(*args):
        raise RuntimeError('installation failed')
    monkeypatch.setattr(manager, 'prepare', fail)
    with pytest.raises(RuntimeError, match='installation failed'):
        manager.start(tmp_path, source=tmp_path/'source', port=18767, restart=True)
    assert state['running'] and state['events'] == []


@pytest.mark.parametrize('blocked', [True, False])
def test_restart_never_launches_when_stop_is_blocked_or_unconfirmed(manager, tmp_path, monkeypatch, blocked):
    state = restart_fixture(manager, tmp_path, monkeypatch)
    def stop(home):
        state['events'].append('stop')
        manager.atomic(home / 'stop-result.json', {
            'state': 'BLOCKED', 'instance': 'old-instance' if blocked else 'foreign', 'reason': 'held work'})
    monkeypatch.setattr(manager, 'stop', stop)
    ticks = iter([0, 50])
    monkeypatch.setattr(manager.time, 'monotonic', lambda: next(ticks))
    with pytest.raises(RuntimeError, match='RESTART_BLOCKED' if blocked else 'RESTART_PENDING'):
        manager.start(tmp_path, source=tmp_path/'source', port=18767, restart=True)
    assert state['running'] and state['events'] == ['prepare', 'stop']


def test_restart_does_not_fall_back_when_candidate_activation_is_blocked(manager, tmp_path, monkeypatch):
    state = restart_fixture(manager, tmp_path, monkeypatch)
    monkeypatch.setattr(manager, 'activate', lambda *args: False)
    with pytest.raises(RuntimeError, match='RESTART_BLOCKED'):
        manager.start(tmp_path, source=tmp_path/'source', port=18767, restart=True)
    assert state['events'] == ['prepare', 'stop']


@pytest.mark.parametrize('packaged,build_fails', [(False,False), (False,True), (True,False)])
def test_restart_builds_selected_checkout_before_preparation_and_preserves_packaged_ui(
        manager, tmp_path, monkeypatch, packaged, build_fails):
    state = restart_fixture(manager, tmp_path, monkeypatch)
    source = tmp_path/'selected source'; (source/'apps/web').mkdir(parents=True)
    (source/'apps/web/package.json').write_text('{}')
    if packaged: (source/manager.MANIFEST).write_text('{}')
    def build(argv, cwd, log, label):
        state['events'].append('build')
        assert argv == ['bash', str(source/'scripts/build-ui.sh'), 'all']
        assert cwd == source and log == tmp_path/'ui-build.log'
        if build_fails: raise RuntimeError('UI build failed')
    monkeypatch.setattr(manager, 'install_step', build)
    if build_fails:
        with pytest.raises(RuntimeError, match='UI build failed'):
            manager.start(tmp_path, source=source, port=18767, restart=True)
        assert state['running'] and state['events'] == ['build']
    else:
        result = manager.start(tmp_path, source=source, port=18767, restart=True)
        assert result['state'] == 'READY'
        assert state['events'] == ([] if packaged else ['build']) + ['prepare', 'stop', 'activate', 'launch']



def test_new_package_detects_old_ready_owner_and_preserves_sibling_runtime(manager, tmp_path, monkeypatch):
    source = tmp_path / 'copied-package'
    source.mkdir()
    (source / manager.MANIFEST).touch()
    monkeypatch.setattr(manager, 'verify', lambda path, **kwargs: {
        'release': 'candidate' if Path(path) == source else 'old', 'source_head': 'fixture-pin'})
    homes = [tmp_path / f'home-{number}' for number in range(2)]
    before = {}
    for number, home in enumerate(homes):
        path = home / 'releases/old'
        runtime = manager.bind_runtime(home, tmp_path / f'runtime-{number}')
        manager.atomic(home / 'current.json', {'release': 'old', 'path': str(path)})
        manager.atomic(home / 'service.json', {'instance': home.name, 'release': 'old', 'path': str(path),
                                              'runtime': str(runtime), 'port': 18766 + number})
        runtime.mkdir()
        db = runtime / 'runs.db'
        with sqlite3.connect(db) as connection:
            connection.execute('CREATE TABLE runs (id TEXT PRIMARY KEY, data TEXT)')
            connection.execute('INSERT INTO runs VALUES (?,?)', (home.name, json.dumps({'state': 'PAUSED'})))
            connection.execute('CREATE TABLE reservations (id TEXT PRIMARY KEY)')
            connection.execute('INSERT INTO reservations VALUES (?)', (home.name,))
        before[db] = db.read_bytes()

    def health(port):
        receipt = manager.read(homes[port - 18766] / 'service.json')
        return {'managed_instance': receipt['instance'], 'managed_release': receipt['release'],
                'managed_runtime': receipt['runtime'], 'managed_source': receipt['path'], 'worker_running': True}

    monkeypatch.setattr(manager, 'health', health)
    with manager.lock(homes[0] / 'service.lock'), manager.lock(homes[1] / 'service.lock'):
        result = manager.deployment_status(homes[0], source, manager.status(homes[0]))
        assert result['state'] == 'READY'
        assert result['deployment']['state'] == 'UPDATE_REQUIRED'
        assert result['deployment']['package_release'] == 'candidate'
        assert result['deployment']['installed_release'] == result['deployment']['running_release'] == 'old'
        assert result['deployment']['running_path'] == str(homes[0] / 'releases/old')
        assert manager.status(homes[1])['release'] == 'old'
        assert all(manager.active(home) for home in homes)
        assert all(not (home / 'stop-request.json').exists() for home in homes)
        monkeypatch.setattr(manager, 'health', lambda port: {'managed_instance': 'unrelated-service'})
        unknown = manager.deployment_status(homes[0], source, manager.status(homes[0]))['deployment']
        assert unknown['state'] == 'UPDATE_REQUIRED' and unknown['receipt_release'] == 'old'
        assert unknown['running_release'] is unknown['running_path'] is None
    assert all(db.read_bytes() == prior for db, prior in before.items())



def test_status_accepts_unbound_absolute_runtime_without_writes_but_rejects_binding_mismatch(manager, tmp_path, capsys):
    home = tmp_path / 'new-home'
    requested = tmp_path / 'external-runtime'
    command = ['status', '--home', str(home), '--runtime', str(requested)]
    assert manager.main(command) == 0
    assert json.loads(capsys.readouterr().out) == {'state': 'STOPPED'}
    assert not home.exists() and not requested.exists()
    other = tmp_path / 'bound-runtime'
    manager.bind_runtime(home, other)
    assert manager.main(command) == 1
    assert manager.runtime_path(home) == other
    assert not requested.exists()



@pytest.mark.parametrize('live', [False, True])
def test_start_reuses_time_wait_port_but_leaves_active_listener_owned(manager, tmp_path, monkeypatch, live):
    ready = {'state': 'READY'}
    started = []
    monkeypatch.setattr(manager, 'prepare', lambda *args: {
        'state': 'REUSED', 'path': str(tmp_path / 'release'), 'release': 'mock-release'})
    monkeypatch.setattr(manager, 'status', lambda home: ready)
    monkeypatch.setattr(manager.subprocess, 'Popen', lambda *args, **kwargs: started.append(args))
    with socket.socket() as listener, socket.socket() as client:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.listen()
        client.connect(('127.0.0.1', port))
        connection, _ = listener.accept()
        connection.close()
        assert client.recv(1) == b''
        client.close()
        if live:
            with pytest.raises(RuntimeError, match='포트'):
                manager.start(tmp_path, port=port)
            assert started == []
        else:
            listener.close()
            assert manager.start(tmp_path, port=port) == ready
            assert len(started) == 1
