"""Nonsecret preconnection handoff: local mocks, no SSH, installs or hardware."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.connector.bootstrap import import_profile
from backend.gui_test.core.connector_bootstrap import FORMAT, load_profile, verify_service, service_headers
from backend.gui_test.core.models import TestError
from backend.gui_test.execution.launch import LaunchLock
from backend.gui_test.standalone.integration import create_app
from backend.gui_test.standalone.plugin_client import PluginClient


@pytest.fixture
def profile(tmp_path):
    path = tmp_path / 'connection.json'
    value = {'format': FORMAT, 'endpoint': {'server': 'linux.company.test', 'account': 'bsp-user', 'ssh_port': 2222,
                                          'remote_dashboard_port': 9876},
             'identity': {'runtime_id': 'a' * 64, 'package_version': '0.1.0'}}
    path.write_text(json.dumps(value))
    return path, value


def test_plugin_exports_explicit_endpoint_and_server_owned_identity(tmp_path):
    app = create_app(tmp_path / 'linux', start_worker=False)
    with TestClient(app, client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        health = http.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin'}).json()
        plugin = PluginClient('http://127.0.0.1', expected_identity={key: health[key] for key in ('runtime_id', 'package_version')}, client=http)
        path = tmp_path / 'handoff.json'
        exported = plugin.export_connector_bootstrap(server='10.20.30.40', account='actual-user', ssh_port=2222,
                                                     remote_dashboard_port=9988, path=path)
        assert load_profile(path).model_dump() == exported
        assert exported['identity']['runtime_id'] == health['runtime_id']
        assert exported['endpoint']['remote_dashboard_port'] == 9988
        assert set(exported) == {'format', 'endpoint', 'identity'}
        assert app.state.registry.manager.shared_settings.read()['integration']['tc_root'] == ''
        bad = exported['endpoint'] | {'password': 'injected', 'ssh_key': 'injected'}
        response = http.post('/api/v1/gui-test/live/integration/connector-bootstrap', json=bad,
                             headers={'X-Bsp-Service': 'plugin'})
        assert response.status_code == 422


def test_initial_import_needs_no_board_and_preserves_every_local_field(tmp_path, profile):
    path, value = profile
    home = tmp_path / 'windows'
    home.mkdir()
    original = {'boards': [], 'custom': {'keep': True}, '_setup': {'ssh_key': 'C:/private/key', 'extra': 9}, 'python': 'C:/TC/python.exe'}
    target = home / 'windows-runner.json'
    target.write_text(json.dumps(original))
    receipt = import_profile(home, path)
    saved = json.loads(target.read_text())
    assert receipt['state'] == 'IMPORTED'
    assert saved['_setup']['ssh_key'] == original['_setup']['ssh_key']
    assert saved['python'] == original['python'] and saved['custom'] == original['custom'] and saved['boards'] == []
    assert saved['_setup']['server'] == value['endpoint']['server']
    assert json.loads(next(home.glob('windows-runner.json.*.bak')).read_text()) == original
    import_profile(home, path)
    assert len(list(home.glob('windows-runner.json.*.bak'))) == 2


@pytest.mark.parametrize('lock', ['connector-manager.lock', 'setup-launch.lock', 'runner.lock'])
def test_active_process_locks_block_before_any_profile_write(tmp_path, profile, lock):
    home = tmp_path / 'windows'
    with LaunchLock(home / 'runtime' / lock):
        with pytest.raises(TestError) as error:
            import_profile(home, profile[0])
        assert error.value.code == 'CONNECTOR_BUSY'
    assert not (home / 'windows-runner.json').exists()


@pytest.mark.parametrize('job,batch', [({'state': 'UNKNOWN', 'terminated': False}, None),
    ({'state': 'RUNNING', 'terminated': False}, None), ({'state': 'DONE', 'terminated': False}, None),
    (None, {'state': 'RESERVED'}), (None, {'state': 'UNKNOWN'})])
def test_durable_active_unknown_and_reservations_block_import(tmp_path, profile, job, batch):
    home = tmp_path / 'windows'; runtime = home / 'runtime'; runtime.mkdir(parents=True)
    with sqlite3.connect(runtime / 'executions.db') as c:
        c.execute('CREATE TABLE jobs(data TEXT)'); c.execute('CREATE TABLE batches(data TEXT)')
        if job: c.execute('INSERT INTO jobs VALUES(?)', (json.dumps(job),))
        if batch: c.execute('INSERT INTO batches VALUES(?)', (json.dumps(batch),))
    with pytest.raises(TestError) as error: import_profile(home, profile[0])
    assert error.value.code == 'CONNECTOR_BUSY' and not (home / 'windows-runner.json').exists()


def test_corrupt_database_is_not_treated_as_an_empty_install(tmp_path, profile):
    home = tmp_path / 'windows'; runtime = home / 'runtime'; runtime.mkdir(parents=True)
    (runtime / 'executions.db').write_bytes(b'invalid')
    with pytest.raises(TestError) as error: import_profile(home, profile[0])
    assert error.value.code == 'CONNECTOR_BUSY'


@pytest.mark.parametrize('mutation', [lambda v: v.pop('format'), lambda v: v.update(format='v2'),
    lambda v: v.update(password='secret'), lambda v: v['endpoint'].update(ssh_key='secret'),
    lambda v: v['endpoint'].update(command=['sh']), lambda v: v['endpoint'].update(tc_root='/srv/tc'),
    lambda v: v['identity'].update(token='secret'), lambda v: v['endpoint'].update(ssh_port=True),
    lambda v: v['endpoint'].update(ssh_port='22'), lambda v: v['endpoint'].update(remote_dashboard_port=0),
    lambda v: v['endpoint'].update(server='127.0.0.1'), lambda v: v['endpoint'].update(server='localhost'),
    lambda v: v['endpoint'].update(server='0.0.0.0'), lambda v: v['endpoint'].update(account='-oProxyCommand=bad'),
    lambda v: v['endpoint'].update(server='host;whoami')])
def test_malformed_secret_and_command_injection_are_rejected(profile, mutation):
    path, value = profile; mutation(value); path.write_text(json.dumps(value))
    with pytest.raises(ValueError): load_profile(path)


def test_duplicate_oversized_symlink_and_identity_mismatch_are_rejected(tmp_path, profile):
    path, value = profile
    duplicate = tmp_path / 'duplicate.json'; duplicate.write_text('{"format":"x","format":"y"}')
    with pytest.raises(ValueError, match='Duplicate'): load_profile(duplicate)
    huge = tmp_path / 'huge.json'; huge.write_bytes(b' ' * 8193)
    with pytest.raises(ValueError, match='large'): load_profile(huge)
    link = tmp_path / 'link.json'; link.symlink_to(path)
    with pytest.raises(ValueError, match='symbolic'): load_profile(link)
    home = tmp_path / 'windows'; import_profile(home, path)
    previous = (home / 'windows-runner.json').read_bytes()
    value['identity']['runtime_id'] = 'different'; path.write_text(json.dumps(value))
    with pytest.raises(TestError) as error: import_profile(home, path)
    assert error.value.code == 'SERVICE_IDENTITY_MISMATCH'
    assert (home / 'windows-runner.json').read_bytes() == previous
    with pytest.raises(TestError): verify_service(value, {'runtime_id': 'other', 'package_version': '0.1.0'})


def test_import_only_does_not_start_manager_or_hardware(tmp_path, profile, monkeypatch):
    from backend.gui_test.connector import __main__ as entry
    from backend.gui_test.connector import bootstrap
    calls = []
    monkeypatch.setattr(bootstrap, 'import_profile', lambda home, path: calls.append((home, path)))
    assert entry.main(['--home', str(tmp_path / 'windows'), '--import-profile', str(profile[0]), '--import-only']) == 0
    assert calls == [(tmp_path / 'windows', profile[0])]


def test_picker_cancel_is_noop_before_manager(tmp_path, monkeypatch):
    from backend.gui_test.connector import __main__ as entry
    from backend.gui_test.connector import native_picker
    monkeypatch.setattr(native_picker, 'choose', lambda kind: '')
    assert entry.main(['--home', str(tmp_path / 'windows'), '--choose-profile']) == 0
    assert not (tmp_path / 'windows').exists()


def test_terminal_execution_history_is_preserved_and_failed_replace_keeps_original(tmp_path, profile, monkeypatch):
    from scripts import setup_runtime
    home = tmp_path / 'windows'; runtime = home / 'runtime'; runtime.mkdir(parents=True)
    with sqlite3.connect(runtime / 'executions.db') as c:
        c.execute('CREATE TABLE jobs(data TEXT)'); c.execute('CREATE TABLE batches(data TEXT)')
        c.execute('INSERT INTO jobs VALUES(?)', (json.dumps({'state': 'DONE', 'terminated': True}),))
        c.execute('INSERT INTO batches VALUES(?)', (json.dumps({'state': 'RELEASED'}),))
    database = (runtime / 'executions.db').read_bytes()
    import_profile(home, profile[0])
    assert (runtime / 'executions.db').read_bytes() == database
    target = home / 'windows-runner.json'; previous = target.read_bytes()
    def fail(*args): raise OSError('simulated replacement failure')
    monkeypatch.setattr(setup_runtime.os, 'replace', fail)
    with pytest.raises(OSError): import_profile(home, profile[0])
    assert target.read_bytes() == previous
    assert all(p.read_bytes() == previous for p in home.glob('windows-runner.json.*.bak'))


def test_invalid_secret_payload_never_enters_launcher_error(profile):
    path, value = profile
    value['endpoint']['password'] = 'PRIVATE-PASSWORD-DO-NOT-LOG'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError) as error: load_profile(path)
    assert 'PRIVATE-PASSWORD' not in str(error.value) and 'password' not in str(error.value)
    with pytest.raises(ValueError) as error: service_headers(value)
    assert 'PRIVATE-PASSWORD' not in str(error.value)


def test_supervisor_refuses_identity_mismatch_before_registering(tmp_path, profile, monkeypatch):
    import time
    import httpx
    from types import SimpleNamespace
    from backend.gui_test.connector.supervisor import Manager
    from backend.gui_test.execution import launch
    receipt = {'runner_url': 'http://127.0.0.1:8771', 'dashboard_url': 'http://127.0.0.1:8766',
               'runner_id': 'runner', 'phase': 'ssh_running', 'remote_runner_port': 8771}
    monkeypatch.setattr(launch, 'read_active', lambda runtime: receipt)
    calls = []
    def transport(request):
        calls.append((request.method, request.url.path))
        payload = {'/v1/inventory': {'runner_id': 'runner', 'boards': [], 'checked_at': time.time(), 'host_busy': False, 'reserved': False},
                   '/v1/console': {'boards': []}, '/v1/recent-executions': {'executions': []},
                   '/api/v1/health': {'runtime_id': 'wrong-runtime', 'package_version': '0.1.0'}}
        return httpx.Response(200, json=payload[request.url.path])
    client = httpx.Client(transport=httpx.MockTransport(transport))
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: client)
    manager = SimpleNamespace(home=tmp_path, error='', thread=None, storage_cache={}, storage_checked=time.monotonic(),
                              console_cursor=0, console_epoch=None,
                              settings=SimpleNamespace(read=lambda: {'_setup': {'connector_bootstrap': profile[1]}}))
    with pytest.raises(TestError) as error: Manager.probe(manager)
    assert error.value.code == 'SERVICE_IDENTITY_MISMATCH'
    assert all(method != 'POST' for method, path in calls)


def test_imported_connector_real_standalone_boundary_and_replaced_endpoint(tmp_path, monkeypatch):
    import time
    import httpx
    from types import SimpleNamespace
    from backend.gui_test.connector.supervisor import Manager
    from backend.gui_test.connector.settings import Settings
    from backend.gui_test.connector.shared_control import request as shared_request
    from backend.gui_test.execution import launch
    app = create_app(tmp_path / 'linux', start_worker=False)
    runner_id = 'a' * 32
    inventory = {'runner_id': runner_id, 'mapping_revision': 'map', 'boards': [], 'checked_at': time.time(),
                 'host_busy': False, 'reserved': False}
    class Remote:
        def request(self, path):
            if path == '/identity': return {'runner_id': runner_id, 'connector_inventory_v1': True, 'source_configured_v1': False}
            if path == '/inventory': return inventory
            return {'runner_id': runner_id, 'boards': [], 'errors': []}
    app.state.registry.manager.runner.registry.factory = lambda url: Remote()
    home = tmp_path / 'windows'
    with TestClient(app, base_url='http://127.0.0.1:8766', client=('127.0.0.1', 1234)) as linux:
        health = linux.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin'}).json()
        profile = {'format': FORMAT, 'endpoint': {'server': 'linux.test', 'account': 'bsp', 'ssh_port': 22, 'remote_dashboard_port': 8766},
                   'identity': {key: health[key] for key in ('runtime_id', 'package_version')}}
        path = tmp_path / 'connection.json'; path.write_text(json.dumps(profile)); import_profile(home, path)
        monkeypatch.setattr(launch, 'read_active', lambda runtime: {'runner_url': 'http://127.0.0.1:8771',
            'dashboard_url': 'http://127.0.0.1:8766', 'runner_id': runner_id, 'phase': 'ssh_running', 'remote_runner_port': 8771})
        seen = []
        def transport(request):
            if request.url.port == 8766:
                seen.append((request.url.path, dict(request.headers)))
                response = linux.request(request.method, str(request.url), headers=request.headers, content=request.content)
                return httpx.Response(response.status_code, content=response.content, headers=response.headers)
            data = {'/v1/inventory': inventory, '/v1/console': {'boards': []}, '/v1/recent-executions': {'executions': []}}
            return httpx.Response(200, json=data[request.url.path])
        original_client = httpx.Client
        monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original_client(transport=httpx.MockTransport(transport)))
        manager = SimpleNamespace(home=home, error='', thread=None, storage_cache={}, storage_checked=time.monotonic(),
                                  console_cursor=0, console_epoch=None, settings=Settings(home))
        result = Manager.probe(manager)
        assert result['state'] == 'CONNECTED', result
        assert not result.get('shared_error')
        assert all(headers.get('x-bsp-service') == 'plugin' and headers.get('x-bsp-runtime-id') == health['runtime_id'] for _, headers in seen)
        app.state.registry.runtime_id = 'replaced-runtime'
        with pytest.raises(TestError) as error: shared_request(home, 'settings')
        assert error.value.code == 'SERVICE_IDENTITY_MISMATCH'
