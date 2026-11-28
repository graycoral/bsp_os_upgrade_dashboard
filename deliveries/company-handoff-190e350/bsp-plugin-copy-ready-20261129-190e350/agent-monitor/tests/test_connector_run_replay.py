"""Host acceptance and Linux prepared-request replay using the packaged mock board."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from types import SimpleNamespace

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
    from backend.gui_test.execution.path_runs import PathRunRequest
    assert json.loads((ROOT / 'contracts/connector-path-run-v1.schema.json').read_text()) == PathRunRequest.model_json_schema()
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
        db.execute('ALTER TABLE connector_runs DROP COLUMN evidence_serials_json')
        db.execute('DROP TABLE connector_failure_evidence')
        db.execute("UPDATE runner_meta SET value='2' WHERE key='connector_schema_version'")
    backup_path = tmp_path / 'before-upgrade.db'
    with sqlite3.connect(host.db) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)
    _, _, reopened, app = _setup_host(tmp_path, with_flash=True)
    monkeypatch.setattr(reopened.connector, 'start_worker', lambda: None)
    with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5101)) as retry:
        identity = retry.get('/v1/identity').json()
        assert identity['runner_id'] == host.identity
        assert identity['connector_schema_version'] == '4'
        assert 'tc-failure-evidence-v1' in identity['capabilities']
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
    prepared = direct.prepare_run(project='P1', build='B1', tc_root=tc, patterns=['t1.py'], command_snapshot=example('tc_only')['command_snapshot'])
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
    from backend.gui_test.standalone.plugin_commands import execute_direct
    request_file = tmp_path / 'prepared-flash.json'
    output = []
    def cli(*args):
        return execute_direct(direct, ['test', *args], source_root=ROOT, project='P1',
                              project_root=tc, emit=output.append)
    assert cli('prepare', '--build', 'B1', '--tc-root', str(tc), '--pattern', 't1.py', '--installer', str(installer),
               '--flash-profile', 'default', '--flash', '--file', str(request_file)) == 0
    prepared = json.loads(request_file.read_text())
    assert output[-1]['flash_confirmation'] == prepared['flash_confirmation']
    spec = prepared['body']['installer']
    assert spec['flash_profile_revision'] == host.flash_profile_revisions['default']['revision']
    from hashlib import sha256
    confirmation = prepared['flash_confirmation']
    assert confirmation['installer_bat'] == {'path': 'flash_all.bat', 'size': installer.stat().st_size,
                                              'sha256': sha256(installer.read_bytes()).hexdigest()}
    assert confirmation['images'] == {'boot.img': {'size': 7, 'sha256': sha256(b'fixture').hexdigest()}}
    assert confirmation['target_boards'] == [prepared['body']['connection']['a']]
    changed = json.loads(json.dumps(prepared))
    changed['flash_confirmation']['images']['boot.img']['sha256'] = 'f' * 64
    changed['fingerprint'] = digest({k: v for k, v in changed.items() if k != 'fingerprint'})
    with pytest.raises(TestError):
        direct.send_prepared_run(changed)
    assert http.get(ROUTE).json()['runs'] == []
    installer.unlink()
    assert cli('send', '--file', str(request_file), '--flash') == 0
    result = output[-1]
    assert result['installer_snapshot_id'] == spec['installer_snapshot_id']
    assert result['flash_confirmation'] == confirmation
    legacy = {k: v for k, v in prepared.items() if k not in {'flash_confirmation', 'fingerprint'}}
    replay = direct.send_prepared_run(legacy | {'fingerprint': digest(legacy)})
    assert replay['run_id'] == result['run_id'] and replay['flash_confirmation'] == confirmation
    assert result['origin']['project'] == 'P1'
    assert [r['run_id'] for r in http.get(ROUTE, params={'project': 'P1'}).json()['runs']] == [result['run_id']]
    assert http.get(ROUTE, params={'project': 'P2'}).json()['runs'] == []
    assert http.get(ROUTE, params={'project': "P1' OR 1=1 --"}).json()['runs'] == []



def test_project_filter_precedes_limit_and_preserves_unlabelled_history(board, tmp_path):
    host, http, body = board
    ids = []
    for index, label in enumerate(('first / &', 'second', None)):
        origin = {'client': 'plugin', 'session_id': 'fixture'}
        if label:
            origin['project'] = label
        reply = http.post(ROUTE, json=body | {'origin': origin}, headers={'Idempotency-Key': f'p-{index}'})
        assert reply.status_code == 201, reply.text
        ids.append(reply.json()['run_id'])
        with sqlite3.connect(host.db) as db:
            db.execute("UPDATE connector_runs SET state='UNKNOWN' WHERE run_id=?", (ids[-1],))
        assert http.post(f'{ROUTE}/{ids[-1]}/reconcile', json={'action': 'MARK_ABORTED'}).status_code == 200

    assert len(http.get(ROUTE).json()['runs']) == 3
    scoped = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'linux', project='first / &')
    assert [r['run_id'] for r in scoped.list_runs(limit=1)] == ids[:1]
    assert scoped.get_run()['run_id'] == ids[0]
    for foreign in ids[1:]:
        with pytest.raises(TestError) as blocked:
            scoped.get_run(foreign)
        assert blocked.value.code == 'NOT_FOUND'


def test_selected_run_is_independent_of_display_catalog(board, tmp_path, monkeypatch):
    host, http, _ = board
    root = tmp_path / 'selected'
    root.mkdir()
    for name in ('z.py', 'a.py', 'other_z.py'):
        (root / name).write_text("from helper import result\nprint(result)\n")
    (root / 'helper.py').write_text("result='Test Result: PASS'\n")
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'linux')
    def offline(*args, **kwargs):
        pytest.fail('Run must not contact the display catalog')
    monkeypatch.setattr(direct, 'push_tc_projection', offline)
    prepared = direct.prepare_run(project='P', build='B', tc_root=root, patterns=['z.py', 'a.py'],
                                  command_snapshot=example('tc_only')['command_snapshot'])
    assert [t['path'] for t in prepared['body']['tests']] == ['z.py', 'a.py']
    result = direct.send_prepared_run(prepared)
    host.connector._execute_run(result['run_id'])
    summary = direct.get_run(result['run_id'])
    assert summary['outcome'] == 'PASSED'
    status = direct.test_status()
    assert not status['has_projection']
    assert [(s['path'], s['state']) for s in status['steps']] == [('z.py', 'PASSED'), ('a.py', 'PASSED')]


def test_unselected_python_file_does_not_need_catalog_decoding(board, tmp_path):
    host, http, _ = board
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'selected.py').write_text("print('Test Result: PASS')\n")
    (root / 'legacy.py').write_bytes(b'# coding: latin-1\n# \xff\n')
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'linux')
    prepared = direct.prepare_run(project='P', build='B', tc_root=root, patterns=['selected.py'],
                                  command_snapshot=example('tc_only')['command_snapshot'])
    received = direct.send_prepared_run(prepared)
    host.connector._execute_run(received['run_id'])
    assert direct.get_run(received['run_id'])['outcome'] == 'PASSED'


def test_empty_tc_root_and_selection_do_not_expand(tmp_path, monkeypatch):
    root = tmp_path / 'unrelated'
    root.mkdir()
    (root / 'unexpected.py').write_text('# unrelated')
    monkeypatch.chdir(root)
    direct = DirectConnectorClient(runtime_dir=tmp_path / 'runtime')
    try:
        for action in (direct.build_tc_projection, direct.preview_run):
            with pytest.raises(TestError) as missing:
                action()
            assert missing.value.code == 'SOURCE_NOT_CONFIGURED'
        for selection in ([], ['missing.py', 'unexpected.py']):
            with pytest.raises(TestError) as empty:
                direct.preview_run(tc_root=root, patterns=selection)
            assert empty.value.code == 'TC_NOT_FOUND'
    finally:
        direct.close()


@pytest.fixture
def adb_board(board, tmp_path):
    if os.name == 'nt':
        pytest.skip('POSIX mock ADB runs the copied fixture with a local sh interpreter')
    host, http, _ = board
    remote = tmp_path / 'mock-device'
    remote.mkdir()
    log = tmp_path / 'adb-calls'
    adb = tmp_path / 'adb'
    adb.write_text(f"#!{sys.executable}\n" + f"log={str(log)!r}\nremote={str(remote)!r}\n" + """
import json, os, shutil, subprocess, sys
from pathlib import Path
if sys.argv[1:] == ['start-server']:
    sys.exit(0)
with open(log, 'a') as output:
    output.write(json.dumps(sys.argv[1:]) + chr(10))
args = sys.argv[3:]
if os.getenv('MOCK_ADB_ERROR') == args[0] and args[:2] != ['shell', 'echo']:
    sys.exit(1)
if args[0] == 'get-state':
    states = os.getenv('MOCK_ADB_STATES', 'device').split(',')
    count = Path(remote) / 'probe-count'
    index = int(count.read_text()) if count.exists() else 0
    count.write_text(str(index + 1))
    print(states[min(index, len(states) - 1)])
elif args == ['shell', 'echo', 'BSP_ADB_READY']:
    if not os.getenv('MOCK_ADB_NO_SHELL'):
        print('BSP_ADB_READY')
elif args[0] == 'push':
    shutil.copyfile(args[1], Path(remote) / Path(args[2]).name)
elif args[0] == 'shell' and args[1].startswith('output=$(dmesg)'):
    print('2')
    print('x')
elif args[:2] == ['shell', 'rm']:
    (Path(remote) / Path(args[-1]).name).unlink(missing_ok=True)
elif args[0] == 'shell':
    # Only the fixture shell runs, in the isolated mock device directory.
    command = args[1].replace('/data/local/tmp/', './')
    sys.exit(subprocess.run(['sh', '-c', command], cwd=remote).returncode)
""")
    adb.chmod(0o755)
    host.path_run = {'board_a': 'B1', 'board_b': 'B2', 'adb_path': str(adb), 'adb_serials': {'B1': 'board-one'}}
    return host, http, log


def test_path_request_host_plans_and_runs_python_and_shell(adb_board, tmp_path, monkeypatch):
    host, http, log = adb_board
    root = tmp_path / 'path-suite'
    suite = root / 'python3'
    suite.mkdir(parents=True)
    (root / 'linux').mkdir()
    (root / 'dual_board').mkdir()
    (root / 'dual_board' / 'pair.py').write_text("import sys\nassert sys.argv[1:] == ['--a', 'COM3', '--b', 'COM4']\nprint('Test Result: PASS')\n")
    (suite / 'a.py').write_text("import sys\nassert sys.argv[1:] == ['--com', 'COM3']\nprint('Test Result: PASS')\n")
    (root / 'linux' / 'b.sh').write_text("echo 'Test Result: PASS'\n")
    (root / 'unrelated.py').write_text("print('Test Result: FAIL')\n")
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'path-linux')
    sent = []
    send = direct._request
    def observe(method, path, **kwargs):
        if method == 'POST' and path.startswith(ROUTE):
            sent.append((path, kwargs['json_body']))
        return send(method, path, **kwargs)
    monkeypatch.setattr(direct, '_request', observe)
    output = []
    from backend.gui_test.standalone.plugin_commands import execute_direct
    execute_direct(direct, ['test', 'run', '--tc-root', str(root), '--no-follow'],
                   emit=output.append)
    assert len(sent) == 1 and sent[0][0] == ROUTE
    assert set(sent[0][1]) == {'tc_path', 'source_snapshot_id', 'source_revision', 'origin'}
    run_id = output[-1]['run_id']
    host.connector._execute_run(run_id)
    result = direct.get_run(run_id)
    assert result['outcome'] == 'PASSED'
    assert [step['path'] for step in result['steps']] == ['dual_board/pair.py', 'linux/b.sh', 'python3/a.py']
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert all(args[:2] == ['-s', 'board-one'] for args in calls)
    assert [args[2] for args in calls] == ['get-state', 'shell', 'push', 'shell', 'shell']
    assert calls[2][-1] == calls[4][-1] and calls[2][-1] in calls[3][-1]


@pytest.mark.parametrize(('states', 'shell_missing', 'reason'), [
    ('offline,device', False, None),
    ('unauthorized', False, 'ADB_UNAUTHORIZED'),
    ('offline', False, 'ADB_OFFLINE'),
    ('device', True, 'ADB_SHELL_NOT_READY'),
])
def test_adb_readiness_before_push(adb_board, tmp_path, monkeypatch, states, shell_missing, reason):
    host, http, log = adb_board
    root = tmp_path / 'readiness'
    (root / 'linux').mkdir(parents=True)
    (root / 'linux' / 'case.sh').write_text("echo 'Test Result: PASS'")
    monkeypatch.setenv('MOCK_ADB_STATES', states)
    if shell_missing:
        monkeypatch.setenv('MOCK_ADB_NO_SHELL', '1')
    monkeypatch.setattr('backend.gui_test.execution.connector_runs.ADB_READY_TIMEOUT_S', 2)
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'readiness-client')
    run = direct.start_run(tc_root=root)
    host.connector._execute_run(run['run_id'])
    summary = direct.get_run(run['run_id'])
    commands = [json.loads(line)[2:] for line in log.read_text().splitlines()]
    if reason:
        assert summary['state'] == 'PAUSED' and summary['steps'][0]['result_reason'] == reason
        assert all(command[0] != 'push' for command in commands)
    else:
        assert summary['outcome'] == 'PASSED'
        assert commands[:3] == [['get-state'], ['get-state'], ['shell', 'echo', 'BSP_ADB_READY']]


@pytest.mark.parametrize(('diagnostic', 'reason'), [
    ("adb: device 'unauthorized-1' not found", 'ADB_DEVICE_NOT_READY'),
    ("adb: device 'offline-1' not found", 'ADB_DEVICE_NOT_READY'),
    ('error: device unauthorized. Check the confirmation dialog.', 'ADB_UNAUTHORIZED'),
    ('error: device offline', 'ADB_OFFLINE'),
])
def test_get_state_errors_do_not_match_substrings_of_serial(adb_board, monkeypatch, diagnostic, reason):
    host, _, _ = adb_board
    def get_state(command, **kwargs):
        assert command[-1] == 'get-state'
        return subprocess.CompletedProcess(command, 1, stdout=b'', stderr=diagnostic.encode())
    monkeypatch.setattr(subprocess, 'run', get_state)
    monkeypatch.setattr(host.connector, '_run_flags', lambda _: (False, False))
    with pytest.raises(TestError) as exc:
        host.connector._wait_for_adb([host.path_run['adb_path'], '-s', 'board-one'], time.monotonic() + 0.4, 'r')
    assert exc.value.code == reason


@pytest.mark.parametrize('interruption', ['cancel_after_push', 'timeout_after_push', 'cancel_during_last_probe'])
def test_adb_pre_execution_boundary(adb_board, tmp_path, monkeypatch, interruption):
    from backend.gui_test.execution import connector_runs as engine
    host, http, log = adb_board
    root = tmp_path / 'boundary'
    (root / 'linux').mkdir(parents=True)
    (root / 'linux' / 'case.sh').write_text("echo 'Test Result: PASS'")
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'boundary-client')
    run_id = direct.start_run(tc_root=root)['run_id']
    if interruption == 'cancel_during_last_probe':
        def last_probe(*_):
            direct.cancel_run(run_id)
            raise TestError('Target board did not become ready', 'ADB_DEVICE_NOT_READY')
        monkeypatch.setattr(host.connector, '_wait_for_adb', last_probe)
    else:
        close_tree = engine.ProcessTree.close
        def after_push(tree):
            close_tree(tree)
            if interruption == 'timeout_after_push':
                monkeypatch.setattr(engine, 'time', SimpleNamespace(monotonic=lambda: time.monotonic() + 10000,
                                                                     sleep=time.sleep))
            else:
                direct.cancel_run(run_id)
        monkeypatch.setattr(engine.ProcessTree, 'close', after_push)
    host.connector._execute_run(run_id)
    summary = direct.get_run(run_id)
    if interruption == 'timeout_after_push':
        assert summary['steps'][0]['result_reason'] == 'ADB_PUSH_TIMEOUT'
    else:
        assert summary['outcome'] == 'CANCELLED'
    commands = log.read_text() if log.exists() else ''
    assert 'BSP_TC_EXIT_' not in commands
    assert ('"push"' in commands) == (interruption != 'cancel_during_last_probe')


@pytest.mark.parametrize(('script', 'fault', 'state', 'reason'), [
    ("echo 'Test Result: FAIL'", '', 'PAUSED', 'Verified final result line'),
    ("echo 'Test Result: PASS'; exit 3", '', 'PAUSED', 'Unexpected exit code'),
    ('echo unmarked', '', 'PAUSED', 'Expected exactly one'),
    ("echo 'Test Result: PASS'", 'push', 'PAUSED', 'ADB_PUSH_FAILED'),
    ("echo 'Test Result: PASS'", 'shell', 'UNKNOWN', 'ADB_REMOTE_EXIT_UNCONFIRMED'),
])
def test_adb_shell_result_requires_remote_evidence(adb_board, tmp_path, monkeypatch, script, fault, state, reason):
    host, http, log = adb_board
    root = tmp_path / 'cases'
    (root / 'linux').mkdir(parents=True)
    (root / 'linux' / 'case.sh').write_text(script)
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'linux-rt')
    monkeypatch.setenv('MOCK_ADB_ERROR', fault)
    run = direct.start_run(tc_root=root)
    host.connector._execute_run(run['run_id'])
    summary = direct.get_run(run['run_id'])
    assert summary['state'] == state
    assert reason in (summary['steps'][0]['result_reason'] or summary.get('recovery_reason', ''))
    if fault == 'push':
        assert not any('BSP_TC_EXIT_' in line for line in log.read_text().splitlines())


def test_path_prepare_pins_board_mapping_and_replays_without_planning(adb_board, tmp_path):
    host, http, _ = adb_board
    root = tmp_path / 'cases'
    (root / 'linux').mkdir(parents=True)
    (root / 'linux' / 'only.sh').write_text("echo 'Test Result: PASS'")
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'linux-rt')
    prepared = direct.prepare_run(project='P', build='B', tc_root=root)
    assert 'tests' not in prepared['body'] and prepared['body']['tc_path'] == '.'
    serials = host.path_run['adb_serials']
    serials['B1'] = 'changed'
    with pytest.raises(TestError) as changed:
        direct.send_prepared_run(prepared)
    assert changed.value.code == 'PREVIEW_CHANGED'
    del serials['B1']
    with pytest.raises(TestError) as missing:
        direct.send_prepared_run(prepared)
    assert missing.value.code == 'ADB_SERIAL_REQUIRED'
    assert direct.list_runs() == []
    serials['B1'] = 'board-one'
    accepted = direct.send_prepared_run(prepared)
    serials.clear()
    assert direct.send_prepared_run(prepared)['run_id'] == accepted['run_id']


def test_saved_tc_root_can_run_without_any_selection_arguments(board, tmp_path):
    host, http, _ = board
    root = tmp_path / 'cases'
    (root / 'python3').mkdir(parents=True)
    (root / 'python3' / 'tc.py').write_text("print('Test Result: PASS')")
    host.path_run = {'board_a': 'B1'}
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'linux-rt')
    config = direct.store.read()
    direct.store.save({'expected_revision': config['revision'], 'integration': config['integration'] |
                       {'tc_root': str(root), 'source_roots': [str(root)]},
                       'timeouts': {k: v for k, v in config['timeouts'].items() if k != 'revision'}})
    run = direct.start_run()
    assert [step['path'] for step in run['steps']] == ['python3/tc.py']


def test_plugin_reads_persisted_failure_tails_and_dual_board_status(adb_board, tmp_path, monkeypatch):
    import threading
    from backend.gui_test.execution import failure_evidence
    from backend.gui_test.standalone.plugin_commands import execute_direct

    host, http, _ = adb_board
    host.path_run['adb_serials']['B2'] = 'board-two'
    entered, release = threading.Event(), threading.Event()
    calls = []

    def kernel(adb, serial):
        calls.append(serial)
        if serial == 'board-one':
            entered.set()
            assert release.wait(5)
            return {'status': 'READY', 'text': 'recent kernel message'}
        return {'status': 'PERMISSION_DENIED'}

    monkeypatch.setattr(failure_evidence, 'kernel_tail', kernel)
    root = tmp_path / 'suite'
    (root / 'dual_board').mkdir(parents=True)
    (root / 'dual_board' / 'pair.py').write_text(
        "import sys\nprint('EARLY_UNRELATED')\nprint('a' * 80000)\nprint('last output')\n"
        "print('password=private-value', file=sys.stderr)\nprint('Test Result: FAIL')\n")
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'client')
    run_id = direct.start_run(tc_root=root)['run_id']
    host.connector._execute_run(run_id)
    run = direct.get_run(run_id)
    assert run['state'] == 'PAUSED' and entered.wait(1)
    attempt = run['active_analysis']['attempt_id']
    try:
        pending = direct.failure_evidence(run_id, attempt)
        assert pending['status'] == 'PENDING' and pending['attempt_id'] == attempt
        assert not any('failure_evidence' in row for row in direct.list_analyses(run_id=run_id))
        assert http.get(f'{ROUTE}/{"b"*32}/attempts/{attempt}/failure-evidence').status_code == 404
    finally:
        release.set()
    bundle = direct.failure_evidence(run_id, attempt, wait_ms=3500)
    assert bundle['status'] == 'PARTIAL'
    assert bundle['dmesg']['B2']['status'] == 'PERMISSION_DENIED'
    assert bundle['dmesg']['B1']['text'] == 'recent kernel message'
    assert sorted(calls) == ['board-one', 'board-two']
    assert bundle['tc_id'] == 'dual_board/pair.py' and bundle['exit_code'] == 0
    logs = bundle['logs']
    assert logs['stdout']['truncated'] and 'last output' in logs['stdout']['text']
    assert 'EARLY_UNRELATED' not in logs['stdout']['text'] and 'private-value' not in json.dumps(logs)
    assert sum(len(item['text'].encode()) for item in logs.values()) <= 48 * 1024
    replay = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'client-reconnected')
    out = []
    assert execute_direct(replay, ['test', 'logs', run_id, '--failure-attempt', attempt], emit=out.append) == 0
    assert out == [bundle]
    seen = []
    def analyze(item):
        seen.append(item)
        return {'verdict': 'HOLD', 'summary': 'inspect failed board'}
    direct.analyze_once(run_id=run_id, analyzer=analyze)
    assert seen[0]['failure_evidence'] == bundle and 'last output' in seen[0]['logs']['stdout']
    assert sorted(calls) == ['board-one', 'board-two']


def test_failure_evidence_recovery_and_mapping_pin(adb_board, tmp_path, monkeypatch):
    from backend.gui_test.execution import failure_evidence
    host, http, _ = adb_board
    monkeypatch.setattr(failure_evidence, 'kernel_tail', lambda *a: pytest.fail('must not read a different board'))
    root = tmp_path / 'suite'
    (root / 'python3').mkdir(parents=True)
    (root / 'python3' / 'single.py').write_text("print('Test Result: FAIL')")
    direct = DirectConnectorClient(client=http, runtime_dir=tmp_path / 'pin')
    run_id = direct.start_run(tc_root=root)['run_id']
    host.path_run['adb_serials']['B1'] = 'replaced'
    host.connector._execute_run(run_id)
    attempt = direct.get_run(run_id)['active_analysis']['attempt_id']
    evidence = direct.failure_evidence(run_id, attempt, wait_ms=3500)
    assert evidence['dmesg']['B1']['status'] == 'BOARD_MISMATCH'
    evidence['dmesg']['B1'] = {'status': 'PENDING'}
    with host.connector._connect() as c:
        c.execute("UPDATE connector_failure_evidence SET status='PENDING', data_json=? WHERE attempt_id=?",
                  (json.dumps(evidence), attempt))
    host.connector.recover()
    recovered = direct.failure_evidence(run_id, attempt)
    assert recovered['status'] == 'PARTIAL' and recovered['dmesg']['B1']['status'] == 'HOST_RESTARTED'
    direct.cancel_run(run_id)
    host.connector.delete_run(run_id)
    assert http.get(f'{ROUTE}/{run_id}/attempts/{attempt}/failure-evidence').status_code == 410
    with host.connector._connect() as c:
        assert not c.execute('SELECT 1 FROM connector_failure_evidence WHERE run_id=?', (run_id,)).fetchone()


@pytest.mark.skipif(os.name == 'nt', reason='POSIX device shell fixture')
def test_device_command_keeps_last_50_lines_and_error_status(tmp_path, monkeypatch):
    from backend.gui_test.execution import failure_evidence
    adb = tmp_path / 'adb'
    adb.write_text('#!/bin/sh\ndmesg() { cat "$FAKE_KERNEL"; return "$FAKE_RC"; }\neval "$4"\n')
    adb.chmod(0o755)
    log = tmp_path / 'kernel.log'
    monkeypatch.setenv('FAKE_KERNEL', str(log))
    monkeypatch.setenv('FAKE_RC', '0')
    log.write_text(''.join(f'kernel {i}\n' for i in range(70)) + 'token=private-key\n')
    item = failure_evidence.kernel_tail(str(adb), 'board')
    assert item['status'] == 'READY' and len(item['text'].splitlines()) == 50
    assert item['text'].startswith('kernel 21\n') and '[REDACTED]' in item['text']
    assert 'private-key' not in item['text']
    log.write_text('password=' + 'X' * 70000 + '\nlast line\n')
    item = failure_evidence.kernel_tail(str(adb), 'board')
    assert item['text'] == 'last line' and item['truncated']
    monkeypatch.setenv('FAKE_RC', '1')
    assert failure_evidence.kernel_tail(str(adb), 'board')['status'] == 'ADB_ERROR'


@pytest.mark.parametrize(('diagnostic', 'expected'), [
    ('dmesg: Operation not permitted', 'PERMISSION_DENIED'),
    ("adb: device 'offline-name' not found", 'ADB_DEVICE_NOT_FOUND'),
    ('error: device offline', 'ADB_UNAVAILABLE'),
    (None, 'TIMEOUT'),
])
def test_kernel_capture_reports_failure_without_returning_raw_errors(monkeypatch, diagnostic, expected):
    from backend.gui_test.execution import failure_evidence
    def run(command, **kwargs):
        assert command[:4] == ['adb', '-s', 'board', 'shell'] and kwargs['timeout'] == 3
        if diagnostic is None:
            raise subprocess.TimeoutExpired(command, timeout=3)
        return subprocess.CompletedProcess(command, 1, b'', (diagnostic + '\npassword=secret-value').encode())
    monkeypatch.setattr(subprocess, 'run', run)
    assert failure_evidence.kernel_tail('adb', 'board') == {'status': expected}
