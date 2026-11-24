"""Browser security, UI host contracts and portable resources. No real devices."""
import copy
import importlib.util
import json
import logging
from pathlib import Path
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.connector.settings import Settings
from backend.gui_test.connector.supervisor import Manager, create_manager_app
from backend.gui_test.connector.web import BrowserUI, asset_file, preview_app
from backend.gui_test.connector.web_actions import ManagerActions, save_profile
from backend.gui_test.connector.preview import MockConnector
from backend.gui_test.core.models import TestError

ORIGIN = 'http://127.0.0.1:18773'
TOKEN = 'fixture-manager-only-' + 'x' * 32
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def rig(tmp_path):
    settings = Settings(tmp_path)
    settings.path.write_text(json.dumps({'_setup': {'server': 'linux.example', 'account': 'tester', 'hidden': 'preserved'},
        'boards': [{'board_id':'board-a','host':'TEST-PC','com':'COM7'}], 'serial_transport':'proxy',
        'serial_settings':{'board-a':{'baudrate':115200,'rts':False,'dtr':True}}, 'private':'not-for-browser'}))
    calls = []
    value = {'state':'CONNECTED', 'fresh':True, 'last_checked_at':time.time(), 'boards':[
        {'board_id':'board-a','com':'COM7','state':'CONNECTED','serial_proxy':{'state':'READY','owner':None}}]}
    manager = SimpleNamespace(home=tmp_path, settings=settings, control_lock=threading.RLock(), thread=None,
        status=lambda:copy.deepcopy(value), connect=lambda:calls.append('connect') or {'state':'CONNECTING'},
        disconnect=lambda:calls.append('disconnect') or {'state':'DISCONNECTING'},
        serial_control=lambda board, enabled:calls.append(('manual',board,enabled)) or {'owner':'manual'},
        open_putty=lambda board:calls.append(('putty',board)) or {'opened':True})
    app = create_manager_app(manager, TOKEN, browser_origin=ORIGIN)
    client = TestClient(app, base_url=ORIGIN, client=('127.0.0.1', 1234))
    return manager, calls, value, app, client


def ticket(app, client):
    response = client.post('/browser-ticket', headers={'Authorization':'Bearer '+TOKEN}, json={})
    assert response.status_code == 200
    return response.json()['url'].split('#ticket=')[1]


def login(app, client):
    ui = app.state.browser_ui
    response = client.post(ui.prefix+'/session', headers={'Origin':ORIGIN}, json={'ticket':ticket(app,client)})
    assert response.status_code == 200
    return ui, {'Origin':ORIGIN, 'X-Connector-CSRF':response.json()['csrf']}


def test_ticket_requires_existing_ipc_and_does_not_leak_bearer(rig):
    _,calls,_,app,client=rig
    assert client.post('/browser-ticket',json={}).status_code==401
    assert client.post('/browser-ticket',headers={'Authorization':'Bearer '+TOKEN,'Origin':ORIGIN},json={}).status_code==401
    ui,headers=login(app,client)
    response=client.get(ui.prefix+'/api/settings')
    assert response.status_code==200 and TOKEN not in response.text
    assert 'private' not in response.json()['profile'] and 'hidden' not in response.json()['profile']['_setup']
    assert not calls
    assert client.get('/status').status_code==401  # browser cookie never grants IPC
    assert client.get('/status',headers={'Authorization':'Bearer '+TOKEN,'Sec-Fetch-Site':'same-origin'}).status_code==401


def test_cookie_csp_assets_and_browser_refresh_do_not_stop_work(rig):
    _,calls,_,app,client=rig
    ui,headers=login(app,client)
    for cookie in client.cookies.jar:
        assert cookie.path==ui.prefix+'/' and cookie.name==ui.cookie
    page=client.get(ui.prefix+'/')
    assert page.status_code==200 and 'no-store' in page.headers['cache-control']
    assert "frame-ancestors 'none'" in page.headers['content-security-policy']
    for name in ('host.mjs','view.mjs','style.css'):
        assert client.get(ui.prefix+'/'+name).status_code==200
    assert client.get(ui.prefix+'/api/session').status_code==200
    assert client.get(ui.prefix+'/api/status').status_code==200
    client.close()
    assert calls==[]


@pytest.mark.parametrize('mutation', [lambda value:value['profile'].update(_setup=[]),
    lambda value:value['profile'].update(serial_settings={'board-a':1}),
    lambda value:value['profile'].update(boards='invalid')])
def test_invalid_profile_types_do_not_write_or_crash(rig,mutation):
    manager,_,_,app,client=rig
    ui,headers=login(app,client)
    before=manager.settings.path.read_bytes();body=client.get(ui.prefix+'/api/settings').json();mutation(body)
    assert client.post(ui.prefix+'/api/settings',headers=headers,json=body).status_code==422
    assert manager.settings.path.read_bytes()==before


@pytest.mark.parametrize('headers', [{}, {'Origin':'http://evil.example'}, {'Origin':ORIGIN,'X-Connector-CSRF':'wrong'},
    {'Origin':ORIGIN,'Sec-Fetch-Site':'cross-site'}, {'Origin':'null'}])
def test_control_requires_origin_and_session_csrf(rig,headers):
    _,calls,_,app,client=rig
    ui,_=login(app,client)
    assert client.post(ui.prefix+'/api/action',headers=headers,json={'action':'connect','payload':{}}).status_code==403
    assert calls==[]


@pytest.mark.parametrize('headers', [{'Host':'evil.example:18773'}, {'Host':'127.0.0.1:18774'}, {'Origin':'http://evil.example'}, {'Sec-Fetch-Site':'cross-site'}])
def test_host_port_origin_and_fetch_site_are_checked_on_reads(rig,headers):
    _,_,_,app,client=rig
    ui,_=login(app,client)
    assert client.get(ui.prefix+'/api/status',headers=headers).status_code==403


def test_ticket_expiry_one_use_limits_and_session_restart(rig):
    _,_,_,app,client=rig
    ui=app.state.browser_ui
    clock=[100.0];ui.clock=lambda:clock[0]
    expired=ticket(app,client);clock[0]+=61
    assert client.post(ui.prefix+'/session',headers={'Origin':ORIGIN},json={'ticket':expired}).status_code==401
    used=ticket(app,client)
    assert client.post(ui.prefix+'/session',headers={'Origin':ORIGIN},json={'ticket':used}).status_code==200
    assert client.post(ui.prefix+'/session',headers={'Origin':ORIGIN},json={'ticket':used}).status_code==401
    for _ in range(20):ticket(app,client)
    assert len(ui.tickets)==16
    clock[0]+=8*3600+1
    assert client.get(ui.prefix+'/api/session').status_code==401


def test_ticket_concurrent_consumption_is_atomic(rig):
    _,_,_,app,client=rig
    ui=app.state.browser_ui;one=ticket(app,client)
    def redeem(_):
        with TestClient(app,base_url=ORIGIN,client=('127.0.0.1',1)) as other:
            return other.post(ui.prefix+'/session',headers={'Origin':ORIGIN},json={'ticket':one}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(redeem,range(2)))==[200,401]


def test_new_tab_ticket_preserves_the_existing_tabs_session_and_csrf(rig):
    _,calls,_,app,client=rig
    ui,first=login(app,client)
    cookie=client.cookies.get(ui.cookie)
    _,second=login(app,client)
    assert client.cookies.get(ui.cookie)==cookie and first==second
    assert len(ui.sessions)==1
    assert client.post(ui.prefix+'/api/action',headers=first,json={'action':'connect','payload':{}}).status_code==200
    assert calls==['connect']


def test_two_managers_have_distinct_cookie_paths_and_no_session_crossover(rig,tmp_path):
    _,_,_,app,client=rig
    first,_=login(app,client)
    other=preview_app(MockConnector(tmp_path/'other'),ORIGIN)
    second=other.state.browser_ui
    assert first.cookie!=second.cookie and first.prefix!=second.prefix
    with TestClient(other,base_url=ORIGIN,client=('127.0.0.1',1)) as other_client:
        other_client.cookies.update(client.cookies)
        assert other_client.get(second.prefix+'/api/session').status_code==401
        # Restart on the same origin invalidates both old tickets and sessions.
        assert other_client.get(first.prefix+'/api/session').status_code==404


def test_body_limit_and_explicit_disconnect_only(rig):
    _,calls,_,app,client=rig
    ui,headers=login(app,client)
    assert client.post(ui.prefix+'/api/action',headers={**headers,'Content-Type':'application/json'},content='x'*65537).status_code==413
    assert client.get(ui.prefix+'/api/action').status_code==405
    assert client.post(ui.prefix+'/api/action',headers=headers,json={'action':'disconnect','payload':{}}).status_code==200
    assert calls==['disconnect']


def test_local_save_preserves_unknown_setup_serial_flags_and_rejects_stale_form(rig):
    manager,_,_,app,client=rig
    ui,headers=login(app,client)
    body=client.get(ui.prefix+'/api/settings').json()
    body['profile']['_setup']['server']='new.example'
    body['profile']['serial_settings']['board-a']={'baudrate':9600}
    first=client.post(ui.prefix+'/api/settings',headers=headers,json=body)
    assert first.status_code==200
    saved=manager.settings.read()
    assert saved['private']=='not-for-browser' and saved['_setup']['hidden']=='preserved'
    assert saved['serial_settings']['board-a']=={'baudrate':9600,'rts':False,'dtr':True}
    assert client.post(ui.prefix+'/api/settings',headers=headers,json=body).status_code==409
    manager.thread=SimpleNamespace(is_alive=lambda:True)
    assert client.post(ui.prefix+'/api/settings',headers=headers,json=first.json()).status_code==409


def test_inactive_board_flags_survive_reduce_save_reload_and_restore(rig):
    manager,_,_,app,client=rig
    profile=manager.settings.read()
    board={'board_id':'board-b','host':'TEST-PC','com':'COM8'}
    profile['boards'].append(board)
    profile['serial_settings']['board-b']={'baudrate':9600,'rts':True,'dtr':True}
    manager.settings.path.write_text(json.dumps(profile))
    ui,headers=login(app,client)
    value=client.get(ui.prefix+'/api/settings').json()
    value['profile']['boards']=value['profile']['boards'][:1]
    value['profile']['serial_settings'].pop('board-b')
    value['profile']['connector_inactive_boards']=[{'board':board,'name':'B','observer':{},'baudrate':9600}]
    assert client.post(ui.prefix+'/api/settings',headers=headers,json=value).status_code==200
    reloaded=client.get(ui.prefix+'/api/settings').json()
    assert reloaded['profile']['serial_settings']['board-b']=={'baudrate':9600,'rts':True,'dtr':True}
    reloaded['profile']['boards'].append(reloaded['profile']['connector_inactive_boards'][0]['board'])
    reloaded['profile']['serial_settings']['board-b']={'baudrate':9600}
    reloaded['profile']['connector_inactive_boards']=[]
    assert client.post(ui.prefix+'/api/settings',headers=headers,json=reloaded).status_code==200
    assert manager.settings.read()['serial_settings']['board-b']=={'baudrate':9600,'rts':True,'dtr':True}


def test_local_save_and_manager_connect_share_the_same_lock(rig,monkeypatch):
    manager,_,_,_,_=rig
    entered,released,connected=threading.Event(),threading.Event(),threading.Event()
    save=manager.settings.save
    def blocked(patch):
        entered.set();assert released.wait(3);return save(patch)
    monkeypatch.setattr(manager.settings,'save',blocked)
    manager._connect=lambda:connected.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        write=pool.submit(save_profile,manager,{'python':'C:/TC/python.exe'})
        assert entered.wait(3)
        connect=pool.submit(Manager.connect,manager)
        assert not connected.wait(.05)
        released.set();write.result();connect.result()
    assert connected.is_set()


@pytest.mark.parametrize('age', [16,-1,None])
def test_fresh_http_response_does_not_revive_stale_hardware(rig,age):
    manager,calls,value,app,client=rig
    value['last_checked_at']=time.time()-age if age is not None else None
    ui,headers=login(app,client)
    status=client.get(ui.prefix+'/api/status').json()
    assert status['fresh'] is False and status['boards'][0]['stale'] is True
    assert client.post(ui.prefix+'/api/action',headers=headers,json={'action':'manual','payload':{'board_id':'board-a','manual':True}}).status_code==409
    assert calls==[]


def test_preview_routes_never_open_processes_or_hardware(tmp_path,monkeypatch):
    app=preview_app(MockConnector(tmp_path),ORIGIN);ui=app.state.browser_ui
    with TestClient(app,base_url=ORIGIN,client=('127.0.0.1',1)) as client:
        one=ui.ticket()['url'].split('#ticket=')[1]
        csrf=client.post(ui.prefix+'/session',headers={'Origin':ORIGIN},json={'ticket':one}).json()['csrf']
        headers={'Origin':ORIGIN,'X-Connector-CSRF':csrf}
        monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:pytest.fail('preview opened a process'))
        for action in ('connect','putty','open-logs'):
            assert client.post(ui.prefix+'/api/action',headers=headers,json={'action':action,'payload':{'board_id':'board-a'} if action=='putty' else {}}).status_code==200
        assert client.post(ui.prefix+'/api/pick',headers=headers,json={'kind':'python'}).json()=={'path':''}
        assert client.get(ui.prefix+'/api/shared').status_code==409


def test_default_browser_dispatch_without_implicit_qt_import(tmp_path,monkeypatch):
    from backend.gui_test.connector import __main__ as entry
    from backend.gui_test.connector import web, supervisor
    opened=[]
    monkeypatch.setattr(supervisor,'ensure_manager',lambda home:SimpleNamespace(browser_ticket=lambda:{'url':'http://127.0.0.1:1/ui/fixture/#ticket=test'}))
    monkeypatch.setattr(web,'open_browser',opened.append)
    import builtins
    original_import=builtins.__import__
    def without_qt(name,*args,**kwargs):
        if name.startswith(('PySide6','shiboken6')):raise AssertionError('default browser imported Qt')
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',without_qt)
    assert entry.main(['--home',str(tmp_path)])==0
    assert opened and 'ticket=' in opened[0]


def test_explicit_qt_entry_remains_available(tmp_path,monkeypatch):
    from backend.gui_test.connector import __main__ as entry
    from backend.gui_test.connector import supervisor
    shown=[]
    application=SimpleNamespace(setApplicationName=lambda name:None,exec=lambda:7)
    monkeypatch.setitem(sys.modules,'PySide6.QtWidgets',SimpleNamespace(QApplication=lambda argv:application))
    monkeypatch.setitem(sys.modules,'backend.gui_test.connector.gui',SimpleNamespace(
        ConnectorWindow=lambda adapter:SimpleNamespace(show=lambda:shown.append(adapter))))
    monkeypatch.setattr(supervisor,'ensure_manager',lambda home:'existing-manager')
    assert entry.main(['--ui','qt','--home',str(tmp_path)])==7
    assert shown==['existing-manager']


@pytest.mark.parametrize('result', [{'path':'C:/한글 폴더/TC Python/python.exe'}, {'path':''}])
def test_native_picker_only_returns_path_and_cancel_preserves_input(rig,monkeypatch,result):
    from backend.gui_test.connector import web_actions
    manager,_,_,_,_=rig;adapter=ManagerActions(manager);commands=[]
    monkeypatch.setattr(web_actions,'os',SimpleNamespace(name='nt',environ={}))
    def run(argv,**kwargs):
        commands.append(argv)
        return SimpleNamespace(returncode=0,stdout=json.dumps(result))
    monkeypatch.setattr(subprocess,'run',run)
    assert adapter.pick({'kind':'python'})==result
    assert commands[0][-1]=='python' and '-m' in commands[0]
    with pytest.raises(TestError):adapter.pick({'kind':'arbitrary-command'})
    assert len(commands)==1


def test_shared_requests_preserve_service_contract_and_separate_local_profile(rig,monkeypatch):
    from backend.gui_test.connector import shared_control
    manager,_,_,_,_=rig;adapter=ManagerActions(manager);calls=[]
    before=manager.settings.path.read_bytes()
    monkeypatch.setattr(shared_control,'request',lambda *args:calls.append(args) or {'state':'PENDING'})
    assert adapter.shared({'expected_revision':'r'})=={'state':'PENDING'}
    assert calls==[(manager.home,'settings','PUT',{'expected_revision':'r'})]
    assert manager.settings.path.read_bytes()==before


def test_resource_exports_resolve_after_source_is_moved(tmp_path):
    spec=importlib.util.spec_from_file_location('connector_resource_packaging',ROOT/'apps/gui-test/package.py')
    packaging=importlib.util.module_from_spec(spec);spec.loader.exec_module(packaging)
    names=packaging.package_files(ROOT)
    for name in ('index.html','host.mjs','view.mjs','style.css'):
        key='backend/gui_test/connector/web_assets/'+name
        assert names[key]==asset_file(name).read_bytes()
    stage=packaging.stage_wheel(ROOT,tmp_path/'wheel',include_ui=False)
    assert all((stage/'gui_test/connector/web_assets'/name).is_file() for name in ('index.html','host.mjs','view.mjs','style.css'))
    from scripts.build_connector_bundle import _source_files,_editable_source
    files=_source_files(ROOT)
    for name in ('index.html','host.mjs','view.mjs','style.css'):
        key='backend/gui_test/connector/web_assets/'+name
        assert files[key].read_bytes()==asset_file(name).read_bytes()
        assert _editable_source('src/'+key)
    # Import from the staged installed namespace with a foreign cwd. No source
    # repository path is needed to mint a mock session or serve its UI assets.
    script='''import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import gui_test.connector.web as web
from gui_test.connector.preview import MockConnector
from fastapi.testclient import TestClient
assert Path(web.__file__).is_relative_to(Path(sys.argv[1]))
app=web.preview_app(MockConnector(Path('isolated-preview')), 'http://127.0.0.1:18773')
ui=app.state.browser_ui
with TestClient(app,base_url=ui.origin,client=('127.0.0.1',1)) as client:
    ticket=ui.ticket()['url'].split('#ticket=')[1]
    assert client.post(ui.prefix+'/session',headers={'Origin':ui.origin},json={'ticket':ticket}).status_code==200
    for name in ('index.html','host.mjs','view.mjs','style.css'):
        assert web.asset_file(name).is_relative_to(Path(sys.argv[1]))
    assert client.get(ui.prefix+'/view.mjs').status_code==200
'''
    result=subprocess.run([sys.executable,'-c',script,str(stage)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('code,status,expected', [('UI_ASSET_MISSING',503,'UI_ASSET_MISSING'),('CONNECTOR_REQUEST',404,'BROWSER_UNAVAILABLE')])
def test_old_manager_and_missing_assets_have_distinct_recovery(tmp_path,monkeypatch,code,status,expected):
    from backend.gui_test.connector.supervisor import Client
    def fail(*args):raise TestError('fixture failure',code,status)
    monkeypatch.setattr(Client,'request',fail)
    with pytest.raises(TestError) as exc:
        Client(tmp_path).browser_ticket()
    assert exc.value.code==expected


def test_preview_entry_binds_loopback_and_launches_an_authenticated_web_page(tmp_path,monkeypatch):
    import uvicorn
    from urllib.parse import urlsplit
    from backend.gui_test.connector import web
    opened=[];listeners=[]
    monkeypatch.setattr(web,'open_browser',opened.append)
    class Timer:
        def __init__(self,delay,launch):self.launch=launch
        def start(self):self.launch()
        def cancel(self):pass
    class Server:
        def __init__(self,config):self.app=config.app
        def run(self,sockets):
            listener=sockets[0];listeners.append(listener)
            address,port=listener.getsockname()
            assert address=='127.0.0.1' and 0<port<65536
            url=urlsplit(opened[0]);ui=self.app.state.browser_ui
            assert url.netloc=='127.0.0.1:'+str(port)
            with TestClient(self.app,base_url=ui.origin,client=('127.0.0.1',1)) as client:
                ticket=url.fragment.removeprefix('ticket=')
                assert client.post(ui.prefix+'/session',headers={'Origin':ui.origin},json={'ticket':ticket}).status_code==200
                assert client.get(ui.prefix+'/').status_code==200
                assert client.get(ui.prefix+'/api/status').json()['preview'] is True
    monkeypatch.setattr(web.threading,'Timer',Timer)
    monkeypatch.setattr(uvicorn,'Server',Server)
    web.run_preview(tmp_path)
    assert opened and listeners[0].fileno()==-1


def test_storage_bridge_preserves_cas_and_requires_browser_csrf(rig,monkeypatch):
    _,_,_,app,client=rig
    ui,headers=login(app,client)
    calls=[]
    def request(home,suffix,method='GET',value=None):
        calls.append((suffix,method,value))
        return {'revision':'a'*64,'enabled':True,'max_age_seconds':604800,'max_bytes':20*1024**3}
    monkeypatch.setattr('backend.gui_test.connector.shared_control.request',request)
    body={'expected_revision':'a'*64,'enabled':True,'max_age_seconds':1209600,'max_bytes':20*1024**3}
    assert client.get(ui.prefix+'/api/storage').status_code==200
    assert client.post(ui.prefix+'/api/storage',json=body,headers={'Origin':ORIGIN}).status_code==403
    assert client.post(ui.prefix+'/api/storage',json=body,headers=headers).status_code==200
    assert calls[-1]==('storage-policy','PUT',body)
    assert client.post(ui.prefix+'/api/storage-cleanup',json={'dry_run':True},headers=headers).status_code==200
    assert calls[-1]==('storage-cleanup','POST',{'dry_run':True})
