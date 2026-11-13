"""T-200/201: headless authenticated API and independently-lived plugin clients."""
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.gui_test.core.integration import CONTRACT_VERSION
from backend.gui_test.core.models import TestError
from backend.gui_test.core.worker import Worker
from backend.gui_test.standalone.integration import create_app
from backend.gui_test.standalone import integration as integration_host
from backend.gui_test.standalone.plugin_client import PatternDefaults, PluginClient
from backend.gui_test.tests.test_plugin_integration_service import rig


TOKEN = 'fixture-integration-token-0123456789abcdef'
PREFIX = '/api/v1/gui-test/live'


def client_for(rig, tmp_path, **options):
    app = create_app(tmp_path, TOKEN, 'plugin-principal', manager=rig[0], start_worker=False)
    return TestClient(app, client=('127.0.0.1', 1000), headers={'X-Bsp-Service': 'plugin'}, **options)


def test_http_202_replay_lookup_and_json_report_reuse_existing_run_contract(rig, tmp_path):
    manager, _, _, request, _, calls = rig
    with client_for(rig, tmp_path) as client:
        accepted = client.post(PREFIX + '/integration/runs', json=request, headers={'Idempotency-Key': 'intent-one'})
        assert accepted.status_code == 202
        run = accepted.json()
        assert 'id' in run and 'run_id' not in run and run['controller'] == 'plugin-principal'
        assert run['attempts'] == [] and run['overall_result'] == 'INCOMPLETE'
        replay = client.post(PREFIX + '/integration/runs', json=request, headers={'Idempotency-Key': 'intent-one'})
        assert replay.status_code == 202 and replay.json() == run
        assert client.get(PREFIX + '/runs/' + run['id']).json()['id'] == run['id']
        report = client.get(PREFIX + '/runs/' + run['id'] + '/report/json')
        assert report.status_code == 200 and run['id'] in report.text
    assert len(manager.store.all()) == 1 and calls == []


@pytest.mark.parametrize('change', ['no-service-marker', 'browser', 'forged-session', 'arbitrary-command', 'missing-key'])
def test_http_rejects_untrusted_mutations_before_acceptance(rig, tmp_path, change):
    _, _, _, request, _, calls = rig
    with client_for(rig, tmp_path) as client:
        headers = {'Idempotency-Key': 'intent-one'}
        body = dict(request)
        if change == 'no-service-marker': headers['X-Bsp-Service'] = ''
        if change == 'browser': headers['Origin'] = 'http://localhost'
        if change == 'forged-session': body['controller'] = 'attacker'
        if change == 'arbitrary-command': body['command'] = 'shell command must not be accepted'
        if change == 'missing-key': headers.pop('Idempotency-Key')
        response = client.post(PREFIX + '/integration/runs', json=body, headers=headers)
        assert response.status_code in {401, 403, 422}
    assert rig[0].store.all() == [] and calls == []


def test_http_version_and_controller_cas_blocks_stale_control_transfer(rig, tmp_path):
    with client_for(rig, tmp_path) as client:
        run = client.post(PREFIX + '/integration/runs', json=rig[3], headers={'Idempotency-Key': 'intent-one'}).json()
        path = PREFIX + '/integration/runs/' + run['id'] + '/actions/transfer-control'
        body = {'expected_version': run['version'], 'data': {'expected_controller': 'plugin-principal', 'controller': 'gui-reviewer'}}
        unavailable = client.post(path, json=body, headers={'Idempotency-Key': 'unavailable-target'})
        assert unavailable.status_code == 422 and unavailable.json()['code'] == 'CONTROL_TARGET_UNAVAILABLE'
        unchanged = client.get(PREFIX + '/runs/' + run['id']).json()
        assert unchanged['version'] == run['version'] and unchanged['controller'] == 'plugin-principal'
        body['data']['controller'] = 'plugin-principal'
        transferred = client.post(path, json=body, headers={'Idempotency-Key': 'transfer-one'})
        assert transferred.status_code == 200 and transferred.json()['controller'] == 'plugin-principal'
        stale = client.post(path, json=body, headers={'Idempotency-Key': 'transfer-stale'})
        assert stale.status_code == 409
        current = client.get(PREFIX + '/runs/' + run['id']).json()
        assert current['controller'] == 'plugin-principal'
        managed = client.post(PREFIX + '/integration/runs/' + run['id'] + '/actions/pause',
                              json={'expected_version': current['version'], 'data': {}},
                              headers={'Idempotency-Key': 'still-manageable'})
        assert managed.status_code == 200 and managed.json()['state'] == 'PAUSED'


def test_headless_rejects_nonlocal_peer_and_legacy_mutation(rig, tmp_path):
    app = create_app(tmp_path, TOKEN, manager=rig[0], start_worker=False)
    with TestClient(app, client=('192.0.2.1', 1000)) as remote:
        assert remote.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin'}).status_code == 403
    with client_for(rig, tmp_path) as client:
        assert client.post(PREFIX + '/runs', json={}, headers={'Idempotency-Key': 'legacy', 'X-Gui-Session': 'forged'}).status_code == 403


def test_headless_worker_lock_registry_identity_and_epoch_persist_across_host_restart(rig, tmp_path, monkeypatch):
    events = []
    class FakeWorker:
        def __init__(self, manager): events.append('created')
        def tick(self): pass
        def close(self): events.append('closed')
    monkeypatch.setattr(integration_host, 'Worker', FakeWorker)
    first_app = create_app(tmp_path, TOKEN, 'plugin-principal', manager=rig[0])
    options = {'client': ('127.0.0.1', 1000), 'headers': {'X-Bsp-Service': 'plugin'}}
    with TestClient(first_app, **options) as first:
        initial = first.get('/api/v1/health').json()
        assert initial['worker_epoch'] == 1 and initial['controller_principal_id'] == 'plugin-principal'
        second_app = create_app(tmp_path, TOKEN, 'plugin-principal', manager=rig[0])
        with pytest.raises(RuntimeError, match='already running'):
            with TestClient(second_app, **options): pass
        assert events == ['created']
    assert events == ['created', 'closed']
    restarted_app = create_app(tmp_path, TOKEN, 'plugin-principal', manager=rig[0])
    with TestClient(restarted_app, **options) as restarted:
        health = restarted.get('/api/v1/health').json()
        assert health['runtime_id'] == initial['runtime_id']
        assert health['service_instance_id'] == initial['service_instance_id']
        assert health['worker_epoch'] == 2
    assert events == ['created', 'closed', 'created', 'closed']


def test_browser_bridge_exchanges_one_time_grant_for_read_only_cookie_without_service_secret(rig, tmp_path):
    with client_for(rig, tmp_path) as service:
        run = service.post(PREFIX + '/integration/runs', json=rig[3], headers={'Idempotency-Key': 'browser-run'}).json()
        response = service.post(PREFIX + '/integration/browser-session')
        assert response.status_code == 200
        grant = response.json()
        assert grant['access'] == 'read-only' and grant['expires_in'] == 60
        assert grant['path'].startswith('/auth#') and TOKEN not in str(grant)
        assert grant['bootstrap_code'] not in str(rig[0].store.documents('integration-browser-grant'))
        app = service.app
        with TestClient(app, client=('127.0.0.1', 1001), follow_redirects=False) as browser:
            assert browser.get(PREFIX + '/runs/' + run['id']).status_code == 401
            login = browser.get('/auth')
            assert login.status_code == 200 and TOKEN not in login.text
            exchanged = browser.post('/auth/session', data={'code': grant['bootstrap_code']},
                                     headers={'Origin': 'http://testserver'})
            assert exchanged.status_code == 303
            cookie = exchanged.headers['set-cookie'].lower()
            assert 'httponly' in cookie and 'samesite=strict' in cookie
            assert browser.get(PREFIX + '/runs/' + run['id']).status_code == 200
            assert browser.get(PREFIX + '/runs/' + run['id'] + '/report/json').status_code == 200
            mutation = browser.post(PREFIX + '/integration/runs', json=rig[3], headers={'Idempotency-Key': 'forbidden'})
            assert mutation.status_code == 403
            assert browser.get(PREFIX + '/runs', headers={'Origin': 'https://attacker.example'}).status_code == 403
            replay = browser.post('/auth/session', data={'code': grant['bootstrap_code']}, headers={'Origin': 'http://testserver'})
            assert replay.status_code == 401
        assert len(rig[0].store.all()) == 1


def test_browser_grant_expiry_and_cross_origin_exchange_fail_closed(rig, tmp_path, monkeypatch):
    with client_for(rig, tmp_path) as service:
        grant = service.post(PREFIX + '/integration/browser-session').json()
        with TestClient(service.app, client=('127.0.0.1', 1001), follow_redirects=False) as browser:
            rejected = browser.post('/auth/session', data={'code': grant['bootstrap_code']}, headers={'Origin': 'https://attacker.example'})
            assert rejected.status_code == 403 and 'set-cookie' not in rejected.headers
            now = integration_host.time.time()
            monkeypatch.setattr(integration_host.time, 'time', lambda: now + 61)
            expired = browser.post('/auth/session', data={'code': grant['bootstrap_code']}, headers={'Origin': 'http://testserver'})
            assert expired.status_code == 401 and 'set-cookie' not in expired.headers


def test_reference_client_reuses_service_and_stable_intent_across_plugin_restarts(tmp_path):
    identity = {'runtime_id': 'runtime-one', 'package_version': '0.1.0', 'config_revision': 'cfg', 'runner_id': 'runner'}
    calls = []
    health = identity | {'integration_contract_version': CONTRACT_VERSION, 'service_instance_id': 'instance',
                         'worker_epoch': 4, 'worker_running': True}
    def transport(request):
        calls.append(request)
        return httpx.Response(200 if request.method == 'GET' else 202,
                              json=health if request.url.path.endswith('/health') else {'id': 'a' * 32})
    class Starter:
        def start(self): pytest.fail('An existing healthy service must be reused')
    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        for _ in range(2):
            plugin = PluginClient('http://127.0.0.1:8767', TOKEN, identity, client=http, starter=Starter(), log_dir=tmp_path / 'logs')
            assert plugin.ensure_service()['service_instance_id'] == 'instance'
            assert plugin.start('same-intent', '/srv/release/install.bat', ['*.py'])['id'] == 'a' * 32
    posts = [request for request in calls if request.method == 'POST']
    assert len(posts) == 2 and {request.headers['Idempotency-Key'] for request in posts} == {'same-intent'}
    assert all('authorization' not in request.headers and request.headers['X-Bsp-Service'] == 'plugin' for request in calls)


@pytest.mark.parametrize('changed', ['runtime_id', 'package_version', 'config_revision', 'runner_id'])
def test_reference_client_identity_mismatch_never_starts_competing_service(changed, tmp_path):
    identity = {'runtime_id': 'runtime', 'package_version': '0.1.0', 'config_revision': 'cfg', 'runner_id': 'runner'}
    health = identity | {'integration_contract_version': CONTRACT_VERSION, 'service_instance_id': 'instance',
                         'worker_epoch': 1, 'worker_running': True, changed: 'different'}
    class Starter:
        def start(self): pytest.fail('Identity mismatch must not start a second service')
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=health))) as http:
        client = PluginClient('http://127.0.0.1:8767', TOKEN, identity, client=http, starter=Starter(), log_dir=tmp_path / 'logs')
        with pytest.raises(TestError) as error:
            client.ensure_service()
        assert error.value.code == 'SERVICE_IDENTITY_MISMATCH'


def test_module_defaults_persist_but_execution_override_never_changes_saved_values(tmp_path):
    path = tmp_path / 'plugin-defaults.json'
    defaults = PatternDefaults(path)
    defaults.save(None, ['global/*.py'])
    defaults.save('ethernet', ['ethernet/*.py'])
    before = path.read_bytes()
    assert defaults.suggest('ethernet', ['edited/*.py']) == ['edited/*.py']
    assert path.read_bytes() == before
    assert PatternDefaults(path).suggest('ethernet') == ['ethernet/*.py']
    assert PatternDefaults(path).suggest('Ethernet') == ['global/*.py']


@pytest.mark.parametrize('trials,expected,next_runs', [
    (['FAIL', 'PASS', 'PASS', 'PASS'], 'PASS', True),
    (['FAIL', 'PASS', 'FAIL'], 'INCOMPLETE', False),
])
def test_api_worker_prepares_once_and_runs_logical_retry_policy_with_raw_evidence(rig, tmp_path, trials, expected, next_runs):
    manager, service, config, request, _, prepared = rig
    original = service.preparer
    def two_cases(*args):
        receipt = original(*args)
        receipt['catalog']['tests'].append({**receipt['catalog']['tests'][0], 'id': 'next-case', 'path': 'next.py'})
        return receipt
    service.preparer = two_cases
    flashed = []
    released = []
    outcomes = iter(trials)
    executed = []
    def begin(receipt, context):
        flashed.append(context)
        return {'state': 'READY', 'id': 'batch-one', 'terminated': True}
    def execute(tc, connections, timeout, context, emit, cancelled):
        executed.append(tc['id'])
        emit('stdout', 'Test Result: ' + next(outcomes) + '\n')
        return {'exit_code': 0, 'terminated': True}
    manager.runner.begin_integration = begin
    manager.runner.execute = execute
    manager.runner.finish_integration = lambda receipt: released.append(receipt) or receipt | {'state': 'RELEASED'}
    worker = Worker(manager)
    try:
        with client_for(rig, tmp_path) as client:
            response = client.post(PREFIX + '/integration/runs', json=request, headers={'Idempotency-Key': 'whole-workflow'})
            assert response.status_code == 202
            accepted = response.json()
            assert accepted['environment_ready'] is False and prepared == []
            config['tc_root'] = '/srv/new-default-must-not-replace-frozen-config'
            replay = client.post(PREFIX + '/integration/runs', json=request, headers={'Idempotency-Key': 'whole-workflow'})
            assert replay.json() == accepted
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                worker.tick()
                run = client.get(PREFIX + '/runs/' + accepted['id']).json()
                if run['state'] == 'COMPLETED': break
                time.sleep(.005)
            assert run['state'] == 'COMPLETED', run
            assert run['overall_result'] == expected
            assert len(prepared) == 1 and len(flashed) == 1
            assert prepared[0][1]['tc_root'] == '/srv/tests'
            assert executed == (['case'] * 3 + ['next-case'] if next_runs else ['case'] * 3)
            report = client.get(PREFIX + '/runs/' + accepted['id'] + '/report/json').json()
            assert [a['state'] for a in report['attempts']] == trials
            assert report['slot_results']['0'] == ('PASS' if next_runs else 'FAIL')
            assert report['results'].get('next-case', 'PENDING') == ('PASS' if next_runs else 'PENDING')
            csv = client.get(PREFIX + '/runs/' + accepted['id'] + '/report/csv').text
            assert 'LOGICAL' in csv and 'FAIL' in csv
            deadline = time.monotonic() + 3
            while not manager.get(accepted['id'])['integration'].get('batch_released') and time.monotonic() < deadline:
                worker.tick()
                time.sleep(.005)
            assert manager.get(accepted['id'])['integration']['batch_released'] is True
            assert len(released) == 1
    finally:
        worker.close()
