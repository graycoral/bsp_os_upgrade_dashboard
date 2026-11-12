"""Connector contracts with injected HTTP/ports/observers; never real hardware."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from backend.gui_test.core.models import TestError
from backend.gui_test.execution.host import Host, create_app as host_app
from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.connector.registry import ConnectorRegistry, RegisteredWindows
from backend.gui_test.connector.console import ConsoleHub

TOKEN = 'x' * 48
BOARD = {'board_id': 'board-a', 'host': 'TEST-PC', 'com': 'COM7'}
RX = {'port':'COM17', 'rx_only_confirmed': True, 'control_lines_isolated': True}


@pytest.fixture
def hardware(tmp_path):
    ports = {'COM7'}
    host = Host({'python':sys.executable, 'boards':[BOARD]}, tmp_path/'host', ports=lambda:ports)
    client = TestClient(host_app(host,TOKEN), base_url='http://127.0.0.1', client=('127.0.0.1',1234))
    def factory(url): return WindowsRemote(url,TOKEN,client=client)
    return host, ports, factory


def test_bootstrap_no_source_no_boards(tmp_path):
    host=Host({},tmp_path/'runtime',ports=lambda:set())
    assert host.inventory()['boards']==[]
    with pytest.raises(TestError,match='Select the TC'): host.catalog()
    assert host.safe_to_stop()


def test_inventory_disconnected_preserves_board_and_verify_refuses(hardware):
    host,ports,_=hardware; ports.clear()
    assert host.boards()==[]
    assert host.inventory()['boards'][0]['state']=='DISCONNECTED'
    assert host.inventory()['boards'][0]['board_id']=='board-a'
    with pytest.raises(TestError) as err: host.verify({'a':BOARD})
    assert err.value.code=='BOARD_MISMATCH'


def test_dynamic_registration_shared_after_start_and_identity_pin(tmp_path,hardware):
    host,ports,factory=hardware; clock=[100]
    registry=ConnectorRegistry(tmp_path,token=TOKEN,factory=factory,clock=lambda:clock[0])
    api=RegisteredWindows(registry); worker=RegisteredWindows(ConnectorRegistry(tmp_path,token=TOKEN,factory=factory,clock=lambda:clock[0]))
    assert not api.readiness()['ready']
    first=registry.register('http://127.0.0.1:8771',host.identity)
    assert api.boards()==worker.boards()==[BOARD]
    assert api.readiness()['runner_id']==host.identity
    clock[0]+=20
    assert api.readiness()['code']=='CONNECTOR_STALE'
    second=registry.register('http://127.0.0.1:60000',host.identity)
    assert second['transport_generation']==first['transport_generation']+1
    assert second['config_revision']==first['config_revision']
    assert api.boards()==[BOARD] and worker.readiness()['ready']
    with pytest.raises(TestError): api.target('a'*32)
    with pytest.raises(TestError): api.delete_session({'runner_id_snapshot':'a'*32})
    ports.clear(); assert worker.boards()==[]


@pytest.mark.parametrize('url',['https://127.0.0.1:9','http://evil.example','http://127.0.0.1:9/path','http://user:pass@127.0.0.1:9'])
def test_registration_rejects_arbitrary_fetch(tmp_path,url):
    with pytest.raises(ValueError): ConnectorRegistry(tmp_path,token=TOKEN).register(url,'a'*32)


def test_authenticated_full_host_registration_and_console_error_replay(tmp_path,hardware,monkeypatch):
    from backend.api.main import create_app
    host,_,factory=hardware
    host.console.refresh()
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN',TOKEN)
    monkeypatch.setenv('GUI_TEST_CONNECTOR_REGISTRATION_TOKEN','r'*48)
    app=create_app(tmp_path/'linux'); registry=app.state.gui_live_manager.runner.registry; registry.factory=factory
    client=TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234))
    url='/api/v1/gui-test/live/connector/register'; body={'url':'http://127.0.0.1:8771','runner_id':host.identity}
    assert client.post(url,json=body).status_code==401
    auth={'Authorization':'Bearer '+'r'*48}
    registered=client.post(url,json=body,headers=auth)
    assert registered.status_code==200 and registered.json()['server_paths']['run'] is None
    assert client.get('/api/v1/gui-test/live/connector/inventory').json()['boards'][0]['board_id']=='board-a'
    assert client.post(url,json=body,headers=auth).status_code==200
    events=registry.errors(); assert len(events['events'])==1
    assert events['events'][0]['code']=='OBSERVER_NOT_CONFIGURED'
    assert registry.errors(events['cursor'])['events']==[]
    assert ConnectorRegistry(tmp_path/'linux',token=TOKEN,factory=factory).errors()==events
    assert client.post(url,json=body,headers=dict(auth,origin='http://127.0.0.1')).status_code==403


class FakeObserver:
    created=[]
    def __init__(self,path,config):
        self.config=config; self.closed=False; self.started=0; self.text='boot login :\n'; self.offset=15; self.gaps=[]; self.directory=path
        self.created.append(self)
    def start(self): self.started+=1
    def close(self): self.closed=True
    def evidence(self): return {'phase':'IDLE','tail':self.text,'end_offset':self.offset,'complete':True,'panic':False,'log_directory':str(self.directory),'retained_from':0}


def test_console_poll_readonly_two_subscribers_and_independent_record_cursor(hardware):
    host,_,_=hardware; FakeObserver.created=[]
    hub=ConsoleHub(host,{'board-a':RX},factory=FakeObserver)
    assert hub.projection()['boards']==[] and not FakeObserver.created
    hub.refresh(); first=hub.projection(); second=hub.projection()
    assert first==second and len(FakeObserver.created)==1
    observer=FakeObserver.created[0]
    observer.text='password=[REDACTED]\n'; observer.offset=999
    hub.refresh(); value=hub.projection(after=first['cursor'],epoch=first['epoch'])
    assert value['cursor']==2 and value['boards'][0]['source_byte_offset']==999
    assert value['records'][0]['seq']==2 and not observer.closed
    assert hub.projection(epoch='previous')['reset']
    hub.close(); assert observer.closed


def test_console_rejects_control_com_and_duplicate_owner(hardware):
    host,_,_=hardware
    with pytest.raises(TestError): ConsoleHub(host,{'board-a':dict(RX,port='COM7')})
    with pytest.raises(TestError): ConsoleHub(host,{'board-a':RX,'b':RX})


def test_unknown_and_batch_reservation_block_stop(hardware):
    host,_,_=hardware
    with sqlite3.connect(host.db) as c: c.execute('INSERT INTO jobs VALUES(?,?,?)',('a'*32,'hash',json.dumps({'id':'a'*32,'state':'UNKNOWN'})))
    assert not host.safe_to_stop() and host.inventory()['boards'][0]['state']=='UNKNOWN'


def test_batch_handoff_no_poll_lifetime_or_board_cross_attribution(hardware):
    host,_,_=hardware; FakeObserver.created=[]
    hub=ConsoleHub(host,{'board-a':RX},factory=FakeObserver); hub.refresh(); normal=FakeObserver.created[0]
    batch={'id':'b'*32,'state':'READY','connection':{'a':BOARD,'b':None}}
    observer=FakeObserver(Path('/fake-batch'),RX); observer.start(); host.flashing.observers[batch['id']]=[observer]
    with sqlite3.connect(host.db) as c: c.execute('INSERT INTO batches VALUES(?,?,?)',(batch['id'],'hash',json.dumps(batch)))
    hub.refresh(); assert normal.closed and not observer.closed
    value=hub.projection(); assert value['boards'][0]['source']=='batch-observer'
    hub.projection(); hub.projection(); assert not observer.closed and len(FakeObserver.created)==2
    hub.close(); assert not observer.closed  # batch service remains owner


def test_console_delivery_retention_reset_and_foreign_identity(tmp_path,hardware):
    host,_,factory=hardware; hub=ConsoleHub(host,{'board-a':RX},factory=FakeObserver)
    hub.refresh()
    for i in range(260):
        hub.normal['board-a'].text=f'line {i}\n'; hub.normal['board-a'].offset=i; hub.refresh()
    assert hub.projection(after=1)['delivery_gap']
    assert len(hub.projection()['records'])==4 and hub.projection()['history_truncated']
    registry=ConnectorRegistry(tmp_path,token=TOKEN,factory=factory); registry.register('http://127.0.0.1:8771',host.identity)
    with pytest.raises(TestError): registry.save_console(dict(hub.projection(),runner_id='f'*32))
    value=hub.projection(); value['boards'][0]['board_id']='foreign'
    with pytest.raises(TestError): registry.save_console(value)
    hub.close()


def test_qt_shared_view_preview_guard_and_close_detaches(tmp_path,monkeypatch):
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from backend.gui_test.connector.gui import ConnectorWindow
    from backend.gui_test.connector.preview import MockConnector
    app=QApplication.instance() or QApplication([])
    adapter=MockConnector(tmp_path); adapter.connect(); window=ConnectorWindow(adapter)
    window.timer.stop(); window.load_settings(adapter.settings()); window.render(adapter.status())
    assert window.tabs.count()==2 and not window.log_panel.isVisible()
    for scenario in ('연결','시험 중','오류','미연결','확인 필요'):
        adapter.scenario=scenario; window.render(adapter.status()); assert window.board_labels
    window.log_source.setCurrentIndex(0); assert 'Kernel panic' not in window.log_text.toPlainText()  # last UNKNOWN scenario
    adapter.scenario='오류'; window.render(adapter.status()); assert 'Kernel panic' in window.log_text.toPlainText()
    window.log_source.setCurrentIndex(3); assert 'CONSOLE_PANIC' in window.log_text.toPlainText()
    window.close(); assert adapter.connected
    # Guard enters before importing production adapters in the actual entry point.
    from backend.gui_test.connector.preview import install_guard
    import socket,subprocess
    with monkeypatch.context() as mp:
        mp.setattr(socket.socket,'connect',socket.socket.connect); mp.setattr(socket.socket,'connect_ex',socket.socket.connect_ex)
        mp.setattr(socket,'create_connection',socket.create_connection); mp.setattr(subprocess,'Popen',subprocess.Popen); mp.setattr(subprocess,'run',subprocess.run)
        install_guard()
        with pytest.raises(RuntimeError,match='PREVIEW_GUARD'): socket.create_connection(('127.0.0.1',9))
        with pytest.raises(RuntimeError,match='PREVIEW_GUARD'): subprocess.Popen(['echo','bad'])
        window2=ConnectorWindow(MockConnector(tmp_path)); window2.timer.stop(); window2.render(adapter.status()); window2.close()
    from PySide6.QtCore import QThreadPool
    QThreadPool.globalInstance().waitForDone(5000); app.processEvents()


def test_board_status_is_target_specific_and_host_exclusion_is_separate(tmp_path):
    second=dict(BOARD,board_id='board-b',com='COM8')
    host=Host({'boards':[BOARD,second]},tmp_path/'host',ports=lambda:{'COM7','COM8'})
    with sqlite3.connect(host.db) as c: c.execute('INSERT INTO jobs VALUES(?,?,?)',('a'*32,'h',json.dumps({'id':'a'*32,'state':'RUNNING','connection':{'a':BOARD}})))
    a,b=host.inventory()['boards']
    assert a['state']=='RUNNING' and b['state']=='CONNECTED' and b['blocked_reason']=='HOST_BUSY'
    assert not host.safe_to_stop()


def test_settings_atomic_preserve_legacy_unknown_and_reject_duplicate_rx(tmp_path):
    from backend.gui_test.connector.settings import Settings
    settings=Settings(tmp_path); value={'source_root':'legacy/path','boards':[BOARD], '_setup':{'server':'linux.example','account':'tester','extra':'kept'},'custom':{'keep':True}}
    settings.path.write_text(json.dumps(value))
    saved=settings.save({'boards':[BOARD], 'console_observers':{'board-a':RX}})
    assert saved['source_root']=='legacy/path' and saved['custom']=={'keep':True} and saved['_setup']['extra']=='kept'
    before=settings.path.read_bytes()
    with pytest.raises(TestError): settings.save({'console_observers':{'board-a':RX,'board-b':RX}})
    assert settings.path.read_bytes()==before and list(tmp_path.glob('*.bak'))


def test_existing_demo_and_live_worker_stores_are_each_scheduled_once(tmp_path,monkeypatch):
    from backend.gui_test.runtime import make_manager,live_manager
    from backend.gui_test.connector import workers
    demo=make_manager(tmp_path,'dashboard'); live=live_manager(tmp_path,'dashboard',demo); calls=[]
    class Worker:
        def __init__(self,manager): self.manager=manager
        def tick(self): calls.append(self.manager.store.path)
        def close(self): pass
    monkeypatch.setattr(workers,'Worker',Worker)
    group=workers.DashboardWorkers([demo,live,live],tmp_path)
    try:
        group.tick(); assert calls==[demo.store.path,live.store.path]
        assert len(group.entries)==2
    finally: group.close()


def test_plugin_bootstrap_reads_same_inventory_and_errors_before_tc_setup(tmp_path,hardware,monkeypatch):
    from backend.api.main import create_app
    from backend.gui_test.standalone.plugin_client import PluginClient
    host,_,factory=hardware; host.console.refresh()
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN',TOKEN); monkeypatch.setenv('GUI_TEST_INTEGRATION_TOKEN','p'*48)
    app=create_app(tmp_path/'linux'); registry=app.state.gui_live_manager.runner.registry; registry.factory=factory
    registry.register('http://127.0.0.1:8771',host.identity); registry.save_console(host.console.projection())
    client=TestClient(app,client=('127.0.0.1',1234))
    plugin=PluginClient('http://127.0.0.1','p'*48,{'runtime_id':'unprepared','package_version':'0.1.0','config_revision':'unprepared','runner_id':host.identity},client=client)
    assert plugin.connector_inventory()['boards']==client.get('/api/v1/gui-test/live/connector/inventory').json()['boards']
    assert plugin.board_console()['runner_id']==host.identity
    errors=plugin.connector_errors(); assert errors['events'][0]['code']=='OBSERVER_NOT_CONFIGURED'
    assert plugin.connector_errors(errors['cursor'])['events']==[]
    assert client.get('/api/v1/gui-test/live/connector/inventory',headers={'Authorization':'Bearer wrong'}).status_code==401
    assert client.get('/api/v1/config',headers={'Authorization':'Bearer '+'p'*48}).status_code==403
    assert client.post('/api/v1/gui-test/live/runs',json={},headers={'Authorization':'Bearer '+'p'*48}).status_code==403
    # Health/preparation remains strict: read-only bootstrap never implies TC execution readiness.
    with pytest.raises(TestError): plugin.health()


def test_source_less_snapshot_capability_and_missing_source_fails_before_execution(hardware):
    host,_,factory=hardware; remote=factory('http://127.0.0.1:8771')
    assert remote.request('/identity')['source_less_snapshot_v1'] is True
    assert remote.request('/identity')['source_configured_v1'] is False
    with pytest.raises(TestError): host.catalog()
    assert host.inventory()['boards'][0]['detected']


def test_qt_multi_board_tabs_draft_resize_cancel_and_preservation(tmp_path):
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QThreadPool
    from backend.gui_test.connector.gui import ConnectorWindow
    from backend.gui_test.connector.preview import MockConnector
    app=QApplication.instance() or QApplication([]); adapter=MockConnector(tmp_path); window=ConnectorWindow(adapter); window.timer.stop()
    QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
    window.load_settings(adapter.settings());QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
    assert window.board_editor.count()==2
    first_id=window.board_drafts[0]['board']['board_id']; window.board_rows[0]['name'].setText('My first board');window.board_rows[0]['node'].setText('NODE_A')
    window.board_editor.setCurrentIndex(1);window.board_count.setValue(3);assert window.board_editor.count()==3
    window.board_count.setValue(2);assert window.board_rows[0]['name'].text()=='My first board'
    assert window.board_rows[0]['node'].text()=='NODE_A' and window.board_drafts[0]['board']['board_id']==first_id
    window.board_count.setValue(1);window.load_settings(adapter.settings());assert window.board_editor.count()==2
    assert window.board_rows[0]['name'].text()=='board-a'
    window.board_rows[0]['name'].setText('Saved name');window.save_settings();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
    assert len(adapter.settings()['boards'])==2 and adapter.settings()['board_names']['board-a']=='Saved name'
    window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_subset_batch_keeps_other_board_rx_owner_and_uses_board_identity(tmp_path):
    second=dict(BOARD,board_id='board-b',com='COM8')
    host=Host({'boards':[BOARD,second]},tmp_path/'host',ports=lambda:{'COM7','COM8'})
    configs={'board-a':RX,'board-b':dict(RX,port='COM18')}; FakeObserver.created=[]
    hub=ConsoleHub(host,configs,factory=FakeObserver);hub.refresh(); normal_a=hub.normal['board-a'];normal_b=hub.normal['board-b']
    batch={'id':'b'*32,'state':'READY','connection':{'a':BOARD,'b':None}}
    batch_observer=FakeObserver(Path('/fake-batch'),dict(RX,port='COM27'));batch_observer.board_id='board-a';host.flashing.observers[batch['id']]=[batch_observer]
    with sqlite3.connect(host.db) as c:c.execute('INSERT INTO batches VALUES(?,?,?)',(batch['id'],'h',json.dumps(batch)))
    hub.refresh();hub.refresh();value=hub.projection()
    assert normal_a.closed and not normal_b.closed and hub.normal['board-b'] is normal_b
    assert value['boards'][0]['source']=='batch-observer' and value['boards'][0]['code']=='CONSOLE_READY'
    assert value['boards'][1]['code']=='CONSOLE_READY' and not value['errors']
    hub.close()


def test_32_board_console_response_size_and_incremental_pages(tmp_path):
    boards=[dict(BOARD,board_id='board-'+str(i),com='COM'+str(i+1)) for i in range(32)]
    host=Host({'boards':boards},tmp_path/'host',ports=lambda:{b['com'] for b in boards})
    configs={b['board_id']:dict(RX,port='COM'+str(i+100)) for i,b in enumerate(boards)}
    hub=ConsoleHub(host,configs,factory=FakeObserver);hub.refresh()
    for i in range(10):
        for observer in hub.normal.values():observer.text='가'*20000+str(i)+'\n';observer.offset+=10000
        hub.refresh()
    page=hub.projection(after=1,epoch=hub.epoch)
    assert len(page['records'])==4 and page['more'] and page['cursor']==5
    assert len(json.dumps(page,ensure_ascii=False).encode())<2*1024*1024
    following=hub.projection(after=page['cursor'],epoch=hub.epoch)
    assert following['records'][0]['seq']==6
    hub.close()


def test_console_redaction_is_structural_and_split_secrets_are_not_published(tmp_path,hardware):
    from backend.gui_test.execution.console_observer import ConsoleObserver
    host,_,factory=hardware
    observer=ConsoleObserver(tmp_path/'raw',dict(RX,redact_values=['sensitive-value']))
    try:
        for chunk in ['로그 password=sen','sitive-value\nUTF8 한글\n']:
            encoded=chunk.encode();observer.feed(encoded[:2]);observer.feed(encoded[2:])
        assert 'sensitive-value' not in observer.evidence()['tail']
        assert 'UTF8 한글' in observer.evidence()['tail']
        registry=ConnectorRegistry(tmp_path/'central',token=TOKEN,factory=factory);registry.register('http://127.0.0.1:8771',host.identity)
        value={'runner_id':host.identity,'epoch':'fixture','cursor':1,'boards':[{'board_id':'board-a','text':'password=secret\n'}],
               'errors':[{'board_id':'board-a','code':'CONSOLE_GAP','phase':'TC','run_ids':[],'evidence':{'tail':'Bearer secret-token'}}]}
        saved=registry.save_console(value)
        assert '[REDACTED]' in saved['boards'][0]['text']
        assert 'secret-token' not in json.dumps(registry.errors())
    finally:observer.close()


def test_manager_ipc_auth_body_limit_and_explicit_disconnect_only(tmp_path):
    from backend.gui_test.connector.supervisor import create_manager_app
    from backend.gui_test.connector.settings import Settings
    calls=[]
    manager=SimpleNamespace(home=tmp_path,thread=None,settings=Settings(tmp_path),status=lambda:{'state':'DISCONNECTED'},
                            connect=lambda:calls.append('connect') or {'state':'CONNECTING'},disconnect=lambda:calls.append('disconnect') or {'state':'DISCONNECTING'})
    client=TestClient(create_manager_app(manager,TOKEN),base_url='http://127.0.0.1',client=('127.0.0.1',1234))
    assert client.get('/status').status_code==401
    auth={'Authorization':'Bearer '+TOKEN}
    assert client.get('/status',headers=auth).status_code==200
    assert client.post('/connect',headers=auth,json={}).status_code==200
    assert client.get('/status',headers=auth).status_code==200 and calls==['connect']
    assert client.post('/settings',headers=auth,content=b'x'*65537).status_code==413
    assert client.get('/status',headers=dict(auth,origin='http://127.0.0.1')).status_code==401
    assert client.post('/disconnect',headers=auth,json={}).status_code==200 and calls==['connect','disconnect']


def test_atomic_safe_stop_fence_rejects_new_tc_and_batch(hardware):
    host,_,factory=hardware; remote=factory('http://127.0.0.1:8771')
    assert remote.request('/connection-stop','POST',{})['safe']
    assert host.stopping
    with pytest.raises(TestError) as error:
        host.start({})
    assert error.value.code=='CONNECTOR_STOPPING'
    with pytest.raises(TestError) as error:
        host.batches.reserve({'id':'c'*32,'runner_id':host.identity,'request_id':'fixture','connection':{'a':BOARD}})
    assert error.value.code=='CONNECTOR_STOPPING'


def test_durable_error_ack_repoll_no_duplicate_and_stale_history(tmp_path,hardware):
    host,_,factory=hardware;clock=[100]
    registry=ConnectorRegistry(tmp_path,token=TOKEN,factory=factory,clock=lambda:clock[0]);registry.register('http://127.0.0.1:8771',host.identity)
    host.console.refresh();first=host.console.projection();registry.save_console(first)
    events=registry.errors();assert len(events['events'])==1
    acked=host.console.projection(error_after=first['error_cursor'])
    assert acked['error_events']==[] and acked['errors']
    registry.save_console(acked);registry.save_console(acked)
    assert registry.errors()==events
    assert registry.console()['fresh'] and registry.console()['received_at']==100
    clock[0]+=16
    assert registry.console()['stale'] and not registry.console()['fresh']
    registry.register('http://127.0.0.1:8771',host.identity)  # inventory recovered, console transfer still old
    assert registry.console()['stale'] and not registry.console()['fresh']
    # Historical console remains available with an explicit stale marker.
    assert registry.console()['boards'][0]['code']=='OBSERVER_NOT_CONFIGURED'


@pytest.mark.parametrize('conflicting_port',['COM8','COM18'])
def test_flash_prepare_rejects_all_control_and_other_board_rx_conflicts(tmp_path,monkeypatch,conflicting_port):
    from backend.gui_test.execution import flashing
    from backend.gui_test.core.models import Connection
    second=dict(BOARD,board_id='board-b',com='COM8')
    host=Host({'boards':[BOARD,second],'console_observers':{'board-a':RX,'board-b':dict(RX,port='COM18')}},tmp_path/'host',ports=lambda:{'COM7','COM8'})
    service=host.flashing; connection=Connection.model_validate({'a':BOARD})
    req=SimpleNamespace(id='a'*32,token='t'*48,epoch=1,connection=connection,profile='fixture',profile_revision='f'*64,snapshot_id='b'*64,manifest=None,source_revision='revision',model_dump=lambda **kwargs:{'id':'a'*32})
    monkeypatch.setattr(flashing.PrepareBatch,'model_validate',lambda payload:req)
    monkeypatch.setattr(host.batches,'validate',lambda *args:{'state':'RESERVED','connection':connection.model_dump(),'prepare_id':None})
    monkeypatch.setattr(service,'verify_profile_revision',lambda *args:None)
    monkeypatch.setattr(flashing.installer_snapshots,'load_manifest',lambda *args:{'batch':'install.bat','files':{}})
    config={'boards':{'board-a':{'login_prompt':'login :','observer':dict(RX,port=conflicting_port,panic_signatures=['PANIC'],boot_signatures=['BOOT'],login_markers=['login :'])}}}
    monkeypatch.setattr(service,'profile',lambda *args,**kwargs:config)
    with pytest.raises(TestError) as error:service.start_prepare('c'*32,{})
    assert error.value.code=='OBSERVER_CONFIG'
    with sqlite3.connect(host.db) as c:assert c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0


def test_stop_fence_covers_legacy_flash_and_batch_preparation(hardware):
    host,_,_=hardware;host.stopping=True
    for operation in (lambda:host.flashing.start({}),lambda:host.flashing.start_prepare('a'*32,{})):
        with pytest.raises(TestError) as error:operation()
        assert error.value.code=='CONNECTOR_STOPPING'
    assert not host.threads


def test_monitor_display_stale_preserves_last_known_execution_and_readonly_storage(tmp_path):
    from backend.gui_test.connector.supervisor import stale_display,storage_usage
    cached={'state':'CONNECTED','boards':[dict(BOARD,state='RUNNING')], 'console':{'boards':[{'code':'CONSOLE_READY','text':'history'}]}, 'last_checked_at':123}
    stale=stale_display(cached,'network lost')
    assert stale['boards'][0]['state']=='UNKNOWN' and stale['boards'][0]['last_known_state']=='RUNNING'
    assert cached['boards'][0]['state']=='RUNNING' and stale['console']['stale'] and stale['last_checked_at']==123
    file=tmp_path/'private.log';file.write_bytes(b'abc')
    assert storage_usage(tmp_path,protected=True)=={'runtime_bytes':3,'partial':False,'protected':True,'automatic_cleanup':False}
    assert file.read_bytes()==b'abc'


def test_missing_external_tc_python_keeps_bootstrap_but_blocks_snapshot_execution(tmp_path):
    from backend.gui_test.core.manager import Manager
    from backend.gui_test.core.store import Store
    host=Host({'boards':[BOARD],'python':'/path-that-does-not-exist/python'},tmp_path/'host',ports=lambda:{'COM7'})
    client=TestClient(host_app(host,TOKEN),base_url='http://127.0.0.1',client=('127.0.0.1',1234))
    remote=WindowsRemote('http://127.0.0.1',TOKEN,client=client)
    assert remote.readiness()['ready'] and not remote.readiness()['execution_ready']
    assert remote.request('/inventory')['boards'][0]['detected']
    manager=Manager(Store(tmp_path/'linux'/'runs.db'),adapter=remote)
    assert manager.source_execution()['code']=='TC_PYTHON_NOT_CONFIGURED'


def test_path_projection_pins_run_and_separates_selected_source_from_history():
    from backend.gui_test.connector.paths import server_paths, path_text
    selected = {'location': '/srv/new-tc'}
    run = {'id':'run-a','state':'RUNNING','created_at':'2026-11-13','simulation':False,
           'integration':{'config':{'runner_id':'runner-a','tc_root':'/srv/frozen-tc'},
                          'request':{'installer_path':'/srv/images/install.bat'},'batch':{'batch_id':'batch-a'}},
           'attempts':[{'process_ref':'windows:attempt-a'}]}
    foreign = dict(run, id='foreign', created_at='2027', integration={'config':{'runner_id':'runner-b'}})
    queued = copy.deepcopy(run); queued.update(id='queued', state='QUEUED', created_at='2028')
    runs = [foreign, queued, run]
    manager = SimpleNamespace(sources=SimpleNamespace(state=lambda:{'active':selected}), store=SimpleNamespace(all=lambda:runs))
    before = copy.deepcopy(runs)
    projection = server_paths(manager,'runner-a')
    assert projection['run']['id']=='run-a' and projection['selected_tc_source']=='/srv/new-tc'
    status = {'state':'CONNECTED','fresh':True,'server_paths':projection,'execution_paths':[
        {'id':'foreign','batch_id':'other','working_directory':'C:/wrong'},
        {'id':'prep','batch_id':'batch-a','kind':'batch-prepare','working_directory':'C:/images'},
        {'id':'attempt-a','working_directory':'C:/tc'}]}
    text = path_text(status)
    assert '/srv/frozen-tc' in text and '/srv/new-tc' in text and 'C:/images' in text and 'C:/tc' in text
    assert 'C:/wrong' not in text and '현재 실행' in text and runs==before
    runs[:]=[run];run['state']='COMPLETED';status['server_paths']=server_paths(manager,'runner-a')
    assert '이전 실행' in path_text(status)
    assert '과거 수신 정보' in path_text(dict(status,state='ERROR',fresh=False))
    assert server_paths(manager,'runner-c')['run'] is None


def test_path_projection_redacts_urls_and_does_not_invent_windows_paths():
    from backend.gui_test.connector.paths import display_path, path_text
    assert display_path('https://user:private@example.com/tc.git?token=private#branch')=='https://example.com/tc.git'
    assert '\n' not in display_path('/srv/x\npretend status')
    status={'state':'CONNECTED','server_paths':{'selected_tc_source':'/srv/tc','run':None}}
    assert '요청 전' in path_text(status)
    status['server_paths']['run']={'id':'r','state':'QUEUED','installer':'/srv/install.bat','execution_ids':[]}
    text=path_text(status)
    assert '준비 전 또는 경로 미수신' in text and 'C:' not in text


def test_recent_paths_retain_parent_and_hide_deleted_metadata(hardware):
    host,_,factory=hardware
    rows=[{'id':'prepare','kind':'batch-prepare','batch_id':'batch','state':'DONE','working_directory':'C:/images',
           'request':{'private':'not-public'},'profile':{'password':'not-public'}}]
    rows += [{'id':f'tc-{n}','batch_id':'batch','state':'DONE','working_directory':f'C:/tc/{n}'} for n in range(10)]
    rows += [{'id':'deleted','state':'DELETED','working_directory':'C:/deleted'}]
    with sqlite3.connect(host.db) as c:
        for row in rows:c.execute('INSERT INTO jobs VALUES(?,?,?)',(row['id'],'f',json.dumps(row)))
    value=factory('http://127.0.0.1').request('/recent-executions')
    assert len(value['executions'])==8
    assert any(row.get('working_directory')=='C:/images' for row in value['execution_paths'])
    assert 'not-public' not in json.dumps(value) and 'C:/deleted' not in json.dumps(value)
    assert len(host.threads)==0


def test_qt_readonly_paths_toggle_and_stale_preview(tmp_path):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QThreadPool
    from backend.gui_test.connector.gui import ConnectorWindow
    from backend.gui_test.connector.preview import MockConnector
    app=QApplication.instance() or QApplication([]);adapter=MockConnector(tmp_path)
    window=ConnectorWindow(adapter);window.timer.stop();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
    assert window.paths_text.isReadOnly() and window.paths_text.isHidden()
    adapter.connect();adapter.scenario='시험 중';window.render(adapter.status())
    window.paths_toggle.setChecked(True)
    assert not window.paths_text.isHidden() and '/srv/images/build-123/install.bat' in window.paths_text.toPlainText()
    assert '현재 실행' in window.paths_text.toPlainText()
    adapter.scenario='확인 필요';window.render(adapter.status())
    assert '과거 수신 정보' in window.paths_text.toPlainText()
    adapter.disconnect();window.render(adapter.status());assert '미수신' in window.paths_text.toPlainText()
    window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
