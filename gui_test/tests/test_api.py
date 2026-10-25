from fastapi.testclient import TestClient
import pytest
from gui_test.standalone.server import create_app
from gui_test.core.models import uid
from .test_core import request, complete


@pytest.fixture
def app(tmp_path):return create_app(tmp_path,start_worker=False)


@pytest.fixture
def client(app):
    with TestClient(app,client=('127.0.0.1',1000),headers={'X-BSP-Client':'dashboard','X-GUI-Session':'owner','Idempotency-Key':uid()}) as c:yield c


def test_api_preflight_run_export_saved_data(client,app):
    base='/api/v1/gui-test'
    req=request(app.state.manager)
    assert client.get(base+'/capabilities').json()['hardware'] is False
    assert client.post(base+'/preflight',json=req).json()['ok']
    r=client.post(base+'/runs',json=req);assert r.status_code==202
    run=r.json();complete(app.state.manager,run)
    for fmt in ['json','csv','pdf','html','logs']:
        out=client.get(f'{base}/runs/{run["id"]}/report/{fmt}');assert out.status_code==200 and out.content
    assert client.get(base+'/runs/missing').status_code==404
    assert client.put(base+'/saved/profile',json={'name':'demo','data':{'connection':req['connection']}}).status_code==200
    assert len(client.get(base+'/saved/profile').json())==1
    assert client.post(base+'/runs',json={**req,'execution':'hardware'}).status_code==409  # same command key, different payload
    assert client.post(base+'/preflight',json={**req,'execution':'hardware'}).status_code==422
    assert client.post(base+'/preflight',json={**req,'password':'forbidden'}).status_code==422


@pytest.mark.parametrize('headers',[{'Origin':'https://hostile.test'},{'Sec-Fetch-Site':'cross-site'},{'Sec-Fetch-Site':'same-site'}])
def test_cross_site_read_write_blocked(client,headers):
    assert client.get('/api/v1/gui-test/catalog',headers=headers).status_code==403
    assert client.post('/api/v1/gui-test/runs',json={},headers=headers).status_code==403


def test_loopback_host_headers_and_limits(app):
    with TestClient(app,client=('192.0.2.1',1000)) as c:
        assert c.get('/api/v1/gui-test/catalog',headers={'X-Forwarded-For':'127.0.0.1'}).status_code==403
    with TestClient(app,client=('127.0.0.1',1000)) as c:
        assert c.post('/api/v1/gui-test/runs',json={}).status_code==403
        assert c.get('/api/v1/gui-test/catalog',headers={'Host':'evil.test'}).status_code==400
        assert c.post('/api/v1/gui-test/runs',content='x'*2_097_153,headers={'X-BSP-Client':'dashboard'}).status_code==413


def test_standalone_never_creates_or_contacts_dashboard(client,app):
    assert client.get('/api/v1/gui-test/demo/jobs').json()==[]
    assert client.post('/api/v1/gui-test/demo/jobs').status_code==409
    assert not list(app.state.manager.store.path.parent.rglob('dashboard.db'))


def test_integrated_mock_routes_leave_existing_dashboard_unchanged(tmp_path):
    from backend.api.main import create_app as dashboard_app
    app=dashboard_app(tmp_path)
    before=app.state.engine.store.all()
    with TestClient(app,client=('127.0.0.1',1000),headers={'X-BSP-Client':'dashboard','X-GUI-Session':'owner','Idempotency-Key':uid()}) as c:
        assert c.get('/api/v1/gui-test/catalog').status_code==200
        job=c.post('/api/v1/gui-test/demo/jobs').json()
        req=request(app.state.gui_manager,job_id=job['id'])
        r=c.post('/api/v1/gui-test/runs',headers={'Idempotency-Key':uid()},json=req).json()
        complete(app.state.gui_manager,r);app.state.gui_manager.sync_one()
    assert app.state.engine.store.all()==before
    assert app.state.gui_manager.get(r['id'])['sync']['status']=='SUCCEEDED'


def test_invalid_saved_document_is_validation_error(client):
    assert client.put('/api/v1/gui-test/saved/profile',json={'name':'bad','data':{}}).status_code==422
