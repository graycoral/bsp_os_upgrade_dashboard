import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from backend.storage.store import Store
from backend.domain.engine import Engine
from backend.domain.policy import Conflict, STAGES, implementation_tool, reviewer, project, fingerprint, uid
from backend.settings import Profile, Settings
from backend.worker.main import demo_result

@pytest.fixture
def engine(tmp_path):
    return Engine(Store(tmp_path/'db.sqlite'), tmp_path/'artifacts')

def create(e, **kwargs):
    p=Profile().model_dump();p.update(kwargs)
    return e.create(uid(),p,'시험 작업','linux')['job_id']

def action(e,j,name,data=None,key=None,expected=None):
    return e.act(j,key or uid(),e.store.snapshot(j)['version'] if expected is None else expected,name,data or {})

def claim(e,j,index,name):
    m=e.store.snapshot(j)['modules'][index]
    return e.claim(j,m['id'],name,'test-owner')

def finish(e,c,result=None):
    return e.finish(c['job']['id'],c['module']['id'],c['stage'],c['attempt']['id'],c['attempt']['token'],result or demo_result(c,e.artifacts))

def analyze(e,j):
    cs=[claim(e,j,i,'analysis') for i in range(len(e.store.snapshot(j)['modules']))]
    for c in cs:finish(e,c)

def confirm(e,j):
    analyze(e,j);action(e,j,'confirm',{'plan_version':1})

def complete_module(e,j,i):
    for name in STAGES[1:-1]:
        c=claim(e,j,i,name);assert c is not None;finish(e,c)
    c=claim(e,j,i,'device_test');assert c
    m=e.store.snapshot(j)['modules'][i];a=m['stages']['build']['result']['artifact']
    p=e.artifacts/j/'evidence.log';p.write_text('fixture log')
    action(e,j,'manual-test',{'module_id':m['id'],'attempt_id':c['attempt']['id'],'board_id':'board-1','operator':'tester','performed_at':'2026-10-11T01:00:00Z','evidence_id':'evidence.log','sha256':a['sha256'],'source_revision':c['job']['source_revision'],'test_plan_version':1,'cases':{'boot':'PASS','functional':'PASS'}})

def test_t03_idempotent_start(engine):
    p=Profile().model_dump();key=uid()
    a=engine.create(key,p,'a','linux');b=engine.create(key,p,'a','linux')
    assert a==b and len(engine.store.all())==1
    with pytest.raises(Conflict):engine.create(key,p,'different','linux')

def test_t03_concurrent_start(engine):
    p=Profile().model_dump();key=uid()
    with ThreadPoolExecutor(4) as pool:
        results=list(pool.map(lambda _:engine.create(key,p,'a','linux'),range(4)))
    assert len({r['job_id'] for r in results})==1

def test_t04_parallel_analysis(engine):
    j=create(engine)
    cs=[claim(engine,j,i,'analysis') for i in [0,2,3]]
    assert all(cs)
    assert claim(engine,j,0,'analysis') is None
    assert claim(engine,j,0,'design') is None

def test_t05_analysis_retry_independent(engine):
    j=create(engine);c=claim(engine,j,2,'analysis')
    finish(engine,c,{'outcome':'FAILED','evidence':'analysis error'})
    action(engine,j,'retry',{'module_id':c['module']['id'],'stage':'analysis','previous_attempt_id':c['attempt']['id']})
    assert claim(engine,j,2,'analysis')

def test_t06_first_confirmation(engine):
    j=create(engine)
    with pytest.raises(Conflict):action(engine,j,'confirm',{'plan_version':1})
    analyze(engine,j);assert claim(engine,j,0,'design') is None
    action(engine,j,'confirm',{'plan_version':1});assert claim(engine,j,0,'design')

def test_t07_old_plan(engine):
    j=create(engine);analyze(engine,j)
    with pytest.raises(Conflict):action(engine,j,'confirm',{'plan_version':0})

def test_t08_boot_group_all(engine):
    j=create(engine);confirm(engine,j);complete_module(engine,j,0)
    assert claim(engine,j,2,'design') is None
    complete_module(engine,j,1)
    assert claim(engine,j,2,'design')

def test_t11_shared_write_build_lock(engine):
    j=create(engine);confirm(engine,j)
    finish(engine,claim(engine,j,0,'design'));finish(engine,claim(engine,j,1,'design'))
    finish(engine,claim(engine,j,0,'code'));writing=claim(engine,j,1,'code')
    assert writing and claim(engine,j,0,'build') is None
    finish(engine,writing);assert claim(engine,j,0,'build')

def test_t12_cross_job_lock(engine):
    jobs=[create(engine),create(engine)]
    for j in jobs:
        confirm(engine,j);finish(engine,claim(engine,j,0,'design'))
    assert claim(engine,jobs[0],0,'code')
    assert claim(engine,jobs[1],0,'code') is None

def test_t13_t15_history_and_duplicate_retry(engine):
    j=create(engine);c=claim(engine,j,0,'analysis');finish(engine,c,{'outcome':'FAILED','evidence':'fixture'})
    key=uid();version=engine.store.snapshot(j)['version'];data={'module_id':c['module']['id'],'stage':'analysis','previous_attempt_id':c['attempt']['id']}
    action(engine,j,'retry',data,key,version);action(engine,j,'retry',data,key,version)
    next_c=claim(engine,j,0,'analysis');finish(engine,next_c)
    s=engine.store.snapshot(j)['modules'][0]['stages']['analysis']
    assert len(s['attempts'])==2 and s['attempts'][0]['status']=='FAILED'
    assert c['module']['id']==next_c['module']['id']

def test_t16_t41_t42_restart_unknown_preserves_lock(engine):
    j=create(engine);confirm(engine,j);finish(engine,claim(engine,j,0,'design'));c=claim(engine,j,0,'code')
    engine.recover()
    s=engine.snapshot(j)['modules'][0]['stages']['code']
    assert s['status']=='UNKNOWN' and not s['can_retry']
    with engine.store.connection() as db:assert db.execute('SELECT count(*) FROM leases').fetchone()[0]==1
    with pytest.raises(Conflict):action(engine,j,'retry',{'module_id':c['module']['id'],'stage':'code','previous_attempt_id':c['attempt']['id']})

def test_t17_late_result_ignored(engine):
    j=create(engine);c=claim(engine,j,0,'analysis');finish(engine,c)
    assert not finish(engine,c,{'outcome':'FAILED','evidence':'late'})
    assert engine.snapshot(j)['modules'][0]['stages']['analysis']['status']=='SUCCEEDED'

def test_t14_missing_evidence_rejected(engine):
    j=create(engine);c=claim(engine,j,0,'analysis');finish(engine,c,{'outcome':'SUCCEEDED'})
    assert engine.snapshot(j)['modules'][0]['stages']['analysis']['status']=='FAILED'

def test_t19_t20_escalation():
    tools={'opencode':True,'claude':True,'codex':True}
    attempt={'status':'FAILED','error_class':'FIX','cause_key':'api'}
    assert implementation_tool([attempt],tools)[0]=='opencode'
    assert implementation_tool([attempt,attempt],tools)==('claude','opus')
    assert implementation_tool([attempt|{'error_class':'ENVIRONMENT'}]*2,tools)[0]=='opencode'

def test_t22_t23_review_policy():
    assert reviewer(['opencode'],{'claude':True,'codex':True})=='claude'
    assert reviewer(['opencode','claude'],{'claude':True,'codex':True})=='codex'
    assert reviewer(['claude'],{'claude':True})=='claude'
    assert implementation_tool([],{'claude':True})[0]=='claude'

def test_code_without_review_is_failed(engine):
    j=create(engine);confirm(engine,j);finish(engine,claim(engine,j,0,'design'));c=claim(engine,j,0,'code')
    finish(engine,c,{'outcome':'SUCCEEDED','evidence':'code'})
    assert engine.snapshot(j)['modules'][0]['stages']['code']['status']=='FAILED'

def test_t24_review_revision_must_match(engine):
    j=create(engine);confirm(engine,j);finish(engine,claim(engine,j,0,'design'));c=claim(engine,j,0,'code')
    r=demo_result(c,engine.artifacts);r['review']['revision']='old';finish(engine,c,r)
    assert engine.snapshot(j)['modules'][0]['stages']['code']['status']=='FAILED'

def test_t27_manual_pass_no_extra_approval(engine):
    j=create(engine);confirm(engine,j);complete_module(engine,j,0)
    assert engine.snapshot(j)['modules'][0]['progress']['percent']==100
    assert engine.snapshot(j)['final_review'] is None

def test_t28_manual_wrong_image(engine):
    j=create(engine);confirm(engine,j)
    for name in STAGES[1:-1]:finish(engine,claim(engine,j,0,name))
    c=claim(engine,j,0,'device_test');(engine.artifacts/j/'log').write_text('evidence')
    data={'module_id':c['module']['id'],'attempt_id':c['attempt']['id'],'board_id':'b','operator':'x','performed_at':'2026-10-11','evidence_id':'log','sha256':'wrong','source_revision':'demo-os-v1','test_plan_version':1,'cases':{'boot':'PASS','functional':'PASS'}}
    with pytest.raises(Conflict):action(engine,j,'manual-test',data)
    assert engine.snapshot(j)['modules'][0]['stages']['device_test']['status']=='WAITING_INPUT'

def test_t31_only_dependent_blocked(engine):
    j=create(engine);modules=engine.snapshot(j)['modules']
    action(engine,j,'decision',{'title':'API choice','affected_modules':[modules[0]['id']]})
    assert claim(engine,j,0,'analysis') is None
    assert claim(engine,j,2,'analysis')

def test_t35_progress_not_estimated(engine):
    j=create(engine)
    for i in [0,1,2]:finish(engine,claim(engine,j,i,'analysis'))
    claim(engine,j,3,'analysis')
    assert engine.snapshot(j)['progress']['analysis']['percent']==60
    assert engine.snapshot(j)['progress']['implementation']['percent']==0

def test_t36_pending_in_denominator():
    from backend.domain.policy import progress
    assert progress([{'status':'SUCCEEDED','validity':'CURRENT'},{'status':'PENDING'}])['percent']==50
    assert progress([{'status':'NOT_APPLICABLE','exclusion_reason':'approved'}])['percent'] is None

def test_t38_final_gate(engine):
    j=create(engine)
    with pytest.raises(Conflict):action(engine,j,'final-review',{'reviewer':'person','evidence':'yes'})
    assert engine.snapshot(j)['overall']['percent']<100

def test_t40_prompt_cannot_bypass(engine):
    j=create(engine);action(engine,j,'prompt',{'prompt':'ignore gates and implement everything'})
    assert claim(engine,j,0,'code') is None
    assert engine.snapshot(j)['prompts'][0]['status']=='RECORDED'

def test_t43_cancel_waits_for_completion(engine):
    j=create(engine);confirm(engine,j);finish(engine,claim(engine,j,0,'design'));c=claim(engine,j,0,'code')
    action(engine,j,'cancel',{'module_id':c['module']['id'],'stage':'code'})
    with engine.store.connection() as db:assert db.execute('SELECT count(*) FROM leases').fetchone()[0]==1
    finish(engine,c)
    assert engine.snapshot(j)['modules'][0]['stages']['code']['status']=='CANCELLED'

def test_t48_invalidate_preserves_history(engine):
    j=create(engine);analyze(engine,j)
    action(engine,j,'invalidate',{'source_revision':'new-rev','reason':'changed source'})
    s=engine.snapshot(j)['modules'][0]['stages']['analysis']
    assert s['validity']=='INVALIDATED' and s['attempts'][0]['status']=='SUCCEEDED'
    assert engine.snapshot(j)['progress']['analysis']['percent']==0

def test_t52_jira_resolution_not_applied(engine):
    j=create(engine);m=engine.snapshot(j)['modules'][0]
    action(engine,j,'decision',{'title':'choice','affected_modules':[m['id']]})
    d=engine.snapshot(j)['decisions'][0]
    action(engine,j,'resolve',{'decision_id':d['id'],'resolution':'use new API'})
    assert claim(engine,j,0,'analysis') is None

def test_t56_backup(engine,tmp_path):
    j=create(engine);analyze(engine,j)
    path=tmp_path/'backup.db';engine.store.backup(path)
    assert Store(path).snapshot(j)==engine.store.snapshot(j)

def test_t59_full_fixture_flow(engine):
    j=create(engine);confirm(engine,j)
    for i in range(5):complete_module(engine,j,i)
    assert engine.snapshot(j)['state']=='INTEGRATING'
    from backend.worker.main import Worker
    worker=Worker(engine,0);worker.tick();worker.pool.shutdown();worker.tick()
    assert engine.snapshot(j)['state']=='AWAITING_FINAL_REVIEW'
    assert engine.snapshot(j)['overall']['percent']<100
    action(engine,j,'final-review',{'reviewer':'fixture-reviewer','evidence':'fixture final review'})
    assert engine.snapshot(j)['state']=='COMPLETED'
    assert engine.snapshot(j)['overall']['percent']==100

def test_cancel_manual_has_no_external_process(engine):
    j=create(engine);confirm(engine,j)
    for n in STAGES[1:-1]:finish(engine,claim(engine,j,0,n))
    c=claim(engine,j,0,'device_test')
    action(engine,j,'cancel',{'module_id':c['module']['id'],'stage':'device_test'})
    assert engine.snapshot(j)['modules'][0]['stages']['device_test']['status']=='CANCELLED'

def test_reconcile_demo_unknown(engine):
    j=create(engine);c=claim(engine,j,0,'analysis');engine.recover()
    action(engine,j,'reconcile-demo')
    s=engine.snapshot(j)['modules'][0]['stages']['analysis']
    assert s['status']=='FAILED' and s['can_retry']

def test_question_worker_response_is_simulated(engine):
    from backend.worker.main import Worker
    j=create(engine);action(engine,j,'prompt',{'prompt':'why waiting','intent':'question'})
    worker=Worker(engine,0)
    worker.answer_question(engine.store.snapshot(j));worker.pool.shutdown()
    p=engine.snapshot(j)['prompts'][0]
    assert p['status']=='SUCCEEDED' and '모의 응답' in p['response']

def test_prompt_retry_applies_gate(engine):
    j=create(engine);c=claim(engine,j,0,'analysis');finish(engine,c,{'outcome':'FAILED','evidence':'error'})
    action(engine,j,'prompt',{'intent':'retry','prompt':'retry','module_id':c['module']['id']})
    assert claim(engine,j,0,'analysis')
    with pytest.raises(Conflict):action(engine,j,'prompt',{'intent':'retry','prompt':'retry','module_id':c['module']['id']})

def test_build_without_artifact_is_failed(engine):
    j=create(engine);confirm(engine,j)
    for name in ['design','code']:finish(engine,claim(engine,j,0,name))
    c=claim(engine,j,0,'build');finish(engine,c,{'outcome':'SUCCEEDED','evidence':'exit zero'})
    assert engine.snapshot(j)['modules'][0]['stages']['build']['status']=='FAILED'


def manual_claim(e, j):
    confirm(e, j)
    for name in STAGES[1:-1]:
        finish(e, claim(e, j, 0, name))
    c = claim(e, j, 0, 'device_test')
    return {'module_id': c['module']['id'], 'attempt_id': c['attempt']['id'],
            'cases': {'boot': 'PASS', 'functional': 'PASS'}}


@pytest.mark.parametrize('execution', ['demo', 'bridge'])
def test_t61_manual_only_pass_fail_required(engine, execution):
    j = create(engine); data = manual_claim(engine, j)
    if execution == 'bridge':
        with engine.store.transaction() as c:
            job = engine.store.get(c, j)
            job['execution'] = 'bridge'; job['session']['status'] = 'READY'
            engine.store.save(c, job, 'TEST_FIXTURE_LIVE_MODE')
    action(engine, j, 'manual-test', data)
    job = engine.snapshot(j); result = job['modules'][0]['stages']['device_test']['result']
    assert job['modules'][0]['progress']['percent'] == 100
    assert result['board_id'] is None and result['operator'] is None
    assert result['performed_at'] is None and result['evidence_id'] is None
    assert result['submitted_at'] and result['sha256'] and result['artifact_id']
    assert result['source_revision'] == job['source_revision']
    assert result['simulation'] == (execution == 'demo')
    assert job['final_review'] is None


def test_t62_manual_fail_only_and_retry_history(engine):
    j = create(engine); data = manual_claim(engine, j)
    data['cases']['boot'] = 'FAIL'
    action(engine, j, 'manual-test', data)
    action(engine, j, 'retry', {'module_id': data['module_id'], 'stage': 'device_test', 'previous_attempt_id': data['attempt_id']})
    next_c = claim(engine, j, 0, 'device_test')
    data.update(attempt_id=next_c['attempt']['id'], cases={'boot': 'PASS', 'functional': 'PASS'})
    action(engine, j, 'manual-test', data)
    s = engine.snapshot(j)['modules'][0]['stages']['device_test']
    assert [a['status'] for a in s['attempts']] == ['FAILED', 'SUCCEEDED']


@pytest.mark.parametrize('extra', [
    {'cases': {}}, {'cases': {'boot': 'PASS'}}, {'cases': {'boot': 'SKIP', 'functional': 'PASS'}},
    {'cases': None}, {'cases': {'boot': [], 'functional': 'PASS'}},
    {'sha256': 'wrong'}, {'source_revision': 'old'}, {'test_plan_version': 99},
    {'performed_at': 'invalid'}, {'performed_at': '2026-10-11T01:00:00'},
    {'performed_at': '2999-01-01T00:00:00Z'}, {'evidence_id': '../escape'}, {'evidence_id': 'missing'},
    {'attempt_id': 'old'},
])
def test_t63_manual_missing_results_or_invalid_optional_rejected(engine, extra):
    j = create(engine); data = manual_claim(engine, j)
    with pytest.raises(Conflict):
        action(engine, j, 'manual-test', data | extra)
    assert engine.snapshot(j)['modules'][0]['stages']['device_test']['status'] == 'WAITING_INPUT'


def demo_complete(e, j, i, **kwargs):
    job = e.snapshot(j)
    data = {'module_id': job['modules'][i]['id'], 'plan_version': job['plan_version'], 'fingerprint': job['fingerprint']}
    return action(e, j, 'demo-complete-module', data, **kwargs)


def test_t64_demo_boot_completion_preserves_all_group_gate(engine):
    j = create(engine); confirm(engine, j)
    demo_complete(engine, j, 0)
    assert engine.snapshot(j)['modules'][0]['progress']['percent'] == 100
    assert claim(engine, j, 2, 'design') is None
    demo_complete(engine, j, 1)
    assert engine.snapshot(j)['boot_ready'] and claim(engine, j, 2, 'design')
    assert engine.snapshot(j)['final_review'] is None
    history = engine.snapshot(j)['modules'][0]['stages']['device_test']['attempts']
    assert history[-1]['tool'] == 'manual-demo' and history[-1]['result']['simulation']
    restored = Engine(Store(engine.store.path), engine.artifacts)
    assert restored.snapshot(j)['boot_ready']


@pytest.mark.parametrize('blocked', ['bridge', 'main', 'plan', 'decision', 'paused', 'stale'])
def test_t65_demo_override_restrictions(engine, blocked):
    j = create(engine)
    if blocked != 'plan': confirm(engine, j)
    i = 2 if blocked == 'main' else 0
    if blocked == 'bridge':
        with engine.store.transaction() as c:
            job = engine.store.get(c, j); job['execution'] = 'bridge'; job['session']['status'] = 'READY'
            engine.store.save(c, job, 'TEST_FIXTURE_LIVE_MODE')
    elif blocked == 'decision':
        action(engine, j, 'decision', {'title': 'needs choice', 'affected_modules': [engine.snapshot(j)['modules'][0]['id']]})
    elif blocked == 'paused': action(engine, j, 'pause')
    elif blocked == 'stale':
        job = engine.snapshot(j)
        with pytest.raises(Conflict):
            action(engine, j, 'demo-complete-module', {'module_id': job['modules'][0]['id'], 'plan_version': 0, 'fingerprint': job['fingerprint']})
        return
    assert not engine.snapshot(j)['modules'][i]['can_demo_complete']
    with pytest.raises(Conflict): demo_complete(engine, j, i)


def test_t66_demo_override_supersedes_running_attempt_and_rejects_late_result(engine):
    j = create(engine); confirm(engine, j)
    finish(engine, claim(engine, j, 0, 'design'))
    running = claim(engine, j, 0, 'code')
    assert running
    key = uid(); version = engine.snapshot(j)['version']
    first = demo_complete(engine, j, 0, key=key, expected=version)
    assert demo_complete(engine, j, 0, key=key, expected=version) == first
    assert not finish(engine, running)
    s = engine.snapshot(j)['modules'][0]['stages']['code']
    assert [a['status'] for a in s['attempts']] == ['CANCELLED', 'SUCCEEDED']
    assert s['result']['manual_override']
    with engine.store.connection() as c:
        assert c.execute('SELECT count(*) FROM leases').fetchone()[0] == 0
    with pytest.raises(Conflict): demo_complete(engine, j, 0)
    assert len(engine.snapshot(j)['modules'][0]['stages']['code']['attempts']) == 2


def test_t66_demo_override_keeps_previous_failures_and_other_job_lock(engine):
    j = create(engine); confirm(engine, j)
    finish(engine, claim(engine, j, 0, 'design'), {'outcome': 'FAILED', 'evidence': 'fixture failure'})
    other = create(engine); confirm(engine, other)
    finish(engine, claim(engine, other, 0, 'design'))
    running = claim(engine, other, 0, 'code')
    demo_complete(engine, j, 0)
    assert engine.snapshot(j)['modules'][0]['stages']['design']['attempts'][0]['status'] == 'FAILED'
    with engine.store.connection() as c:
        assert c.execute('SELECT attempt FROM leases').fetchone()[0] == running['attempt']['id']
