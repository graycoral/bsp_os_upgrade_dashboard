import json
from pathlib import Path
import sys
import time

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.execution.host import Host, create_app
from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.core.manager import Manager
from backend.gui_test.core.store import Store
from backend.gui_test.core.worker import Worker
from backend.gui_test.core.models import TestError, uid

TOKEN = 'test-only-runner-token-never-use-in-production'
BOARD = {'host': 'test-windows', 'board_id': 'test-a', 'com': 'COM31'}
BOARD_B = {'host': 'test-windows', 'board_id': 'test-b', 'com': 'COM32'}
TEMPLATE = {'single': ['python', '{tc_path}', '{com_a}'], 'dual': ['python', '{tc_path}', '{com_a}', '{com_b}']}


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / 'shared TC'; source.mkdir()
    (source / '01_pass.py').write_text("import sys\nprint('ARGS=' + '|'.join(sys.argv[1:]), flush=True)\nprint('Test Result: PASS', flush=True)\n")
    (source / '02_fail.py').write_text("print('Test Result: FAIL', flush=True)\n")
    (source / 'dual').mkdir()
    (source / 'dual' / '03_pair.py').write_text("import sys\nassert sys.argv[1:]==['COM31','COM32']\nprint('Test Result: PASS', flush=True)\n")
    host = Host({'source_root': str(source), 'python': sys.executable, 'boards': [BOARD, BOARD_B]}, tmp_path / 'host', ports=lambda: {'COM31', 'COM32'})
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1', 50000)) as client:
        remote = WindowsRemote('http://localhost', TOKEN, client=client)
        yield host, remote, source, client, tmp_path


def request(remote, tc='01_pass.py'):
    return {'id': uid(), 'tc_id': tc, 'source_revision': remote.catalog()['revision'],
            'connection': {'a': BOARD, 'b': BOARD_B if tc.startswith('dual/') else None}, 'template': TEMPLATE}


def done(host, identity):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = host.poll(identity)
        if result['state'] != 'RUNNING': return result
        time.sleep(.02)
    pytest.fail('Fixture execution did not finish')


def test_real_python_single_dual_and_idempotency(setup):
    host, remote, source, client, root = setup
    for tc in ['01_pass.py', 'dual/03_pair.py']:
        req = request(remote, tc)
        first = host.start(req)
        assert host.start(req)['id'] == first['id']
        result = done(host, req['id'])
        assert result['terminated'] and result['exit_code'] == 0
        assert 'Test Result: PASS' in result['stdout']
        assert Path(result['argv'][1]).is_relative_to(root / 'host' / 'snapshots')
        assert result['working_directory'] == str(root / 'host' / 'snapshots' / req['id'])
        assert host.start(req)['state'] == 'DONE'
        with pytest.raises(TestError, match='different content'):
            host.start(req | {'tc_id': '02_fail.py'})


@pytest.mark.parametrize('executable', ['python3', 'python'])
def test_confirmed_single_port_flag_uses_configured_python_and_com7(tmp_path, executable):
    source = tmp_path / 'shared TC'; source.mkdir()
    (source / 'tc1.py').write_text("import argparse\np=argparse.ArgumentParser()\np.add_argument('-p', required=True)\na=p.parse_args()\nassert a.p=='COM7'\nprint('PORT='+a.p, flush=True)\nprint('Test Result: PASS', flush=True)\n")
    board = BOARD | {'com': 'COM7'}
    host = Host({'source_root': str(source), 'python': sys.executable, 'boards': [board]},
                tmp_path / 'host', ports=lambda: {'COM7'})
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1', 50000)) as client:
        remote = WindowsRemote('http://localhost', TOKEN, client=client)
        req = {'id': uid(), 'tc_id': 'tc1.py', 'source_revision': remote.catalog()['revision'],
               'connection': {'a': board},
               'template': TEMPLATE | {'single': [executable, '{tc_path}', '-p', '{com_a}']}}
        host.start(req)
        result = done(host, req['id'])
        assert result['terminated'] and result['exit_code'] == 0
        assert result['argv'] == [str(Path(sys.executable).resolve()),
                                  str(host.runtime / 'snapshots' / req['id'] / 'tc1.py'), '-p', 'COM7']
        assert 'PORT=COM7' in result['stdout'] and 'Test Result: PASS' in result['stdout']


def test_source_command_board_boundaries(setup):
    host, remote, source, client, root = setup
    req = request(remote)
    (source / 'data.txt').write_text('new dependency')
    with pytest.raises(TestError, match='changed'): host.start(req)
    req = request(remote)
    with pytest.raises(TestError, match='must begin'):
        host.start(req | {'template': {'single': ['cmd', '{tc_path}', '{com_a}'], 'dual': TEMPLATE['dual']}})
    with pytest.raises(TestError, match='unavailable'):
        host.start(req | {'connection': {'a': BOARD | {'com': 'COM99'}}})
    with pytest.raises(TestError, match='Unknown/disabled'):
        host.start(req | {'tc_id': '../outside.py'})


@pytest.mark.parametrize('cause', ['cancel', 'timeout', 'lease'])
def test_contained_process_termination_and_host_reservation(setup, cause):
    host, remote, source, client, root = setup
    (source / 'slow.py').write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'])\nprint('started',flush=True)\ntime.sleep(20)\n")
    if cause == 'timeout': host.metadata = {'slow.py': {'timeout': .3}}
    req = request(remote, 'slow.py'); host.start(req)
    with pytest.raises(TestError, match='busy'): host.start(req | {'id': uid()})
    if cause != 'timeout':
        deadline = time.monotonic()+3
        while 'started' not in host.poll(req['id'])['stdout'] and time.monotonic()<deadline: time.sleep(.02)
        assert 'started' in host.get(req['id'])['stdout']
    if cause == 'cancel': host.poll(req['id'], cancel=True)
    if cause == 'lease':
        with host.lock: host.leases[req['id']] = time.monotonic() - 11
        # Do not renew the lease while waiting for watchdog evidence.
        deadline = time.monotonic()+7
        while host.get(req['id'])['state'] == 'RUNNING' and time.monotonic()<deadline: time.sleep(.03)
    result = done(host, req['id'])
    assert result['state'] == 'DONE' and result['terminated'] is True
    assert result['forced_state'] == {'cancel':'CANCELLED', 'timeout':'TIMEOUT', 'lease':'ERROR'}[cause]


def test_runner_http_tokenless_and_browser_rejection(setup):
    host, remote, source, client, root = setup
    assert client.get('/v1/catalog').status_code == 200
    assert client.get('/v1/catalog', headers={'Authorization':'Bearer '+TOKEN,'Origin':'http://localhost'}).status_code == 403
    assert client.post('/v1/executions', headers={'Authorization':'Bearer '+TOKEN}, content=b'x'*65537).status_code == 413
    assert client.get('/v1/catalog', headers={'Authorization':'Bearer '+TOKEN}).status_code == 200
    with pytest.raises(ValueError): WindowsRemote('http://external.example', TOKEN)


def test_manager_actual_adapter_repeat_fail_and_no_job_sync(setup):
    host, remote, source, client, root = setup
    manager = Manager(Store(root/'manager.db'), mode='dashboard', adapter=remote)
    catalog = manager.catalog(); ids = [tc['id'] for tc in catalog['tests']]
    profile = manager.save_document('command', 'Windows TC', TEMPLATE)
    payload = {'tc_ids':ids, 'source_revision':catalog['revision'], 'connection':{'a':BOARD,'b':BOARD_B},
               'execution':'hardware', 'command_profile':'Windows TC', 'command_revision':profile['revision'], 'cycles':2}
    with pytest.raises(TestError): manager.preflight(payload | {'execution':'mock'})
    with pytest.raises(TestError): manager.preflight(payload | {'job_id':'operational-job'})
    run = manager.start(uid(), 'test', payload)
    worker = Worker(manager)
    try:
        deadline = time.monotonic()+15
        while time.monotonic()<deadline:
            worker.tick(); current = manager.get(run['id'])
            if current['state']=='COMPLETED': break
            time.sleep(.03)
        assert current['state']=='COMPLETED'
        assert current['overall_result']=='FAIL'
        assert current['simulation'] is False
        assert current['sync']['status']=='NOT_LINKED'
        assert len(current['attempts'])==6
        assert all(a['terminated'] for a in current['attempts'])
        assert 'ARGS=COM31' in current['attempts'][0]['stdout']
    finally: worker.close()


def test_lost_start_response_does_not_duplicate_execution(setup):
    host, remote, source, client, root = setup
    req = request(remote)
    original = remote.request
    calls = []
    def lossy(path, method='GET', data=None):
        result = original(path, method, data)
        if path == '/executions':
            calls.append(data['id'])
            raise TestError('Lost response')
        return result
    remote.request = lossy
    output = []
    result = remote.execute(
        {'id':req['tc_id']}, req['connection'], 10,
        {'process_ref':'windows:'+req['id'], 'source_revision':req['source_revision'], 'command_template':TEMPLATE},
        lambda stream,text: output.append(text), lambda:False)
    assert result['terminated'] and calls == [req['id']]
    assert 'Test Result: PASS' in ''.join(output)


def test_disconnected_runner_is_unknown_not_pass(setup):
    host, remote, source, client, root = setup
    def unavailable(*args, **kwargs): raise TestError('Disconnected')
    remote.request = unavailable
    result = remote.execute({'id':'01_pass.py'}, {'a':BOARD}, 1,
        {'process_ref':'windows:'+uid(), 'source_revision':'pinned', 'command_template':TEMPLATE}, lambda *args:None, lambda:False)
    assert result == {'exit_code':None, 'terminated':False}
    assert remote.probe('windows:'+uid()) == 'UNKNOWN'


def test_restart_blocks_uncertain_execution(setup):
    host, remote, source, client, root = setup
    import sqlite3
    identity = uid()
    with sqlite3.connect(host.db) as c:
        c.execute('INSERT INTO jobs VALUES(?,?,?)', (identity,'fingerprint',json.dumps({'id':identity,'state':'RUNNING','terminated':False})))
    host.recover()
    assert host.get(identity)['state']=='UNKNOWN'
    with pytest.raises(TestError, match='unresolved'): host.start(request(remote))


def test_snapshot_stays_fixed_and_runner_credential_is_not_inherited(setup, monkeypatch):
    host, remote, source, client, root = setup
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', TOKEN)
    (source/'01_pass.py').write_text("import os,time\nassert 'GUI_TEST_RUNNER_TOKEN' not in os.environ\ntime.sleep(.2)\nprint('Test Result: PASS',flush=True)\n")
    req = request(remote); host.start(req)
    (source/'01_pass.py').write_text("raise RuntimeError('changed after start')\n")
    result = done(host, req['id'])
    assert result['exit_code']==0 and 'Test Result: PASS' in result['stdout']
    assert TOKEN not in json.dumps(result)


def test_integrated_windows_runtime_selection_and_mock_history(setup, monkeypatch):
    from backend.gui_test.runtime import make_manager
    host, remote, source, client, root = setup
    runtime = root/'dashboard-runtime'; runtime.mkdir()
    assert make_manager(runtime,'dashboard').simulation is True
    (runtime/'gui-test.json').write_text(json.dumps({'runner':'windows-http','url':'http://127.0.0.1:8771'}))
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', TOKEN)
    manager = make_manager(runtime,'dashboard')
    assert manager.simulation is False and manager.dashboard is None
    assert manager.store.path.parent.name=='gui-test-dashboard-windows'
    with pytest.raises(ValueError): make_manager(runtime,'standalone')
    (runtime/'gui-test.json').write_text('{"runner":"typo"}')
    with pytest.raises(ValueError): make_manager(runtime,'dashboard')


@pytest.mark.parametrize('body,expected', [
    ("print('Test Result: PASS',flush=True)\nraise SystemExit(7)\n", 'ERROR'),
    ("import sys\nsys.stdout.buffer.write(b'Test Result: PA\\xffSS\\n')\n", 'ERROR'),
])
def test_exit_code_and_invalid_bytes_cannot_become_pass(setup, body, expected):
    from backend.gui_test.core.results import parse_result
    host, remote, source, client, root = setup
    (source/'01_pass.py').write_text(body)
    req = request(remote); host.start(req)
    result = done(host,req['id'])
    verdict, _, _ = parse_result(result['stdout'],result['stderr'],result['exit_code'],terminated=result['terminated'])
    assert verdict==expected
    if 'SystemExit(7)' in body: assert result['exit_code']==7


@pytest.mark.parametrize('tail', [b'Test Result: FAIL\n', b'x'*70000], ids=['late-conflicting-result', 'late-overflow'])
def test_final_pipe_tail_and_overflow_cannot_be_lost(setup, monkeypatch, tail):
    import io
    from types import SimpleNamespace
    from backend.gui_test.core.results import parse_result
    host, remote, source, client, root = setup
    released = __import__('threading').Event()
    class Pipe(io.BytesIO):
        def __init__(self, tail): super().__init__(b'Test Result: PASS\n'); self.tail=tail; self.sent=False
        def read1(self,n):
            first=super().read1(n)
            if first: return first
            if not self.sent:
                released.wait(2); self.sent=True; return self.tail
            return b''
    class FinalizingTree:
        def __init__(self,*args): self.process=SimpleNamespace(stdout=Pipe(tail),stderr=io.BytesIO(b''),poll=lambda:0)
        def stopped(self): released.set(); return True
        def stop(self): released.set(); return True
        def close(self): pass
    monkeypatch.setattr('backend.gui_test.execution.host.ProcessTree',FinalizingTree)
    req=request(remote);host.start(req);result=done(host,req['id'])
    if len(tail)>65536: assert result['forced_state']=='ERROR'
    else:
        assert 'FAIL' in result['stdout']
        assert parse_result(result['stdout'],result['stderr'],result['exit_code'],terminated=True)[0]=='ERROR'


def test_rejected_source_is_recorded_as_not_started_not_unknown(setup):
    host, remote, source, client, root = setup
    req=request(remote)
    (source/'01_pass.py').write_text("print('changed')\n")
    result=remote.execute({'id':req['tc_id']},req['connection'],10,
        {'process_ref':'windows:'+req['id'],'source_revision':req['source_revision'],'command_template':TEMPLATE},lambda *args:None,lambda:False)
    assert result['terminated'] is True and result['forced_state']=='ERROR'
    assert host.get(req['id'])['not_started'] is True
    assert remote.probe('windows:'+req['id'])=='STOPPED'
    assert host.start(req)['not_started'] is True


def test_claim_before_send_recovery_fences_delayed_start(setup):
    host, remote, source, client, root = setup
    req=request(remote)
    assert remote.probe('windows:'+req['id'])=='STOPPED'
    assert host.get(req['id'])['not_started'] is True
    with pytest.raises(TestError,match='different content'): host.start(req)
    assert host.get(req['id'])['state']=='DONE'


def test_secrets_split_across_writes_never_persist_in_logs(setup):
    host, remote, source, client, root = setup
    (source/'01_pass.py').write_text("import sys,time\nprint('password=',end='',flush=True)\ntime.sleep(.1)\nprint('sensitive-value',flush=True)\nprint('Authorization: Bearer another-sensitive-value',flush=True)\nprint('password: a secret with spaces',flush=True)\nprint('Test Result: PASS',flush=True)\n")
    req=request(remote);host.start(req)
    result=done(host,req['id'])
    assert '[REDACTED]' in result['stdout'] and 'sensitive-value' not in result['stdout']
    assert b'sensitive-value' not in host.db.read_bytes()
    assert 'another-sensitive-value' not in result['stdout'] and 'a secret with spaces' not in result['stdout']
    assert b'another-sensitive-value' not in host.db.read_bytes() and b'a secret with spaces' not in host.db.read_bytes()
    assert not list((root/'host').rglob('*.stdout')) and not list((root/'host').rglob('*.stderr'))


@pytest.mark.parametrize('failure', [None, 'missing', 'swapped', 'duplicate'])
def test_confirmed_dual_node_command_and_board_mapping(tmp_path, failure):
    source = tmp_path / 'shared TC'; (source / 'dual').mkdir(parents=True)
    (source / 'dual' / 'tc_2.py').write_text("import argparse\np=argparse.ArgumentParser()\np.add_argument('-n', required=True)\np.add_argument('-n2', required=True)\na=p.parse_args()\nassert (a.n,a.n2)==('n295_sadk','n296_sadk')\nprint('NODES='+a.n+'|'+a.n2, flush=True)\nprint('Test Result: PASS', flush=True)\n")
    a, b = BOARD | {'node': 'n295_sadk'}, BOARD_B | {'node': 'n296_sadk'}
    host = Host({'source_root': str(source), 'python': sys.executable, 'boards': [a, b]},
                tmp_path / 'host', ports=lambda: {'COM31', 'COM32'})
    template = TEMPLATE | {'dual': ['python3', '{tc_path}', '-n', '{node_a}', '-n2', '{node_b}']}
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1', 50000)) as client:
        remote = WindowsRemote('http://localhost', TOKEN, client=client)
        assert remote.boards() == [a, b]
        connection = {'a': dict(a), 'b': dict(b)}
        if failure == 'missing': connection['a'].pop('node')
        if failure == 'swapped':
            connection['a']['node'], connection['b']['node'] = connection['b']['node'], connection['a']['node']
        if failure == 'duplicate': connection['b']['node'] = connection['a']['node']
        req = {'id': uid(), 'tc_id': 'dual/tc_2.py', 'source_revision': remote.catalog()['revision'],
               'connection': connection, 'template': template}
        response = client.post('/v1/executions', headers={'Authorization': 'Bearer '+TOKEN}, json=req)
        if failure:
            if failure == 'duplicate':
                assert response.status_code == 422
            else:
                assert response.status_code == 200
                assert response.json()['not_started'] and response.json()['reason'] == 'BOARD_MISMATCH'
            assert not host.threads
        else:
            assert response.status_code == 200
            result = done(host, req['id'])
            assert result['terminated'] and result['exit_code'] == 0
            assert result['argv'][2:] == ['-n', 'n295_sadk', '-n2', 'n296_sadk']
            assert 'NODES=n295_sadk|n296_sadk' in result['stdout']
            assert host.start(req)['state'] == 'DONE'


def test_duplicate_configured_nodes_rejected(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    with pytest.raises(ValueError, match='node names must be unique'):
        Host({'source_root': str(source), 'boards': [BOARD | {'node':'same'}, BOARD_B | {'node':'SAME'}]},
             tmp_path / 'host')


def test_manager_confirmed_single_and_dual_commands_end_to_end(tmp_path):
    source = tmp_path / 'shared TC'; (source / 'dual').mkdir(parents=True)
    (source / 'tc1.py').write_text("import sys\nassert sys.argv[1:]==['-p','COM7']\nprint('Test Result: PASS',flush=True)\n")
    (source / 'dual' / 'tc_2.py').write_text("import sys\nassert sys.argv[1:]==['-n','n295_sadk','-n2','n296_sadk']\nprint('Test Result: PASS',flush=True)\n")
    a = BOARD | {'com':'COM7', 'node':'n295_sadk'}
    b = BOARD_B | {'com':'COM8', 'node':'n296_sadk'}
    host = Host({'source_root':str(source), 'python':sys.executable, 'boards':[a,b]},
                tmp_path/'host', ports=lambda:{'COM7','COM8'})
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1',50000)) as client:
        remote = WindowsRemote('http://localhost', TOKEN, client=client)
        manager = Manager(Store(tmp_path/'manager.db'), mode='dashboard', adapter=remote)
        template = {'single':['python3','{tc_path}','-p','{com_a}'],
                    'dual':['python3','{tc_path}','-n','{node_a}','-n2','{node_b}']}
        saved = manager.save_document('command','Confirmed commands',template)
        catalog = manager.catalog()
        payload = {'tc_ids':[tc['id'] for tc in catalog['tests']], 'source_revision':catalog['revision'],
                   'connection':{'a':a,'b':b}, 'execution':'hardware',
                   'command_profile':'Confirmed commands','command_revision':saved['revision']}
        with pytest.raises(TestError, match='node names'):
            manager.preflight(payload | {'connection':{'a':BOARD|{'com':'COM7'},'b':BOARD_B|{'com':'COM8'}}})
        assert manager.preflight(payload)['ok']
        run = manager.start(uid(),'test',payload); worker = Worker(manager)
        try:
            deadline = time.monotonic()+15
            while time.monotonic()<deadline:
                worker.tick(); current = manager.get(run['id'])
                if current['state']=='COMPLETED': break
                time.sleep(.03)
            assert current['state']=='COMPLETED' and current['overall_result']=='PASS'
            assert current['progress']['done']==current['progress']['total']==2
            assert current['connection_snapshot']=={'a':a,'b':b}
            assert {tuple(item['executed_command_argv'][2:]) for item in current['attempts']}=={
                ('-p','COM7'), ('-n','n295_sadk','-n2','n296_sadk')}
        finally:
            worker.close()
