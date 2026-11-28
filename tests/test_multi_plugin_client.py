"""Linux plugin entry, replay, and task-scoped Monitor for RQ-87/T-324."""
import concurrent.futures
import json
from pathlib import Path
import stat
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit

import httpx
import pytest

from backend.gui_test.core.models import TestError
from backend.gui_test.standalone.direct_connector_client import DirectConnectorClient
from backend.gui_test.standalone.plugin_sharing import SharingError, SharingState, private_json
from test_direct_connector_unit4 import _start_live_host


ROOT = Path(__file__).resolve().parents[1]


def secure_file(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    path.chmod(0o600)
    return path


def test_two_same_project_windows_and_other_account_via_plugin_entry(tmp_path):
    host, port, server, thread = _start_live_host(tmp_path)
    try:
        with host.lock, host.sharing.connect() as db:
            host.sharing.enable(db)
            first = host.sharing.issue(db, 'account', 'alice', trusted_tc_author=True)
            second = host.sharing.issue(db, 'account', 'bob')
            host.sharing.approve_monitor(db, 'alice', 'monitor-alice', 'ssh-a', 8766, protected_listener=True)
            host.sharing.approve_monitor(db, 'bob', 'monitor-bob', 'ssh-b', 8866, protected_listener=True)
        home = tmp_path / 'home'
        runtime = tmp_path / 'runtime'
        source = tmp_path / 'project'
        (source / 'python3').mkdir(parents=True)
        (source / 'python3' / 'smoke.py').write_text("print('private run result')\nprint('Test Result: PASS')\n", encoding='utf-8')

        def cli(*args, account='alice', task=None, fail=None):
            cmd = [sys.executable, str(ROOT / 'apps/agent-monitor/plugin.py'), '--home', str(home),
                   '--runtime', str(runtime), '--state-dir', str(tmp_path / account), '--project', 'same-project',
                   '--project-root', str(source), '--connector-port', str(port)]
            if task is not None:
                cmd += ['--task', task]
            result = subprocess.run([*cmd, *map(str, args)], capture_output=True, text=True, timeout=30)
            for credential in (first, second):
                assert credential['token'] not in result.stdout + result.stderr
            if fail is not None:
                assert result.returncode == 1, result
                assert json.loads(result.stderr)['code'] == fail
                return
            assert result.returncode == 0, result.stderr
            return json.loads(result.stdout)

        cli('sharing', 'import', '--trust-protected-loopback', '--credential-file', secure_file(tmp_path / 'issued-a.json', first))
        cli('sharing', 'import', '--trust-protected-loopback', '--credential-file', secure_file(tmp_path / 'issued-b.json', second), account='bob')
        cli('test', 'runs', fail='TASK_REQUIRED')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
            windows = [workers.submit(cli, 'task', 'create', '--monitor-id', 'monitor-alice') for _ in range(2)]
            task_a, task_b = [window.result()['task_id'] for window in windows]
        assert task_a != task_b
        assert {item['task_id'] for item in cli('task', 'list')['tasks']} == {task_a, task_b}
        assert cli('task', 'open', task=task_a)['task_id'] == task_a
        assert cli('task', 'create', '--monitor-id', 'monitor-alice', task=task_a)['task_id'] == task_a
        task_c = cli('task', 'create', '--monitor-id', 'monitor-bob', account='bob')['task_id']
        cli('task', 'open', account='bob', task=task_a, fail='TASK_NOT_FOUND')
        assert cli('status', '--json')['state'] == 'connected'
        assert cli('settings', 'show', task=task_a)['settings_db_path'] != cli('settings', 'show', task=task_b)['settings_db_path']
        result = cli('test', 'run', '--tc-root', source, task=task_a)
        assert result['state'] == 'COMPLETED' and result['outcome'] == 'PASSED'
        run_id = result['run_id']
        assert cli('test', 'status', '--json', task=task_a)['run_id'] == run_id
        logs = cli('test', 'logs', task=task_a)
        assert logs['run_id'] == run_id and 'private run result' in json.dumps(logs)
        for owner, task in [('alice', task_b), ('bob', task_c)]:
            cli('test', 'status', run_id, task=task, account=owner, fail='NOT_FOUND')
            cli('test', 'cancel', run_id, task=task, account=owner, fail='NOT_FOUND')
            assert cli('test', 'runs', account=owner, task=task)['runs'] == []
        cli('test', 'run', '--tc-root', source, task=task_c, account='bob', fail='SHARING_EXECUTION_APPROVAL_REQUIRED')
        denied_pending = tmp_path / 'bob' / 'sharing' / str(port) / task_c / 'pending-run.json'
        assert not denied_pending.exists()
        cli('test', 'recover', task=task_c, account='bob', fail='NOT_FOUND')
        assert cli('test', 'runs', account='bob', task=task_c)['runs'] == []
        prepared_file = tmp_path / 'reviewed-run.json'
        cli('test', 'prepare', '--tc-root', source, '--file', prepared_file, '--build', 'reviewed',
            task=task_c, account='bob')
        operator = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/manage_connector_sharing.py'), '--runtime', str(host.runtime),
             'approve-prepared-run', '--prepared', str(prepared_file)],
            capture_output=True, text=True, timeout=30,
        )
        assert operator.returncode == 0, operator.stderr
        assert json.loads(operator.stdout)['approved'] is True
        approved = cli('test', 'send', '--file', prepared_file, task=task_c, account='bob')
        assert cli('test', 'watch', approved['run_id'], '--json', task=task_c, account='bob')['state'] == 'passed'
        (source / 'python3' / 'failure.py').write_text("print('Test Result: FAIL')\n", encoding='utf-8')
        failed = cli('test', 'run', '--tc-root', source, '--tc-path', 'python3/failure.py', task=task_a)
        assert failed['state'] == 'PAUSED' and failed['analysis_latched'] is True
        assert cli('test', 'analyze', task=task_b)['status'] == 'NO_PENDING_ANALYSES'
        assert cli('test', 'analyze', task=task_c, account='bob')['status'] == 'NO_PENDING_ANALYSES'
        state = tmp_path / 'alice' / 'sharing' / str(port)
        for path in [state, state / 'account.json', state / task_a, state / task_a / 'task.json',
                     state / task_a / 'selected-run.json']:
            assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
        assert not (home / 'service.json').exists()
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_private_credential_and_concurrent_stable_task_registration(tmp_path):
    credential = {'schema_version': 1, 'account': 'alice', 'token': 's' * 48, 'runner_id': 'c' * 32}
    source = secure_file(tmp_path / 'issued.json', credential)
    state = SharingState(tmp_path / 'private', 8771)
    source.chmod(0o644)
    with pytest.raises(SharingError, match='private'):
        state.import_credential(source)
    source.chmod(0o600)
    alias = tmp_path / 'symlink.json'
    alias.symlink_to(source)
    with pytest.raises(SharingError):
        state.import_credential(alias)
    with pytest.raises(SharingError, match='private socket'):
        state.import_credential(source)
    state.import_credential(source, {'kind': 'protected-tcp'})
    task_id = 'd' * 32
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as workers:
        records = list(workers.map(lambda _: state.create_task(task_id, 'same project', 'local'), range(12)))
    assert len({record['task_key'] for record in records}) == 1
    assert records[0] == private_json(state.task_directory(task_id) / 'task.json')
    assert 'task_key' not in state.tasks()[0]
    with pytest.raises(SharingError, match='different project'):
        state.create_task(task_id, 'another project', 'local')


def shared_client(tmp_path, handler, *, task_id='d' * 32):
    credential = {'schema_version': 1, 'account': 'alice', 'token': 's' * 48, 'runner_id': 'c' * 32}
    state = SharingState(tmp_path / 'state', 8771)
    state.import_credential(secure_file(tmp_path / 'issued.json', credential), {'kind': 'protected-tcp'})
    task = state.create_task(task_id, 'project', 'mine')
    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    return DirectConnectorClient(runtime_dir=tmp_path, sharing_state=state, task_id=task_id, client=client), task


def shared_identity():
    return {'service': 'bsp-board-connector', 'runner_id': 'c' * 32, 'sharing_mode': 'shared',
            'capabilities': ['multi-plugin-ownership-v1']}


def test_normal_run_recovers_same_bytes_and_header_after_response_loss(tmp_path, monkeypatch):
    from backend.gui_test.core.models import digest

    posted = []
    run_id = 'e' * 32

    def handler(req):
        if req.url.path == '/v1/identity':
            assert 'authorization' not in req.headers
            return httpx.Response(200, json=shared_identity())
        assert req.url.path == '/v1/connector-runs'
        assert req.headers['authorization'] == 'Bearer ' + 's' * 48
        assert req.headers['x-bsp-task-id'] == task['task_id'] and req.headers['x-bsp-task-key'] == task['task_key']
        posted.append((req.headers['idempotency-key'], req.content))
        if len(posted) == 1:
            raise httpx.ReadError('simulated response loss')
        blocked = {2: (403, 'SHARING_FORBIDDEN'), 3: (404, 'NOT_FOUND')}
        if len(posted) in blocked:
            status, code = blocked[len(posted)]
            return httpx.Response(status, json={'code': code})
        return httpx.Response(200, json={'run_id': run_id, 'runner_id': 'c' * 32})

    client, task = shared_client(tmp_path, handler)
    record = {'schema_version': 1, 'project': 'project', 'build': 'direct', 'runner_id': 'c' * 32,
              'idempotency_key': 'saved-key', 'task_id': task['task_id'],
              'body': {'origin': {'project': 'project'}, 'execution_mode': 'tc_only'}}
    monkeypatch.setattr(client, 'prepare_run', lambda **kwargs: record | {'fingerprint': digest(record)})
    with pytest.raises(TestError, match='ReadError'):
        client.start_run()
    assert private_json(client.state_dir / 'pending-run.json')['prepared']['idempotency_key'] == 'saved-key'
    with pytest.raises(TestError, match='Recover the pending Run'):
        client.start_run(patterns=['different.py'])
    for expected in ('SHARING_FORBIDDEN', 'NOT_FOUND'):
        with pytest.raises(TestError) as denied:
            client.recover_run()
        assert denied.value.code == expected
        assert private_json(client.state_dir / 'pending-run.json')['prepared']['idempotency_key'] == 'saved-key'
    assert client.recover_run()['run_id'] == run_id
    assert posted == [posted[0]] * 4
    assert client.selected_run() == run_id and not (client.state_dir / 'pending-run.json').exists()
    client._client.close()



def test_lost_response_before_handoff_releases_only_terminal_task_pending(tmp_path):
    host, port, server, thread = _start_live_host(tmp_path)
    try:
        with host.lock, host.sharing.connect() as db:
            host.sharing.enable(db)
            credential = host.sharing.issue(db, 'account', 'alice', trusted_tc_author=True)
            host.sharing.approve_monitor(db, 'alice', 'mine', 'ssh', 8766, protected_listener=True)
        state = SharingState(tmp_path / 'state', port)
        state.import_credential(secure_file(tmp_path / 'issued.json', credential), {'kind': 'protected-tcp'})
        source = tmp_path / 'project'
        (source / 'python3').mkdir(parents=True)
        (source / 'python3' / 'smoke.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
        accepted = []

        with httpx.HTTPTransport(trust_env=False) as forwarding, httpx.Client(trust_env=False) as http:
            def lose_first_response(request):
                response = forwarding.handle_request(request)
                if request.method == 'POST' and request.url.path == '/v1/connector-runs' and not accepted:
                    assert response.status_code in {200, 201, 202}
                    response.read()
                    accepted.append(response.json()['run_id'])
                    response.close()
                    raise httpx.ReadError('simulated response loss after Host commit')
                return response

            with httpx.Client(transport=httpx.MockTransport(lose_first_response), trust_env=False) as lossy:
                original = DirectConnectorClient(runtime_dir=tmp_path, connector_port=port, sharing_state=state, client=lossy)
                recipient = DirectConnectorClient(runtime_dir=tmp_path, connector_port=port, sharing_state=state, client=http)
                original.register_task('a' * 32, project='project', monitor_id='mine')
                target = recipient.register_task('b' * 32, project='project', monitor_id='mine')
                with pytest.raises(TestError) as disconnected:
                    original.start_run(tc_root=source)
                assert disconnected.value.code == 'CONNECTOR_UNREACHABLE'
                pending = original.state_dir / 'pending-run.json'
                assert pending.is_file()

                run_id, = accepted
                endpoint = f'http://127.0.0.1:{port}/v1/sharing/runs/{run_id}/handoff'
                authorization = {'Authorization': 'Bearer ' + host.sharing.admin.load()}
                moved = http.post(endpoint, headers=authorization, json={'expected_epoch': 1, 'task_id': target['task_id']})
                assert moved.status_code == 200 and moved.json()['ownership_epoch'] == 2
                with pytest.raises(TestError) as transferred:
                    original.recover_run()
                assert transferred.value.code == 'OWNERSHIP_TRANSFERRED'
                assert run_id not in transferred.value.message and not pending.exists()
                with pytest.raises(TestError) as denied:
                    original.get_run(run_id)
                assert denied.value.code == 'NOT_FOUND'

                assert recipient.watch_run(run_id, timeout_s=10)['outcome'] == 'PASSED'
                fresh = original.start_run(tc_root=source)
                assert fresh['run_id'] != run_id
                assert original.watch_run(fresh['run_id'], timeout_s=10)['outcome'] == 'PASSED'
    finally:
        server.should_exit = True
        thread.join(timeout=10)

def test_monitor_launch_keeps_ticket_in_private_file_and_requires_bound_identity(tmp_path, monkeypatch):
    ticket = 'v' * 48
    opened = []
    host_calls = []
    local_id = {'value': 'wrong-monitor', 'proof_matches': True}

    def handler(req):
        if req.url.path == '/api/v1/health':
            assert 'authorization' not in req.headers
            assert len(req.headers['x-bsp-monitor-challenge']) == 64
            return httpx.Response(200, json={'mode': 'shared-task-monitor', 'monitor_id': local_id['value'],
                                             'monitor_proof': 'e' * 64})
        if req.url.path == '/v1/identity':
            return httpx.Response(200, json=shared_identity())
        host_calls.append(req.url.path)
        assert req.headers['x-bsp-task-id'] == task['task_id']
        if req.url.path.endswith('/monitor-proof'):
            assert json.loads(req.content)['proof'] == 'e' * 64
            return httpx.Response(200, json={'verified': local_id['proof_matches']})
        return httpx.Response(201, json={'task_id': task['task_id'], 'monitor_id': 'mine',
                                        'monitor_port': 8766, 'ticket': ticket, 'expires_at': time.time()+30})

    client, task = shared_client(tmp_path, handler)
    launches = []
    monkeypatch.setattr(subprocess, 'Popen', lambda argv, **kw: launches.append(argv) or type('Child', (), {'poll': lambda self: None})())

    def browser(uri):
        assert ticket not in uri
        path = Path(unquote(urlsplit(uri).path))
        assert path.stat().st_mode & 0o077 == 0
        assert '#ticket=' + ticket in path.read_text()
        opened.append(uri)
        return True

    with pytest.raises(TestError, match='identity differs'):
        client.open_task_monitor(8766, browser=browser)
    assert not host_calls and not opened
    local_id['value'] = 'mine'
    local_id['proof_matches'] = False
    with pytest.raises(TestError, match='did not approve'):
        client.open_task_monitor(8766, browser=browser)
    assert host_calls[-1].endswith('/monitor-proof')
    local_id['proof_matches'] = True
    with pytest.raises(TestError, match='did not approve'):
        client.open_task_monitor(8866, browser=browser)
    assert not opened
    result = client.open_task_monitor(8766, browser=browser)
    assert result['url'] == 'http://127.0.0.1:8766/plugin-task/?task=' + task['task_id']
    assert ticket not in json.dumps(result) and all(ticket not in ' '.join(argv) for argv in launches)
    assert len(opened) == 1
    client._client.close()
