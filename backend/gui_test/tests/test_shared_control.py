"""T-241: common settings authority, bootstrap and scoped browser control."""
import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.gui_test.core.discovery import discover
from backend.gui_test.core.models import TestError
from backend.gui_test.core.shared_settings import attach_shared_settings
from backend.gui_test.runtime import make_manager
from backend.gui_test.standalone.integration import create_app
from backend.gui_test.standalone.plugin_client import PluginClient
from backend.gui_test.tests.test_plugin_integration_service import rig

BASE = '/api/v1/gui-test/live/integration'
HEADERS = {'X-Bsp-Service': 'plugin'}


def update(value):
    return {'expected_revision': value['revision'], 'integration': value['integration'],
            'timeouts': {k: v for k, v in value['timeouts'].items() if k != 'revision'}}


def test_bootstrap_without_board_tc_or_config_supports_health_settings_and_registration(tmp_path):
    manager = make_manager(tmp_path, 'integration')
    runner_id = 'a' * 32
    class Remote:
        def request(self, path):
            if path == '/identity': return {'runner_id': runner_id, 'connector_inventory_v1': True}
            if path == '/inventory': return {'runner_id': runner_id, 'mapping_revision': 'map1', 'boards': []}
            return {'runner_id': runner_id, 'boards': [], 'cursor': 0}
    manager.runner.registry.factory = lambda url: Remote()
    app = create_app(tmp_path, manager=manager, start_worker=False)
    with TestClient(app, client=('127.0.0.1', 1200)) as client:
        health = client.get('/api/v1/health', headers=HEADERS).json()
        assert health['execution_configured'] is False and health['runner_id'] is None
        value = client.get(BASE + '/settings', headers=HEADERS).json()
        assert value['integration']['tc_root'] == '' and manager.store.all() == []
        response = client.post('/api/v1/gui-test/live/connector/register',
                               json={'url': 'http://127.0.0.1:9876', 'runner_id': runner_id})
        assert response.status_code == 200, response.text
        assert client.get('/api/v1/health', headers=HEADERS).json()['runner_id'] == runner_id
        assert client.post(BASE + '/runs', headers=HEADERS | {'Idempotency-Key': 'unconfigured'},
                           json={'installer_path': '/srv/install.bat', 'tc_patterns': ['*.py']}).status_code == 422
        assert manager.store.all() == []
        assert client.post('/api/v1/gui-test/live/connector/register',
                           headers={'Origin': 'http://testserver'}, json={'url': 'http://127.0.0.1:9876', 'runner_id': runner_id}).status_code in {401, 403}


def test_shared_json_file_and_legacy_timeout_route_use_one_atomic_revision(tmp_path):
    manager = make_manager(tmp_path, 'integration')
    settings = manager.shared_settings
    original = settings.export()
    edited = copy.deepcopy(original)
    edited['timeouts']['default_seconds'] = 95
    applied = settings.import_file(edited)
    assert applied['timeouts']['default_seconds'] == 95
    with pytest.raises(TestError, match='changed'):
        settings.import_file(original)
    before = settings.read()
    manager.timeouts.save({'expected_revision': before['timeouts']['revision'], 'default_seconds': 10})
    with pytest.raises(TestError) as error:
        settings.save(update(before))
    assert error.value.code == 'SETTINGS_CHANGED'
    assert settings.read()['timeouts']['default_seconds'] == 10
    reopened = make_manager(tmp_path, 'integration')
    assert reopened.shared_settings.read() == settings.read()


def test_timeout_precedence_and_fallback_preserve_explicit_ten_seconds(tmp_path):
    (tmp_path / 'fallback.py').write_text('pass')
    (tmp_path / 'explicit.py').write_text('pass')
    manager = make_manager(tmp_path / 'runtime', 'integration')
    catalog = discover(tmp_path, {'explicit.py': {'timeout': 10}})
    tests = {t['id']: t for t in manager.timeouts.apply(catalog)['tests']}
    assert tests['fallback.py']['timeout'] == 600 and tests['fallback.py']['timeout_explicit'] is False
    assert tests['explicit.py']['timeout'] == 10 and tests['explicit.py']['timeout_explicit'] is True
    first = manager.timeouts.read()
    manager.timeouts.save({'expected_revision': first['revision'], 'default_seconds': 70,
                           'source_revision': catalog['revision'], 'overrides': {'explicit.py': 15}})
    values = {t['id']: t['timeout'] for t in manager.timeouts.apply(catalog)['tests']}
    assert values == {'explicit.py': 15, 'fallback.py': 70}
    frozen = manager.timeouts.apply(catalog)
    manager.timeouts.save({'expected_revision': manager.timeouts.read()['revision'], 'default_seconds': 50})
    assert {t['timeout'] for t in frozen['tests']} == {15, 70}


def test_allowed_server_browser_rejects_traversal_and_links(tmp_path):
    root = tmp_path / 'published'
    root.mkdir(); (root / 'install.bat').write_text('rem fixture')
    outside = tmp_path / 'private'; outside.mkdir()
    (root / 'escape').symlink_to(outside, target_is_directory=True)
    settings = make_manager(tmp_path / 'runtime', 'integration').shared_settings
    value = settings.read(); body = update(value)
    body['integration'].update(installer_roots=[str(root)], source_roots=[str(root)], installer_path=str(root / 'install.bat'))
    settings.save(body)
    assert settings.browse('installer', str(root))['entries'] == [{'name': 'install.bat', 'path': str(root / 'install.bat'), 'directory': False}]
    for invalid in (str(outside), str(root / 'escape'), str(root) + '/../private'):
        with pytest.raises(TestError) as exc:
            settings.browse('installer', invalid)
        assert exc.value.code == 'PATH_SCOPE'
    bad = update(settings.read()); bad['integration']['tc_root'] = str(outside)
    with pytest.raises(ValueError): settings.save(bad)


def test_same_plugin_survives_settings_mutation_and_runtime_pin_remains_strict(tmp_path):
    app = create_app(tmp_path, start_worker=False)
    app.state.registry.start(); app.state.worker_running = True
    with TestClient(app, client=('127.0.0.1', 1200), base_url='http://127.0.0.1') as http:
        initial = http.get('/api/v1/health', headers=HEADERS).json()
        identity = {k: initial[k] for k in ('runtime_id', 'package_version', 'config_revision')}
        plugin = PluginClient('http://127.0.0.1', expected_identity=identity, client=http, log_dir=tmp_path / 'logs')
        before = plugin.health()
        value = plugin.settings(); value['timeouts']['default_seconds'] = 200
        saved = plugin.save_settings(value)
        assert saved['timeouts']['default_seconds'] == 200
        assert plugin.health()['service_instance_id'] == before['service_instance_id']
        path = tmp_path / 'settings.json'; plugin.export_settings(path)
        exported = json.loads(path.read_text()); exported['timeouts']['default_seconds'] = 150
        assert plugin.import_settings(exported, validate_only=True)['revision_matches'] is True
        assert plugin.import_settings(exported)['timeouts']['default_seconds'] == 150
        with pytest.raises(TestError) as stale: plugin.import_settings(exported)
        assert stale.value.code == 'SETTINGS_CHANGED'
        other = PluginClient('http://127.0.0.1', expected_identity=identity | {'runtime_id': 'other'}, client=http, log_dir=tmp_path / 'logs')
        with pytest.raises(TestError) as wrong: other.health()
        assert wrong.value.code == 'SERVICE_IDENTITY_MISMATCH'


def test_browser_explicit_settings_scope_csrf_and_readonly_compatibility(tmp_path):
    app = create_app(tmp_path, start_worker=False)
    with TestClient(app, client=('127.0.0.1', 1200)) as service:
        grant = service.post(BASE + '/browser-session', headers=HEADERS, json={'scopes': ['settings']}).json()
        with TestClient(app, client=('127.0.0.1', 1201)) as browser:
            assert browser.post('/auth/session', data={'code': grant['bootstrap_code']}, headers={'Origin': 'http://testserver'}, follow_redirects=False).status_code == 303
            access = browser.get(BASE + '/browser-session').json()
            assert access['scopes'] == ['settings'] and access['principal_id'] == 'bsp-upgrade'
            value = browser.get(BASE + '/settings').json(); body = update(value); body['timeouts']['default_seconds'] = 99
            path = BASE + '/settings'
            csrf = {'Origin': 'http://testserver', 'X-Bsp-Client': 'dashboard', 'X-Gui-Csrf': access['csrf_token']}
            assert browser.put(path, json=body).status_code == 403
            assert browser.put(path, json=body, headers=csrf | {'Origin': 'https://evil.example'}).status_code == 403
            assert browser.put(path, json=body, headers={k: v for k, v in csrf.items() if k != 'Origin'}).status_code == 403
            assert browser.put(path, json=body, headers=csrf).status_code == 200
            assert browser.post(BASE + '/runs', json={}, headers=csrf).status_code == 403
            assert browser.post(BASE + '/browser-session', json={'scopes': ['control']}, headers=csrf).status_code == 403
        grant = service.post(BASE + '/browser-session', headers=HEADERS).json()
        assert grant['access'] == 'read-only'
        with TestClient(app, client=('127.0.0.1', 1202)) as readonly:
            readonly.post('/auth/session', data={'code': grant['bootstrap_code']}, headers={'Origin': 'http://testserver'})
            assert readonly.get(BASE + '/settings').status_code == 200
            assert readonly.put(BASE + '/settings', json=body, headers=csrf).status_code == 403


def test_windows_desired_is_pending_and_receipt_requires_correct_registered_runner(tmp_path):
    manager = make_manager(tmp_path, 'integration'); settings = manager.shared_settings
    revision = settings.connector_application()['revision']
    desired = settings.desired({'expected_revision': revision, 'runner_id': 'a' * 32, 'settings': {'python': 'C:/Python/python.exe'}})
    assert desired['state'] == 'PENDING' and desired['applied_revision'] == ''
    receipt = {'runner_id': 'a' * 32, 'desired_revision': desired['desired_revision'], 'state': 'APPLIED', 'applied_revision': 'physical-mapping-revision'}
    with pytest.raises(TestError): settings.receipt(receipt)
    manager.runner.registry.read = lambda: {'runner_id': 'b' * 32}
    with pytest.raises(TestError): settings.receipt(receipt)
    manager.runner.registry.read = lambda: {'runner_id': 'a' * 32}
    assert settings.receipt(receipt)['state'] == 'APPLIED'
    changed = settings.desired({'expected_revision': settings.connector_application()['revision'], 'runner_id': 'a' * 32, 'settings': {'serial_transport': 'proxy'}})
    with pytest.raises(TestError) as stale: settings.receipt(receipt)
    assert stale.value.code == 'SETTINGS_CHANGED' and changed['state'] == 'PENDING'


def test_concurrent_settings_save_commits_one_value(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    settings = make_manager(tmp_path, 'integration').shared_settings
    base = update(settings.read())
    def save(seconds):
        body = copy.deepcopy(base); body['timeouts']['default_seconds'] = seconds
        try:
            return settings.save(body)['timeouts']['default_seconds']
        except TestError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, [101, 102]))
    assert outcomes.count('SETTINGS_CHANGED') == 1
    assert settings.read()['timeouts']['default_seconds'] in {101, 102}


def test_shared_save_applies_only_new_acceptance_and_invalidates_old_preview(rig):
    manager, service, _, request, _, _ = rig
    settings = attach_shared_settings(manager)
    accepted = service.start('frozen', 'principal', request)
    preparation = service.preview('principal', request)
    service.prepare_one()
    token = service.preparation(preparation['preparation_id'], 'principal')['prepared_token']
    body = update(settings.read()); body['integration']['global_defaults'] = ['new/*.py']
    body['timeouts']['default_seconds'] = 321
    settings.save(body)
    assert manager.get(accepted['id'])['integration']['config']['config_revision'] == accepted['integration']['config_revision']
    assert manager.get(accepted['id'])['timeout_settings_snapshot']['default_seconds'] is None
    with pytest.raises(TestError) as exc:
        service.start('stale-preview', 'principal', request | {'prepared_token': token})
    assert exc.value.code in {'PREPARED_TOKEN_STALE', 'TC_TIMEOUT_CHANGED'}
    fresh = service.start('fresh', 'principal', request)
    assert fresh['timeout_settings_snapshot']['default_seconds'] == 321
    assert fresh['integration']['config']['global_defaults'] == ['new/*.py']


def test_full_host_shared_principal_and_narrow_service_mutations(tmp_path, monkeypatch):
    from backend.api.main import create_app as full_app
    monkeypatch.setenv('AGENT_MONITOR_RELEASE', 'fixture-release')
    monkeypatch.setenv('AGENT_MONITOR_INSTANCE', 'fixture-instance')
    app = full_app(tmp_path)
    with TestClient(app, client=('127.0.0.1', 1300)) as client:
        health = client.get('/api/v1/health', headers=HEADERS).json()
        assert health['execution_configured'] is False and health['managed_release'] == 'fixture-release'
        assert health['managed_instance'] == 'fixture-instance' and health['managed_runtime'] == str(tmp_path)
        assert client.get('/api/v1/gui-test/live/capabilities', headers={'X-Bsp-Client': 'dashboard'}).json()['control_principal_id'] == 'bsp-upgrade'
        value = client.get(BASE + '/settings', headers=HEADERS).json(); body = update(value)
        body['timeouts']['default_seconds'] = 250
        assert client.put(BASE + '/settings', json=body, headers={'X-Bsp-Client': 'dashboard'}).status_code == 403
        assert client.put(BASE + '/settings', json=body, headers={'X-Bsp-Client': 'dashboard', 'Origin': 'http://testserver'}).status_code == 200
        assert client.put('/api/v1/gui-test/live/execution-timeouts', json={'expected_revision': app.state.gui_live_manager.timeouts.read()['revision'], 'default_seconds': 55}, headers=HEADERS).status_code == 200
        assert client.post('/api/v1/gui-test/live/runs', json={}, headers=HEADERS).status_code == 403
        assert client.put('/api/v1/config', json={}, headers=HEADERS).status_code == 403
        assert client.put(BASE + '/settings', json=body, headers=HEADERS | {'Origin': 'http://testserver'}).status_code == 403


@pytest.mark.parametrize('state', ['RUNNING', 'UNKNOWN', 'PAUSED'])
def test_windows_local_ack_is_blocked_while_run_not_terminal(tmp_path, state):
    manager = make_manager(tmp_path, 'integration'); settings = manager.shared_settings
    manager.runner.registry.read = lambda: {'runner_id': 'a' * 32}
    desired = settings.desired({'expected_revision': settings.connector_application()['revision'],
                                'runner_id': 'a' * 32, 'settings': {'serial_transport': 'proxy'}})
    with manager.store.transaction() as c:
        manager.store.save(c, {'id': 'b' * 32, 'version': 0, 'state': state}, 'FIXTURE_ACTIVE')
    receipt = {'runner_id': 'a' * 32, 'desired_revision': desired['desired_revision'],
               'state': 'APPLIED', 'applied_revision': 'physical-revision'}
    with pytest.raises(TestError) as busy:
        settings.receipt(receipt)
    assert busy.value.code == 'CONNECTOR_BUSY'
    assert settings.connector_application()['state'] == 'PENDING'
    blocked = settings.receipt(receipt | {'state': 'BLOCKED', 'applied_revision': '', 'reason': 'Active run'})
    assert blocked['state'] == 'BLOCKED' and blocked['applied_revision'] == ''


def test_health_remains_available_for_invalid_execution_reference(tmp_path):
    app = create_app(tmp_path, start_worker=False)
    settings = app.state.manager.shared_settings
    value = update(settings.read())
    value['integration'].update(installer_roots=['/srv/images'], source_roots=['/srv/tests'], tc_root='/srv/tests',
                                connection={'a': {'board_id': 'board', 'host': 'host', 'com': 'COM1'}},
                                command_profile='missing-profile', command_revision='missing-revision',
                                runner_id='a' * 32, flash_profile='missing-flash')
    settings.save(value)
    with TestClient(app, client=('127.0.0.1', 1200)) as client:
        response = client.get('/api/v1/health', headers=HEADERS)
        assert response.status_code == 200
        assert response.json()['execution_configured'] is False
        assert response.json()['execution_status']['code'] != 'CONFIGURED'


def test_shared_defaults_blank_runner_uses_registered_identity_for_acceptance(rig):
    from types import SimpleNamespace
    manager, service, config, request, _, _ = rig
    runner_id = config['runner_id']
    config['runner_id'] = ''
    settings = attach_shared_settings(manager, config)
    manager.runner.registry = SimpleNamespace(read=lambda: {'runner_id': runner_id, 'inventory': {'boards': manager.boards.boards()}})
    assert settings.read()['integration']['runner_id'] == ''
    run = service.start('registered-bootstrap', 'plugin-principal', request)
    assert run['integration']['config']['runner_id'] == runner_id
    assert settings.read()['integration']['runner_id'] == ''
