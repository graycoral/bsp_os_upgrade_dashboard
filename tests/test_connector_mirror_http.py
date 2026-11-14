"""Mirror API authorization and reference-client round trips, no hardware I/O."""
from contextlib import contextmanager

from fastapi.testclient import TestClient
import httpx
import pytest

from backend.gui_test.connector.mirror import ConnectorMirror
from backend.gui_test.core.models import digest
from backend.gui_test.runtime import make_manager
from backend.gui_test.standalone.integration import create_app
from backend.gui_test.standalone.plugin_client import PluginClient


BASE = '/api/v1/gui-test/live/connector/mirror'
CONTROL = '/api/v1/gui-test/live/integration'
SERVICE = {'X-Bsp-Service': 'plugin'}
RUNNER = 'a' * 32


def register_manager(manager):
    calls = []

    class Remote:
        def request(self, path):
            calls.append(path)
            if path == '/identity':
                return {'runner_id': RUNNER, 'connector_inventory_v1': True}
            if path == '/inventory':
                return {'runner_id': RUNNER, 'mapping_revision': 'map-one',
                        'host_busy': False, 'reserved': False,
                        'boards': [{'board_id': 'A', 'host': 'windows', 'com': 'COM1', 'state': 'CONNECTED',
                                    'serial_proxy': {'owner': None, 'putty_connected': False}}]}
            raise AssertionError('Unexpected hardware access: ' + path)

    registry = manager.runner.registry
    registry.factory = lambda _: Remote()
    registration = registry.register('http://127.0.0.1:9876', RUNNER)
    registry.save_console({'runner_id': RUNNER, 'boards': [], 'cursor': 0})
    profile = {'boards': [{'board_id': 'A', 'host': 'windows', 'com': 'COM1'}], 'serial_transport': 'proxy'}
    projection = {'runner_id': RUNNER, 'session_id': 'manager-boot-one', 'revision': digest(profile),
                  'profile': profile, 'ports': [{'com': 'COM1'}], 'state': 'CONNECTED', 'error': ''}
    ConnectorMirror(registry).publish(projection, expected_registration=registration)
    calls.clear()
    return registration, projection, calls


@pytest.fixture
def rig(tmp_path):
    manager = make_manager(tmp_path, 'integration')
    registration, projection, calls = register_manager(manager)
    app = create_app(tmp_path, manager=manager, start_worker=False)
    with TestClient(app, client=('127.0.0.1', 1200)) as http:
        yield app, http, manager, registration, projection, calls


def command(projection, *, action='putty', body=None, key='request-one'):
    return {name: projection[name] for name in ('runner_id', 'session_id', 'revision')} | {
        'idempotency_key': key, 'action': action, 'body': {'board_id': 'A'} if body is None else body}


@contextmanager
def browser_for(app, service, scopes):
    grant = service.post(CONTROL + '/browser-session', json={'scopes': scopes}, headers=SERVICE)
    assert grant.status_code == 200, grant.text
    with TestClient(app, client=('127.0.0.1', 1201)) as browser:
        login = browser.post('/auth/session', data={'code': grant.json()['bootstrap_code']},
                             headers={'Origin': 'http://testserver'}, follow_redirects=False)
        assert login.status_code == 303, login.text
        access = browser.get(CONTROL + '/browser-session').json()
        yield browser, {'Origin': 'http://testserver', 'X-Bsp-Client': 'dashboard',
                        'X-Gui-Csrf': access['csrf_token']}


def test_snapshot_reads_persisted_settings_and_console_without_contacting_hardware(rig):
    app, service, _, _, projection, calls = rig
    response = service.get(BASE, headers=SERVICE)
    assert response.status_code == 200, response.text
    value = response.json()
    assert value['fresh'] and value['projection']['session_id'] == projection['session_id']
    assert value['inventory']['runner_id'] == RUNNER
    assert {'settings', 'console', 'errors', 'commands'} <= value.keys()
    assert calls == []
    with browser_for(app, service, []) as (browser, _):
        assert browser.get(BASE).status_code == 200
    assert service.get(BASE).status_code == 401
    assert calls == []


def test_service_command_claim_receipt_round_trip_and_public_token_filtering(rig):
    _, service, _, registration, projection, calls = rig
    published = service.post(BASE + '/state', json={'projection': projection, 'registration': registration}, headers=SERVICE)
    assert published.status_code == 200, published.text
    requested = service.post(BASE + '/commands', json=command(projection), headers=SERVICE)
    assert requested.status_code == 200, requested.text
    queued = requested.json()
    assert queued['state'] == 'QUEUED'
    identity = {key: projection[key] for key in ('runner_id', 'session_id')}
    claimed = service.post(BASE + '/claim', json=identity, headers=SERVICE)
    assert claimed.status_code == 200, claimed.text
    active = claimed.json()['command']
    assert active['state'] == 'RUNNING' and active['claim_token']
    assert service.post(BASE + '/claim', json=identity, headers=SERVICE).json()['command'] is None
    path = BASE + '/commands/' + queued['command_id']
    assert 'claim_token' not in service.get(path, headers=SERVICE).json()
    receipt = {key: active[key] for key in ('runner_id', 'session_id', 'claim_token')} | {
        'state': 'APPLIED', 'result': {'opened': True}}
    done = service.post(path + '/receipt', json=receipt, headers=SERVICE)
    assert done.status_code == 200 and done.json()['state'] == 'APPLIED'
    assert service.post(path + '/receipt', json=receipt, headers=SERVICE).json() == done.json()
    assert calls == []


@pytest.mark.parametrize('suffix,body', [('/state', {'projection': {}, 'registration': {}}),
                                       ('/claim', {'runner_id': RUNNER, 'session_id': 'manager-boot-one'}),
                                       ('/commands/' + 'b' * 32 + '/receipt', {})])
def test_projection_claim_and_receipt_require_nonbrowser_service_client(rig, suffix, body):
    app, service, *_ = rig
    assert service.post(BASE + suffix, json=body, headers=SERVICE | {'Origin': 'http://testserver'}).status_code == 403
    assert service.post(BASE + suffix, json=body, headers=SERVICE | {'Sec-Fetch-Site': 'same-origin'}).status_code == 403
    with browser_for(app, service, ['control', 'settings']) as (browser, headers):
        assert browser.post(BASE + suffix, json=body, headers=headers).status_code == 403


@pytest.mark.parametrize('scopes,action,allowed', [([], 'putty', False), ([], 'apply-settings', False),
                                               (['settings'], 'putty', False), (['control'], 'apply-settings', False),
                                               (['control'], 'putty', True), (['settings'], 'apply-settings', True)])
def test_browser_commands_require_exact_action_scope_and_same_origin_csrf(rig, scopes, action, allowed):
    app, service, manager, _, projection, _ = rig
    body = {'board_id': 'A'}
    if action == 'apply-settings':
        current = manager.shared_settings.connector_application()
        desired = manager.shared_settings.desired({'expected_revision': current['revision'], 'runner_id': RUNNER,
                                                    'settings': {'board_names': {'A': 'Board A'}}})
        body = {'desired_revision': desired['desired_revision']}
    request = command(projection, action=action, body=body)
    with browser_for(app, service, scopes) as (browser, headers):
        assert browser.post(BASE + '/commands', json=request).status_code == 403
        assert browser.post(BASE + '/commands', json=request, headers={key: value for key, value in headers.items() if key != 'X-Gui-Csrf'}).status_code == 403
        assert browser.post(BASE + '/commands', json=request, headers=headers | {'Origin': 'https://evil.example'}).status_code == 403
        result = browser.post(BASE + '/commands', json=request, headers=headers)
        assert result.status_code == (200 if allowed else 403), result.text


def test_apply_settings_requires_current_central_desired_revision(rig):
    _, service, manager, _, projection, _ = rig
    current = manager.shared_settings.connector_application()
    desired = manager.shared_settings.desired({'expected_revision': current['revision'], 'runner_id': RUNNER,
                                                'settings': {'board_names': {'A': 'Board A'}}})
    bad = service.post(BASE + '/commands', json=command(projection, action='apply-settings',
                       body={'desired_revision': 'outdated-desired-revision'}), headers=SERVICE)
    assert bad.status_code == 409, bad.text
    good = service.post(BASE + '/commands', json=command(projection, action='apply-settings',
                        body={'desired_revision': desired['desired_revision']}), headers=SERVICE)
    assert good.status_code == 200 and good.json()['state'] == 'QUEUED', good.text
    current = manager.shared_settings.connector_application()
    manager.shared_settings.desired({'expected_revision': current['revision'], 'runner_id': RUNNER,
                                     'settings': {'board_names': {'A': 'Updated Board A'}}})
    replay = service.post(BASE + '/commands', json=command(projection, action='apply-settings',
                          body={'desired_revision': desired['desired_revision']}), headers=SERVICE)
    assert replay.status_code == 200 and replay.json()['command_id'] == good.json()['command_id'], replay.text


@pytest.mark.parametrize('scopes,allowed', [([], False), (['settings'], False), (['control'], True)])
def test_unknown_acknowledgement_uses_control_scope_csrf_and_current_replacement_session(rig, scopes, allowed):
    app, service, manager, _, projection, _ = rig
    mirror = ConnectorMirror(manager.runner.registry)
    queued = mirror.create(command(projection))
    mirror.claim({key: projection[key] for key in ('runner_id', 'session_id')})
    replacement = dict(projection, session_id='replacement-manager-boot')
    mirror.publish(replacement)
    unknown = mirror.get(queued['command_id'])
    path = BASE + '/commands/' + queued['command_id'] + '/abandon'
    body = {key: replacement[key] for key in ('runner_id', 'session_id')} | {'expected_updated_at': unknown['updated_at']}
    with browser_for(app, service, scopes) as (browser, headers):
        assert browser.post(path, json=body).status_code == 403
        assert browser.post(path, json=body, headers={key: value for key, value in headers.items() if key != 'X-Gui-Csrf'}).status_code == 403
        response = browser.post(path, json=body, headers=headers)
        assert response.status_code == (200 if allowed else 403), response.text
    if allowed:
        assert response.json()['state'] == 'ABANDONED'
        assert response.json()['result']['code'] == 'UNKNOWN_ACKNOWLEDGED'
        assert response.json()['result']['outcome_unknown']
        fresh = service.post(BASE + '/commands', json=command(replacement, key='new-explicit-intent'), headers=SERVICE)
        assert fresh.status_code == 200 and fresh.json()['state'] == 'QUEUED', fresh.text


def test_plugin_client_paths_bodies_identity_headers_and_receipt_id_validation():
    calls = []
    identity = {'runtime_id': 'runtime-one', 'package_version': '0.1.0'}
    snapshot = {'projection': {'session_id': 'boot-one', 'revision': 'profile-one'}, 'inventory': {'runner_id': RUNNER}}

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={'ok': True})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        plugin = PluginClient('http://127.0.0.1', expected_identity=identity, client=http)
        assert plugin.connector_mirror() == {'ok': True}
        assert plugin.connector_command('putty', {'board_id': 'A'}, key='intent-one', snapshot=snapshot) == {'ok': True}
        assert plugin.connector_command_receipt('b' * 32) == {'ok': True}
        assert plugin.acknowledge_unknown_connector_command('b' * 32, snapshot=snapshot, expected_updated_at=123.0) == {'ok': True}
        for invalid in ('../claim', 'short', 'B' * 32, 'b' * 32 + '/receipt'):
            with pytest.raises(ValueError):
                plugin.connector_command_receipt(invalid)
            with pytest.raises(ValueError):
                plugin.acknowledge_unknown_connector_command(invalid, snapshot=snapshot, expected_updated_at=123.0)
    assert [(request.method, request.url.path) for request in calls] == [
        ('GET', BASE), ('POST', BASE + '/commands'), ('GET', BASE + '/commands/' + 'b' * 32),
        ('POST', BASE + '/commands/' + 'b' * 32 + '/abandon')]
    import json
    assert json.loads(calls[1].content) == {'idempotency_key': 'intent-one', 'runner_id': RUNNER,
           'session_id': 'boot-one', 'revision': 'profile-one', 'action': 'putty', 'body': {'board_id': 'A'}}
    assert json.loads(calls[3].content) == {'runner_id': RUNNER, 'session_id': 'boot-one', 'expected_updated_at': 123.0}
    assert all(request.headers['x-bsp-service'] == 'plugin' and request.headers['x-bsp-runtime-id'] == identity['runtime_id']
               for request in calls)


def test_full_dashboard_control_header_and_native_only_command_routes(tmp_path):
    from backend.api.main import create_app as full_app
    app = full_app(tmp_path)
    _, projection, calls = register_manager(app.state.gui_live_manager)
    with TestClient(app, client=('127.0.0.1', 1200)) as http:
        assert http.get(BASE).status_code == 200
        assert http.post(BASE + '/commands', json=command(projection)).status_code == 403
        assert http.post(BASE + '/commands', json=command(projection), headers={'X-Bsp-Client': 'dashboard'}).status_code == 403
        headers = {'X-Bsp-Client': 'dashboard', 'Origin': 'http://testserver'}
        queued = http.post(BASE + '/commands', json=command(projection), headers=headers)
        assert queued.status_code == 200, queued.text
        assert http.post(BASE + '/claim', json={'runner_id': RUNNER, 'session_id': projection['session_id']},
                         headers=headers).status_code == 403
    assert calls == []
