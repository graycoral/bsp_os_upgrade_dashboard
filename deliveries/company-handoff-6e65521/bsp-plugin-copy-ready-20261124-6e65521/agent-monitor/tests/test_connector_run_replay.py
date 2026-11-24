"""Host acceptance and Linux prepared-request replay using the packaged mock board."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import pytest

from backend.gui_test.core.models import TestError, digest
from backend.gui_test.execution.connector_runs import ConnectorRunRequest
from backend.gui_test.standalone.direct_connector_client import DirectConnectorClient
from test_direct_connector_unit3 import _build_installer_zip, _build_source_zip, _setup_host, _upload_source


ROOT = Path(__file__).resolve().parents[1]
ROUTE = '/v1/connector-runs'


def example(name):
    return json.loads((ROOT / 'examples' / 'connector-runs' / f'{name}.json').read_text(encoding='utf-8'))


@contextmanager
def mock_board(tmp_path, monkeypatch):
    _, _, host, app = _setup_host(tmp_path, with_flash=True)
    # Leave the accepted run queued so concurrency and busy checks are deterministic.
    monkeypatch.setattr(host.connector, 'start_worker', lambda: None)
    with TestClient(app, base_url='http://127.0.0.1:8771', client=('127.0.0.1', 5100)) as client:
        bundle, snapshot, _ = _build_source_zip(tmp_path, scripts={
            't1.py': "print('Test Result: PASS')\n", 't2.py': "print('Test Result: PASS')\n",
        })
        src, rev = _upload_source(client, bundle, snapshot)
        yield host, client, example('tc_only') | {'source_snapshot_id': src, 'source_revision': rev}


@pytest.fixture
def board(tmp_path, monkeypatch):
    with mock_board(tmp_path, monkeypatch) as result:
        yield result


def test_public_schema_and_flash_example_match_host(board, tmp_path):
    host, http, body = board
    public = json.loads((ROOT / 'contracts/connector-run-request-v1.schema.json').read_text(encoding='utf-8'))
    assert public == ConnectorRunRequest.model_json_schema()
    _, installer, sha, raw = _build_installer_zip(tmp_path)
    upload = http.put(f'/v1/installer-snapshots/{installer}', content=raw, headers={
        'Content-Type': 'application/zip', 'Content-Range': f'bytes 0-{len(raw)-1}/{len(raw)}',
        'Content-Length': str(len(raw)), 'X-Archive-SHA256': sha,
    })
    assert upload.status_code == 200 and upload.json()['state'] == 'READY'
    flash = example('flash_and_test') | {k: body[k] for k in ('source_snapshot_id', 'source_revision')}
    flash['installer'].update(installer_snapshot_id=installer, flash_profile_revision=host.flash_profile_revisions['default']['revision'])
    headers = {'Idempotency-Key': 'flash'}
    for invalid in (flash | {'installer': None}, flash | {'execution_mode': 'tc_only'}):
        response = http.post(ROUTE, json=invalid, headers=headers)
        assert (response.status_code, response.json()['code']) == (422, 'INVALID_REQUEST')
    accepted = http.post(ROUTE, json=flash, headers=headers)
    assert (accepted.status_code, accepted.json()['installer_snapshot_id']) == (201, installer)


def test_body_fingerprint_and_busy_state_across_clients(board):
    host, http, body = board
    body.update(run_id='a' * 32, request_hash='b' * 64)
    body['tests'].append(dict(step_index=1, tc_id='t2.py', path='t2.py', kind='Single'))
    headers = {'Idempotency-Key': 'same'}
    contender = body | {'origin': {'session_id': 'competitor'}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda item: http.post(ROUTE, json=item, headers=headers), [body, contender] * 2))
    assert sorted(r.status_code for r in results) == [200, 201, 409, 409]
    winner = next(payload for payload, response in zip([body, contender] * 2, results) if response.status_code == 201)
    # Reordered object keys and presentation whitespace are insignificant.
    payload = json.dumps(dict(reversed(winner.items())), indent=2)
    replay = http.post(ROUTE, content=payload, headers=headers | {'Content-Type': 'application/json'})
    assert replay.status_code == 200 and replay.json()['request_hash'] == 'b' * 64
    assert replay.json()['run_id'] == winner['run_id']
    for mutation in (
        {'run_id': 'c' * 32}, {'tests': winner['tests'][::-1]}, {'installer': None},
        {'request_hash': 'd' * 64}, {'execution_mode': 'invalid'}, {'unknown': 'field'},
    ):
        conflict = http.post(ROUTE, json=winner | mutation, headers=headers)
        assert (conflict.status_code, conflict.json()['code'], conflict.json()['run_id']) == (
            409, 'IDEMPOTENCY_CONFLICT', winner['run_id'])
    with sqlite3.connect(host.db) as db:
        assert db.execute('SELECT body_fingerprint FROM connector_runs').fetchall() == [(digest(winner),)]
        db.execute("UPDATE connector_runs SET state='UNKNOWN', version=version+1")
    assert http.post(ROUTE, json=winner, headers=headers).json()['state'] == 'UNKNOWN'
    other_board = winner | {'connection': {'a': {'host': 'WINPC', 'board_id': 'B2', 'com': 'COM4'}}, 'run_id': None}
    blocked = http.post(ROUTE, json=other_board, headers={'Idempotency-Key': 'project-B'})
    assert (blocked.status_code, blocked.json()['code']) == (409, 'ACTIVE_RUN_EXISTS')
    assert http.post(f"{ROUTE}/{winner['run_id']}/reconcile", json={'action': 'MARK_ABORTED'}).status_code == 200
    assert http.delete(f"{ROUTE}/{winner['run_id']}").status_code == 200
    assert http.post(ROUTE, json=winner, headers=headers).status_code == 410


@pytest.mark.parametrize('hint,can_prove', [('server', True), ('direct', True), ('arbitrary', False)])
def test_reopen_v2_database_and_prove_legacy_request(tmp_path, monkeypatch, hint, can_prove):
    with mock_board(tmp_path, monkeypatch) as (host, http, body):
        if hint == 'direct':
            body['tests'][0]['effective_timeout_s'] = 600
            body['request_hash'] = digest(body)
        elif hint == 'arbitrary':
            body['request_hash'] = '2' * 64
        headers = {'Idempotency-Key': f'old-{hint}'}
        accepted = http.post(ROUTE, json=body, headers=headers)
        assert accepted.status_code == 201
        run_id = accepted.json()['run_id']
    with sqlite3.connect(host.db) as db:
        db.execute("UPDATE connector_runs SET state='COMPLETED', outcome='PASSED'")
        db.execute('ALTER TABLE connector_runs DROP COLUMN body_fingerprint')
        db.execute("UPDATE runner_meta SET value='2' WHERE key='connector_schema_version'")
    backup_path = tmp_path / 'before-upgrade.db'
    with sqlite3.connect(host.db) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    _, _, reopened, app = _setup_host(tmp_path, with_flash=True)
    monkeypatch.setattr(reopened.connector, 'start_worker', lambda: None)
    with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5101)) as retry:
        identity = retry.get('/v1/identity').json()
        assert identity['runner_id'] == host.identity
        assert identity['connector_schema_version'] == '3'
        for changed in (body | {'run_id': run_id}, body | {'timeout_settings_snapshot': {'default_seconds': 5}}):
            rejected = retry.post(ROUTE, json=changed, headers=headers)
            assert (rejected.status_code, rejected.json()['code']) == (409, 'IDEMPOTENCY_CONFLICT')
        res = retry.post(ROUTE, json=body, headers=headers)
        assert res.status_code == (200 if can_prove else 409)
        assert res.json()['run_id'] == run_id
        assert retry.get(f'{ROUTE}/{run_id}').json()['outcome'] == 'PASSED'
        if can_prove:
            assert retry.post(ROUTE, json=body | {'installer': None}, headers=headers).status_code == 409
        with sqlite3.connect(reopened.db) as db:
            assert db.execute('SELECT body_fingerprint FROM connector_runs').fetchone()[0] == (digest(body) if can_prove else None)
        rerun = retry.post(f'{ROUTE}/{run_id}/rerun', headers={'Idempotency-Key': 'rerun'})
        assert rerun.status_code == 201 and rerun.json()['parent_run_id'] == run_id
        duplicate = retry.post(f'{ROUTE}/{run_id}/rerun', headers={'Idempotency-Key': 'rerun'})
        assert duplicate.status_code == 200 and duplicate.json()['run_id'] == rerun.json()['run_id']

    # Restore a stopped copy, preserving the upgraded DB and its new rerun.
    with sqlite3.connect(backup_path) as source, sqlite3.connect(tmp_path / 'rollback.db') as restored:
        source.backup(restored)
        assert restored.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert restored.execute("SELECT value FROM runner_meta WHERE key='connector_schema_version'").fetchone()[0] == '2'
        assert 'body_fingerprint' not in {row[1] for row in restored.execute('PRAGMA table_info(connector_runs)')}
        assert restored.execute('SELECT run_id, outcome FROM connector_runs').fetchall() == [(run_id, 'PASSED')]


def test_saved_prepared_run_survives_lost_response_and_changed_source(board, tmp_path, monkeypatch):
    host, http, _ = board
    tc = tmp_path / 'tcs'
    tc.mkdir()
    (tc / 't1.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'linux')
    prepared = direct.prepare_run(project='P1', build='B1', tc_root=tc, command_snapshot=example('tc_only')['command_snapshot'])
    assert prepared['runner_id'] == host.identity and prepared['project'] == 'P1' and prepared['build'] == 'B1'
    assert http.get(ROUTE).json()['runs'] == []
    saved = json.loads(json.dumps(prepared))
    original_request = direct._request
    calls = []
    def lose_response(method, path, **kwargs):
        calls.append((method, path))
        data = original_request(method, path, **kwargs)
        if method == 'POST':
            raise TestError('Response lost after acceptance', 'CONNECTOR_UNREACHABLE', 503)
        return data
    monkeypatch.setattr(direct, '_request', lose_response)
    with pytest.raises(TestError, match='Response lost'):
        direct.send_prepared_run(prepared)
    assert calls == [('GET', '/v1/identity'), ('POST', ROUTE)]
    run_id = http.get(ROUTE).json()['runs'][0]['run_id']
    (tc / 't1.py').unlink()
    recovered = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'new-session')
    expected = recovered.send_prepared_run(saved)
    assert expected['run_id'] == run_id
    assert len(http.get(ROUTE).json()['runs']) == 1
    wrong = saved | {'build': 'B2'}
    with pytest.raises(TestError) as invalid:
        recovered.send_prepared_run(wrong)
    assert invalid.value.code == 'INVALID_PREPARED_RUN'
    with monkeypatch.context() as m:
        m.setattr(recovered, 'identity', lambda: {'service': 'bsp-board-connector', 'runner_id': 'replacement'})
        m.setattr(recovered, '_request', lambda *a, **kw: pytest.fail('Must reject before POST'))
        with pytest.raises(TestError) as changed:
            recovered.send_prepared_run(saved)
        assert changed.value.code == 'RUNNER_CHANGED'
    raced = http.post(ROUTE, headers={'X-Expected-Runner-ID': 'replacement', 'Idempotency-Key': saved['idempotency_key']}, json=saved['body'])
    assert (raced.status_code, raced.json()['code']) == (409, 'RUNNER_CHANGED')


def test_prepare_flash_with_registered_profile_through_host(board, tmp_path):
    host, http, _ = board
    tc = tmp_path / 'flash-tests'
    tc.mkdir()
    (tc / 't1.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
    images = tmp_path / 'images'
    images.mkdir()
    installer = images / 'flash_all.bat'
    installer.write_bytes(b'@echo FLASH OK\r\n')
    (images / 'boot.img').write_bytes(b'fixture')
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'linux')
    settings = direct.store.read()
    direct.store.save({
        'expected_revision': settings['revision'],
        'integration': settings['integration'] | {'installer_roots': [str(images)]},
        'timeouts': {k: v for k, v in settings['timeouts'].items() if k != 'revision'},
    })
    direct.store.save_command_profile('default', example('tc_only')['command_snapshot']['template'])
    prepared = direct.prepare_run(project='P1', build='B1', tc_root=tc, installer=installer)
    spec = prepared['body']['installer']
    assert spec['flash_profile_revision'] == host.flash_profile_revisions['default']['revision']
    installer.unlink()
    assert direct.send_prepared_run(prepared)['installer_snapshot_id'] == spec['installer_snapshot_id']
