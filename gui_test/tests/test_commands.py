"""Command templates are frozen invocation evidence; they never enable real execution."""
import copy
import subprocess

import pytest
from fastapi.testclient import TestClient

from gui_test.adapters.runner import default_command_template, resolve_argv, validate_command_template
from gui_test.core.models import TestError, uid
from gui_test.core.worker import Worker
from gui_test.runtime import make_manager
from gui_test.standalone.server import create_app


@pytest.fixture
def manager(tmp_path):
    return make_manager(tmp_path, 'standalone')


def request(manager, **changes):
    catalog = manager.catalog()
    return {'tc_ids': [t['id'] for t in catalog['tests']], 'source_revision': catalog['revision'],
            'connection': {'a': manager.boards.boards()[0], 'b': manager.boards.boards()[1]},
            'speed': 20, **changes}


def template():
    common = [r'C:\Program Files\Python312\python.exe', 'fixed runner.py', '--case', '{tc_name}', '--port-a', '{com_a}']
    return {'single': common, 'dual': common + ['--port-b', '{com_b}']}


@pytest.mark.parametrize('slot,expected', [('{tc_name}', 'example.case'), ('{tc_file}', 'example.case.py'),
                                          ('{tc_path}', 'folder with spaces/example.case.py')])
def test_tc_name_file_and_path_are_distinct_slots(manager, slot, expected):
    command = ['python', 'fixed.py', slot, '{com_a}']
    resolved = resolve_argv(command, {'kind': 'Single', 'path': 'folder with spaces/example.case.py'}, request(manager)['connection'])
    assert resolved == ['python', 'fixed.py', expected, 'COM3']
    assert command[2] == slot


@pytest.mark.parametrize('argv', [
    ['python', '{tc_name}', '{tc_file}', '{com_a}'],
    ['python', '{tc_name}', '{tc_name}', '{com_a}'],
    ['python', '{tc_name}', '{com_a}', '{com_a}'],
    ['python', '{tc_name}', '{com_a}', '{com_b}'],
    ['python', '--case={tc_name}', '{com_a}'],
    ['python', '{tc_name}', '--port={com_a}'],
    ['python', '{tc_name}', '{com_a}', 'trailing}'],
    ['python', '{tc_name}', '{com_a}', '{unknown}'],
    ['python', '{tc_name}', '{com_a}', 'bad\narg'],
    ['python', '{tc_name}', '{com_a}', 'bad\rarg'],
    ['python', '{tc_name}', '{com_a}', 'bad\0arg'],
    ['python', '{tc_name}', '{com_a}', ''],
    ['{tc_name}', 'fixed.py', '{com_a}'],
    ['python', '{tc_name}', '{com_a}', 1],
    ['python', '{tc_name}', '{com_a}'] + ['fixed'] * 62,
    ['python', '{tc_name}', '{com_a}', 'x' * 4097],
    ['python', '{tc_name}', '{com_a}'] + ['x' * 4096] * 4,
])
def test_invalid_templates_rejected_before_persistence(manager, argv):
    with pytest.raises(TestError) as error:
        manager.save_document('command', 'bad', {**template(), 'single': argv})
    assert error.value.status == 422
    assert manager.store.documents('command') == []


def test_profile_schema_and_dual_slots_are_required():
    with pytest.raises(TestError):
        validate_command_template({'single': template()['single']})
    with pytest.raises(TestError):
        validate_command_template({**template(), 'unexpected': 'ignored?'})
    with pytest.raises(TestError):
        validate_command_template({**template(), 'dual': template()['single']})


def test_saved_profile_persists_and_stale_selection_is_blocked(manager, tmp_path):
    saved = manager.save_document('command', 'Python commands', template())
    reopened = make_manager(tmp_path, 'standalone')
    assert reopened.store.documents('command') == [{'name': 'Python commands', **saved}]
    req = request(manager, command_profile='Python commands', command_revision=saved['revision'])
    assert reopened.preflight(req)['command_snapshot']['template'] == template()
    changed = template(); changed['single'][1] = 'new runner.py'
    current = manager.save_document('command', 'Python commands', changed)
    assert current['revision'] != saved['revision']
    for operation in (lambda: manager.preflight(req), lambda: manager.start(uid(), 'owner', req)):
        with pytest.raises(TestError) as error:
            operation()
        assert error.value.code == 'COMMAND_CHANGED'
    assert manager.store.all() == []


def test_snapshot_and_attempts_ignore_later_profile_edit_and_never_execute(manager, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Configuring a template must not execute a subprocess')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    saved = manager.save_document('command', 'Example', template())
    req = request(manager, command_profile='Example', command_revision=saved['revision'])
    run = manager.start(uid(), 'owner', req)
    snapshot = copy.deepcopy(run['command_snapshot'])
    changed = template(); changed['single'][1] = 'replacement.py'; changed['dual'][1] = 'replacement.py'
    manager.save_document('command', 'Example', changed)
    worker = Worker(manager)
    try:
        while claim := manager.claim(run['id']):
            assert claim['attempt']['resolved_command_argv'][1] == 'fixed runner.py'
            assert claim['context']['resolved_command_argv'] == claim['attempt']['resolved_command_argv']
            manager.finish(claim, worker.execute(claim))
    finally:
        worker.close()
    finished = manager.get(run['id'])
    assert finished['overall_result'] == 'PASS'
    assert finished['command_snapshot'] == snapshot
    assert len(finished['attempts']) == 5
    assert all(a['resolved_command_argv'][1] == 'fixed runner.py' for a in finished['attempts'])
    dual = next(a for a in finished['attempts'] if 'dual' in a['tc_id'])
    assert dual['resolved_command_argv'][-2:] == ['--port-b', 'COM4']
    assert 'MOCK ONLY' in dual['stdout']


def test_default_and_legacy_runs_keep_mock_template(manager):
    req = request(manager)
    run = manager.start(uid(), 'owner', req)
    assert run['command_snapshot']['template'] == default_command_template()
    with manager.store.transaction() as connection:
        raw = manager.store.get(connection, run['id']); del raw['command_snapshot']
        manager.store.save(connection, raw, 'LEGACY_FIXTURE')
    assert manager.claim(run['id'])['attempt']['resolved_command_argv'][0] == 'mock-tc'
    with pytest.raises(TestError) as error:
        manager.preflight({**req, 'command_revision': 'unused'})
    assert error.value.status == 422


def test_preview_api_save_and_stale_start(tmp_path):
    app = create_app(tmp_path, start_worker=False)
    manager = app.state.manager
    req = request(manager)
    headers = {'X-BSP-Client': 'dashboard', 'X-GUI-Session': 'owner', 'Idempotency-Key': uid()}
    with TestClient(app, client=('127.0.0.1', 1000), headers=headers) as client:
        base = '/api/v1/gui-test'
        preview = {'tc_id': req['tc_ids'][0], 'source_revision': req['source_revision'],
                   'connection': req['connection'], 'template': template()}
        response = client.post(base + '/commands/preview', json=preview)
        assert response.status_code == 200
        data = response.json()
        assert data['simulation'] is True and data['argv'][3] == '01_boot' and data['argv'][-1] == 'COM3'
        assert manager.store.all() == []
        assert client.post(base + '/commands/preview', json={**preview, 'template': {'single': ['bad'], 'dual': ['bad']}}).status_code == 422
        assert client.post(base + '/commands/preview', json={**preview, 'tc_id': 'missing'}).status_code == 422
        assert client.post(base + '/commands/preview', json={**preview, 'source_revision': 'stale'}).status_code == 409
        saved = client.put(base + '/saved/command', json={'name': 'Python example', 'data': template()})
        assert saved.status_code == 200 and saved.json()['revision'] == data['revision']
        assert client.get(base + '/saved/command').json()[0]['name'] == 'Python example'
        selected = {**req, 'command_profile': 'Python example', 'command_revision': saved.json()['revision']}
        assert client.post(base + '/preflight', json=selected).status_code == 200
        assert client.post(base + '/runs', json={**selected, 'command_revision': 'stale'}).status_code == 409
        assert client.post(base + '/preflight', json={**selected, 'execution': 'hardware'}).status_code == 422
        started = client.post(base + '/runs', json=selected)
        assert started.status_code == 202 and started.json()['command_snapshot']['template'] == template()


def test_recovery_after_restart_uses_original_command_profile(manager, tmp_path):
    saved = manager.save_document('command', 'Recoverable', template())
    run = manager.start(uid(), 'owner', request(manager, command_profile='Recoverable', command_revision=saved['revision']))
    claim = manager.claim(run['id'])
    manager.finish(claim, {'exit_code': 1, 'terminated': True, 'forced_state': 'ERROR'})
    changed = template(); changed['single'][1] = 'changed-after-error.py'
    manager.save_document('command', 'Recoverable', changed)
    reopened = make_manager(tmp_path, 'standalone')
    reopened.recover()
    current = reopened.get(run['id'])
    current = reopened.act(run['id'], uid(), 'owner', current['version'], 'demo-recover')
    reopened.act(run['id'], uid(), 'owner', current['version'], 'resume')
    next_attempt = reopened.claim(run['id'])
    assert next_attempt['attempt']['ordinal'] == 2
    assert next_attempt['attempt']['resolved_command_argv'][1] == 'fixed runner.py'
    assert reopened.get(run['id'])['command_snapshot']['revision'] == saved['revision']
