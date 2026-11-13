"""Portable Runner boundaries; no board, SSH server, or model calls."""
import io
import os
from contextlib import contextmanager
from pathlib import Path
import sys
import types

import pytest

from backend.gui_test.execution import bundle
from scripts import setup_runtime as setup
from scripts import windows_runner_entry as entry


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    root = tmp_path / 'portable Runner 한글'
    internal = root / '_internal'
    internal.mkdir(parents=True)
    exe = root / 'BSPRunner.exe'
    exe.touch()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(internal), raising=False)
    monkeypatch.setattr(sys, 'executable', str(exe))
    return root, internal, exe


def test_bundle_roots_are_only_present_in_frozen_runtime(monkeypatch, frozen):
    root, internal, _ = frozen
    assert bundle.is_frozen()
    assert {root.resolve(), internal.resolve()} <= set(bundle.bundle_roots())
    monkeypatch.delattr(sys, 'frozen')
    assert not bundle.is_frozen()
    assert bundle.bundle_roots() == ()


@pytest.mark.parametrize('choice', ['', 'relative-python.exe', None])
def test_external_python_requires_explicit_existing_file(choice, frozen):
    with pytest.raises(ValueError):
        bundle.validate_external_python(choice)


def test_external_python_rejects_bundle_and_missing_but_accepts_separate_tc_runtime(frozen, tmp_path):
    root, internal, exe = frozen
    bundled = internal / 'python.exe'
    bundled.touch()
    for path in (exe, bundled, root, tmp_path / 'missing.exe'):
        with pytest.raises(ValueError):
            bundle.validate_external_python(str(path))
    external = tmp_path / 'TC Python 한글' / 'python.exe'
    external.parent.mkdir()
    external.touch()
    assert bundle.validate_external_python(str(external)) == str(external.resolve())


def test_external_environment_removes_secrets_bootloader_and_bundle_paths_without_mutation(frozen, tmp_path):
    root, internal, _ = frozen
    keep = tmp_path / 'TC Python'
    sibling = Path(str(root) + '-other')
    original = {'gui_test_runner_token': 'never-forward', '_PYI_APPLICATION_HOME_DIR': str(root),
                '_PYI_PARENT_PROCESS_LEVEL': '1', 'KEEP': 'value',
                'PATH': os.pathsep.join(map(str, [internal, root, internal / 'nested', keep, sibling]))}
    saved = original.copy()
    result = bundle.external_environment(original)
    assert original == saved
    assert result is not original
    assert not any(k.upper() == 'GUI_TEST_RUNNER_TOKEN' or k.upper().startswith('_PYI_') for k in result)
    assert result['KEEP'] == 'value'
    assert result['PATH'].split(os.pathsep) == [str(keep), str(sibling)]


@pytest.mark.parametrize('gate', [b'', b'?', b'\n'])
def test_contained_child_never_launches_without_gate(monkeypatch, gate):
    monkeypatch.setattr(sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(gate)))
    monkeypatch.setattr(bundle.subprocess, 'call', lambda *a, **k: pytest.fail('ungated execution'))
    assert bundle.contained_child(['external.exe', 'tc.py']) == 125


def test_contained_child_preserves_argv_exit_and_strips_token(monkeypatch):
    monkeypatch.setattr(sys, 'stdin', types.SimpleNamespace(buffer=io.BytesIO(b'!')))
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', 'must-not-leak')
    calls = []
    monkeypatch.setattr(bundle.subprocess, 'call', lambda argv, **kw: calls.append((argv, kw)) or 7)
    argv = ['C:/TC Python/python.exe', 'C:/공유 TC/pass.py', 'arg with spaces', '&literal']
    assert bundle.contained_child(argv) == 7
    actual, options = calls.pop()
    assert actual == argv
    assert options['stdin'] == bundle.subprocess.DEVNULL
    assert options.get('shell', False) is False
    assert 'GUI_TEST_RUNNER_TOKEN' not in options['env']


@pytest.mark.parametrize('args', [['--contained-child'], ['--contained-child', 'x'],
                                 ['--contained-child', '--']])
def test_entry_rejects_malformed_helper_before_dispatch(monkeypatch, args):
    monkeypatch.setattr(bundle, 'contained_child', lambda *_: pytest.fail('malformed helper dispatched'))
    assert entry.main(args) == 2


def test_entry_dispatches_only_fixed_lazy_modes(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, 'backend.gui_test.execution.host', types.SimpleNamespace(
        main=lambda args: calls.append(('host', args)) or 4))
    monkeypatch.setattr(setup, 'main', lambda args: calls.append(('wizard', args)) or 3)
    monkeypatch.setattr(bundle, 'contained_child', lambda args: calls.append(('child', args)) or 5)
    assert entry.main(['--home', 'private settings']) == 3
    assert entry.main(['--runner', '--config', 'runner.json']) == 4
    assert entry.main(['--contained-child', '--', 'python.exe', 'tc.py']) == 5
    assert calls == [('wizard', ['--home', 'private settings']),
                     ('host', ['--config', 'runner.json']), ('child', ['python.exe', 'tc.py'])]


def test_frozen_wizard_reuses_home_and_skips_dependency_install(frozen, tmp_path, monkeypatch):
    root, _, exe = frozen
    home = tmp_path / 'existing private home'
    setup.save_json(home / 'windows-runner.json', {'_setup': {'server': 'saved.example', 'account': 'user'}})
    w = setup.Wizard(root=tmp_path / 'absent-source', windows=True, home=home)
    assert Path(w.python) == exe
    assert w.root == root
    assert w.runtime == home / 'runtime'
    assert w.config == home / 'windows-runner.json'
    assert w.state['server'] == 'saved.example'
    monkeypatch.setattr(w, 'command', lambda *_a, **_k: pytest.fail('frozen pip/venv invoked'))
    monkeypatch.setattr(setup, 'yes', lambda *_a, **_k: True)
    w.install()
    assert not (home / 'venv').exists()


def test_source_wizard_keeps_venv_install_contract(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    root = tmp_path / 'source'
    root.mkdir()
    w = setup.Wizard(root=root, windows=True, home=tmp_path / 'private')
    assert w.python == w.home / 'venv' / 'Scripts' / 'python.exe'
    calls = []
    monkeypatch.setattr(setup, 'yes', lambda *_a, **_k: True)
    monkeypatch.setattr(w, 'command', lambda argv: calls.append([str(v) for v in argv]))
    w.install()
    assert calls[0][1:3] == ['-m', 'venv']
    assert calls[1][1:4] == ['-m', 'pip', 'install']


@pytest.mark.parametrize('choice', ['unset', 'bundled', 'missing'])
def test_frozen_host_allows_status_but_requires_separate_tc_python_for_execution(
        frozen, tmp_path, monkeypatch, choice):
    from fastapi.testclient import TestClient
    from backend.gui_test.execution.host import Host, create_app
    from backend.gui_test.core.models import TestError
    from backend.gui_test.execution import host as host_module
    source = tmp_path / 'TC'
    source.mkdir()
    board = {'host': 'fixture', 'board_id': 'a', 'com': 'COM31'}
    config = {'source_root': str(source), 'boards': [board]}
    if choice != 'unset':
        config['python'] = str(frozen[2] if choice == 'bundled' else frozen[1] / 'missing.exe')
    host = Host(config, tmp_path / 'runtime', ports=lambda: {'COM31'})
    assert host.python is None
    monkeypatch.setattr(host_module, 'ProcessTree',
                        lambda *a, **k: pytest.fail('invalid TC Python launched a process'))
    token = 'fixture-token-' + 'a' * 48
    with TestClient(create_app(host, token), client=('127.0.0.1', 50000)) as client:
        response = client.get('/v1/identity', headers={'Authorization': 'Bearer ' + token})
        assert response.status_code == 200
        assert response.json()['tc_python_configured_v1'] is False
        assert host.inventory()['boards'][0]['detected'] is True
        with pytest.raises(TestError) as error:
            host.start({'id': 'a' * 32, 'tc_id': 'test_example.py', 'source_revision': 'fixture',
                        'connection': {'a': board},
                        'template': {'single': ['python', '{tc_path}', '{com_a}'],
                                     'dual': ['python', '{tc_path}', '{com_a}', '{com_b}']}})
        assert error.value.code == 'TC_PYTHON_NOT_CONFIGURED'
        assert error.value.status == 409
        assert not host.threads
        assert not (host.runtime / 'snapshots').exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows DLL directory API')
def test_external_dll_search_restores_on_exception(frozen, monkeypatch):
    import ctypes
    changes = []

    class Function:
        def __init__(self, callback): self.callback = callback
        def __call__(self, *args): return self.callback(*args)

    def get_dir(size, buffer):
        value = str(frozen[1])
        if size and buffer is not None:
            buffer.value = value
        return len(value)

    kernel = types.SimpleNamespace(GetDllDirectoryW=Function(get_dir),
                                   SetDllDirectoryW=Function(lambda value: changes.append(value) or 1))
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *_a, **_k: kernel)
    with pytest.raises(RuntimeError, match='fixture'):
        with bundle.external_dll_search():
            assert changes == [None]
            raise RuntimeError('fixture')
    assert changes == [None, str(frozen[1])]


def test_frozen_connection_never_defaults_tc_python_to_runner(frozen, tmp_path, monkeypatch):
    w = setup.Wizard(windows=True, home=tmp_path / 'private')
    source = tmp_path / 'shared TC'
    source.mkdir()
    defaults = []

    def checked(_label, default, *args):
        defaults.append(default)
        return str(source) if len(defaults) == 1 else str(frozen[2])

    monkeypatch.setattr(setup, 'checked_path', checked)
    monkeypatch.setattr(w, 'preview_save', lambda *_: pytest.fail('invalid TC interpreter persisted'))
    with pytest.raises(ValueError):
        w.connection()
    assert defaults == ['', '']


@pytest.mark.skipif(os.name != 'nt', reason='Windows Job Object startup')
def test_job_assignment_failure_kills_helper_without_opening_gate(frozen, tmp_path, monkeypatch):
    from backend.gui_test.execution import process
    events = []

    class Function:
        def __init__(self, callback): self.callback = callback
        def __call__(self, *args): return self.callback(*args)

    class Child:
        _handle = 123
        stdin = types.SimpleNamespace(write=lambda data: events.append(('gate', data)), close=lambda: None)
        def kill(self): events.append('kill')
        def wait(self): events.append('wait')

    kernel = types.SimpleNamespace(**{name: Function(lambda *args: 1) for name in
        ('CreateJobObjectW', 'AssignProcessToJobObject', 'TerminateJobObject', 'CloseHandle',
         'QueryInformationJobObject', 'SetInformationJobObject')})
    kernel.AssignProcessToJobObject = Function(lambda *_: 0)
    launches = []
    monkeypatch.setattr(process.ctypes, 'WinDLL', lambda *_a, **_k: kernel)
    monkeypatch.setattr(process.subprocess, 'Popen', lambda argv, **kw: launches.append((argv, kw)) or Child())
    with pytest.raises(OSError, match='assign'):
        process.ProcessTree(['external-python.exe', 'fixture.py'], tmp_path, None, None)
    assert launches[0][0] == [str(frozen[2]), '--contained-child', '--', 'external-python.exe', 'fixture.py']
    assert events == ['kill', 'wait']


@pytest.mark.parametrize('ssh_outcome', ['exit-zero', 'exit-failure', 'spawn-failure'])
@pytest.mark.parametrize('runner_port', [8771, 18771], ids=['default-port', 'custom-port'])
def test_frozen_wizard_start_scopes_environment_and_waits_for_owned_runner(
        frozen, tmp_path, monkeypatch, ssh_outcome, runner_port):
    root, internal, exe = frozen
    external = tmp_path / 'external TC Python' / 'python.exe'
    external.parent.mkdir()
    external.touch()
    w = setup.Wizard(windows=True, home=tmp_path / 'saved private home', runner_port=runner_port)
    w.state = {'server': 'fixture.invalid', 'account': 'operator', 'ssh_port': 22}
    setup.save_json(w.config, {'python': str(external), '_setup': w.state})
    config_before = w.config.read_bytes()
    token = 'fixture-token-' + 'a' * 48
    outside = tmp_path / 'system tools'
    ssh_exe = str(outside / 'ssh.exe')
    monkeypatch.setenv('PATH', os.pathsep.join(map(str, [root, internal, outside])))
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', 'old-parent-token')
    monkeypatch.setenv('gui_test_runner_token', 'old-lowercase-token')
    monkeypatch.setenv('_PYI_APPLICATION_HOME_DIR', str(internal))
    monkeypatch.setenv('FIXTURE_KEEP', 'preserved')
    monkeypatch.setattr(w.tokens, 'load', lambda: pytest.fail('Unexpected connection token read'))
    monkeypatch.setattr(setup.subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x200, raising=False)
    monkeypatch.setattr(setup.signal, 'CTRL_BREAK_EVENT', 21, raising=False)
    monkeypatch.setattr(setup, 'require_free', lambda _port: None)
    events = []
    spawned = []

    class Runner:
        pid = 12345
        returncode = None
        waits = 0
        def poll(self): return self.returncode
        def send_signal(self, value):
            assert value == setup.signal.CTRL_BREAK_EVENT
            events.append('runner-break')
        def wait(self, timeout):
            assert timeout == 1
            events.append('runner-wait')
            self.waits += 1
            if self.waits == 1:
                raise setup.subprocess.TimeoutExpired('fixture-runner', timeout)
            self.returncode = 0
            return 0
        def terminate(self): pytest.fail('owned Runner forcibly terminated')
        def kill(self): pytest.fail('owned Runner forcibly killed')

    class Transport:
        returncode = 0 if ssh_outcome == 'exit-zero' else 7
        def poll(self): return self.returncode
        def terminate(self): pytest.fail('already exited SSH terminated')
        def kill(self): pytest.fail('already exited SSH killed')

    runner = Runner()
    actual_lock = setup.LaunchLock
    ready = []
    monkeypatch.setattr(setup, 'process_identity', lambda pid: {'pid': pid, 'creation_time': 'fixture-created'})
    def startup(path, *, launch_id, owner, runner):
        ready.append(True)
        return {'version': 1, 'launch_id': launch_id, 'owner': owner, 'runner': runner,
                'runner_id': 'c' * 32, 'runner_port': runner_port}
    monkeypatch.setattr(setup, 'read_startup', startup)
    class Lock:
        def __init__(self, path): self.path = Path(path)
        def __enter__(self):
            if self.path.name == 'runner.lock' and ready:
                raise RuntimeError('fixture owned Host lock')
            self.lock = actual_lock(self.path)
            return self.lock.__enter__()
        def __exit__(self, *args): return self.lock.__exit__(*args)
    monkeypatch.setattr(setup, 'LaunchLock', Lock)

    def which(name, *, path):
        assert name == 'ssh'
        assert path == str(outside)
        return ssh_exe

    @contextmanager
    def dll_context():
        events.append('dll-reset')
        try:
            yield
        finally:
            events.append('dll-restore')

    def popen(argv, **options):
        spawned.append((argv, options))
        assert options['cwd'] == root
        assert options['creationflags'] == setup.subprocess.CREATE_NEW_PROCESS_GROUP
        if len(spawned) == 1:
            events.append('runner-spawn')
            assert argv[:8] == [str(exe), '--runner', '--config', str(w.config),
                               '--runtime', str(w.runtime), '--port', str(runner_port)]
            assert '--launch-id' in argv and '--startup-receipt' in argv
            assert '--allow-port-fallback' not in argv  # explicit CLI remains fixed
            assert setup.TOKEN_ENV not in options['env']
            return runner
        assert events[-1] == 'dll-reset', 'SSH must spawn inside the external DLL context'
        events.append('ssh-spawn')
        assert argv[0] == ssh_exe
        assert argv[-3:] == ['-l', 'operator', 'fixture.invalid']
        assert argv[argv.index('-R') + 1] == f'127.0.0.1:8771:127.0.0.1:{runner_port}'
        env = options['env']
        assert env['PATH'] == str(outside)
        assert env['FIXTURE_KEEP'] == 'preserved'
        assert not any(k.upper() == setup.TOKEN_ENV or k.upper().startswith('_PYI_') for k in env)
        if ssh_outcome == 'spawn-failure':
            raise OSError('fixture SSH launch failed')
        return Transport()

    def identity(path, supplied_token, port=8771):
        assert path == '/identity' and supplied_token is None and port == runner_port
        return {'runner_id': 'c' * 32}

    monkeypatch.setattr(setup.shutil, 'which', which)
    monkeypatch.setattr(setup, 'external_dll_search', dll_context)
    monkeypatch.setattr(setup.subprocess, 'Popen', popen)
    monkeypatch.setattr(setup, 'runner_get', identity)
    if ssh_outcome == 'spawn-failure':
        with pytest.raises(setup.RunFailure) as failure:
            w.start()
        assert failure.value.stage == 'ssh'
        assert failure.value.category == 'CONNECT'
        assert failure.value.port == w.ssh_port
        assert isinstance(failure.value.__cause__, OSError)
        assert str(failure.value.__cause__) == 'fixture SSH launch failed'
    elif ssh_outcome == 'exit-failure':
        with pytest.raises(RuntimeError, match='SSH'):
            w.start()
    else:
        w.start()
    assert events == ['runner-spawn', 'dll-reset', 'ssh-spawn', 'dll-restore',
                      'runner-break', 'runner-wait', 'runner-wait']
    assert runner.returncode == 0
    assert w.config.read_bytes() == config_before
    assert w.runtime == w.home / 'runtime'
