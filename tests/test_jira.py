import httpx
from backend.settings import Profile
from backend.adapters.jira import Jira
from backend.domain.policy import uid

def test_t51_create_ack_lost_does_not_duplicate(monkeypatch):
    monkeypatch.setenv('BSP_JIRA_TOKEN','test-only')
    calls=[];created=[];d={'id':uid(),'title':'New decision'}
    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/search'):
            return httpx.Response(200,json={'issues':created})
        created.append({'key':'BSP-1'})
        raise httpx.ReadTimeout('lost response')
    p=Profile(jira_url='https://jira.example',jira_project='BSP').model_dump()
    adapter=Jira(p,httpx.MockTransport(handler))
    assert adapter.ensure_link(d,'QUEUED')['sync_status']=='UNKNOWN'
    assert adapter.ensure_link(d,'UNKNOWN')['jira_key']=='BSP-1'
    assert calls.count('/rest/api/2/issue')==1

def test_t51_unknown_missing_search_result_does_not_create(monkeypatch):
    monkeypatch.setenv('BSP_JIRA_TOKEN','test-only')
    calls=[]
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200,json={'issues':[]})
    p=Profile(jira_url='https://jira.example',jira_project='BSP').model_dump()
    r=Jira(p,httpx.MockTransport(handler)).ensure_link({'id':uid(),'title':'d'},'UNKNOWN')
    assert r['sync_status']=='UNKNOWN' and len(calls)==1

def test_no_credentials_no_send(monkeypatch):
    monkeypatch.delenv('BSP_JIRA_TOKEN',raising=False)
    def handler(request):raise AssertionError('must not send')
    p=Profile(jira_url='https://jira.example').model_dump()
    assert Jira(p,httpx.MockTransport(handler)).ensure_link({'id':uid(),'title':'d'},'QUEUED')['sync_status']=='UNKNOWN'
