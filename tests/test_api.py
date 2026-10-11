from fastapi.testclient import TestClient
import pytest
from backend.api.main import create_app
from backend.domain.policy import uid

@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path,'test-access-key')

@pytest.fixture
def client(app):
    return TestClient(app,headers={'Authorization':'Bearer test-access-key'})

def test_login_auth_and_cookie(app):
    with TestClient(app) as c:
        assert c.get('/api/v1/config').status_code==401
        assert c.post('/api/v1/session',json={'token':'bad'}).status_code==401
        r=c.post('/api/v1/session',json={'token':'test-access-key'})
        assert r.status_code==200
        assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
        assert c.get('/api/v1/config').status_code==200

def test_csrf_and_dns_rebinding(app):
    with TestClient(app,headers={'Authorization':'Bearer test-access-key'}) as c:
        assert c.post('/api/v1/jobs',json={},headers={'Origin':'https://hostile.test'}).status_code==403
        assert c.get('/api/v1/health',headers={'Host':'attacker.example'}).status_code==400

def test_settings_roundtrip_and_optimistic_version(client):
    c=client.get('/api/v1/config').json();c['profile']['host']='bsp.internal'
    assert client.put('/api/v1/config',json=c).status_code==200
    assert client.put('/api/v1/config',json=c).status_code==409
    assert client.get('/api/v1/config').json()['profile']['host']=='bsp.internal'

def test_settings_reject_secret_field_and_invalid_type(client):
    c=client.get('/api/v1/config').json();c['profile']['password']='not-allowed'
    assert client.put('/api/v1/config',json=c).status_code==422
    del c['profile']['password'];c['profile']['agents']={'claude':'rm -rf'}
    assert client.put('/api/v1/config',json=c).status_code==422

def test_no_live_without_configuration(client):
    c=client.get('/api/v1/config').json();c['profile']['execution']='bridge'
    assert client.put('/api/v1/config',json=c).status_code==200
    r=client.post('/api/v1/jobs',json={},headers={'Idempotency-Key':uid()})
    assert r.status_code==422
    assert client.get('/api/v1/jobs').json()==[]

def test_command_version_and_identity(client):
    key=uid();r=client.post('/api/v1/jobs',json={},headers={'Idempotency-Key':key})
    assert r.status_code==202
    assert client.post('/api/v1/jobs',json={},headers={'Idempotency-Key':key}).json()==r.json()
    j=r.json()['job_id']
    assert client.get(f'/api/v1/jobs/{j}').json()['execution']=='demo'
    bad=client.post(f'/api/v1/jobs/{j}/actions/pause',json={'expected_version':0},headers={'Idempotency-Key':uid()})
    assert bad.status_code==409 and bad.json()['code']=='VERSION_CONFLICT'

def test_evidence_ownership_and_path(client):
    j=client.post('/api/v1/jobs',json={},headers={'Idempotency-Key':uid()}).json()['job_id']
    r=client.post(f'/api/v1/jobs/{j}/evidence',content=b'test log',headers={'Content-Type':'application/octet-stream'})
    assert r.status_code==200 and len(r.json()['sha256'])==64
    assert client.get(f'/api/v1/jobs/{j}/artifacts/{r.json()["id"]}').status_code==404
    assert client.post('/api/v1/jobs/absent/evidence',content=b'bad').status_code==404

def test_upload_limit(client):
    assert client.post('/api/v1/jobs',content=b'x'*(2_097_152+1)).status_code==413

def test_no_fake_jira_connection(client):
    r=client.post('/api/v1/jira/probe')
    assert r.status_code==200 and r.json()['status']=='NOT_CONFIGURED'
    c=client.get('/api/v1/config').json();c['profile']['jira_mode']='claude_mcp';c['profile']['mcp_name']='jira'
    client.put('/api/v1/config',json=c)
    assert client.post('/api/v1/jira/probe').json()['status']=='UNVERIFIED'

def test_probe_distinguishes_registration(client):
    r=client.post('/api/v1/config/probe').json()
    assert all(x['status']=='NOT_CONFIGURED' for x in r['checks'])


@pytest.mark.parametrize('execution, expected', [('demo', 200), ('bridge', 409)])
def test_t65_demo_completion_api_checks_stored_execution(client, app, execution, expected):
    from backend.worker.main import demo_result
    e = app.state.engine
    j = client.post('/api/v1/jobs', json={}, headers={'Idempotency-Key': uid()}).json()['job_id']
    for m in e.snapshot(j)['modules']:
        c = e.claim(j, m['id'], 'analysis', 'fixture')
        e.finish(j, m['id'], 'analysis', c['attempt']['id'], c['attempt']['token'], demo_result(c, e.artifacts))
    e.act(j, uid(), e.snapshot(j)['version'], 'confirm', {'plan_version': 1})
    with e.store.transaction() as c:
        job = e.store.get(c, j); job['execution'] = execution; job['session']['status'] = 'READY'
        e.store.save(c, job, 'FIXTURE_MODE')
    job = e.snapshot(j)
    data = {'module_id': job['modules'][0]['id'], 'plan_version': 1, 'fingerprint': job['fingerprint'], 'execution': 'demo'}
    response = client.post(f'/api/v1/jobs/{j}/actions/demo-complete-module',
                           json={'expected_version': job['version'], 'data': data}, headers={'Idempotency-Key': uid()})
    assert response.status_code == expected
    updated = client.get(f'/api/v1/jobs/{j}').json()
    assert (updated['modules'][0]['progress']['percent'] == 100) == (execution == 'demo')
