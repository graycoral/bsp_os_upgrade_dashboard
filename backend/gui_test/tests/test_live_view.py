"""Live Test view isolation and execution gates; no external runner is contacted."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app as dashboard_app
from backend.gui_test.adapters.mock import MockBoards, demo_catalog
from backend.gui_test.core.models import TestError, uid
from backend.gui_test.runtime import live_manager
from backend.gui_test.standalone.server import create_app as standalone_app
from .test_core import request


BASE = '/api/v1/gui-test'
HEADERS = {'X-BSP-Client': 'dashboard', 'X-GUI-Session': 'owner', 'Idempotency-Key': 'live-view-test'}


@pytest.mark.parametrize('kind', ['dashboard', 'standalone'])
def test_unconfigured_live_view_has_no_mock_data_or_history_and_rejects_forged_run(tmp_path, kind):
    app = dashboard_app(tmp_path) if kind == 'dashboard' else standalone_app(tmp_path, start_worker=False)
    with TestClient(app, client=('127.0.0.1', 1000), headers=HEADERS) as client:
        mock = client.get(BASE + '/catalog').json()
        assert mock['tests']
        mock_request = request(app.state.gui_manager if kind == 'dashboard' else app.state.manager)
        assert client.post(BASE + '/runs', json=mock_request).status_code == 202
        assert len(client.get(BASE + '/runs').json()) == 1

        live = BASE + '/live'
        capability = client.get(live + '/capabilities').json()
        assert capability['simulation'] is False and capability['hardware'] is True
        assert capability['connection']['state'] == 'unconfigured'
        assert capability['connection']['ready'] is False
        assert capability['branches'] == ['shared']
        assert client.get(live + '/catalog').json() == {
            'branch': 'shared', 'revision': '', 'metadata_revision': '', 'tests': []}
        assert client.get(live + '/boards').json() == {'source': 'WINDOWS_CONFIGURED', 'boards': []}
        assert client.get(live + '/runs').json() == []
        assert client.get(live + '/saved/suite').json() == []
        assert client.get(live + '/saved/profile').json() == []
        assert client.get(live + '/demo/jobs').json() == []
        for endpoint in ('/preflight', '/runs'):
            rejected = client.post(live + endpoint, json=mock_request)
            assert rejected.status_code == 503
            assert rejected.json()['code'] == 'RUNNER_UNAVAILABLE'
        assert client.get(live + '/runs').json() == []
        assert len(client.get(BASE + '/runs').json()) == 1


@pytest.mark.parametrize('kind', ['dashboard', 'standalone'])
def test_configured_manager_is_reused_and_disconnection_blocks_execution(tmp_path, monkeypatch, kind):
    (tmp_path / 'gui-test.json').write_text(json.dumps({'runner': 'windows-http', 'url': 'http://127.0.0.1:43871'}))
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', 'local-test-token-' + 'x' * 32)
    if kind == 'standalone':
        with pytest.raises(ValueError, match='integrated Dashboard'):
            standalone_app(tmp_path, start_worker=False)
        return

    app = dashboard_app(tmp_path)
    manager = app.state.gui_manager
    assert live_manager(tmp_path, 'dashboard', manager) is manager
    calls = []

    def offline(path, method='GET', data=None):
        calls.append(path)
        raise TestError('fixture disconnected', 'RUNNER_UNAVAILABLE')

    monkeypatch.setattr(manager.runner, 'request', offline)
    with TestClient(app, client=('127.0.0.1', 1000), headers=HEADERS) as client:
        live = BASE + '/live'
        capability = client.get(live + '/capabilities').json()
        assert capability['simulation'] is False
        assert capability['connection']['state'] == 'disconnected'
        assert capability['connection']['ready'] is False
        assert calls == ['/identity']
        assert client.get(live + '/catalog').json()['tests'] == []
        assert client.get(live + '/boards').json()['boards'] == []
        forged = {'tc_ids': ['demo/test'], 'source_revision': 'forged', 'connection': {
            'a': {'host': 'fake', 'board_id': 'fake', 'com': 'COM1'},
            'b': {'host': 'fake', 'board_id': 'fake-b', 'com': 'COM2'}},
            'execution': 'hardware'}
        for endpoint in ('/preflight', '/runs'):
            response = client.post(live + endpoint, json=forged)
            assert response.status_code == 503
            assert response.json()['code'] == 'RUNNER_UNAVAILABLE'
        assert client.get(live + '/runs').json() == []


def test_connected_capability_uses_real_manager_without_a_second_worker(tmp_path, monkeypatch):
    (tmp_path / 'gui-test.json').write_text(json.dumps({'runner': 'windows-http', 'url': 'http://127.0.0.1:43871'}))
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', 'local-test-token-' + 'x' * 32)
    app = dashboard_app(tmp_path)
    manager = app.state.gui_manager
    seen = []

    def fixture_response(path, method='GET', data=None):
        seen.append(path)
        if path == '/identity':
            return {'status': 'ok'}
        if path == '/catalog':
            return {'branch': 'shared', 'revision': 'real-revision', 'metadata_revision': 'real-metadata', 'tests': []}
        if path == '/boards':
            return {'boards': []}
        raise AssertionError(f'unexpected runner request: {path}')

    monkeypatch.setattr(manager.runner, 'request', fixture_response)
    assert live_manager(tmp_path, 'dashboard', manager) is manager
    with TestClient(app, client=('127.0.0.1', 1000), headers=HEADERS) as client:
        cap = client.get(BASE + '/live/capabilities').json()
        assert cap['connection'] == {'state': 'connected', 'ready': True,
                                     'message': cap['connection']['message']}
        assert cap['simulation'] is False
        assert client.get(BASE + '/live/catalog').json()['revision'] == 'real-revision'
        assert client.get(BASE + '/live/boards').json() == {'source': 'WINDOWS_CONFIGURED', 'boards': []}
        assert seen == ['/identity', '/identity', '/catalog', '/identity', '/boards']
        assert client.get(BASE + '/live/runs').json() == client.get(BASE + '/runs').json() == []


def test_offline_run_can_be_paused_cancelled_and_controlled_but_not_resumed(tmp_path, monkeypatch):
    (tmp_path / 'gui-test.json').write_text(json.dumps({'runner': 'windows-http', 'url': 'http://127.0.0.1:43871'}))
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', 'local-test-token-' + 'x' * 32)
    app = dashboard_app(tmp_path)
    manager = app.state.gui_manager
    online = {'ready': True}
    catalog = demo_catalog()
    boards = MockBoards().boards()

    def fixture_response(path, method='GET', data=None):
        if not online['ready']:
            raise TestError('fixture disconnected', 'RUNNER_UNAVAILABLE')
        if path == '/identity':
            return {'status': 'ok'}
        if path == '/catalog':
            return catalog
        if path == '/boards':
            return {'boards': boards}
        if path == '/verify':
            return {'ok': True}
        raise AssertionError(f'unexpected runner request: {path}')

    monkeypatch.setattr(manager.runner, 'request', fixture_response)
    profile = manager.save_document('command', 'Fixture command', {
        'single': ['python3', '{tc_path}', '-p', '{com_a}'],
        'dual': ['python3', '{tc_path}', '-n', '{node_a}', '-n2', '{node_b}']})
    tc = next(t for t in catalog['tests'] if t['kind'] == 'Single' and not t['disabled_reason'])
    payload = {'tc_ids': [tc['id']], 'source_revision': catalog['revision'],
               'connection': {'a': boards[0]}, 'execution': 'hardware',
               'command_profile': 'Fixture command', 'command_revision': profile['revision']}
    live = BASE + '/live'
    with TestClient(app, client=('127.0.0.1', 1000), headers=HEADERS) as client:
        created = client.post(live + '/runs', json=payload, headers={'Idempotency-Key': uid()})
        assert created.status_code == 202
        queued = created.json()
        online['ready'] = False
        action = lambda run, name: client.post(
            live + '/runs/' + run['id'] + '/actions/' + name,
            json={'expected_version': run['version'], 'data': {}},
            headers={'Idempotency-Key': uid()})
        paused = action(queued, 'pause')
        assert paused.status_code == 200 and paused.json()['state'] == 'PAUSED'
        blocked = action(paused.json(), 'resume')
        assert blocked.status_code == 503 and blocked.json()['code'] == 'RUNNER_UNAVAILABLE'
        controlled = client.post(live + '/runs/' + queued['id'] + '/actions/request-control',
                                 json={'expected_version': paused.json()['version'], 'data': {}},
                                 headers={'Idempotency-Key': uid(), 'X-GUI-Session': 'observer'})
        assert controlled.status_code == 200
        cancelled = action(controlled.json(), 'cancel')
        assert cancelled.status_code == 200 and cancelled.json()['state'] == 'CANCELLED'

        online['ready'] = True
        second = client.post(live + '/runs', json=payload, headers={'Idempotency-Key': uid()})
        assert second.status_code == 202
        running = second.json()
        # Simulate a persisted active attempt. No worker or TC process is started.
        with manager.store.transaction() as connection:
            record = manager.store.get(connection, running['id'])
            record['state'] = 'RUNNING'
            record['attempts'].append({'tc_id': tc['id'], 'state': 'RUNNING'})
            manager.store.save(connection, record, 'FIXTURE_ACTIVE')
        online['ready'] = False
        running = client.get(live + '/runs/' + running['id']).json()
        intent = action(running, 'cancel')
        assert intent.status_code == 200 and intent.json()['state'] == 'CANCEL_REQUESTED'
        assert client.get(live + '/runs/' + running['id']).json()['state'] == 'CANCEL_REQUESTED'
