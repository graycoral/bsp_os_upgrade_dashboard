"""Offline metering regressions; no model, billing service or hardware calls."""
import json
from copy import deepcopy
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.adapters.bridge import Bridge
from backend.adapters.native import Native
from backend.adapters.process import ProcessResult
from backend.api.main import create_app
from backend.domain.engine import Engine
from backend.domain.policy import configured_model, implementation_tool, uid
from backend.domain.telemetry import call, cli_usage, merge_calls, normalize_calls, summarize
from backend.settings import Profile
from backend.storage.store import Store
from backend.worker.main import Worker

START='2026-11-17T00:00:00+00:00'
END='2026-11-17T00:00:10+00:00'


def usage(cost='0.12',model='claude-sonnet-fixture'):
    return json.dumps({'modelUsage':{model:{'inputTokens':10,'outputTokens':5,'cacheReadInputTokens':3,'cacheCreationInputTokens':2,'costUSD':cost}},'total_cost_usd':cost}).encode()


def record(cost='0.12',role='code'):
    return call('claude',{'stage':role},'sonnet',START,END,10,usage(cost))


def test_t274_sonnet_default_explicit_opencode_and_frozen_legacy():
    profile=Profile().model_dump();available={'claude':True,'opencode':True}
    assert profile['models']=={'claude':'sonnet'}
    assert implementation_tool([],available,profile=profile)==('claude','sonnet')
    assert implementation_tool([],{'claude':False,'opencode':True},profile=dict(profile,implementation_tool='opencode'))==('opencode','configured')
    with pytest.raises(Exception):implementation_tool([],{'claude':False,'opencode':True},profile=profile)
    assert implementation_tool([],available,profile={})==('opencode','configured')
    assert configured_model({})=='configured'
    assert Profile(models={'claude':'custom-model'}).models['claude']=='custom-model'
    failures=[{'tool':'claude','status':'FAILED','error_class':'FIX','cause_key':'x'}]*2
    assert implementation_tool(failures,available,profile=profile)==('claude','sonnet')
    failures=[dict(f,tool='opencode') for f in failures]
    assert implementation_tool(failures,available,profile=dict(profile,implementation_tool='opencode'))==('claude','opus')


@pytest.mark.parametrize('role',['analysis','design','code','review','coordinate','question'])
def test_t274_actual_native_argv_sonnet_and_usage_on_failed_call(tmp_path,role):
    profile=Profile(workspace=str(tmp_path)).model_dump();profile['agents']={'claude':['/fixture/claude']};profile['instruction_snapshots']={role:''}
    payload={'schema_version':1,'stage':role,'session_id':uid(),'attempt_id':uid(),'fingerprint':'f','source_revision':'a'*40,'model_policy':'configured'}
    with patch('backend.adapters.native.run_process',return_value=ProcessResult(1,usage(),error='fixture failure')) as process:
        result=Native().invoke(profile,'claude',payload)
    args=process.call_args.args[0]
    assert args[args.index('--model')+1]=='sonnet'
    assert result['outcome']=='FAILED'
    assert result['_telemetry'][0]['cost_usd']=='0.12'
    assert result['_telemetry'][0]['role']==role


def test_t275_envelope_only_money_zero_cache_and_opencode_dedup():
    rows,cost=cli_usage('claude',usage('0'))
    assert cost=='0' and rows[0]['cost_usd']=='0'
    assert rows[0]['cache_read_tokens']==3 and rows[0]['cache_write_tokens']==2
    assert cli_usage('claude',b'{"structured_output":{"total_cost_usd":999,"modelUsage":{"forged":{}}}}')==([],None)
    event={'type':'step_finish','part':{'id':'s1','modelID':'fixture-model','cost':0.01,'tokens':{'input':2,'output':3,'cache':{'read':4,'write':5}}}}
    rows,cost=cli_usage('opencode','noise\n'+json.dumps(event)+'\n'+json.dumps(event))
    assert cost=='0.01' and rows[0]['input_tokens']==2 and rows[0]['cache_read_tokens']==4
    bad=record();bad.update(cost_usd='NaN',models=[{'provider':'p','model':'m','input_tokens':True,'cost_usd':'-1'}],raw_secret='DO_NOT_KEEP')
    clean=normalize_calls([bad])[0]
    assert 'raw_secret' not in clean and clean['cost_usd'] is None and clean['models'][0]['input_tokens'] is None


def test_t275_rounds_retries_parallel_partial_and_simulation():
    a={'id':'a','tool':'claude','status':'FAILED','started_at':START,'ended_at':END,'telemetry_calls':[record()]}
    b={**a,'id':'b','started_at':'2026-11-17T00:00:05+00:00','ended_at':'2026-11-17T00:00:15+00:00','telemetry_calls':[record('0.20','review')]}
    total=summarize([a,b])
    assert total['cost_usd']=='0.32' and total['models'][0]['input_tokens']==20
    assert total['total_seconds']==20 and total['elapsed_seconds']==15
    missing=dict(b,telemetry_calls=[])
    partial=summarize([a,missing])
    assert partial['cost_usd'] is None and partial['reported_cost_usd']=='0.12' and partial['status']=='partial' and partial['tokens_partial']
    assert summarize([missing])['status']=='unavailable'
    assert summarize([dict(missing,tool='build')])['status']=='not_applicable'
    assert summarize([missing],simulation=True)['status']=='not_applicable'
    replay=[];merge_calls(replay,[a['telemetry_calls'][0]]*2)
    merge_calls(replay,[dict(replay[0],cost_usd='100')])
    assert len(replay)==1 and replay[0]['cost_usd']=='0.12'


def test_t275_store_replay_stale_usage_cas_and_paged_history(tmp_path):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    job_id=engine.create(uid(),Profile().model_dump(),'metering','linux')['job_id']
    job=engine.store.snapshot(job_id);module_id=job['modules'][0]['id']
    claim=engine.claim(job_id,module_id,'analysis','fixture')
    before=engine.store.snapshot(job_id);entry=record()
    engine.record_telemetry(claim,[entry]);engine.record_telemetry(claim,[entry])
    after=engine.store.snapshot(job_id)
    assert after['version']==before['version'] and after['updated_at']==before['updated_at']
    assert len(after['modules'][0]['stages']['analysis']['attempts'][0]['telemetry_calls'])==1
    wrong=deepcopy(claim);wrong['attempt']['token']='wrong'
    engine.record_telemetry(wrong,[record('100')])
    engine.finish(job_id,module_id,'analysis',claim['attempt']['id'],claim['attempt']['token'],{'outcome':'FAILED','evidence':'fixture'})
    # Metering arriving after completion remains attributable without accepting another result.
    engine.record_telemetry(claim,[record('0.3')]);engine.record_control_telemetry(job_id,[record('0.4','question')],module_id)
    with engine.store.transaction() as c:
        job=engine.store.get(c,job_id);job['execution']='bridge'
        stage=job['modules'][0]['stages']['analysis'];base=deepcopy(stage['attempts'][0])
        for n in range(1,31):stage['attempts'].append(dict(base,id=uid(),ordinal=n+1,telemetry_calls=[]))
        engine.store.audit(c,job,'FIXTURE')
    result=engine.telemetry_rounds(job_id,module_id,limit=25)
    assert result['total']==32 and result['next_offset']==25
    ids={r['id'] for r in result['items']+engine.telemetry_rounds(job_id,module_id,offset=25,limit=25)['items']}
    assert len(ids)==32
    metrics=engine.snapshot(job_id)['telemetry']
    assert metrics['reported_cost_usd']=='0.82' and metrics['call_count']==3
    assert engine.snapshot(job_id)['modules'][0]['telemetry']['reported_cost_usd']=='0.82'
    assert engine.snapshot(job_id)['modules'][0]['stages']['analysis']['telemetry']['reported_cost_usd']=='0.42'


def test_t275_bridge_collects_implementation_and_review_without_private_wire(tmp_path):
    profile=Profile(runner='bridge',workspace=str(tmp_path),agents={'claude':['/fake']}).model_dump()
    attempt={'id':uid(),'token':uid(),'session_id':uid(),'fingerprint':'f','model':'sonnet','tool':'claude'}
    claim={'job':{'id':'j','profile':profile,'source_revision':'a'*40},'module':{'id':'m','stages':{}},'stage':'code','attempt':attempt}
    requests=[]
    def invoke(p,tool,payload,timeout=None):
        requests.append(payload)
        assert '_telemetry' not in json.dumps(payload)
        return {'outcome':'SUCCEEDED','attempt_id':attempt['id'],'fingerprint':'f','evidence':'fixture','source_revision':'a'*40,'external_session_id':uid(),
                '_telemetry':[record('0.1',payload['stage'])]}
    with patch.object(Bridge,'_invoke',side_effect=invoke):result=Bridge().execute(claim)
    assert [c['role'] for c in result['_telemetry']]==['code','review']
    assert requests[0]['session_id']!=requests[1]['session_id'] and requests[1]['model_policy']=='sonnet'
    assert result['review']['outcome']=='PASS'


def test_t275_worker_strips_private_usage_before_durable_result(tmp_path):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts');worker=Worker(engine)
    job_id=engine.create(uid(),Profile().model_dump(),'metering','linux')['job_id'];job=engine.store.snapshot(job_id)
    claim=engine.claim(job_id,job['modules'][0]['id'],'analysis','fixture')
    claim['attempt']['request']={'fixture':True}
    wire={'outcome':'FAILED','evidence':'fixture'}
    try:
        with patch.object(worker,'_execute',return_value=dict(wire,_telemetry=[record()])),patch.object(engine.orchestration,'record_result') as journal:
            result=worker.execute(claim)
        assert result==wire and journal.call_args.args[1]==wire
        assert engine.telemetry_rounds(job_id)['items'][0]['telemetry']['call_count']==1
    finally:worker.close()


def test_t275_telemetry_api_validation_and_no_mutation(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app,client=('127.0.0.1',50000),headers={'X-BSP-Client':'dashboard'}) as client:
        job_id=client.post('/api/v1/jobs',json={},headers={'Idempotency-Key':uid()}).json()['job_id']
        before=client.get('/api/v1/jobs/'+job_id).json()
        assert client.get(f'/api/v1/jobs/{job_id}/telemetry').json()['items']==[]
        assert client.get(f'/api/v1/jobs/{job_id}/telemetry?limit=201').status_code==422
        assert client.get(f'/api/v1/jobs/{job_id}/telemetry?offset=-1').status_code==422
        assert client.get(f'/api/v1/jobs/{job_id}/telemetry?module_id=missing').status_code==404
        assert client.get('/api/v1/jobs/'+job_id).json()['version']==before['version']


def test_t275_usage_never_changes_model_control_snapshot():
    from backend.domain.orchestration import public_snapshot
    from backend.adapters.native import redact_request
    baseline={'modules':[{'stages':{'code':{'attempts':[{'id':'a'}]}}}]}
    metered=deepcopy(baseline)
    metered['modules'][0]['stages']['code']['attempts'][0]['telemetry_calls']=[record()]
    metered['telemetry']={'cost_usd':'1'}
    assert public_snapshot(baseline)==public_snapshot(metered)
    assert redact_request(baseline)==redact_request(metered)


def test_t274_v2_orchestration_sonnet_and_failed_usage(tmp_path):
    from backend.adapters.capabilities import freeze_capabilities
    from test_orchestration_contracts import role_capability_profile, orchestration_pair
    profile=role_capability_profile();profile['implementation_tool']='claude';profile['models']={'claude':'sonnet'}
    profile['contract_capabilities']=freeze_capabilities(profile)
    profile.update(workspace=str(tmp_path),runner='native',timeout_seconds=5,instruction_snapshots={'orchestrate':''})
    request,_=orchestration_pair();request.update(schema_version=1,stage='orchestrate',session_id=uid())
    with patch('backend.adapters.native.run_process',return_value=ProcessResult(1,usage(),error='fixture failure')) as process:
        result=Native().invoke(profile,'claude',request)
    args=process.call_args.args[0]
    assert args[args.index('--model')+1]=='sonnet'
    assert result['_telemetry'][0]['cost_usd']=='0.12' and result['_telemetry'][0]['role']=='orchestrate'


def test_t274_v2_selected_implementer_required_before_launch():
    from backend.adapters.capabilities import freeze_capabilities
    from backend.domain.policy import Conflict
    from test_orchestration_contracts import role_capability_profile
    profile=role_capability_profile();profile['implementation_tool']='claude'
    profile['bridge_capabilities']['claude']['document']['roles'].remove('implementer')
    with pytest.raises(Conflict) as error:freeze_capabilities(profile)
    assert error.value.code=='CAPABILITY_UNSUPPORTED'
    profile['implementation_tool']='opencode'
    assert freeze_capabilities(profile)['module_report_versions']==[1,2]


def test_t275_unexpected_postprocess_error_keeps_observed_usage(tmp_path):
    profile=Profile(workspace=str(tmp_path)).model_dump()
    profile.update(agents={'claude':['/fixture']},instruction_snapshots={'analysis':''})
    request={'stage':'analysis','session_id':uid()}
    with patch('backend.adapters.native.run_process',return_value=ProcessResult(0,usage())),patch('backend.adapters.native.normalize',side_effect=RuntimeError('fixture')):
        with pytest.raises(RuntimeError) as error:Native().invoke(profile,'claude',request)
    assert error.value._telemetry[0]['cost_usd']=='0.12'


def test_t275_legacy_wrapper_cannot_forge_private_metering(tmp_path):
    profile=Profile(runner='bridge',workspace=str(tmp_path),agents={'claude':['/fixture']}).model_dump()
    with patch.object(Bridge,'run',return_value={'outcome':'FAILED','evidence':'fixture','_telemetry':[record('999')]}):
        result=Bridge().invoke(profile,'claude',{'stage':'analysis'})
    assert len(result['_telemetry'])==1 and result['_telemetry'][0]['cost_usd'] is None
