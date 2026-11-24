"""RQ-61: editable isolation and real OS socket/lock boundaries (no devices)."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from backend.gui_test.execution import bundle


@pytest.fixture
def editable(tmp_path, monkeypatch):
    root = tmp_path / '편집 Runner space'
    interpreter = root / 'runtime/python.exe'
    module = root / 'src/backend/gui_test/execution/bundle.py'
    interpreter.parent.mkdir(parents=True)
    module.parent.mkdir(parents=True)
    interpreter.touch()
    module.touch()
    (root / 'deps').mkdir()
    (root / 'bundle.json').write_text(json.dumps({
        'version': 1, 'mode': 'editable', 'python': 'runtime/python.exe',
        'source': 'src', 'dependencies': 'deps', 'python_version': '3.12.10',
        'platform': 'win_amd64'}), encoding='utf-8')
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.setattr(sys, 'executable', str(interpreter))
    monkeypatch.setattr(bundle, '__file__', str(module))
    return root


def test_editable_requires_matching_interpreter_and_code_location(editable, monkeypatch):
    assert bundle.runtime_mode() == 'editable'
    assert bundle.editable_root() == editable.resolve()
    assert editable.resolve() in bundle.bundle_roots()
    assert not bundle.is_frozen()
    monkeypatch.setattr(bundle, '__file__', str(editable / 'unrelated/bundle.py'))
    with pytest.raises(ValueError):
        bundle.runtime_mode()


@pytest.mark.parametrize('field,value', [('python', '../python.exe'), ('mode', 'unknown'),
                                          ('source', '../src'), ('dependencies', 'elsewhere')])
def test_malformed_marker_never_silently_becomes_source(editable, field, value):
    path = editable / 'bundle.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data[field] = value
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        bundle.runtime_mode()


def test_editable_external_tc_python_and_child_environment_are_isolated(editable, tmp_path):
    external = tmp_path / 'separate TC/python.exe'
    external.parent.mkdir()
    external.touch()
    assert bundle.validate_external_python(external) == str(external.resolve())
    for path in [editable / 'runtime/python.exe', editable / 'deps/python.exe']:
        path.touch()
        with pytest.raises(ValueError):
            bundle.validate_external_python(path)
    overlay = str(tmp_path / 'external TC modules')
    env = {'GUI_TEST_RUNNER_TOKEN': 'private-token',
           'PYTHONPATH': os.pathsep.join([str(editable / 'src'), overlay]),
           'PYTHONHOME': str(editable / 'runtime'),
           'PATH': os.pathsep.join([str(editable / 'runtime'), str(external.parent)]), 'TC_SETTING': 'keep'}
    original = env.copy()
    clean = bundle.external_environment(env)
    assert env == original
    assert 'GUI_TEST_RUNNER_TOKEN' not in clean
    assert 'PYTHONHOME' not in clean
    assert clean['PYTHONPATH'] == overlay
    assert clean['PATH'] == str(external.parent)
    assert clean['TC_SETTING'] == 'keep'


def test_loopback_fallback_uses_owned_listening_socket_but_explicit_conflict_fails():
    from backend.gui_test.execution.launch import bind_loopback
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        with pytest.raises(OSError):
            bind_loopback(port, allow_fallback=False)
        with bind_loopback(port, allow_fallback=True) as selected:
            assert selected.getsockname()[0] == '127.0.0.1'
            assert selected.getsockname()[1] != port
            with socket.create_connection(selected.getsockname(), timeout=2):
                connection, _ = selected.accept()
                connection.close()


@pytest.mark.parametrize('value', [True, -1, 65536, '8771'])
def test_loopback_rejects_invalid_port(value):
    from backend.gui_test.execution.launch import bind_loopback
    with pytest.raises(ValueError):
        bind_loopback(value)


def test_launch_lock_excludes_another_os_process_and_releases_after_exception(tmp_path):
    from backend.gui_test.execution.launch import LaunchLock
    path = tmp_path / 'setup-launch.lock'
    code = '''
import sys
from pathlib import Path
from backend.gui_test.execution.launch import LaunchLock
try:
    with LaunchLock(Path(sys.argv[1])): pass
except RuntimeError:
    sys.exit(23)
'''
    with pytest.raises(LookupError):
        with LaunchLock(path):
            result = subprocess.run([sys.executable, '-B', '-c', code, str(path)],
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == 23, result.stderr
            raise LookupError('release on failure')
    with LaunchLock(path):
        pass


def test_process_identity_detects_live_child_and_does_not_accept_dead_pid():
    from backend.gui_test.execution.launch import process_identity
    with subprocess.Popen([sys.executable, '-B', '-c', 'import time; time.sleep(30)']) as child:
        try:
            identity = process_identity(child.pid)
            assert identity['pid'] == child.pid
            assert isinstance(identity['creation_time'], str) and identity['creation_time']
            assert process_identity(child.pid) == identity
        finally:
            child.terminate()
            child.wait(timeout=5)
    assert process_identity(child.pid) is None


def test_startup_nonce_pid_creation_and_missing_are_distinct(tmp_path):
    from backend.gui_test.execution.launch import read_startup, write_receipt
    path = tmp_path / 'launch.json'
    owner = {'pid': 101, 'creation_time': 'owner-generation'}
    runner = {'pid': 202, 'creation_time': 'runner-generation'}
    nonce = 'a' * 32
    assert read_startup(path, launch_id=nonce, owner=owner, runner=runner) is None
    receipt = {'version': 1, 'launch_id': nonce, 'owner': owner, 'runner': runner,
               'runner_id': 'c' * 32, 'runner_port': 18771}
    write_receipt(path, receipt)
    assert read_startup(path, launch_id=nonce, owner=owner, runner=runner) == receipt
    for kwargs in [dict(launch_id='b' * 32, owner=owner, runner=runner),
                   dict(launch_id=nonce, owner={**owner, 'creation_time': 'reused'}, runner=runner),
                   dict(launch_id=nonce, owner=owner, runner={**runner, 'pid': 203})]:
        with pytest.raises(ValueError):
            read_startup(path, **kwargs)
    path.write_text('{broken', encoding='utf-8')
    with pytest.raises(ValueError):
        read_startup(path, launch_id=nonce, owner=owner, runner=runner)


def test_cleanup_removes_only_own_nonce_and_preserves_other_launch(tmp_path):
    from backend.gui_test.execution.launch import remove_owned_receipts, write_receipt
    own, other = 'a' * 32, 'b' * 32
    # Cleanup must also tolerate incomplete records from an interrupted write.
    for name, nonce in [('launch-' + own + '.json', own),
                        ('launch-' + other + '.json', other), ('active-endpoints.json', other)]:
        (tmp_path / name).write_text(json.dumps({'launch_id': nonce}), encoding='utf-8')
    remove_owned_receipts(tmp_path, own)
    assert not (tmp_path / ('launch-' + own + '.json')).exists()
    assert (tmp_path / ('launch-' + other + '.json')).exists()
    assert json.loads((tmp_path / 'active-endpoints.json').read_text())['launch_id'] == other


@pytest.mark.parametrize('case', ['valid', 'unrelated', 'newer-parent', 'cycle', 'reused-generation'])
def test_startup_redirector_requires_generation_stable_ancestry(tmp_path, monkeypatch, case):
    from backend.gui_test.execution import launch
    def identity(pid, born):
        return {'pid': pid, 'creation_time': str(born) if os.name == 'nt' else 'fixture-boot:' + str(born)}
    owner, redirector = identity(101, 100), identity(202, 200)
    middle, python = identity(250, 250), identity(303, 300)
    identities = {v['pid']: v for v in (owner, redirector, middle, python)}
    parents = {303: 250, 250: 202}
    if case == 'unrelated': parents = {303: 999}
    if case == 'newer-parent': identities[250] = identity(250, 500)
    if case == 'cycle': parents = {303: 250, 250: 303}
    observations = {}
    def inspect(pid):
        observations[pid] = observations.get(pid, 0) + 1
        if case == 'reused-generation' and pid == 250 and observations[pid] > 1:
            return identity(pid, 999)
        return identities.get(pid)
    monkeypatch.setattr(launch, 'process_identity', inspect)
    monkeypatch.setattr(launch, '_process_parents', lambda: parents)
    path = tmp_path / 'startup.json'
    nonce = 'a' * 32
    value = {'version': 1, 'launch_id': nonce, 'owner': owner, 'runner': python,
             'runner_id': 'c' * 32, 'runner_port': 18771}
    launch.write_receipt(path, value)
    if case == 'valid':
        assert launch.read_startup(path, launch_id=nonce, owner=owner, runner=redirector) == value
    else:
        with pytest.raises(ValueError):
            launch.read_startup(path, launch_id=nonce, owner=owner, runner=redirector)
