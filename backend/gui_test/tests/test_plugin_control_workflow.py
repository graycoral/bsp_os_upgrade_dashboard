"""Plugin-only management uses the same ownership and termination gates as UI."""
import pytest
import httpx
from fastapi.testclient import TestClient

from backend.gui_test.tests.test_plugin_integration_service import rig
from backend.gui_test.tests.test_plugin_integration_http import client_for, PREFIX
from backend.gui_test.standalone.plugin_client import PluginClient
from backend.gui_test.standalone.integration import create_app
from backend.gui_test.core.models import TestError


def test_plugin_deletes_cancelled_run_without_forging_browser_session(rig, tmp_path):
    manager = rig[0]
    with client_for(rig, tmp_path) as client:
        run = client.post(PREFIX + '/integration/runs', json=rig[3],
                          headers={'Idempotency-Key': 'delete-workflow'}).json()
        path = PREFIX + '/integration/runs/' + run['id']
        active = client.request('DELETE', path, json={'expected_version': run['version']})
        assert active.status_code == 409 and active.json()['code'] == 'SESSION_ACTIVE'
        finished = client.post(path + '/actions/cancel', json={'expected_version': run['version']},
                               headers={'Idempotency-Key': 'cancel-delete-workflow'}).json()
        assert finished['state'] == 'CANCELLED'
        stale = client.request('DELETE', path, json={'expected_version': run['version']})
        assert stale.status_code == 409 and stale.json()['code'] == 'VERSION_CONFLICT'
        deleted = client.request('DELETE', path, json={'expected_version': finished['version']})
        assert deleted.status_code == 200 and deleted.json()['deleted'] is True
        assert client.get(PREFIX + '/runs/' + run['id']).status_code == 410
        replay = client.post(PREFIX + '/integration/runs', json=rig[3],
                             headers={'Idempotency-Key': 'delete-workflow'})
        assert replay.status_code == 410 and replay.json()['code'] == 'RUN_DELETED'
    assert manager.store.all() == []


def test_plugin_delete_cannot_override_controller_with_session_header(rig, tmp_path):
    manager, service = rig[:2]
    run = service.start('other-owner', 'another-plugin', rig[3])
    finished = service.act(run['id'], 'cancel-other', 'another-plugin', run['version'], 'cancel')
    with client_for(rig, tmp_path) as client:
        denied = client.request('DELETE', PREFIX + '/integration/runs/' + run['id'],
                                json={'expected_version': finished['version']},
                                headers={'X-Gui-Session': 'another-plugin'})
        assert denied.status_code == 403 and denied.json()['code'] == 'CONTROL_REQUIRED'
    assert manager.get(run['id'])['state'] == 'CANCELLED'


@pytest.mark.parametrize('full_host', [False, True])
def test_every_plugin_request_checks_identity_without_optional_health_call(tmp_path, full_host):
    factory = create_app
    if full_host:
        from backend.api.main import create_app as factory
    app = factory(tmp_path) if full_host else factory(tmp_path, start_worker=False)
    with TestClient(app, client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        health = http.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin'}).json()
        pins = {key: health[key] for key in ('runtime_id', 'package_version')}
        correct = PluginClient('http://127.0.0.1', expected_identity=pins, client=http)
        original = correct.settings()
        for changed in ({'runtime_id': 'other-runtime'}, {'package_version': 'future-version'}):
            wrong = PluginClient('http://127.0.0.1', expected_identity=pins | changed, client=http)
            with pytest.raises(TestError) as error:
                wrong.settings()
            assert error.value.code == 'SERVICE_IDENTITY_MISMATCH'
            original['timeouts']['default_seconds'] = 123
            with pytest.raises(TestError) as error:
                wrong.save_settings(original)
            assert error.value.code == 'SERVICE_IDENTITY_MISMATCH'
        assert correct.settings()['timeouts']['default_seconds'] != 123
        headers = {'X-Bsp-Service': 'plugin', 'X-Bsp-Runtime-Id': pins['runtime_id']}
        assert http.get(PREFIX + '/integration/settings', headers=headers).status_code == 409


@pytest.mark.parametrize('scopes,allowed', [([], False), (['control'], False), (['settings'], True)])
def test_storage_browser_scope_reuses_csrf_and_settings_permission(tmp_path, scopes, allowed):
    app = create_app(tmp_path, start_worker=False)
    base = PREFIX + '/integration'
    with TestClient(app, client=('127.0.0.1', 1234)) as http:
        grant = http.post(base + '/browser-session', json={'scopes': scopes},
                          headers={'X-Bsp-Service': 'plugin'}).json()
        assert http.post('/auth/session', data={'code': grant['bootstrap_code']},
                         headers={'Origin': 'http://testserver'}, follow_redirects=False).status_code == 303
        access = http.get(base + '/browser-session').json()
        headers = {'Origin': 'http://testserver', 'X-Bsp-Client': 'dashboard', 'X-Gui-Csrf': access['csrf_token']}
        policy = http.get(base + '/storage-policy').json()
        body = {k: policy[k] for k in ('enabled', 'max_age_seconds', 'max_bytes')}
        body['expected_revision'] = policy['revision']
        assert http.put(base + '/storage-policy', json=body, headers=headers).status_code == (200 if allowed else 403)
        assert http.post(base + '/storage-cleanup', json={'dry_run': True}, headers=headers).status_code == (200 if allowed else 403)
        assert http.post(base + '/storage-cleanup', json={'dry_run': True},
                         headers=headers | {'X-Gui-Csrf': 'wrong'}).status_code == 403


def test_plugin_log_transport_and_path_validation():
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, text='UART ready\nTest Result: FAIL\n')
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        plugin = PluginClient('http://127.0.0.1', expected_identity={'runtime_id': 'fixture', 'package_version': '0.1.0'}, client=http)
        assert plugin.attempt_log('a' * 32, 'b' * 32).startswith('UART ready')
        assert requests[-1].headers['X-Bsp-Runtime-Id'] == 'fixture'
        with pytest.raises(ValueError): plugin.attempt_log('../private', 'b' * 32)
        with pytest.raises(ValueError): plugin.attempt_log('a' * 32, 'b' * 32, '../../private')
        with pytest.raises(ValueError): plugin.action('a' * 32, 'retry-failed', key='x', expected_version=1)


def test_plugin_keeps_actionable_server_error_code_without_leaking_secret(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(422,
            json={'code': 'FLASH_PROFILE_ADVANCED', 'message': 'Keep existing profile. password=private-value'}))) as http:
        plugin = PluginClient('http://127.0.0.1', expected_identity={'runtime_id': 'fixture', 'package_version': '0.1.0'},
                              client=http, log_dir=tmp_path / 'logs')
        with pytest.raises(TestError) as error: plugin.flash_profiles()
        assert error.value.code == 'FLASH_PROFILE_ADVANCED'
        assert 'private-value' not in error.value.message
        assert 'private-value' not in plugin.last_diagnostic['cause']
