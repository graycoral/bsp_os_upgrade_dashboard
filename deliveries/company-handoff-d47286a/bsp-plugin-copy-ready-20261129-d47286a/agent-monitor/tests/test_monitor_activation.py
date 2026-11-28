"""Company activation command and Windows export port contract (T-323)."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'apps/agent-monitor'
pytestmark = pytest.mark.skipif(os.name == 'nt', reason='Agent Monitor runs on Linux/POSIX')


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.syspath_prepend(str(APP))
    spec = importlib.util.spec_from_file_location('monitor_activation_manager', APP / 'manage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def installation(manager, tmp_path, monkeypatch):
    home, runtime, source = (tmp_path / name for name in ('managed-home', 'runtime', 'source'))
    release = home / 'releases' / 'copied-release'
    for folder in (source, release):
        folder.mkdir(parents=True)
        (folder / manager.MANIFEST).touch()
        (folder / 'requirements.lock').write_text('fixture lock')
    manager.atomic(home / 'current.json', {'release': release.name, 'path': str(release)})
    manager.atomic(home / 'runtime-location.json', {'path': str(runtime)})
    monkeypatch.setattr(manager, 'verify', lambda path, **kwargs: {'release': release.name, 'include_ui': True})
    monkeypatch.setattr(manager, 'valid_environment', lambda path: Path(path) == release)
    return SimpleNamespace(home=home, runtime=runtime, source=source, release=release)


def test_cli_activation_without_installation_is_structured_and_cannot_provision(tmp_path):
    home = tmp_path / 'fresh-home'
    command = [sys.executable, '-B', str(APP / 'plugin.py'), '--home', str(home), 'monitor', 'ensure', '--no-provision']
    run = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert run.returncode == 6, run.stderr
    assert not run.stdout
    assert json.loads(run.stderr)['code'] == 'NOT_PROVISIONED'
    assert not (home / 'current.json').exists()
    assert not (home / 'install.log').exists()
    assert not (home / 'service.json').exists()


def test_cold_installed_and_concurrent_activation_join_without_provision(manager, installation, monkeypatch):
    install = installation
    ready, entered, resume = threading.Event(), threading.Event(), threading.Event()
    launches, results, failures = [], [], []
    receipt = {'port': 18766, 'runtime': str(install.runtime), 'release': install.release.name,
               'path': str(install.release), 'instance': 'managed-instance'}
    manager.atomic(install.home / 'service.json', receipt)
    monkeypatch.setattr(manager, 'active', lambda home: ready.is_set())
    monkeypatch.setattr(manager, 'health', lambda port: {'worker_running': True, 'managed_instance': receipt['instance'],
        'managed_runtime': receipt['runtime'], 'managed_release': receipt['release'], 'managed_source': receipt['path']})
    monkeypatch.setattr(manager, 'prepare', lambda *a, **k: pytest.fail('unexpected source/dependency installation'))
    import prerequisites
    monkeypatch.setattr(prerequisites, 'prepare', lambda *a, **k: pytest.fail('unexpected tool provisioning'))

    def launch(home, installed, port):
        launches.append((home, installed['path'], port))
        entered.set()
        assert resume.wait(5)
        ready.set()
        return manager.status(home)

    monkeypatch.setattr(manager, 'launch_service', launch, raising=False)

    def ensure():
        try:
            result = manager.ensure(install.home, install.source, runtime=install.runtime, no_provision=True)
            results.append(result)
        except BaseException as exc:
            failures.append(exc)
            entered.set()

    threads = [threading.Thread(target=ensure) for _ in range(2)]
    threads[0].start()
    try:
        assert entered.wait(5)
        threads[1].start()
        time.sleep(0.2)
    finally:
        resume.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join(5)
    assert not failures
    assert all(not thread.is_alive() for thread in threads)
    assert launches == [(install.home, str(install.release), 18766)]
    assert sorted(result['reused'] for result in results) == [False, True]
    for result in results:
        assert result['state'] == 'READY'
        assert result['runtime'] == str(install.runtime)
        assert result['release'] == install.release.name
        assert result['port'] == 18766
        assert result['url'] == 'http://127.0.0.1:18766'
        assert set(result) == {'state', 'home', 'runtime', 'release', 'port', 'url', 'reused'}


@pytest.mark.parametrize(('case', 'expected'), [
    ('runtime', 'RUNTIME_MISMATCH'), ('release', 'UPDATE_REQUIRED'),
    ('headless', 'UI_UNAVAILABLE'), ('environment', 'NOT_PROVISIONED'),
])
def test_preflight_rejects_unusable_owned_installation(manager, installation, tmp_path, monkeypatch, capsys, case, expected):
    install = installation
    runtime = tmp_path / 'wrong-runtime' if case == 'runtime' else install.runtime
    if case in {'release', 'headless'}:
        def verify(path, **kwargs):
            release_id = 'different' if Path(path) == install.source and case == 'release' else install.release.name
            return {'release': release_id, 'include_ui': case != 'headless'}
        monkeypatch.setattr(manager, 'verify', verify)
    if case == 'environment':
        monkeypatch.setattr(manager, 'valid_environment', lambda path: False)
    monkeypatch.setattr(manager, 'prepare', lambda *a, **k: pytest.fail('unexpected installation'))
    monkeypatch.setattr(manager, 'launch_service', lambda *a, **k: pytest.fail('unexpected launch'), raising=False)
    command = ['ensure', '--home', str(install.home), '--source', str(install.source),
               '--runtime', str(runtime), '--no-provision']
    assert manager.main(command) == (6 if case == 'environment' else 1)
    captured = capsys.readouterr()
    assert not captured.out
    output = json.loads(captured.err)
    assert output['state'] == 'ERROR'
    assert output['code'] == expected
    assert manager.runtime_path(install.home) == install.runtime
    assert not (install.home / 'service.json').exists()


def test_busy_activation_is_bounded_and_does_not_spawn(manager, installation, monkeypatch):
    install = installation
    monkeypatch.setattr(manager, 'START_TIMEOUT', 0.05)
    monkeypatch.setattr(manager, 'launch_service', lambda *a, **k: pytest.fail('unexpected launch'))
    with manager.lock(install.home / 'start.lock'):
        with pytest.raises(manager.MonitorActivationError) as error:
            manager.ensure(install.home, install.source, no_provision=True)
        assert error.value.code == 'START_PENDING'
    assert not (install.home / 'service.json').exists()


def test_running_monitor_with_different_port_is_not_restarted(manager, installation, monkeypatch):
    install = installation
    receipt = {'port': 18766, 'runtime': str(install.runtime), 'release': install.release.name,
               'path': str(install.release), 'instance': 'service-instance'}
    manager.atomic(install.home / 'service.json', receipt)
    monkeypatch.setattr(manager, 'launch_service', lambda *a, **k: pytest.fail('unexpected launch'))
    monkeypatch.setattr(manager, 'stop', lambda *a, **k: pytest.fail('unexpected stop'))
    monkeypatch.setattr(manager, 'prepare', lambda *a, **k: pytest.fail('unexpected installation'))
    with manager.lock(install.home / 'service.lock'):
        with pytest.raises(manager.MonitorActivationError) as error:
            manager.ensure(install.home, install.source, port=18767)
        assert error.value.code == 'PORT_CONFLICT'
        assert manager.read(install.home / 'service.json') == receipt


@pytest.mark.parametrize('existing', [False, True])
def test_normal_activation_provisions_cold_installation_once(manager, installation, monkeypatch, existing):
    import prerequisites
    install = installation
    if not existing:
        (install.home / 'current.json').unlink()
    ready, provisioned = threading.Event(), threading.Event()
    events = []
    installed = {'release': install.release.name, 'path': str(install.release)}

    def prepare_tools(home, *, apply):
        assert home == install.home and apply is True
        events.append('tools')
        return {'state': 'READY'}

    def prepare(source, home, python):
        assert source == install.source and home == install.home
        events.append('install')
        manager.atomic(home / 'current.json', installed)
        provisioned.set()
        return installed | {'state': 'INSTALLED'}

    def launch(home, current, port):
        assert current == installed and port == 18762
        events.append('launch')
        manager.atomic(home / 'service.json', {'instance': 'new-instance', 'port': port,
            'release': installed['release'], 'path': installed['path'], 'runtime': str(install.runtime)})
        ready.set()
        return manager.status(home)

    monkeypatch.setenv('BSP_PORT', '18762')
    monkeypatch.setattr(prerequisites, 'prepare', prepare_tools)
    monkeypatch.setattr(manager, 'prepare', prepare)
    monkeypatch.setattr(manager, 'launch_service', launch)
    monkeypatch.setattr(manager, 'valid_environment', lambda path: provisioned.is_set())
    monkeypatch.setattr(manager, 'active', lambda home: ready.is_set())
    monkeypatch.setattr(manager, 'health', lambda port: {'worker_running': True, 'managed_instance': 'new-instance',
        'managed_runtime': str(install.runtime), 'managed_release': installed['release'], 'managed_source': installed['path']})

    first = manager.ensure(install.home, install.source, runtime=install.runtime)
    monkeypatch.setenv('BSP_PORT', '18763')
    second = manager.ensure(install.home, install.source, runtime=install.runtime)
    assert events == ['tools', 'install', 'launch']
    assert first == second | {'reused': False}
    assert second['reused'] is True and second['port'] == 18762


@pytest.mark.parametrize('configured', [None, 18888])
def test_monitor_preserves_default_and_configured_reverse_port(manager, installation, monkeypatch, configured):
    from backend.gui_test.core.shared_settings_store import SharedSettingsStore

    install = installation
    if configured is not None:
        store = SharedSettingsStore(install.runtime)
        store.save_preferences({'preferred_connector_port': configured})
        before = store.path.read_bytes()
    monkeypatch.setattr(manager, 'launch_service', lambda *a, **k: pytest.fail('unexpected launch'))
    with pytest.raises(manager.MonitorActivationError) as error:
        manager.ensure(install.home, install.source, port=configured or 8771, no_provision=True)
    assert error.value.code == 'PORT_CONFLICT'
    if configured is not None:
        assert store.path.read_bytes() == before


def test_managed_export_port_requires_matching_home_runtime_and_release(manager, installation, tmp_path):
    install = installation
    receipt = {'port': 18766, 'runtime': str(install.runtime), 'release': install.release.name,
               'path': str(install.release), 'instance': 'owned-instance'}
    manager.atomic(install.home / 'service.json', receipt)
    assert manager.managed_monitor_port(install.home, install.runtime) == 18766
    assert manager.managed_monitor_port(install.home, tmp_path / 'other-runtime') is None
    assert manager.managed_monitor_port(tmp_path / 'other-home', install.runtime) is None

    manager.remember_monitor_port(install.home, install.runtime, {'release': install.release.name, 'path': str(install.release)}, 18766)
    (install.home / 'service.json').unlink()
    assert manager.managed_monitor_port(install.home, install.runtime) == 18766
    manager.atomic(install.home / 'current.json', {'release': 'different', 'path': str(install.release)})
    assert manager.managed_monitor_port(install.home, install.runtime) is None


def test_export_monitor_port_precedence_and_legacy_headless(tmp_path, monkeypatch):
    from backend.gui_test.standalone import direct_connector_client, plugin_commands

    exports = []
    monkeypatch.setattr(direct_connector_client, 'export_windows_bootstrap_local',
                        lambda source, output, **fields: exports.append(fields) or {'state': 'EXPORTED'})
    home, runtime = tmp_path / 'home', tmp_path / 'runtime'
    direct = SimpleNamespace(home=home, runtime_dir=runtime, port=8771,
                             store=SimpleNamespace(read_preferences=lambda: {}))
    command = ['connect', 'export', '--output', str(tmp_path / 'windows'), '--server', 'linux.example', '--account', 'bsp']

    def export(*args, **kwargs):
        assert plugin_commands.execute_direct(direct, [*command, *args], source_root=ROOT, **kwargs) == 0
        return exports[-1]['remote_dashboard_port']

    monkeypatch.setenv('BSP_PORT', '18766')
    assert export() is None
    assert export(managed_monitor_port=lambda: 18763) == 18763
    assert export(monitor_port=18765, managed_monitor_port=lambda: 18763) == 18765
    assert export('--remote-dashboard-port', '18764', monitor_port=18765) == 18764
    assert export('--without-monitor', monitor_port=18765, managed_monitor_port=lambda: 18763) is None
    with pytest.raises(SystemExit) as error:
        export('--without-monitor', '--remote-dashboard-port', '18764')
    assert error.value.code == 2
