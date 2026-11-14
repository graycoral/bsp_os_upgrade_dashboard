"""No network/installation/process side effects: manager lifecycle ownership contracts."""
import importlib.util
import json
import os
import sqlite3
import subprocess
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
    monkeypatch.setattr(manager, 'verify', lambda path: {'release': 'a' * 64})
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
