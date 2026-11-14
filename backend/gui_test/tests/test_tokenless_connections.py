"""Service credentials removed by user request; local/SSH and ownership fences remain."""
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.gui_test.execution.host import Host, create_app as runner_app
from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.standalone.plugin_client import PluginClient
from backend.gui_test.standalone.integration import create_app as plugin_app
from backend.gui_test.tests.test_plugin_integration_service import rig
from scripts import setup_runtime


@pytest.fixture(autouse=True)
def no_service_tokens(monkeypatch):
    for key in ('GUI_TEST_RUNNER_TOKEN','GUI_TEST_CONNECTOR_REGISTRATION_TOKEN','GUI_TEST_INTEGRATION_TOKEN'):
        monkeypatch.delenv(key,raising=False)


def test_tokenless_host_rejects_remote_and_browser(tmp_path):
    host=Host({},tmp_path/'host',ports=lambda:set());app=runner_app(host)
    with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234)) as client:
        remote=WindowsRemote('http://127.0.0.1',client=client)
        assert remote.request('/identity')['runner_id']==host.identity
        assert remote.request('/inventory')['boards']==[]
        assert client.get('/v1/identity',headers={'Origin':'http://127.0.0.1'}).status_code==403
        assert client.get('/v1/identity',headers={'Sec-Fetch-Site':'same-origin'}).status_code==403
    with TestClient(app,client=('192.0.2.4',1234)) as client:
        assert client.get('/v1/identity').status_code==403


def test_full_dashboard_pairing_and_plugin_discovery_without_credentials(tmp_path):
    from backend.api.main import create_app
    host=Host({},tmp_path/'host',ports=lambda:set())
    with TestClient(runner_app(host),base_url='http://127.0.0.1',client=('127.0.0.1',1234)) as runner:
        app=create_app(tmp_path/'linux')
        app.state.gui_live_manager.runner.registry.factory=lambda url:WindowsRemote(url,client=runner)
        with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234)) as client:
            path='/api/v1/gui-test/live/connector'
            body={'url':'http://127.0.0.1:8771','runner_id':host.identity}
            assert client.post(path+'/register',json=body).status_code==200
            assert client.get(path+'/stop-readiness').json()=={'safe':True}
            plugin=PluginClient('http://127.0.0.1',expected_identity={'runtime_id':'test','package_version':'0.1.0','config_revision':'test','runner_id':host.identity},client=client)
            assert plugin.connector_inventory()['runner_id']==host.identity
            assert plugin.board_console()['runner_id']==host.identity
            assert isinstance(plugin.connector_errors()['events'],list)
            for method,route in [('POST',path+'/register'),('GET',path+'/stop-readiness')]:
                assert client.request(method,route,json=body if method=='POST' else None,headers={'Origin':'http://127.0.0.1'}).status_code==403
            assert client.post('/api/v1/jobs',json={},headers={'X-Bsp-Service':'plugin'}).status_code==403
            assert client.post('/api/v1/gui-test/live/runs',json={},headers={'X-Bsp-Service':'plugin'}).status_code==403


def test_plugin_requests_no_bearer_and_preserves_idempotency(rig,tmp_path):
    manager,_,_,request,_,calls=rig
    app=plugin_app(tmp_path,manager=manager,start_worker=False)
    with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1234)) as client:
        plugin=PluginClient('http://127.0.0.1',expected_identity={'runtime_id':'test','package_version':'0.1.0','config_revision':'test','runner_id':'test'},client=client)
        first=plugin.request('POST','/api/v1/gui-test/live/integration/runs',request,key='same-intent')
        second=plugin.request('POST','/api/v1/gui-test/live/integration/runs',request,key='same-intent')
        assert first['id']==second['id'] and first['controller']=='bsp-upgrade'
        assert len(manager.store.all())==1 and calls==[]
        assert 'authorization' not in client.headers
    seen=[]
    with httpx.Client(transport=httpx.MockTransport(lambda req: seen.append(req) or httpx.Response(200,json={}))) as client:
        remote=WindowsRemote('http://127.0.0.1','legacy-secret',client=client);remote.request('/inventory')
        plugin=PluginClient('http://127.0.0.1','legacy-secret',{'runtime_id':'x','package_version':'x','config_revision':'x','runner_id':'x'},client=client)
        plugin.request('GET','/api/v1/health')
    assert all('authorization' not in req.headers for req in seen)
    assert seen[1].headers['x-bsp-service']=='plugin'


def test_wizard_does_not_read_or_create_token_files(tmp_path,monkeypatch):
    wizard=setup_runtime.Wizard(root=tmp_path,windows=True,home=tmp_path/'private')
    monkeypatch.setattr(wizard.tokens,'load',lambda *a,**k:pytest.fail('Service token read'))
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN','old-service-secret')
    monkeypatch.setenv('GUI_TEST_CONNECTOR_REGISTRATION_TOKEN','old-registration-secret')
    monkeypatch.setenv('gui_test_integration_token','old-plugin-secret')
    env=wizard.environment()
    assert 'GUI_TEST_RUNNER_TOKEN' not in env and 'GUI_TEST_CONNECTOR_REGISTRATION_TOKEN' not in env
    assert 'gui_test_integration_token' not in env
    assert not wizard.home.exists()


def test_connector_monitor_and_disconnect_never_read_service_tokens(tmp_path,monkeypatch):
    from backend.gui_test.connector import supervisor
    from backend.gui_test.execution import launch
    from threading import Event, RLock
    manager=supervisor.Manager.__new__(supervisor.Manager)
    manager.home=tmp_path;manager.error='';manager.thread=None;manager.console_cursor=0;manager.console_epoch=None
    manager.storage_cache={};manager.storage_checked=10**20;manager.stop_event=Event();manager.control_lock=RLock()
    receipt={'runner_url':'http://127.0.0.1:8771','runner_id':'r'*32,'dashboard_url':'http://127.0.0.1:8765','remote_runner_port':8771,'phase':'ssh_running'}
    monkeypatch.setattr(launch,'read_active',lambda root:receipt)
    monkeypatch.setattr(setup_runtime.TokenStore,'load',lambda *a,**k:pytest.fail('Service token read'))
    seen=[]
    def respond(req):
        seen.append(req);path=req.url.path
        values={'/v1/inventory':{'runner_id':'r'*32,'boards':[],'checked_at':1,'host_busy':False,'reserved':False},
                '/v1/console':{'boards':[],'errors':[]},'/v1/recent-executions':{'executions':[]},
                '/api/v1/gui-test/live/connector/register':{'source_ready':False},
                '/api/v1/gui-test/live/connector/stop-readiness':{'safe':True},'/v1/connection-stop':{'safe':True}}
        return httpx.Response(200,json=values[path])
    real_client=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(respond)))
    assert manager.probe()['state']=='CONNECTED'
    assert manager.disconnect()['state']=='DISCONNECTING' and manager.stop_event.is_set()
    assert all('authorization' not in req.headers for req in seen)
