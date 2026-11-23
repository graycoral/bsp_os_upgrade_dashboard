"""Automatic PuTTY ownership with real loopback UART proxy and mocked windows."""
import logging
import socket
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.connector.supervisor import Manager
from backend.gui_test.core.models import TestError
from backend.gui_test.execution.host import Host, create_app
from backend.gui_test.tests.test_serial_multiplexer import BOARD, FakePort, wait_for


@pytest.fixture
def session(tmp_path, monkeypatch):
    host = Host({'boards':[BOARD], 'serial_transport':'proxy'}, tmp_path/'runtime', ports=lambda:{'COM7'})
    port = FakePort()
    mux = host.multiplexers.ports['board-a']
    mux.factory = lambda *_:port
    host.recover()
    client = TestClient(create_app(host), client=('127.0.0.1',123))
    executable = tmp_path/'putty.exe'; executable.touch()
    manager = Manager.__new__(Manager)
    manager.control_lock = threading.RLock(); manager.putty_cleanup = {}; manager.shutdown = threading.Event(); manager.cached = {}
    manager.log = logging.getLogger('putty-test')
    manager.settings = SimpleNamespace(read=lambda:{'putty_path':str(executable)})
    manager.probe = lambda:dict(host.inventory(),state='CONNECTED',fresh=True)
    requests = []
    def control(board, manual, *, exclusive=False, lease=None):
        body = {'board_id':board,'manual':manual}
        if exclusive: body['exclusive'] = True
        if lease is not None: body['lease'] = lease
        requests.append(body)
        response = client.post('/v1/serial-control',json=body)
        if response.status_code != 200: raise TestError(response.json()['message'],status=response.status_code)
        return response.json()
    manager.serial_control = control
    processes = []
    class Window:
        def __init__(self, argv, **options):
            assert mux.owner == 'manual'  # Input is granted before PuTTY connects.
            self.argv = argv; self.exit = threading.Event(); processes.append(self)
        def wait(self):
            self.exit.wait(5)
            return 0
    monkeypatch.setattr('backend.gui_test.connector.supervisor.subprocess.Popen',Window)
    yield SimpleNamespace(host=host,port=port,mux=mux,client=client,manager=manager,requests=requests,processes=processes,executable=executable)
    for process in processes: process.exit.set()
    wait_for(lambda:not processes or len(requests)>=2)
    manager.shutdown.set(); host.close()


def test_open_putty_claims_input_console_still_receives_and_window_exit_releases(session):
    s = session; observer = s.mux.subscribe()
    assert s.manager.open_putty('board-a') == {'opened':True}
    assert s.processes[0].argv[1:] == ['-raw','127.0.0.1','-P',str(s.mux.raw_port)]
    with socket.create_connection(('127.0.0.1',s.mux.raw_port)) as terminal:
        terminal.settimeout(2)
        wait_for(lambda:s.mux.manual_client is not None)
        s.port.input.put(b'board output\n')
        assert terminal.recv(99)==b'board output\n'
        assert observer.read(99,1)==b'board output\n'
        terminal.sendall(b'help\r');wait_for(lambda:s.port.written==[b'help\r'])
    wait_for(lambda:s.mux.owner is None)
    s.processes[0].exit.set()
    wait_for(lambda:len(s.requests)==2)
    assert s.mux.owner is None
    assert 'manual_lease' not in s.host.inventory()['boards'][0]['serial_proxy']
    observer.close()


def test_window_exit_without_a_proxy_connection_releases_pending_input(session):
    s=session;s.manager.open_putty('board-a')
    assert s.mux.owner=='manual'
    s.processes[0].exit.set();wait_for(lambda:s.mux.owner is None)


def test_launch_failure_rolls_back_input(session,monkeypatch):
    s=session
    def failed(*args,**kwargs):raise OSError('cannot start')
    monkeypatch.setattr('backend.gui_test.connector.supervisor.subprocess.Popen',failed)
    with pytest.raises(TestError) as error:s.manager.open_putty('board-a')
    assert error.value.code=='PUTTY_START_FAILED'
    assert s.mux.owner is None
    assert s.requests[0]['exclusive'] is True and s.requests[1]['lease']


def test_busy_host_refuses_input_before_launch_even_after_probe(session,monkeypatch):
    s=session;monkeypatch.setattr(s.host,'safe_to_stop',lambda:False)
    with pytest.raises(TestError):s.manager.open_putty('board-a')
    assert not s.processes and s.mux.owner is None


def test_missing_binary_and_stale_status_do_not_acquire_input(session,monkeypatch):
    s=session
    monkeypatch.setattr('shutil.which',lambda *_:None)
    s.executable.unlink()
    for name in ('ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA'):monkeypatch.delenv(name,raising=False)
    with pytest.raises(TestError):s.manager.open_putty('board-a')
    assert not s.requests
    monkeypatch.setattr(s.manager,'probe',lambda:dict(s.host.inventory(),state='CONNECTED',fresh=False))
    with pytest.raises(TestError) as error:s.manager.open_putty('board-a')
    assert error.value.code=='CONNECTOR_STALE' and not s.requests


def test_old_window_cleanup_cannot_release_a_new_manual_grant(session):
    s=session;s.manager.open_putty('board-a')
    s.client.post('/v1/serial-control',json={'board_id':'board-a','manual':False})
    newer=s.client.post('/v1/serial-control',json={'board_id':'board-a','manual':True,'exclusive':True}).json()
    s.processes[0].exit.set();wait_for(lambda:len(s.requests)==2)
    assert s.requests[-1]['lease']!=newer['manual_lease']
    assert s.mux.owner=='manual' and s.mux.key==newer['manual_lease']


def test_exclusive_grant_rejects_duplicate_and_invalid_release(session):
    s=session
    body={'board_id':'board-a','manual':True,'exclusive':True}
    assert s.client.post('/v1/serial-control',json=body).status_code==200
    assert s.client.post('/v1/serial-control',json=body).status_code==409
    assert s.client.post('/v1/serial-control',json={'board_id':'board-a','manual':False,'lease':'older'}).json()['owner']=='manual'
    assert s.client.post('/v1/serial-control',json={'board_id':'board-a','manual':False,'lease':123}).status_code==422


def test_manager_transport_passes_exclusive_grant_and_guarded_release(tmp_path,monkeypatch):
    import httpx
    from backend.gui_test.execution import launch
    manager=Manager.__new__(Manager);manager.home=tmp_path
    monkeypatch.setattr(launch,'read_active',lambda *_:{'runner_url':'http://127.0.0.1:8771'})
    calls=[]
    def handler(request):
        import json
        calls.append(json.loads(request.content))
        return httpx.Response(200,json={'owner':'manual','manual_lease':'sample-grant'})
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **options:original(transport=httpx.MockTransport(handler),**options))
    manager.serial_control('board-a',True,exclusive=True)
    manager.serial_control('board-a',False,lease='sample-grant')
    assert calls==[{'board_id':'board-a','manual':True,'exclusive':True},
                   {'board_id':'board-a','manual':False,'lease':'sample-grant'}]


def test_pending_window_cannot_be_opened_twice_and_other_manual_board_does_not_block(session,monkeypatch):
    s=session;original=s.manager.probe
    def status():
        value=original()
        value['boards'].append({'board_id':'board-b','state':'RESERVED','serial_proxy':{'owner':'manual'}})
        return value
    monkeypatch.setattr(s.manager,'probe',status)
    s.manager.open_putty('board-a')
    with pytest.raises(TestError):s.manager.open_putty('board-a')
    assert len(s.processes)==1
    s.processes[0].exit.set();wait_for(lambda:s.mux.owner is None)


@pytest.mark.parametrize('spawn_fails',[False,True])
@pytest.mark.parametrize('newer_grant',[False,True])
def test_cleanup_retries_after_transport_recovers_and_preserves_newer_grants(session,monkeypatch,spawn_fails,newer_grant):
    s=session;healthy=s.manager.serial_control;recovered=threading.Event()
    def flaky(board,manual,**options):
        if not manual and not recovered.is_set():raise OSError('temporary transport failure')
        return healthy(board,manual,**options)
    monkeypatch.setattr(s.manager,'serial_control',flaky)
    if spawn_fails:
        def failed(*args,**kwargs):raise OSError('cannot start')
        monkeypatch.setattr('backend.gui_test.connector.supervisor.subprocess.Popen',failed)
        with pytest.raises(TestError):s.manager.open_putty('board-a')
    else:
        s.manager.open_putty('board-a');s.processes[0].exit.set()
    wait_for(lambda:bool(s.manager.status()['putty_cleanup']))
    pending=s.manager.status()['putty_cleanup']
    assert pending[0]['state']=='RETRYING' and pending[0]['attempts']==1
    assert s.mux.key not in str(pending)
    assert s.mux.owner=='manual'
    if newer_grant:
        s.client.post('/v1/serial-control',json={'board_id':'board-a','manual':False})
        current=s.client.post('/v1/serial-control',json={'board_id':'board-a','manual':True,'exclusive':True}).json()['manual_lease']
    recovered.set();wait_for(lambda:not s.manager.status()['putty_cleanup'])
    assert s.mux.owner==('manual' if newer_grant else None)
    if newer_grant:assert s.mux.key==current
