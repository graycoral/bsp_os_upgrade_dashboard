"""New job policy normalization; real Engine claims, mocked BSP/model results."""
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.domain.engine import Engine
from backend.domain.policy import uid
from backend.settings import Profile
from backend.storage.store import Store
from backend.worker.main import demo_result


def code_claim(engine, job_id):
    job=engine.store.snapshot(job_id)
    for module in job['modules']:
        claim=engine.claim(job_id,module['id'],'analysis','fixture')
        engine.finish(job_id,module['id'],'analysis',claim['attempt']['id'],claim['attempt']['token'],demo_result(claim,engine.artifacts))
    job=engine.store.snapshot(job_id)
    engine.act(job_id,uid(),job['version'],'confirm',{'plan_version':job['plan_version']})
    module_id=job['modules'][0]['id']
    claim=engine.claim(job_id,module_id,'design','fixture')
    engine.finish(job_id,module_id,'design',claim['attempt']['id'],claim['attempt']['token'],demo_result(claim,engine.artifacts))
    return engine.claim(job_id,module_id,'code','fixture')


@pytest.mark.parametrize('model',[None,'','custom-model'])
def test_direct_new_job_with_legacy_config_defaults_to_claude(tmp_path,model):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    profile=Profile().model_dump();profile.pop('implementation_tool')
    profile['models']={} if model is None else {'claude':model}
    original=deepcopy(profile)
    job_id=engine.create(uid(),profile,'new direct job','linux')['job_id']
    claim=code_claim(engine,job_id)
    assert claim['attempt']['tool']=='claude'
    assert claim['attempt']['model']==(model or 'sonnet')
    assert engine.store.snapshot(job_id)['profile']['implementation_tool']=='claude'
    assert profile==original


def test_explicit_opencode_is_kept_for_new_job(tmp_path):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    profile=Profile(implementation_tool='opencode',models={'claude':'custom-review','opencode':'custom-code'}).model_dump()
    job_id=engine.create(uid(),profile,'explicit','linux')['job_id']
    assert code_claim(engine,job_id)['attempt']['tool']=='opencode'
    assert engine.store.snapshot(job_id)['profile']['models']==profile['models']


def test_existing_legacy_snapshot_and_idempotent_replay_remain_unchanged(tmp_path):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    profile=Profile().model_dump();profile.pop('implementation_tool');profile['models']={}
    key=uid();created=engine.create(key,profile,'old','linux');job_id=created['job_id']
    with engine.store.transaction() as c:
        job=engine.store.get(c,job_id);job['profile'].pop('implementation_tool',None);job['profile']['models']={}
        engine.store.save(c,job,"fixture_legacy_snapshot")
    before=deepcopy(engine.store.snapshot(job_id))
    assert engine.create(key,profile,'old','linux')==created
    assert engine.store.snapshot(job_id)==before
    assert code_claim(engine,job_id)['attempt']['tool']=='opencode'


def test_dashboard_new_job_from_old_saved_settings_defaults_to_claude(tmp_path):
    app=create_app(tmp_path)
    profile=Profile().model_dump();profile.pop('implementation_tool');profile['models']={}
    with app.state.engine.store.transaction() as c:
        c.execute('UPDATE config SET data=? WHERE id=1',(json.dumps(profile),))
    with TestClient(app,client=('127.0.0.1',123),headers={'X-BSP-Client':'dashboard'}) as client:
        response=client.post('/api/v1/jobs',json={},headers={'Idempotency-Key':uid()})
        assert response.status_code==202
        assert code_claim(app.state.engine,response.json()['job_id'])['attempt']['tool']=='claude'


def test_new_policy_is_frozen_before_v2_capability_probes(monkeypatch):
    from backend.settings import prepare_job_profile
    from backend.adapters import capabilities,inventory
    profile=Profile(module_report_version=2).model_dump();profile.pop('implementation_tool');profile['models']={}
    original=deepcopy(profile);seen=[]
    def freeze(value):
        seen.append(deepcopy(value))
        return {'fixture':'capabilities'}
    monkeypatch.setattr(capabilities,'freeze_capabilities',freeze)
    monkeypatch.setattr(inventory,'build_vendor_inventory',lambda _: {'changes':[]})
    prepared=prepare_job_profile(profile)
    assert seen[0]['implementation_tool']=='claude' and seen[0]['models']=={'claude':'sonnet'}
    assert prepared['contract_capabilities']=={'fixture':'capabilities'}
    assert prepared['runner']==profile['runner'] and prepared['agents']==profile['agents']
    assert profile==original
