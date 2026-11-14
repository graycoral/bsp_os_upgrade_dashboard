"""Supervisor lifecycle tests with fake children only; no installs or services."""
import importlib.util
import os
import json
from pathlib import Path
import signal
import sqlite3
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.name == 'nt', reason='Linux/macOS service lifecycle uses POSIX process locks')

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'apps/agent-monitor'))
    spec = importlib.util.spec_from_file_location('monitor_lifecycle_tests', ROOT / 'apps/agent-monitor/manage.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    import prerequisites
    monkeypatch.setattr(prerequisites, 'prepare', lambda *a, **k: {'state':'REUSED','missing':[]})
    return module


class Child:
    def __init__(self, kind, events):
        self.kind, self.events, self.returncode = kind, events, None
        self.slow = False

    def poll(self): return self.returncode

    def send_signal(self, number):
        self.events.append(('signal', self.kind, number))
        if not self.slow: self.returncode = 0

    def wait(self, timeout=None):
        self.events.append(('wait', self.kind, timeout))
        if self.slow: raise subprocess.TimeoutExpired(self.kind, timeout)
        self.returncode = self.returncode if self.returncode is not None else 0
        return self.returncode

    def kill(self): pytest.fail('Lifecycle must never hard-kill a child')
    def terminate(self): pytest.fail('Lifecycle must never terminate a child blindly')


def supervisor(manager, monkeypatch, home):
    events, children, handlers = [], [], {}
    release = home / 'releases/fixed'
    monkeypatch.setattr(manager, 'current', lambda path: {'path': str(release), 'release': 'a' * 64})
    def create(argv, **kwargs):
        kind = 'worker' if 'backend.worker.main' in argv else 'api'
        child = Child(kind, events); children.append(child)
        events.append(('create', kind))
        assert kwargs['env']['BSP_RUNTIME'] == str(home / 'runtime')
        assert kwargs['env']['AGENT_MONITOR_RELEASE'] == 'a' * 64
        assert kwargs['start_new_session'] is True
        return child
    monkeypatch.setattr(manager.subprocess, 'Popen', create)
    def handler(number, callback):
        previous = handlers.get(number, signal.SIG_DFL); handlers[number] = callback
        return previous
    monkeypatch.setattr(manager.signal, 'signal', handler)
    return events, children, handlers


def request_stop(manager, home):
    receipt = manager.read(home / 'service.json')
    manager.atomic(home / 'stop-request.json', {'instance': receipt['instance']})


def test_api_crash_restarts_same_owner_without_stopping_worker(manager, tmp_path, monkeypatch):
    events, children, _ = supervisor(manager, monkeypatch, tmp_path)
    sleeps = 0
    def sleep(seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            children[1].returncode = 9
        elif sleeps == 2:
            assert [c.kind for c in children] == ['worker', 'api', 'api']
            assert children[0].poll() is None
            assert not any(e[0] == 'signal' for e in events)
            request_stop(manager, tmp_path)
        else: pytest.fail('Supervisor failed to stop')
    monkeypatch.setattr(manager.time, 'sleep', sleep)
    monkeypatch.setattr(manager, 'has_work', lambda runtime: events.append(('proof', children[-1].poll())) or False)
    assert manager.serve(tmp_path, 18766) == {'state': 'STOPPED'}
    proof = next(i for i, e in enumerate(events) if e[0] == 'proof')
    worker_signal = next(i for i, e in enumerate(events) if e[:2] == ('signal', 'worker'))
    assert events[proof] == ('proof', 0) and worker_signal > proof
    assert [e for e in events if e == ('create', 'worker')] == [('create', 'worker')]
    assert not (tmp_path / 'service.json').exists() and not manager.active(tmp_path)


def test_stop_checks_work_after_api_exit_and_restarts_api_when_busy(manager, tmp_path, monkeypatch):
    events, children, _ = supervisor(manager, monkeypatch, tmp_path)
    proofs, sleeps = 0, 0
    def has_work(runtime):
        nonlocal proofs
        proofs += 1
        assert children[-1].kind == 'api' and children[-1].poll() == 0
        return proofs == 1
    def sleep(seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1: request_stop(manager, tmp_path)
        elif sleeps == 2:
            assert manager.read(tmp_path / 'stop-result.json')['state'] == 'BLOCKED'
            assert children[0].poll() is None
            assert children[-1].kind == 'api' and children[-1].poll() is None
            assert not any(e[:2] == ('signal', 'worker') for e in events)
            request_stop(manager, tmp_path)
        else: pytest.fail('Supervisor failed to stop')
    monkeypatch.setattr(manager, 'has_work', has_work)
    monkeypatch.setattr(manager.time, 'sleep', sleep)
    manager.serve(tmp_path, 18766)
    assert proofs == 2 and len(children) == 3


def test_supervisor_signals_are_guarded_stop_requests(manager, tmp_path, monkeypatch):
    events, children, handlers = supervisor(manager, monkeypatch, tmp_path)
    proofs, sleeps = 0, 0
    def has_work(runtime):
        nonlocal proofs
        proofs += 1
        return proofs == 1
    def sleep(seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1: handlers[signal.SIGTERM](signal.SIGTERM, None)
        elif sleeps == 2:
            assert children[0].poll() is None and manager.active(tmp_path)
            assert manager.read(tmp_path / 'stop-result.json')['state'] == 'BLOCKED'
            handlers[signal.SIGINT](signal.SIGINT, None)
        else: pytest.fail('Supervisor failed to stop')
    monkeypatch.setattr(manager, 'has_work', has_work)
    monkeypatch.setattr(manager.time, 'sleep', sleep)
    manager.serve(tmp_path, 18766)
    assert proofs == 2
    assert handlers == {signal.SIGINT: signal.SIG_DFL, signal.SIGTERM: signal.SIG_DFL}


def test_unexpected_worker_exit_keeps_api_and_never_restarts_execution(manager, tmp_path, monkeypatch):
    events, children, _ = supervisor(manager, monkeypatch, tmp_path)
    sleeps = 0
    def sleep(seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1: children[0].returncode = 7
        elif sleeps == 2:
            assert len(children) == 2 and children[1].poll() is None
            assert manager.read(tmp_path / 'service.json')['state'] == 'DEGRADED'
            assert manager.active(tmp_path)
            request_stop(manager, tmp_path)
        else: pytest.fail('Supervisor failed to stop')
    monkeypatch.setattr(manager, 'has_work', lambda runtime: False)
    monkeypatch.setattr(manager.time, 'sleep', sleep)
    manager.serve(tmp_path, 18766)
    assert [e for e in events if e == ('create', 'worker')] == [('create', 'worker')]
    assert not any(e[:2] == ('signal', 'worker') for e in events)


def test_malformed_stop_request_cannot_stop_worker_or_prevent_api_repair(manager, tmp_path, monkeypatch):
    events, children, _ = supervisor(manager, monkeypatch, tmp_path)
    sleeps = 0
    def sleep(seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            (tmp_path / 'stop-request.json').write_text('{broken')
            children[1].returncode = 9
        elif sleeps == 2:
            assert len(children) == 3 and children[0].poll() is None
            assert not any(e[:2] == ('signal', 'worker') for e in events)
            request_stop(manager, tmp_path)
        else: pytest.fail('Supervisor failed to stop')
    monkeypatch.setattr(manager, 'has_work', lambda runtime: False)
    monkeypatch.setattr(manager.time, 'sleep', sleep)
    manager.serve(tmp_path, 18766)


def test_api_that_has_not_exited_keeps_worker_and_skips_stop_proof(manager, tmp_path, monkeypatch):
    events, children, _ = supervisor(manager, monkeypatch, tmp_path)
    sleeps, proofs = 0, 0
    def has_work(runtime):
        nonlocal proofs
        proofs += 1
        return False
    def sleep(seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            children[1].slow = True; request_stop(manager, tmp_path)
        elif sleeps == 2:
            assert manager.read(tmp_path / 'stop-result.json')['state'] == 'BLOCKED'
            assert children[0].poll() is None and proofs == 0
            children[1].slow = False; request_stop(manager, tmp_path)
        else: pytest.fail('Supervisor failed to stop')
    monkeypatch.setattr(manager, 'has_work', has_work)
    monkeypatch.setattr(manager.time, 'sleep', sleep)
    manager.serve(tmp_path, 18766)
    assert proofs == 1


def finished_job():
    return {'fingerprint': 'current-source',
            'modules': [{'stages': {name: {'status': 'SUCCEEDED', 'validity': 'CURRENT'} for name in
                                    ('analysis', 'design', 'code', 'build', 'verification', 'device_test')}}],
            'integration': {'status': 'SUCCEEDED'},
            'final_review': {'fingerprint': 'current-source', 'reviewer': 'person', 'evidence': 'Reviewed'},
            'decisions': [], 'prompts': []}


def write_job(runtime, value):
    runtime.mkdir(exist_ok=True)
    with sqlite3.connect(runtime / 'dashboard.db') as c:
        c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT)')
        c.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)', ('job', json.dumps(value)))


def test_actual_bsp_final_review_proves_finished_without_invented_top_level_status(manager, tmp_path):
    job = finished_job(); write_job(tmp_path, job)
    before = (tmp_path / 'dashboard.db').read_bytes()
    assert manager.has_work(tmp_path) is False
    assert (tmp_path / 'dashboard.db').read_bytes() == before
    job['final_review']['fingerprint'] = 'stale'
    write_job(tmp_path, job)
    assert manager.has_work(tmp_path) is True


@pytest.mark.parametrize('state', ['PENDING', 'RUNNING', 'UNKNOWN', 'CANCEL_REQUESTED', 'FAILED'])
def test_unfinished_bsp_stage_blocks_stop(manager, tmp_path, state):
    job = finished_job(); job['modules'][0]['stages']['build']['status'] = state
    write_job(tmp_path, job)
    assert manager.has_work(tmp_path) is True


def test_bsp_leases_and_unterminated_launch_receipt_block_even_with_final_review(manager, tmp_path):
    write_job(tmp_path, finished_job())
    with sqlite3.connect(tmp_path / 'dashboard.db') as c:
        c.execute('CREATE TABLE leases(resource TEXT)'); c.execute("INSERT INTO leases VALUES('linux-write')")
    assert manager.has_work(tmp_path) is True
    with sqlite3.connect(tmp_path / 'dashboard.db') as c:
        c.execute('DELETE FROM leases'); c.execute('CREATE TABLE launch_receipts(data TEXT)')
        c.execute('INSERT INTO launch_receipts VALUES(?)', (json.dumps({'process_receipt': {'phase': 'UNKNOWN'}}),))
    assert manager.has_work(tmp_path) is True
    with sqlite3.connect(tmp_path / 'dashboard.db') as c:
        c.execute('UPDATE launch_receipts SET data=?', (json.dumps({'process_receipt': {'phase': 'TERMINATED'}}),))
    assert manager.has_work(tmp_path) is False


def test_corrupt_db_and_unknown_job_layout_fail_closed(manager, tmp_path):
    (tmp_path / 'runs.db').write_bytes(b'corrupt sqlite')
    assert manager.has_work(tmp_path) is True
    (tmp_path / 'runs.db').unlink()
    write_job(tmp_path, {'status': 'SUCCEEDED'})
    assert manager.has_work(tmp_path) is True


def test_stopped_supervisor_with_persisted_unknown_defers_release_activation(manager, tmp_path):
    old = {'release': 'old-release', 'path': str(tmp_path / 'releases/old')}
    manager.atomic(tmp_path / 'current.json', old)
    runtime = tmp_path / 'runtime'; runtime.mkdir()
    with sqlite3.connect(runtime / 'runs.db') as c:
        c.execute('CREATE TABLE runs(data TEXT)'); c.execute('INSERT INTO runs VALUES(?)', (json.dumps({'state': 'UNKNOWN'}),))
    assert manager.active(tmp_path) is False
    assert manager.activate(tmp_path, 'new-release', tmp_path / 'releases/new') is False
    assert manager.read(tmp_path / 'current.json') == old


def test_activation_and_supervisor_share_exclusive_lock_and_same_release_reuse_is_inert(manager, tmp_path):
    target = tmp_path / 'releases/old'
    old = {'release': 'old-release', 'path': str(target), 'previous': {'release': 'older', 'path': '/older'}}
    manager.atomic(tmp_path / 'current.json', old)
    with manager.lock(tmp_path / 'service.lock'):
        assert manager.activate(tmp_path, 'new-release', tmp_path / 'releases/new') is False
        assert manager.activate(tmp_path, 'old-release', target) is True
    assert manager.read(tmp_path / 'current.json') == old
    assert manager.activate(tmp_path, 'new-release', tmp_path / 'releases/new') is True
    assert manager.read(tmp_path / 'current.json')['previous'] == {'release': 'old-release', 'path': str(target)}


def test_supervisor_rejects_activation_changed_before_ownership_without_launch(manager, tmp_path, monkeypatch):
    events, children, _ = supervisor(manager, monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match='활성 버전'):
        manager.serve(tmp_path, 18766, expected_release='other-release')
    assert children == [] and not manager.active(tmp_path)


def test_deferred_update_start_launches_previous_current_release(manager, tmp_path, monkeypatch):
    previous = tmp_path / 'releases/previous'
    candidate = tmp_path / 'releases/candidate'
    manager.atomic(tmp_path / 'current.json', {'release':'previous', 'path':str(previous)})
    monkeypatch.setattr(manager, 'active', lambda home: False)
    monkeypatch.setattr(manager, 'prepare', lambda *a, **k: {'state': 'UPDATE_PENDING', 'release': 'candidate', 'path': str(candidate)})
    monkeypatch.setattr(manager, 'current', lambda home: {'release': 'previous', 'path': str(previous)})
    manager.atomic(tmp_path/'current.json', {'release':'previous','path':str(previous)})
    monkeypatch.setattr(manager, 'status', lambda home: {'state': 'READY'})
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address): pass
    monkeypatch.setattr(manager.socket, 'socket', lambda: Socket())
    calls = []
    def spawn(argv, **kwargs):
        calls.append(argv)
        return Child('supervisor', [])
    monkeypatch.setattr(manager.subprocess, 'Popen', spawn)
    assert manager.start(tmp_path, source=tmp_path / 'source', port=18766)['state'] == 'READY'
    assert calls[0][0] == str(previous / '.venv/bin/python')
    assert calls[0][-2:] == ['--release', 'previous']
    assert str(candidate) not in str(calls)


def test_explicit_runtime_binding_preserves_existing_data_and_is_sticky(manager, tmp_path):
    home = tmp_path / 'service home'
    existing = tmp_path / 'project/.runtime'
    existing.mkdir(parents=True)
    sentinel = existing / 'settings.json'; sentinel.write_bytes(b'{"kept":true}')
    assert manager.bind_runtime(home, existing) == existing.resolve()
    assert manager.runtime_path(home) == existing.resolve()
    assert manager.bind_runtime(home) == existing.resolve()
    assert sentinel.read_bytes() == b'{"kept":true}'
    with pytest.raises(ValueError, match='runtime'):
        manager.bind_runtime(home, tmp_path / 'different')
    assert manager.runtime_path(home) == existing.resolve()


def test_active_or_existing_default_runtime_cannot_be_rebound(manager, tmp_path):
    home = tmp_path / 'home'
    with manager.lock(home / 'service.lock'):
        assert manager.bind_runtime(home) == home / 'runtime'
        with pytest.raises(ValueError): manager.bind_runtime(home, tmp_path / 'other')
    (home / 'runtime').mkdir()
    with pytest.raises(ValueError): manager.bind_runtime(home, tmp_path / 'other')


def test_activation_checks_bound_runtime_even_when_service_stopped(manager, tmp_path, monkeypatch):
    home = tmp_path / 'home'; runtime = tmp_path / 'existing-runtime'
    manager.bind_runtime(home, runtime)
    checked = []
    monkeypatch.setattr(manager, 'has_work', lambda path: checked.append(path) or True)
    assert not manager.activate(home, 'new-release', tmp_path / 'candidate')
    assert checked == [runtime] and not (home / 'current.json').exists()


def test_cli_start_binds_runtime_before_calling_manager(manager, tmp_path, monkeypatch):
    home = tmp_path / 'home'; runtime = tmp_path / 'project/.runtime'
    def start(given, *args):
        assert given == home and manager.runtime_path(home) == runtime.resolve()
        return {'state':'READY'}
    monkeypatch.setattr(manager, 'start', start)
    assert manager.main(['start','--home',str(home),'--runtime',str(runtime)]) == 0
    assert manager.main(['start','--home',str(home),'--runtime',str(tmp_path/'wrong')]) == 1


def test_root_launcher_preserves_runtime_and_port_from_other_cwd(tmp_path):
    import shutil
    source = ROOT / 'run.sh'; root = tmp_path / 'source tree'
    root.mkdir(); shutil.copy2(source, root / 'run.sh')
    fake = tmp_path / 'bin'; fake.mkdir(); python = fake / 'python3'
    capture = tmp_path / 'arguments'
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE"\n')
    python.chmod(0o755)
    env = dict(os.environ, PATH=str(fake)+':/usr/bin:/bin', CAPTURE=str(capture), BSP_PORT='8765')
    env.pop('BSP_RUNTIME', None)
    result = subprocess.run(['/bin/bash', str(root/'run.sh')], cwd=tmp_path, env=env)
    assert result.returncode == 0
    assert capture.read_text().splitlines() == [str(root/'apps/agent-monitor/manage.py'), 'start', '--runtime', str(root/'.runtime'), '--port', '8765']


def test_first_adoption_with_unresolved_runtime_has_actionable_error_and_never_starts_worker(manager, tmp_path, monkeypatch):
    home = tmp_path / 'home'; runtime = tmp_path / 'existing'
    manager.bind_runtime(home, runtime)
    monkeypatch.setattr(manager, 'prepare', lambda *a: {'state':'UPDATE_PENDING','path':'/candidate','release':'candidate'})
    monkeypatch.setattr(manager.subprocess, 'Popen', lambda *a, **k: pytest.fail('unverified adoption started process'))
    with pytest.raises(RuntimeError, match='INITIAL_RUNTIME_ADOPTION_BLOCKED'):
        manager.start(home)
    assert not (home / 'current.json').exists() and manager.runtime_path(home) == runtime
