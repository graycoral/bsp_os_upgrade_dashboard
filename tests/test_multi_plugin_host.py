"""RQ-87 / T-324 Host boundary and persistence on temporary mock boards."""
from concurrent.futures import ThreadPoolExecutor
import json
import hmac
import os
import socket
import tempfile
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.core.models import TestError, uid
from backend.gui_test.execution.host import Host, create_app
from backend.gui_test.execution.sharing import load_admin_token
from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.core.integration_sources import prepare_inputs
from backend.gui_test.tests.test_flashing import FakeIO, TEMPLATE, rig
from backend.gui_test.tests.test_plugin_integration_pipeline import batch_rig
from test_direct_connector_unit3 import _base_command, _build_installer_zip, _build_source_zip, _setup_host


RUNS = '/v1/connector-runs'
TASKS = '/v1/sharing/tasks'
A, B, C = (value * 32 for value in 'abc')
KEY = 'task-private-key-' + 'x' * 48
BOARD = {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}


def account_headers(document, task_id=None, key=KEY):
    headers = {'Authorization': 'Bearer ' + document['token']}
    if task_id:
        headers.update({'X-Bsp-Task-ID': task_id, 'X-Bsp-Task-Key': key})
    return headers


@pytest.fixture
def shared_host(tmp_path, monkeypatch):
    home, runtime, host, app = _setup_host(tmp_path, with_flash=True)
    sharing = host.sharing
    with sharing.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        sharing.enable(db)
        alice = sharing.issue(db, 'account', 'alice')
        bob = sharing.issue(db, 'account', 'bob')
        service = sharing.issue(db, 'service', 'company-gui-test')
        other_service = sharing.issue(db, 'service', 'another-service')
        for account, monitor, profile, port in (
            ('alice', 'mon1', 'default', 8766),
            ('bob', 'mon1', 'second-login', 8766),
            ('bob', 'mon2', 'other-installation', 8866),
        ):
            sharing.approve_monitor(db, account, monitor, profile, port)
    monkeypatch.setattr(host.connector, 'start_worker', lambda: None)
    with TestClient(app, client=('127.0.0.1', 5100)) as api:
        operator = {'Authorization': 'Bearer ' + load_admin_token(runtime)}
        yield host, api, alice, bob, service, other_service, operator


def register(api, task_id, headers, project, monitor_id='mon1'):
    return api.put(f'{TASKS}/{task_id}', headers=headers, json={'project': project, 'monitor_id': monitor_id})


def create_tasks(api, alice, bob):
    scopes = (account_headers(alice, A), account_headers(alice, B, 'different-' + KEY), account_headers(bob, C))
    for task_id, headers, project in zip((A, B, C), scopes, ('A-project', 'B-project', 'C-project')):
        response = register(api, task_id, headers, project)
        assert response.status_code == 200, response.text
        assert response.json()['task_id'] == task_id
    return scopes


def source_payload(tmp_path):
    archive, identity, revision = _build_source_zip(tmp_path, scripts={'t.py': "print('Test Result: PASS')\n"})
    return archive, identity, {
        'execution_mode': 'tc_only',
        'connection': {'a': BOARD},
        'source_snapshot_id': identity,
        'source_revision': revision,
        'command_snapshot': _base_command(),
        'tests': [{'step_index': 0, 'tc_id': 't.py', 'path': 't.py', 'kind': 'Single'}],
    }


def put_source(api, archive, identity, headers):
    return api.put('/v1/source-snapshots/' + identity, content=archive.read_bytes(),
                   headers=headers | {'Content-Type': 'application/zip'})


def create_run(api, headers, body, key='same-key'):
    return api.post(RUNS, headers=headers | {'Idempotency-Key': key}, json=body)


def epoch(headers, value=1):
    return headers | {'X-Bsp-Run-Epoch': str(value)}


def test_registration_idempotency_scope_monitor_approvals_and_denied_legacy_paths(shared_host):
    host, api, alice, bob, service, _, admin = shared_host
    a = account_headers(alice, A)
    b = account_headers(bob, A)
    assert api.get('/v1/identity').json()['sharing_mode'] == 'shared'
    assert api.get('/v1/identity').json().get('local_port') is None
    assert api.get('/v1/identity', headers=account_headers(service)).json()['batch_reservation_v1']
    with ThreadPoolExecutor(max_workers=4) as workers:
        attempts = list(workers.map(lambda h: register(api, A, h, 'project'), (a, a, b, b)))
    assert sorted(r.status_code for r in attempts) == [200, 200, 401, 401]
    winner = a if attempts[0].status_code == 200 else b
    assert register(api, A, winner, 'different').status_code == 409
    assert register(api, A, winner | {'X-Bsp-Task-Key': 'stolen-' + KEY}, 'project').status_code == 401
    assert api.get(TASKS, headers=account_headers(alice)).status_code == 401
    assert api.get(TASKS, headers=winner).json()['tasks'][0]['project'] == 'project'
    assert register(api, C, account_headers(alice, C), 'other-install', monitor_id='mon2').status_code == 403
    assert register(api, C, account_headers(bob, C), 'other-install', monitor_id='mon2').json()['monitor_port'] == 8866
    assert {row['ssh_profile'] for row in api.get(TASKS, headers=admin).json()['tasks']} <= {
        'default', 'second-login', 'other-installation',
    }
    assert api.get('/v1/inventory').status_code == 401
    for legacy in ('/v1/control/settings', '/v1/tc-catalog-projection', '/v1/serial-control', '/v1/executions', '/v1/batches'):
        assert api.post(legacy, headers=winner, json={}).status_code == 403
    assert api.get('/v1/control/settings', headers=admin).status_code == 200
    assert api.get(RUNS, headers=admin).status_code == 403
    assert api.get(RUNS, headers=account_headers(service)).status_code == 403
    assert api.get('/v1/diagnostics/connection', headers=account_headers(alice)).json()['host_busy'] is False
    with host.sharing.connect() as db:
        with pytest.raises(TestError) as rejected:
            host.sharing.approve_monitor(db, 'bob', 'mon1', 'another-login', 8888)
        assert rejected.value.code == 'SHARING_MONITOR_CONFLICT'


def test_replay_tombstones_busy_visibility_and_snapshots(shared_host, tmp_path):
    _, api, alice, bob, *_ = shared_host
    a, b, c = create_tasks(api, alice, bob)
    archive, source, body = source_payload(tmp_path)
    assert put_source(api, archive, source, a).status_code == 200
    assert api.get(f'/v1/source-snapshots/{source}', headers=b).json() == {
        'snapshot_id': source, 'state': 'MISSING', 'runner_id': alice['runner_id'],
    }
    assert create_run(api, b, body).json()['code'] == 'SNAPSHOT_NOT_READY'
    assert put_source(api, archive, source, b).status_code == 200
    assert put_source(api, archive, source, c).status_code == 200
    with ThreadPoolExecutor(max_workers=3) as workers:
        results = list(workers.map(lambda _: create_run(api, a, body), range(3)))
    assert sorted(result.status_code for result in results) == [200, 200, 201]
    run_id = results[0].json()['run_id']
    assert all(result.json()['run_id'] == run_id for result in results)
    assert results[0].json()['ownership_epoch'] == 1
    assert 'idempotency_key' not in results[0].json()
    assert create_run(api, a, body | {'unknown': True}).json()['run_id'] == run_id
    for scope in (b, c):
        response = create_run(api, scope, body)
        assert response.status_code == 409 and response.json()['code'] == 'ACTIVE_RUN_EXISTS'
        assert run_id not in response.text
        assert api.get(f'{RUNS}/{run_id}', headers=scope).status_code == 404
        assert api.get(RUNS, headers=scope).json() == {'runs': []}
        assert api.post(f'{RUNS}/{run_id}/cancel', headers=epoch(scope)).status_code == 404
        assert api.get(f'{RUNS}/{run_id}/attempts/{uid()}/logs', headers=scope).status_code == 404
        assert api.get(f'{RUNS}/{run_id}/attempts/{uid()}/failure-evidence', headers=scope).status_code == 404
        occupancy = api.get(f'{RUNS}/active', headers=scope).json()
        assert occupancy['host_busy'] and occupancy['run'] is None
        assert ('occupied_project' in occupancy) == (scope is b)
    assert api.post(f'{RUNS}/{run_id}/cancel', headers=a).json()['code'] == 'RUN_EPOCH_REQUIRED'
    assert api.post(f'{RUNS}/{run_id}/cancel', headers=epoch(a)).status_code == 200
    assert api.delete(f'{RUNS}/{run_id}', headers=epoch(a)).status_code == 200
    assert create_run(api, a, body).status_code == 410
    assert api.get(f'{RUNS}/{run_id}', headers=b).status_code == 404
    admitted = create_run(api, b, body)
    assert admitted.status_code == 201 and admitted.json()['run_id'] != run_id
    assert api.get(f'{RUNS}/{run_id}', headers=a).status_code == 410


def test_one_time_view_redeem_revoke_and_cas_handoff_invalidates_delayed_commands(shared_host, tmp_path):
    host, api, alice, bob, _, _, admin = shared_host
    a, b, c = create_tasks(api, alice, bob)
    archive, source, body = source_payload(tmp_path)
    assert put_source(api, archive, source, a).status_code == 200
    run_id = create_run(api, a, body).json()['run_id']
    attempt_id, analysis_id = uid(), uid()
    with host.sharing.connect() as db:
        db.execute("UPDATE connector_runs SET state='PAUSED',analysis_latched=1 WHERE run_id=?", (run_id,))
        db.execute(
            'INSERT INTO connector_analyses(analysis_id,run_id,attempt_id,phase,failed_step_index,evidence_revision,status,created_at,updated_at) '
            "VALUES(?,?,?,'TC',0,1,'PENDING',1,1)", (analysis_id, run_id, attempt_id),
        )
    analysis = f'/v1/analyses/{analysis_id}'
    lease = api.post(analysis + '/claim', json={'lease_owner': 'alice-analysis'}, headers=epoch(a))
    assert lease.status_code == 200, lease.text
    assert lease.json()['ownership_epoch'] == 1
    assert api.get('/v1/analyses', headers=b).json()['analyses'] == []
    mint = f'{TASKS}/{A}/view-tickets'
    redeem = '/v1/sharing/view-tickets/redeem'
    issued = api.post(mint, headers=a).json()
    assert issued['monitor_port'] == 8766 and issued['task_id'] == A
    assert api.post(mint, headers=b).status_code == 404
    for rejected in ({'monitor_id': 'mon2', 'task_id': A}, {'monitor_id': 'mon1', 'task_id': B}):
        assert api.post(redeem, json={'ticket': issued['ticket'], 'monitor_proof': '0' * 64} | rejected).status_code == 401
    token = host.sharing._monitor_store('mon1').load().encode()
    nonce = '1' * 64
    proof = hmac.digest(token, b'bsp-monitor-v1:mon1:' + nonce.encode(), 'sha256').hex()
    proof_route = f'{TASKS}/{A}/monitor-proof'
    assert api.post(proof_route, headers=admin, json={'challenge': nonce, 'proof': proof}).json() == {'verified': True}
    assert api.post(proof_route, headers=a, json={'challenge': nonce, 'proof': proof}).status_code == 200
    assert api.post(proof_route, headers=b, json={'challenge': nonce, 'proof': proof}).status_code == 404
    assert api.post(proof_route, headers=a, json={'challenge': '0' * 64, 'proof': proof}).status_code == 403
    signature = hmac.digest(token, ('bsp-monitor-redeem-v1:mon1:' + issued['ticket']).encode(), 'sha256').hex()
    payload = {'ticket': issued['ticket'], 'monitor_id': 'mon1', 'task_id': A, 'monitor_proof': signature}
    assert api.post(redeem, json=payload | {'monitor_proof': '0' * 64}).status_code == 403
    view = api.post(redeem, json=payload)
    assert view.status_code == 200 and view.headers['cache-control'] == 'no-store'
    read = {'Authorization': 'Bearer ' + view.json()['view_token']}
    assert api.post(redeem, json=payload).status_code == 401
    assert api.get(f'{TASKS}/{A}/view', headers=read).json()['run']['run_id'] == run_id
    assert api.get(f'{TASKS}/{B}/view', headers=read).status_code == 401
    assert api.get('/v1/control/settings', headers=read).status_code == 401

    handoff = f'/v1/sharing/runs/{run_id}/handoff'
    assert api.post(handoff, headers=admin, json={'expected_epoch': 1, 'task_id': B}).json()['ownership_epoch'] == 2
    assert api.post(handoff, headers=admin, json={'expected_epoch': 1, 'task_id': A}).status_code == 409
    assert api.get(f'{TASKS}/{A}/view', headers=read).status_code == 401
    assert api.get(f'{RUNS}/{run_id}', headers=a).status_code == 404
    assert api.get(f'{RUNS}/{run_id}', headers=b).json()['ownership_epoch'] == 2
    assert api.get(f'/v1/source-snapshots/{source}', headers=b).json()['state'] == 'READY'
    assert api.get(f'/v1/source-snapshots/{source}', headers=c).json()['state'] == 'MISSING'
    assert api.get('/v1/analyses', headers=b).json()['analyses'][0]['status'] == 'PENDING'
    assert api.post(analysis + '/heartbeat', headers=epoch(b, 2), json={'lease_token': lease.json()['lease_token']}).status_code == 409

    assert api.post(handoff, headers=admin, json={'expected_epoch': 2, 'task_id': A}).json()['ownership_epoch'] == 3
    assert api.post(f'{RUNS}/{run_id}/cancel', headers=epoch(a)).json()['code'] == 'RUN_OWNERSHIP_CHANGED'
    assert create_run(api, a, body).json()['code'] == 'RUN_OWNERSHIP_CHANGED'
    revoke = '/v1/sharing/principals/revoke'
    assert api.post(revoke, headers=admin, json={'role': 'account', 'name': 'alice'}).status_code == 200
    assert api.get(f'{RUNS}/{run_id}', headers=a).status_code == 401
    assert api.get(f'{RUNS}/active', headers=c).json()['host_busy'] is True
    operator_tasks = api.get(TASKS, headers=admin).json()
    assert operator_tasks['active_task_id'] == A
    assert [row['task_id'] for row in operator_tasks['tasks']] == [C]
    with host.sharing.connect() as db:
        assert [tuple(row) for row in db.execute('SELECT old_task_id,new_task_id FROM sharing_handoffs ORDER BY epoch')] == [(A, B), (B, A)]


def test_installer_offsets_and_legacy_service_batch_are_scoped(shared_host, tmp_path):
    _, api, alice, bob, service, other_service, _ = shared_host
    a, b, _ = create_tasks(api, alice, bob)
    _, installer, sha, raw = _build_installer_zip(tmp_path)
    path = f'/v1/installer-snapshots/{installer}'
    attrs = {'Content-Type': 'application/zip', 'X-Archive-SHA256': sha}
    cut = len(raw) // 2
    assert api.put(path, content=raw[:cut], headers=a | attrs | {
        'Content-Range': f'bytes 0-{cut - 1}/{len(raw)}', 'Content-Length': str(cut),
    }).json()['offset'] == cut
    assert api.get(path, headers=b).json()['offset'] == 0
    tail = {'Content-Range': f'bytes {cut}-{len(raw) - 1}/{len(raw)}', 'Content-Length': str(len(raw) - cut)}
    assert api.put(path, content=raw[cut:], headers=b | attrs | tail).status_code == 409
    assert api.put(path, content=raw[cut:], headers=a | attrs | tail).json()['state'] == 'READY'
    assert api.get(path + '?manifest=true', headers=b).json()['state'] == 'PARTIAL'
    assert api.get(path + '?manifest=true', headers=a).json()['manifest']['batch'] == 'flash_all.bat'

    credential, another = account_headers(service), account_headers(other_service)
    batch_id = uid()
    batch_payload = {'id': batch_id, 'runner_id': alice['runner_id'], 'request_id': 'service-test', 'connection': {'a': BOARD}}
    batch = api.post('/v1/batches', json=batch_payload, headers=credential)
    assert batch.status_code == 200, batch.text
    assert api.post('/v1/batches', json=batch_payload, headers=another).status_code == 404
    assert api.get(f'/v1/batches/{batch_id}', headers=another).status_code == 404
    archive, source, body = source_payload(tmp_path)
    assert put_source(api, archive, source, a).status_code == 200
    assert create_run(api, a, body).json()['code'] == 'RESERVATION_CONFLICT'
    receipt = {key: batch.json()[key] for key in ('token', 'epoch')}
    assert api.post(f'/v1/batches/{batch_id}/release', json=receipt, headers=credential).status_code == 200
    assert create_run(api, a, body).status_code == 201
    blocked = api.post('/v1/batches', json=batch_payload | {'id': uid()}, headers=credential)
    assert blocked.json()['code'] == 'CONNECTOR_BUSY'


def test_local_provisioning_restart_and_corruption_fail_closed(tmp_path, monkeypatch):
    home, runtime, host, app = _setup_host(tmp_path)
    monkeypatch.setattr(host.connector, 'start_worker', lambda: None)
    root = Path(__file__).resolve().parents[1]
    cli = [sys.executable, str(root / 'scripts/manage_connector_sharing.py'), '--runtime', str(runtime)]
    credential = tmp_path / 'credential.json'
    with TestClient(app, client=('127.0.0.1', 5100)) as api:
        assert api.get('/v1/inventory').status_code == 200
        assert subprocess.run([*cli, 'enable'], capture_output=True).returncode == 1
    with sqlite3.connect(host.db) as db:
        busy = uid()
        db.execute('INSERT INTO jobs VALUES(?,?,?)', (busy, 'f', json.dumps({'id': busy, 'state': 'UNKNOWN'})))
    assert subprocess.run([*cli, 'enable'], capture_output=True).returncode == 1
    with sqlite3.connect(host.db) as db:
        db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps({'id': busy, 'state': 'DONE'}), busy))
    assert subprocess.run([*cli, 'enable'], capture_output=True).returncode == 0
    result = subprocess.run([*cli, 'issue-account', 'alice', '--output', str(credential)], capture_output=True)
    assert result.returncode == 0, result.stderr
    document = json.loads(credential.read_text())
    assert document['runner_id'] == host.identity and document['token'].encode() not in result.stdout + result.stderr
    if os.name != 'nt':
        assert credential.stat().st_mode & 0o077 == 0
    assert subprocess.run([*cli, 'issue-account', 'new', '--output', str(credential)], capture_output=True).returncode == 1
    cfg_path = home / 'windows-runner.json'
    reopened = Host(json.loads(cfg_path.read_text()), runtime, ports=lambda: {'COM3', 'COM4'}, config_path=cfg_path)
    monkeypatch.setattr(reopened.connector, 'start_worker', lambda: None)
    with TestClient(create_app(reopened), client=('127.0.0.1', 5100)) as api:
        assert api.get('/v1/identity').json()['sharing_mode'] == 'shared'
        assert api.get('/v1/diagnostics/connection', headers=account_headers(document)).status_code == 200
        reopened.sharing.admin.path.unlink()
        assert api.get('/v1/identity').json()['sharing_mode'] == 'blocked'
        assert api.get('/v1/inventory').status_code == 503
        assert api.get('/v1/diagnostics/connection', headers=account_headers(document)).status_code == 503


def test_service_adapter_streams_prepares_polls_and_releases_under_shared_mode(tmp_path, rig, batch_rig):
    host, io, unused_batch, _ = batch_rig
    _, _, request, images, source, _ = rig
    host.batches.release(unused_batch['id'], {'token': unused_batch['token'], 'epoch': unused_batch['epoch']})
    with host.sharing.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        host.sharing.enable(db)
        service = host.sharing.issue(db, 'service', 'company-gui-test')
    path = tmp_path / 'service.json'
    path.touch(mode=0o600)
    path.write_text(json.dumps(service))
    receipt = prepare_inputs({'installer_path': str(images / 'flash.bat')},
                             {'installer_roots': [str(images.parent)], 'tc_root': str(source)}, tmp_path / 'prepared')
    run_id = uid()

    def flash(*args):
        value = FakeIO.flash(io, *args)
        observer = host.flashing.observers[run_id][0]
        observer.feed(b'BOOT START\n')
        observer.feed(b'BOOT_READY')
        return value

    io.flash = flash

    def execute(item, directory, timeout):
        item.update(state='DONE', terminated=True, exit_code=0, stdout='Test Result: PASS\n', stderr='')
        host.save(item)

    host.execute = execute
    saved = []
    with TestClient(create_app(host), client=('127.0.0.1', 5100)) as api:
        remote = WindowsRemote('http://127.0.0.1', client=api, service_credential_file=path,
                               service_trust_protected_loopback=True)
        context = {'run_id': run_id, 'connection': request()['connection'], 'command_template': TEMPLATE,
                   'config': {'runner_id': host.identity, 'flash_profile': 'fixture',
                              'flash_profile_revision': remote.integration_profile('fixture')['revision']},
                   'save_batch': saved.append}
        initial = remote.begin_integration(receipt, context)
        assert initial['state'] == 'RUNNING'
        assert saved[0]['batch_id'] == run_id
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            ready = remote.reconcile_integration(run_id, initial)
            if ready['state'] == 'READY':
                break
            time.sleep(.01)
        assert ready['state'] == 'READY', ready
        tc = next(test for test in receipt['catalog']['tests'] if test['id'] == 'single.py')
        result = remote.execute(tc, context['connection'], 2,
                                {'process_ref': 'windows:' + uid(), 'source_revision': receipt['source_snapshot']['source_revision'],
                                 'command_template': TEMPLATE, 'source_snapshot': receipt['source_snapshot'],
                                 'source_directory': receipt['source_directory'], 'integration_batch': ready},
                                lambda *args: None, lambda: False)
        assert result['terminated'] and result['exit_code'] == 0
        assert remote.finish_integration(ready)['state'] == 'RELEASED'
        assert sum(event[0] == 'flash' for event in io.events) == 1
        assert api.get('/v1/control/settings', headers=account_headers(service)).status_code == 403
        if os.name != 'nt':
            path.chmod(0o644)
            with pytest.raises(TestError) as unsafe:
                remote.integration_identity()
            assert unsafe.value.code == 'RUNNER_AUTH_REQUIRED'


def test_editable_windows_connector_bundle_includes_operator_cli():
    from scripts.build_connector_bundle import _editable_source, _source_files

    source = Path(__file__).resolve().parents[1]
    cli = 'scripts/manage_connector_sharing.py'
    assert _source_files(source)[cli] == source / cli
    assert _editable_source('src/' + cli)


@pytest.mark.skipif(os.name == 'nt', reason='Linux SSH streamlocal protection')
def test_protected_streamlocal_socket_requires_trusted_filesystem(tmp_path):
    from backend.gui_test.core.shared_transport import shared_uds_transport, validate_shared_socket

    with tempfile.TemporaryDirectory(prefix='bsp-host-', dir=Path.home()) as directory:
        path = Path(directory) / 'ssh.sock'
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(os.fspath(path))
            path.chmod(0o660)
            assert validate_shared_socket(path, os.getuid()) == path
            shared_uds_transport(path, os.getuid()).close()
            with pytest.raises(ValueError):
                validate_shared_socket(path, os.getuid() + 1)
            path.chmod(0o667)
            with pytest.raises(ValueError):
                shared_uds_transport(path, os.getuid())
            path.chmod(0o660)
            Path(directory).chmod(0o770)
            with pytest.raises(ValueError):
                shared_uds_transport(path, os.getuid())
            Path(directory).chmod(0o700)
            link = Path(directory) / 'link.sock'
            link.symlink_to(path)
            with pytest.raises(ValueError):
                shared_uds_transport(link, os.getuid())

    with pytest.raises(ValueError):
        WindowsRemote('http://127.0.0.1', service_credential_file=tmp_path / 'protected.json')
