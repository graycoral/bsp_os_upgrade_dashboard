from fastapi.testclient import TestClient
import pytest
from backend.api.main import create_app
from backend.domain.policy import uid

@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path)

@pytest.fixture
def client(app):
    return TestClient(app, client=('127.0.0.1', 50000), headers={'X-BSP-Client':'dashboard'})

def test_t68_local_access_without_token_or_cookie(app, tmp_path):
    with TestClient(app, client=('127.0.0.1', 50000)) as c:
        assert c.get('/api/v1/config').status_code == 200
        assert c.get('/api/v1/jobs').json() == []  # Opening the UI never starts an upgrade.
        assert not c.cookies
        assert not (tmp_path / 'access-token').exists()
        r = c.post('/api/v1/jobs', json={}, headers={'X-BSP-Client':'dashboard', 'Idempotency-Key':uid()})
        assert r.status_code == 202 and not c.cookies


def test_t68_legacy_token_file_and_cookie_do_not_gate_access(tmp_path):
    (tmp_path / 'access-token').write_text('obsolete-token')
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 50000)) as c:
        c.cookies.set('bsp_session', 'expired-cookie')
        assert c.get('/api/v1/config').status_code == 200
        assert (tmp_path / 'access-token').read_text() == 'obsolete-token'
        response = c.post('/api/v1/session', json={'token':'unused'}, headers={'X-BSP-Client':'dashboard'})
        # StaticFiles returns 405 for unknown POST paths when the UI build is mounted.
        assert response.status_code in {404, 405}
        assert 'set-cookie' not in response.headers


@pytest.mark.parametrize('peer', ['192.0.2.1', '10.0.0.3', '2001:db8::1'])
def test_t69_nonlocal_peer_rejected_despite_forged_headers(app, peer):
    with TestClient(app, client=(peer, 50000), headers={'X-BSP-Client':'dashboard', 'X-Forwarded-For':'127.0.0.1'}) as c:
        assert c.get('/api/v1/config').status_code == 403
        assert c.post('/api/v1/jobs', json={}, headers={'Idempotency-Key':uid()}).status_code == 403


@pytest.mark.parametrize('origin', ['https://hostile.test', 'http://127.0.0.1:9999', 'null'])
def test_t69_cross_origin_read_and_write_rejected(client, origin):
    assert client.get('/api/v1/config', headers={'Origin':origin}).status_code == 403
    assert client.post('/api/v1/jobs', json={}, headers={'Origin':origin}).status_code == 403


@pytest.mark.parametrize('site', ['cross-site', 'same-site'])
def test_t69_browser_foreign_site_rejected(client, site):
    assert client.get('/api/v1/config', headers={'Sec-Fetch-Site':site}).status_code == 403
    assert client.post('/api/v1/jobs', json={}, headers={'Sec-Fetch-Site':site}).status_code == 403


def test_t69_local_same_origin_and_dns_rebinding(client, app):
    assert client.get('/api/v1/health', headers={'Host':'attacker.example'}).status_code == 400
    assert client.get('/api/v1/config', headers={'Origin':'http://testserver', 'Sec-Fetch-Site':'same-origin'}).status_code == 200
    with TestClient(app, client=('127.0.0.1', 50000)) as c:
        assert c.post('/api/v1/jobs', json={}, headers={'Idempotency-Key':uid()}).status_code == 403
        assert c.post('/api/v1/jobs', content='title=form', headers={'Content-Type':'text/plain'}).status_code == 403
    with TestClient(app, client=('::1', 50000)) as c:
        assert c.get('/api/v1/config').status_code == 200

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
    from backend.settings import bridge_defaults
    config=client.get('/api/v1/config').json()
    config['profile'].update(runner='bridge', **bridge_defaults('/fixture/nonexistent'))
    assert client.put('/api/v1/config',json=config).status_code == 200
    r=client.post('/api/v1/config/probe').json()
    assert r['checks'][0]['status']=='NOT_CONFIGURED'
    assert all(x['status']=='MISSING' for x in r['checks'][1:])
    assert {x['name'] for x in r['checks'][1:]} == {'claude','opencode','codex','build'}


def test_t94_default_suggestion_does_not_save_or_start(client):
    c=client.get('/api/v1/config').json()
    p=dict(c['profile'], workspace='/srv/custom bsp')
    result=client.post('/api/v1/config/bridge-defaults',json=p)
    assert result.status_code == 200
    assert result.json()['build_argv'] == ['/srv/custom bsp/.bsp-dashboard/bridges/build']
    assert client.get('/api/v1/config').json() == c
    assert client.get('/api/v1/jobs').json() == []


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
