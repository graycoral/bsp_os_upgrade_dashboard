"""Port option persistence and Manager ownership checks; no SSH or hardware."""
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.connector.server_port import save_server_port
from backend.gui_test.connector.supervisor import Manager, create_manager_app
from backend.gui_test.core.models import TestError
from backend.gui_test.execution.launch import LaunchLock


def test_first_launch_port_and_repeat_preserve_profile(tmp_path):
    manager = Manager(tmp_path)
    assert save_server_port(manager, 8765) == {'server_port':8765, 'changed':True}
    before = manager.settings.path.read_bytes()
    manager.thread = SimpleNamespace(is_alive=lambda:True)
    assert save_server_port(manager, 8765)['changed'] is False
    assert manager.settings.path.read_bytes() == before
    with pytest.raises(TestError): save_server_port(manager, 8767)
    assert manager.settings.path.read_bytes() == before


@pytest.mark.parametrize('value', [0,65536,-1,True,'8765',None,1.5])
def test_ipc_invalid_port_and_browser_cannot_mutate(tmp_path, value):
    manager = Manager(tmp_path)
    client = TestClient(create_manager_app(manager, 'local'), client=('127.0.0.1',123))
    assert client.post('/server-port',json={'server_port':8765}).status_code == 401
    assert client.post('/server-port',headers={'Authorization':'Bearer local','Origin':'http://127.0.0.1'},json={'server_port':8765}).status_code == 401
    assert client.post('/server-port',headers={'Authorization':'Bearer local'},json={'server_port':value}).status_code == 422
    assert not manager.settings.path.exists()


def test_ipc_updates_same_settings_seen_by_gui(tmp_path):
    manager = Manager(tmp_path)
    client = TestClient(create_manager_app(manager, 'local'), client=('127.0.0.1',123), headers={'Authorization':'Bearer local'})
    assert client.post('/server-port',json={'server_port':8765}).json()['changed']
    assert client.get('/settings').json()['_setup']['remote_dashboard_port'] == 8765
    assert client.post('/server-port',json={'server_port':8765,'extra':True}).status_code == 422


@pytest.mark.parametrize('jobs,batches', [(['RUNNING'],[]), (['UNKNOWN'],[]), ([],['RESERVED'])])
def test_unresolved_execution_blocks_port_change(tmp_path, jobs, batches):
    manager = Manager(tmp_path)
    manager.settings.path.write_text(json.dumps({'_setup':{'remote_dashboard_port':8766},'private':'keep'}))
    runtime = tmp_path/'runtime';runtime.mkdir()
    with sqlite3.connect(runtime/'executions.db') as db:
        for table,states in [('jobs',jobs),('batches',batches)]:
            db.execute(f'CREATE TABLE {table}(data TEXT)')
            db.executemany(f'INSERT INTO {table} VALUES(?)',[(json.dumps({'state':v}),) for v in states])
    before = manager.settings.path.read_bytes()
    with pytest.raises(TestError): save_server_port(manager,8765)
    assert manager.settings.path.read_bytes() == before


@pytest.mark.parametrize('lock', ['runner.lock','setup-launch.lock'])
def test_launcher_lock_prevents_port_change(tmp_path,lock):
    manager = Manager(tmp_path)
    with LaunchLock(tmp_path/'runtime'/lock):
        with pytest.raises(TestError): save_server_port(manager,8765)
    assert not manager.settings.path.exists()


def test_import_profile_override_is_atomic_and_preserves_identity(tmp_path):
    from backend.gui_test.connector.bootstrap import import_profile
    profile={'format':'gui-test-connector-bootstrap-v1','endpoint':{'server':'linux.example','account':'tester','ssh_port':22,'remote_dashboard_port':8766},'identity':{'runtime_id':'stable','package_version':'1.0'}}
    path=tmp_path/'connection.json';path.write_text(json.dumps(profile));home=tmp_path/'windows'
    result=import_profile(home,path,server_port=8765)
    assert result["endpoint"]["remote_dashboard_port"]==8765
    manager=Manager(home);saved=manager.settings.read()
    assert saved['_setup']['remote_dashboard_port']==8765
    assert saved['_setup']['connector_bootstrap']['endpoint']['remote_dashboard_port']==8765
    assert saved['_setup']['connector_bootstrap']['identity']==profile['identity']
    assert json.loads(path.read_text())==profile
    save_server_port(manager,8767)
    assert manager.settings.read()['_setup']['connector_bootstrap']['endpoint']['remote_dashboard_port']==8767
    assert list(home.glob('*.bak'))


@pytest.mark.parametrize('option', ['--server-port','--remote-dashboard-port'])
def test_gui_entry_applies_option_before_browser(tmp_path,monkeypatch,option):
    from backend.gui_test.connector import __main__ as entry, supervisor, web
    calls=[]
    class Client:
        def server_port(self,value):calls.append(('port',value))
        def request_auto_connect(self):calls.append(('auto-connect',))
        def browser_ticket(self):calls.append(('ticket',));return {'url':'fixture'}
    monkeypatch.setattr(supervisor,'ensure_manager',lambda home:Client())
    monkeypatch.setattr(web,'open_browser',lambda url:calls.append(('open',url)))
    assert entry.main(['--home',str(tmp_path),option,'8765'])==0
    assert calls==[('port',8765),('ticket',),('auto-connect',),('open','fixture')]
    calls.clear()
    assert entry.main(['--home',str(tmp_path)])==0
    assert calls==[('ticket',),('auto-connect',),('open','fixture')]


@pytest.mark.parametrize('value',['0','65536','invalid'])
def test_invalid_cli_before_manager_or_install(tmp_path,monkeypatch,value):
    from backend.gui_test.connector import __main__ as entry, supervisor
    from scripts import board_connector as launcher
    monkeypatch.setattr(supervisor,'ensure_manager',lambda *_:pytest.fail('manager called'))
    monkeypatch.setattr(launcher,'prepare',lambda *a,**k:pytest.fail('install called'))
    for main in (entry.main,launcher.main):
        with pytest.raises(SystemExit) as error:main(['--home',str(tmp_path),'--server-port',value])
        assert error.value.code==2


def test_collision_and_saved_profile_preserve_original(tmp_path):
    from scripts.setup_ports import PortsProfile, DEFAULT_PORTS
    manager=Manager(tmp_path)
    save_server_port(manager,8765)
    before=manager.settings.path.read_bytes()
    client=TestClient(create_manager_app(manager,'local'),client=('127.0.0.1',123),headers={'Authorization':'Bearer local'})
    assert client.post('/server-port',json={'server_port':8771}).status_code==422
    assert manager.settings.path.read_bytes()==before
    PortsProfile(tmp_path/'setup-ports.json').save(dict(DEFAULT_PORTS, remote_runner_port=9871))
    assert client.post('/server-port',json={'server_port':9871}).status_code==422
    assert client.post('/server-port',json={'server_port':8771}).status_code==200


def test_bootstrap_option_import_only_without_manager(tmp_path,monkeypatch):
    from backend.gui_test.connector import __main__ as entry,supervisor
    profile={'format':'gui-test-connector-bootstrap-v1','endpoint':{'server':'linux.example','account':'tester','ssh_port':22,'remote_dashboard_port':8766},'identity':{'runtime_id':'stable','package_version':'1.0'}}
    path=tmp_path/'connection.json';path.write_text(json.dumps(profile));home=tmp_path/'windows'
    monkeypatch.setattr(supervisor,'ensure_manager',lambda *_:pytest.fail('manager started'))
    assert entry.main(['--home',str(home),'--import-profile',str(path),'--import-only','--server-port','8765'])==0
    assert json.loads((home/'windows-runner.json').read_text())['_setup']['remote_dashboard_port']==8765


def test_old_manager_reports_upgrade_without_fallback(tmp_path,monkeypatch):
    from backend.gui_test.connector.supervisor import Client
    client=Client(tmp_path)
    def old(*a,**kw):raise TestError('Not Found','CONNECTOR_REQUEST',404)
    monkeypatch.setattr(client,'request',old)
    with pytest.raises(TestError) as error:client.server_port(8765)
    assert error.value.code=='CONNECTOR_UPDATE_REQUIRED'


def test_auto_connect_once_after_setup_and_manual_stop(tmp_path, monkeypatch):
    manager = Manager(tmp_path)
    manager.close()  # Drive individual monitor ticks deterministically.
    client = TestClient(create_manager_app(manager, 'local'), client=('127.0.0.1', 123))
    calls = []
    monkeypatch.setattr(manager, '_connect', lambda: calls.append('start'))
    assert client.post('/auto-connect').status_code == 401
    def launch():
        assert client.post('/auto-connect', headers={'Authorization':'Bearer local'}).status_code == 200
    launch()
    manager._auto_connect()
    assert calls == []
    profile = {'_setup': {'server': 'linux', 'account': 'test'}, 'boards': []}
    manager.settings.path.write_text(json.dumps(profile))
    manager._auto_connect()
    manager._auto_connect()
    assert calls == ['start']
    manager.host_url = 'http://127.0.0.1:8772'
    launch()
    manager._auto_connect()
    assert calls == ['start']
    launch()
    monkeypatch.setattr(manager, '_disconnect', lambda: None)
    manager.disconnect()
    manager.host_url = None
    manager._auto_connect()
    assert calls == ['start']
    launch()
    def fail():
        calls.append('failed')
        raise TestError('profile requires recovery')
    monkeypatch.setattr(manager, '_connect', fail)
    manager._auto_connect()
    manager._auto_connect()
    assert calls == ['start', 'failed']
    assert 'profile requires recovery' in manager.status()['error']


def test_old_manager_opens_manually_when_auto_connect_is_unavailable(tmp_path, monkeypatch, capsys):
    from backend.gui_test.connector.supervisor import Client
    client = Client(tmp_path)
    def unavailable(*args):
        raise TestError('Not Found', 'CONNECTOR_REQUEST', 404)
    monkeypatch.setattr(client, 'request', unavailable)
    client.request_auto_connect()
    assert '시작 버튼' in capsys.readouterr().err


def test_running_manager_starts_saved_profile_from_launch_request(tmp_path, monkeypatch):
    from threading import Event
    (tmp_path / 'windows-runner.json').write_text(json.dumps({'_setup': {'server': 'linux', 'account': 'test'}}))
    started = Event()
    manager = Manager(tmp_path)
    monkeypatch.setattr(manager, '_connect', started.set)
    try:
        client = TestClient(create_manager_app(manager, 'local'), client=('127.0.0.1', 123))
        assert client.post('/auto-connect', headers={'Authorization': 'Bearer local'}).status_code == 200
        assert started.wait(8)
        assert manager.auto_connect_requested is False
    finally:
        manager.close()
