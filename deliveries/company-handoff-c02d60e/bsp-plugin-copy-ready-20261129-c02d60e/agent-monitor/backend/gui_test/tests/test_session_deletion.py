"""Explicit test-record deletion: private copies only, no devices or real user data."""
import json
import sqlite3
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.core.models import TestError, uid
from backend.gui_test.execution.host import Host
from backend.gui_test.execution.session_deletion import delete_session
from backend.gui_test.standalone.server import create_app
from .test_core import request, complete, legacy_policy
from .test_windows_runner import BOARD, TEMPLATE


def test_permanent_delete_removes_failed_records_and_blocks_late_replay(tmp_path):
    app = create_app(tmp_path, start_worker=False); m = app.state.manager
    key = uid(); req = request(m); run = legacy_policy(m, m.start(key, 'owner', req))
    with pytest.raises(TestError) as exc: m.sessions.delete(run['id'], 'owner', run['version'])
    assert exc.value.code == 'SESSION_ACTIVE'
    finished = complete(m, run, {run['tests'][0]['id']: 'FAIL'})
    with pytest.raises(TestError): m.sessions.delete(run['id'], 'observer', finished['version'])
    with pytest.raises(TestError): m.sessions.delete(run['id'], 'owner', finished['version'] - 1)
    with TestClient(app, client=('127.0.0.1', 1234), headers={'X-BSP-Client': 'dashboard', 'X-GUI-Session': 'owner'}) as client:
        result = client.request('DELETE', '/api/v1/gui-test/runs/' + run['id'], json={'expected_version': finished['version'], 'data': {}})
        assert result.status_code == 200 and result.json()['deleted']
        assert client.get('/api/v1/gui-test/runs').json() == []
        assert client.get('/api/v1/gui-test/runs/' + run['id']).status_code == 410
        assert client.get('/api/v1/gui-test/runs/' + run['id'] + '/report/json').status_code == 410
    with m.store.connection() as c:
        assert c.execute('SELECT COUNT(*) FROM events WHERE run_id=?', (run['id'],)).fetchone()[0] == 0
        assert all('attempts' not in json.loads(row[0]) for row in c.execute('SELECT result FROM commands'))
    with pytest.raises(TestError) as exc: m.start(key, 'owner', req)
    assert exc.value.code == 'RUN_DELETED'


def test_remote_failure_keeps_records_and_retry_finishes_deletion(tmp_path):
    app = create_app(tmp_path, start_worker=False); m = app.state.manager
    run = m.start(uid(), 'owner', request(m)); finished = complete(m, run)
    with m.store.transaction() as c:
        stored = m.store.get(c, run['id']); stored['simulation'] = False; m.store.save(c, stored, 'FIXTURE_REAL_ADAPTER')
    version = m.get(run['id'])['version']
    def fail(_): raise TestError('fixture disconnected', 'RUNNER_UNAVAILABLE', 503)
    m.runner = SimpleNamespace(delete_session=fail)
    with pytest.raises(TestError): m.sessions.delete(run['id'], 'owner', version)
    assert m.get(run['id'])['attempts'] == finished['attempts']
    with pytest.raises(TestError) as exc: m.act(run['id'], uid(), 'owner', version, 'request-control')
    assert exc.value.code == 'RUN_DELETING'
    m.runner.delete_session = lambda _: {'deleted': True}
    assert m.sessions.delete(run['id'], 'owner', version)['deleted']


def rig(tmp_path):
    source = tmp_path / 'shared'; source.mkdir(); (source / 'case.py').write_text("print('Test Result: PASS')")
    host = Host({'source_root': str(source), 'python': sys.executable, 'boards': [BOARD]}, tmp_path / 'runtime', ports=lambda: {BOARD['com']})
    return host


def job(host, identity, state='DONE', batch=None):
    item = {'id': identity, 'request_hash': 'a' * 64, 'state': state, 'terminated': state == 'DONE', 'stdout': 'sensitive-evidence', 'stderr': '', 'request': {'private': 'evidence'}}
    if batch: item['batch_id'] = batch
    with sqlite3.connect(host.db) as c: c.execute('INSERT INTO jobs VALUES(?,?,?)', (identity, 'a' * 64, json.dumps(item)))
    directory = host.runtime / 'snapshots' / identity
    directory.mkdir(parents=True); (directory / 'generated-data.bin').write_bytes(b'generated test bytes')
    return directory


def test_host_purges_private_output_and_prevents_deleted_execution_replay(tmp_path):
    host = rig(tmp_path); identity = uid(); directory = job(host, identity)
    shared = host.runtime / 'source-snapshots' / ('b' * 64); shared.mkdir(parents=True); (shared / 'file.py').touch()
    other_id = uid(); other = job(host, other_id)
    payload = {'runner_id': host.identity, 'execution_ids': [identity]}
    assert delete_session(host, payload)['deleted']
    assert not directory.exists() and other.exists() and shared.exists()
    data = host.get(identity)
    assert data['state'] == 'DELETED' and 'sensitive-evidence' not in str(data) and 'request' not in data
    assert delete_session(host, payload)['deleted']
    with pytest.raises(TestError) as exc:
        host.start({'id': identity, 'tc_id': 'case.py', 'source_revision': host.catalog()['revision'], 'connection': {'a': BOARD}, 'template': TEMPLATE})
    assert exc.value.code == 'RUN_DELETED'


@pytest.mark.parametrize('state', ['RUNNING', 'UNKNOWN'])
def test_active_or_unknown_work_prevents_any_cleanup(tmp_path, state):
    host = rig(tmp_path); completed = uid(); directory = job(host, completed); active = uid(); job(host, active, state)
    with pytest.raises(TestError) as exc: delete_session(host, {'runner_id': host.identity, 'execution_ids': [completed]})
    assert exc.value.code == 'SESSION_ACTIVE' and directory.exists()
    assert host.get(completed)['stdout'] == 'sensitive-evidence'


def test_paths_identity_and_links_cannot_escape_private_copies(tmp_path):
    host = rig(tmp_path); identity = uid(); directory = job(host, identity)
    with pytest.raises(TestError): delete_session(host, {'runner_id': 'f' * 32, 'execution_ids': [identity]})
    with pytest.raises(TestError): delete_session(host, {'runner_id': host.identity, 'execution_ids': ['../shared']})
    external = tmp_path / 'external'; external.mkdir(); (external / 'keep.txt').write_text('keep')
    (directory / 'link').symlink_to(external, target_is_directory=True)
    with pytest.raises(TestError): delete_session(host, {'runner_id': host.identity, 'execution_ids': [identity]})
    assert (external / 'keep.txt').read_text() == 'keep' and directory.exists()


def test_released_batch_evidence_purged_but_held_reservation_preserved(tmp_path):
    host = rig(tmp_path); batch = uid(); child = uid(); directory = job(host, child, batch=batch)
    with sqlite3.connect(host.db) as c:
        c.execute('INSERT INTO batches VALUES(?,?,?)', (batch, 'frozen', json.dumps({'id': batch, 'state': 'RESERVED', 'epoch': 1})))
    payload = {'runner_id': host.identity, 'execution_ids': [child], 'batch_id': batch}
    with pytest.raises(TestError): delete_session(host, payload)
    assert directory.exists()
    with sqlite3.connect(host.db) as c:
        c.execute('UPDATE batches SET data=? WHERE id=?', (json.dumps({'id': batch, 'state': 'RELEASED', 'epoch': 1, 'private': 'evidence'}), batch))
    assert delete_session(host, payload)['deleted'] and not directory.exists()
    with sqlite3.connect(host.db) as c:
        assert 'evidence' not in c.execute('SELECT data FROM batches WHERE id=?', (batch,)).fetchone()[0]
