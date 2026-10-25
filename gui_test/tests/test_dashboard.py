import copy
import pytest
from backend.domain.policy import uid, Conflict
from gui_test.runtime import make_manager
from gui_test.core.models import TestError
from .test_core import request, start, complete, action


@pytest.fixture
def linked(tmp_path):
    manager=make_manager(tmp_path,'dashboard')
    job=manager.dashboard.create(uid())
    return manager,job


def test_no_partial_sync_and_module_independent_results(linked):
    m,j=linked;r=start(m,job_id=j['id'])
    claim=m.claim(r['id']);m.emit(r['id'],claim['attempt']['id'],'stdout','Test Result: PASS');m.finish(claim,{'terminated':True,'exit_code':0})
    before=m.dashboard.engine.store.snapshot(j['id']);m.sync_one()
    assert m.dashboard.engine.store.snapshot(j['id'])==before
    r=complete(m,r,{'network/03_link.py':'FAIL'})
    assert r['overall_result']=='FAIL'
    m.sync_one();job=m.dashboard.engine.snapshot(j['id'])
    assert job['modules'][0]['stages']['device_test']['status']=='SUCCEEDED'
    assert job['modules'][1]['stages']['device_test']['status']=='FAILED'
    assert m.get(r['id'])['sync']['status']=='SUCCEEDED'


def test_unmapped_fail_does_not_taint_modules(linked):
    m,j=linked;r=complete(m,start(m,job_id=j['id']),{'extra/05_observation.py':'FAIL'})
    m.sync_one();assert r['overall_result']=='FAIL'
    assert all(x['stages']['device_test']['status']=='SUCCEEDED' for x in m.dashboard.engine.snapshot(j['id'])['modules'])


def test_unmapped_error_blocks_every_module(linked):
    m,j=linked;r=complete(m,start(m,job_id=j['id']),{'extra/05_observation.py':'ERROR'})
    assert r['state']=='PAUSED'
    r=action(m,r,'cancel');m.sync_one()
    assert r['overall_result']=='INCOMPLETE' and r['sync']['status']=='BLOCKED'
    assert all(x['stages']['device_test']['status']=='WAITING_INPUT' for x in m.dashboard.engine.snapshot(j['id'])['modules'])


def test_baseline_change_stops_next_tc(linked):
    m,j=linked;r=start(m,job_id=j['id']);claim=m.claim(r['id'])
    e=m.dashboard.engine;e.act(j['id'],uid(),e.snapshot(j['id'])['version'],'invalidate',{'source_revision':'changed','reason':'fixture'})
    m.emit(r['id'],claim['attempt']['id'],'stdout','Test Result: PASS');m.finish(claim,{'terminated':True,'exit_code':0})
    assert m.claim(r['id']) is None
    r=m.get(r['id']);assert r['state']=='PAUSED' and r['baseline_changed']
    with pytest.raises(TestError):action(m,r,'resume')


def test_stale_at_final_sync_blocked(linked):
    m,j=linked;r=complete(m,start(m,job_id=j['id']));e=m.dashboard.engine
    e.act(j['id'],uid(),e.snapshot(j['id'])['version'],'invalidate',{'source_revision':'changed','reason':'fixture'})
    m.sync_one();assert m.get(r['id'])['sync']['status']=='BLOCKED'
    assert m.get(r['id'])['overall_result']=='PASS'


@pytest.mark.parametrize('scenario',['sync-failure','sync-lost-response'])
def test_outbox_retry_and_lost_response_idempotent(linked,scenario):
    m,j=linked;r=complete(m,start(m,job_id=j['id'],scenario=scenario))
    m.sync_one();assert m.get(r['id'])['sync']['status']=='PENDING'
    m.sync_one();assert m.get(r['id'])['sync']['status']=='SUCCEEDED'
    for module in m.dashboard.engine.snapshot(j['id'])['modules']:
        assert sum(a['tool']=='gui-test' for a in module['stages']['device_test']['attempts'])==1


def test_sync_limited_retry_and_manual_retry(linked,monkeypatch):
    m,j=linked;r=complete(m,start(m,job_id=j['id']));original=m.dashboard.submit
    def fail(_):raise TimeoutError('temporary unavailable')
    monkeypatch.setattr(m.dashboard,'submit',fail)
    for _ in range(3):m.sync_one()
    assert m.get(r['id'])['sync']['status']=='FAILED' and m.get(r['id'])['overall_result']=='PASS'
    monkeypatch.setattr(m.dashboard,'submit',original)
    action(m,r,'retry-sync');m.sync_one();assert m.get(r['id'])['sync']['status']=='SUCCEEDED'


def test_manual_history_completed_job_reopens_requires_approval(linked):
    m,j=linked;e=m.dashboard.engine
    for module in e.snapshot(j['id'])['modules']:
        stage=module['stages']['device_test']
        e.act(j['id'],uid(),e.snapshot(j['id'])['version'],'manual-test',{'module_id':module['id'],'attempt_id':stage['attempts'][-1]['id'],'cases':{'boot':'PASS','functional':'PASS'}})
    with e.store.transaction() as c:
        job=e.store.get(c,j['id']);job['integration']={'status':'SUCCEEDED','evidence':'fixture'};job['final_review']={'reviewer':'synthetic-reviewer','evidence':'fixture'};e.store.save(c,job,'FIXTURE_COMPLETED')
    originals=[copy.deepcopy(module['stages']['device_test']['attempts']) for module in e.snapshot(j['id'])['modules']]
    r=complete(m,start(m,job_id=j['id']),{'boot/01_boot.py':'FAIL'});m.sync_one();job=e.snapshot(j['id'])
    assert job['state']!='COMPLETED' and job['final_review'] is None and len(job['final_review_history'])==1
    assert job['gui_revalidation']['status']=='AWAITING_APPROVAL' and job['paused']
    for module,old in zip(job['modules'],originals):assert module['stages']['device_test']['attempts'][:len(old)]==old
    with pytest.raises(Conflict):e.act(j['id'],uid(),job['version'],'resume',{})
    e.act(j['id'],uid(),job['version'],'approve-gui-revalidation',{'run_id':r['id']})
    assert e.snapshot(j['id'])['gui_revalidation']['status']=='APPROVED'


def test_demo_cannot_mutate_operational_job_even_forged_link(linked):
    m,j=linked;r=complete(m,start(m,job_id=j['id']));e=m.dashboard.engine
    with e.store.transaction() as c:
        job=e.store.get(c,j['id']);job['execution']='bridge';job['session']['status']='READY';e.store.save(c,job,'FIXTURE_LIVE')
    r['link']['baseline']['job_version']=e.snapshot(j['id'])['version']
    before=e.store.snapshot(j['id'])
    with pytest.raises(TestError,match='Mock'):e.automatic_device_test(r)
    assert e.store.snapshot(j['id'])==before


def test_evidence_reparsed_and_missing_tc_rejected(linked):
    m,j=linked;r=complete(m,start(m,job_id=j['id']))
    r['attempts'][0]['stdout']='arbitrary PASS'
    with pytest.raises(TestError):m.dashboard.submit(r)
    r=m.get(r['id']);del r['results']['extra/05_observation.py']
    with pytest.raises(TestError):m.dashboard.submit(r)


def test_same_result_receipt_survives_manager_recreation(linked):
    m,j=linked;r=complete(m,start(m,job_id=j['id']));first=m.dashboard.submit(r)
    assert m.dashboard.submit(r)==first
