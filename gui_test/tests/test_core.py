import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from pydantic import ValidationError
from gui_test.core.models import TestError, Connection, uid
from gui_test.core.results import parse_result, aggregate, module_results
from gui_test.core.discovery import discover, classify
from gui_test.core.store import Store
from gui_test.core.manager import Manager
from gui_test.core.reporting import export
from gui_test.runtime import make_manager
from gui_test.adapters.runner import resolve_argv, UnconfiguredRunner
from gui_test.standalone.server import ProcessLock


@pytest.fixture
def manager(tmp_path):
    return make_manager(tmp_path, 'standalone')


def request(m, **changes):
    c = m.catalog()
    return {'tc_ids': [t['id'] for t in c['tests']], 'source_revision': c['revision'],
            'connection': {'a': m.boards.boards()[0], 'b': m.boards.boards()[1]}, 'speed': 20, **changes}


def start(m, **changes):
    return m.start(uid(), 'owner', request(m, **changes))


def action(m, r, name, data=None, session='owner'):
    return m.act(r['id'], uid(), session, m.get(r['id'])['version'], name, data)


def complete(m, r, states=None):
    states = states or {}
    while True:
        claim = m.claim(r['id'])
        if not claim:
            break
        state = states.get(claim['tc']['id'], 'PASS')
        m.emit(r['id'], claim['attempt']['id'], 'stdout', 'Test Result: ' + state + '\n')
        m.finish(claim, {'exit_code': 0, 'terminated': True})
    return m.get(r['id'])


@pytest.mark.parametrize('stdout,stderr,code,terminated,expected', [
    ('Test Result: PASS\n','',0,True,'PASS'),('Test Result: FAIL\r\n','',0,True,'FAIL'),
    ('random PASS','',0,True,'ERROR'),('Test Result: PASS\nTest Result: PASS','',0,True,'ERROR'),
    ('Test Result: PASS','Test Result: FAIL',0,True,'ERROR'),('', '',0,True,'ERROR'),
    ('Test Result: PASS','',1,True,'ERROR'),('Test Result: PASS','',0,False,'UNKNOWN'),
    ('prefix Test Result: PASS','',0,True,'ERROR'),('', 'Test Result: FAIL',0,True,'FAIL')])
def test_strict_parser(stdout,stderr,code,terminated,expected):
    assert parse_result(stdout,stderr,code,terminated=terminated)[0] == expected


def test_explicit_parser_exception():
    assert parse_result('Test Result: FAIL\nTest Result: FAIL','',2,allowed_codes=[2],allow_repeated=True)[0]=='FAIL'


@pytest.mark.parametrize('states,result', [(['PASS'],'PASS'),(['PASS','FAIL'],'FAIL'),(['FAIL','ERROR'],'INCOMPLETE'),([], 'INCOMPLETE'),(['UNKNOWN'],'INCOMPLETE')])
def test_aggregate(states,result):
    assert aggregate(states)==result


@pytest.mark.parametrize('field,value', [('board_id','demo-board-a'),('host','other-host'),('com','COM3')])
def test_dual_identity_constraints(manager,field,value):
    connection=request(manager)['connection'];connection['b'][field]=value
    with pytest.raises(ValidationError): Connection.model_validate(connection)


@pytest.mark.parametrize('port', ['COM0','COM3;evil','com3','COM3 & whoami','/dev/ttyUSB0'])
def test_unsafe_port_rejected(manager,port):
    connection=request(manager)['connection'];connection['a']['com']=port
    with pytest.raises(ValidationError): Connection.model_validate(connection)


def test_single_dual_argv_slots_are_exact(manager):
    c=request(manager)['connection']
    single={'kind':'Single','path':'folder with spaces/test.py'}
    dual={**single,'kind':'Dual'}
    assert resolve_argv(['python','{tc_path}','--existing-slot','{com_a}'],single,c)==['python','folder with spaces/test.py','--existing-slot','COM3']
    assert resolve_argv(['old-client','{com_b}','{tc_path}','{com_a}'],dual,c)==['old-client','COM4','folder with spaces/test.py','COM3']
    with pytest.raises(TestError):resolve_argv(['old-client','--com={com_a}','{tc_path}'],single,c)
    with pytest.raises(TestError):resolve_argv(['old-client','{com_a}','{tc_path}'],dual,c)
    with pytest.raises(TestError):UnconfiguredRunner().execute()


def test_discovery_conflict_duplicates_and_symlink(tmp_path):
    (tmp_path/'module/DuAL_pair').mkdir(parents=True)
    (tmp_path/'module/DuAL_pair/case.py').write_text('pass')
    (tmp_path/'single.py').write_text('pass')
    catalog=discover(tmp_path,{'module/DuAL_pair/case.py':{'kind':'Single'}})
    dual=next(t for t in catalog['tests'] if 'DuAL_pair' in t['path'])
    assert dual['kind']=='Dual' and dual['disabled_reason']
    assert classify('module/not_dual_file.py')=='Single'
    assert discover(tmp_path,{'single.py':{'id':'same'},'module/DuAL_pair/case.py':{'id':'same'}})['tests'][0]['disabled_reason']=='Duplicate TC identity'
    outside=tmp_path.parent/'external.py';outside.write_text('private')
    try:(tmp_path/'escape.py').symlink_to(outside)
    except OSError: return  # Windows account may not have symlink privilege.
    assert all(t['path']!='escape.py' for t in discover(tmp_path)['tests'])


def test_folder_source_hash_changes(tmp_path):
    file=tmp_path/'tc.py';file.write_text('pass')
    before=discover(tmp_path);file.write_text('print(1)')
    assert discover(tmp_path)['revision']!=before['revision']


def test_atomic_reservation_collision_and_all_or_nothing(manager):
    r=start(manager)
    with pytest.raises(TestError,match='reserved'):start(manager)
    with manager.store.connection() as c:
        assert c.execute('SELECT count(*) FROM runs').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM reservations').fetchone()[0]==4
    action(manager,r,'cancel')
    assert start(manager)['id']!=r['id']


def test_concurrent_start_only_one_wins(manager):
    def attempt(_):
        try:return start(manager)['id']
        except TestError:return None
    with ThreadPoolExecutor(2) as pool: results=list(pool.map(attempt,range(2)))
    assert sum(x is not None for x in results)==1


def test_idempotency_and_version(manager):
    key=uid();req=request(manager)
    r=manager.start(key,'owner',req)
    assert manager.start(key,'owner',req)==r
    with pytest.raises(TestError,match='reused'):manager.start(key,'owner',{**req,'speed':5})
    cmd=uid();first=manager.act(r['id'],cmd,'owner',r['version'],'pause')
    assert manager.act(r['id'],cmd,'owner',r['version'],'pause')==first
    with pytest.raises(TestError,match='State changed'):manager.act(r['id'],uid(),'owner',r['version'],'resume')


def test_fail_continues_and_completion_is_immutable(manager):
    r=start(manager);ids=[t['id'] for t in r['tests']]
    r=complete(manager,r,{ids[1]:'FAIL'})
    assert r['state']=='COMPLETED' and r['overall_result']=='FAIL'
    assert len(r['attempts'])==5 and r['progress']['percent']==100
    with pytest.raises(TestError):action(manager,r,'resume')
    with pytest.raises(TestError):action(manager,r,'demo-inject',{'fault':'fail'})
    copy_before=manager.get(r['id'])
    new=start(manager,parent_run_id=r['id'])
    assert new['parent_run_id']==r['id'] and manager.get(r['id'])==copy_before


def test_error_resume_new_attempt_keeps_prior_pass(manager):
    r=start(manager)
    c=manager.claim(r['id']);manager.emit(r['id'],c['attempt']['id'],'stdout','Test Result: PASS\n');manager.finish(c,{'exit_code':0,'terminated':True})
    c=manager.claim(r['id']);manager.emit(r['id'],c['attempt']['id'],'stderr','port disconnected\n');manager.finish(c,{'exit_code':1,'terminated':True})
    r=manager.get(r['id']);assert r['state']=='PAUSED' and r['progress']['done']==1
    with pytest.raises(TestError):action(manager,r,'resume')
    action(manager,r,'demo-recover');action(manager,r,'resume')
    r=complete(manager,r)
    assert r['overall_result']=='PASS' and len(r['attempts'])==6
    assert r['attempts'][1]['state']=='ERROR' and r['attempts'][2]['ordinal']==2


def test_pause_waits_for_current_tc_retains_reservations(manager):
    r=start(manager);c=manager.claim(r['id']);action(manager,r,'pause')
    assert manager.get(r['id'])['state']=='PAUSE_REQUESTED'
    manager.emit(r['id'],c['attempt']['id'],'stdout','Test Result: PASS');manager.finish(c,{'exit_code':0,'terminated':True})
    assert manager.get(r['id'])['state']=='PAUSED'
    with pytest.raises(TestError):start(manager)
    action(manager,r,'resume');assert complete(manager,r)['overall_result']=='PASS'


@pytest.mark.parametrize('terminated,state',[(True,'TIMEOUT'),(False,'UNKNOWN')])
def test_timeout_termination_evidence(manager,terminated,state):
    r=start(manager);c=manager.claim(r['id']);manager.finish(c,{'exit_code':-1,'terminated':terminated,'forced_state':'TIMEOUT'})
    r=manager.get(r['id']);assert r['attempts'][-1]['state']==state
    with pytest.raises(TestError):start(manager)
    if not terminated:
        with pytest.raises(TestError):action(manager,r,'cancel')
    action(manager,r,'demo-recover');action(manager,r,'resume');assert complete(manager,r)['overall_result']=='PASS'


def test_cancel_waits_for_process_and_blocks_late_finish(manager):
    r=start(manager);c=manager.claim(r['id']);action(manager,r,'cancel')
    with pytest.raises(TestError):start(manager)
    manager.finish(c,{'exit_code':0,'terminated':True});snapshot=manager.get(r['id'])
    assert snapshot['state']=='CANCELLED' and snapshot['overall_result']=='INCOMPLETE'
    assert manager.finish(c,{'exit_code':0,'terminated':True}) is False
    assert manager.get(r['id'])==snapshot
    assert start(manager)['id']!=r['id']


def test_restart_queries_process_preserves_lock_and_history(manager):
    r=start(manager);c=manager.claim(r['id']);manager.emit(r['id'],c['attempt']['id'],'stdout','partial log\n')
    restarted=Manager(Store(manager.store.path))
    restarted.recover()
    r=restarted.get(r['id']);assert r['state']=='PAUSED' and r['attempts'][0]['stdout']=='partial log\n'
    with pytest.raises(TestError):start(restarted)
    action(restarted,r,'resume');assert complete(restarted,r)['overall_result']=='PASS'


def test_unobservable_process_unknown_on_restart(manager):
    r=start(manager);manager.claim(r['id'])
    with manager.store.transaction() as c:
        raw=manager.store.get(c,r['id']);raw['attempts'][0]['process_ref']='unobservable:123';manager.store.save(c,raw,'FIXTURE')
    manager.recover();assert manager.get(r['id'])['state']=='UNKNOWN'
    with pytest.raises(TestError):action(manager,r,'demo-recover')


def test_control_transfer_and_explicit_expiry(manager):
    r=start(manager)
    with pytest.raises(TestError):action(manager,r,'pause',session='observer')
    action(manager,r,'request-control',session='observer')
    with pytest.raises(TestError):action(manager,r,'take-control',session='observer')
    action(manager,r,'grant-control')
    assert manager.get(r['id'])['controller']=='observer'
    with manager.store.transaction() as c:
        r=manager.store.get(c,r['id']);r['controller_seen_at']=(datetime.now(timezone.utc)-timedelta(seconds=120)).isoformat();manager.store.save(c,r,'FIXTURE')
    action(manager,r,'take-control',session='new-owner')
    assert manager.get(r['id'])['controller']=='new-owner'


def test_suite_profile_source_consistency(manager):
    req=request(manager)
    s=manager.save_document('suite','example',{'tc_ids':req['tc_ids']})
    p=manager.save_document('profile','example',{'connection':req['connection']})
    assert p['connection']==req['connection']
    assert manager.preflight({**req,'suite_revision':s['revision']})['ok']
    with pytest.raises(TestError):manager.preflight({**req,'suite_revision':s['revision'],'tc_ids':req['tc_ids'][:-1]})
    with pytest.raises(TestError):manager.preflight({**req,'tc_ids':['missing']})
    with pytest.raises(TestError):manager.preflight({**req,'execution':'hardware'})
    with pytest.raises(TestError):manager.preflight({**req,'source_revision':'changed'})


def test_reports_escaping_and_logs(manager):
    r=start(manager);c=manager.claim(r['id']);manager.emit(r['id'],c['attempt']['id'],'stdout','<script>alert(1)</script> token=private\nTest Result: PASS')
    manager.finish(c,{'terminated':True,'exit_code':0});r=complete(manager,r)
    assert 'private' not in json.dumps(r)
    html,_=export(r,'html');assert b'<script>' not in html and b'&lt;script&gt;' in html
    pdf,_=export(r,'pdf');assert pdf.startswith(b'%PDF')
    archive,_=export(r,'logs');assert archive.startswith(b'PK')
    raw,_=export(r,'json');assert json.loads(raw)['overall_result']=='PASS'
    r['attempts'][0]['reason']='=HYPERLINK("evil")';csv,_=export(r,'csv');assert b"'=HYPERLINK" in csv


def test_log_overflow_never_passes(manager):
    manager.log_limit=40;r=start(manager);c=manager.claim(r['id'])
    manager.emit(r['id'],c['attempt']['id'],'stdout','a'*100)
    manager.emit(r['id'],c['attempt']['id'],'stdout','Test Result: PASS')
    manager.finish(c,{'exit_code':0,'terminated':True})
    assert manager.get(r['id'])['results'][c['tc']['id']]=='ERROR'


def test_backup_restore_schema_and_process_lock(manager,tmp_path):
    r=start(manager);target=tmp_path/'backup.db';manager.store.backup(target)
    assert Store(target).snapshot(r['id'])==manager.store.snapshot(r['id'])
    with ProcessLock(tmp_path/'worker.lock'):
        with pytest.raises(RuntimeError):
            with ProcessLock(tmp_path/'worker.lock'):pass
    with ProcessLock(tmp_path/'worker.lock'):pass


def test_git_discovery_pins_commit_and_never_checks_out(tmp_path):
    import subprocess
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args],stderr=subprocess.DEVNULL).decode().strip()
    git('init','-b','main');git('config','user.name','Fixture');git('config','user.email','fixture@example.invalid')
    (tmp_path/'tc.py').write_text('pass');git('add','.');git('commit','-m','first')
    first=discover(tmp_path,revision='main')
    (tmp_path/'tc.py').write_text('print(2)');git('add','.');git('commit','-m','second')
    assert discover(tmp_path,revision=first['revision'])==first
    assert git('rev-parse','HEAD')!=first['revision']


def test_order_dependency_preflight_and_fail_warning(manager,monkeypatch):
    catalog=manager.catalog();catalog['tests'][1]['after']=[catalog['tests'][0]['id']]
    monkeypatch.setattr(manager,'catalog',lambda branch='demo/main':catalog)
    req=request(manager);req['tc_ids'][:2]=list(reversed(req['tc_ids'][:2]))
    with pytest.raises(TestError,match='predecessor'):manager.preflight(req)
    r=start(manager);c=manager.claim(r['id']);manager.emit(r['id'],c['attempt']['id'],'stdout','Test Result: FAIL');manager.finish(c,{'exit_code':0,'terminated':True})
    next_claim=manager.claim(r['id'])
    assert next_claim and next_claim['attempt']['warnings']


def test_preflight_board_changed_between_tcs(manager,monkeypatch):
    r=start(manager)
    def reject(*args):raise TestError('COM moved; user confirmation required')
    monkeypatch.setattr(manager.boards,'verify',reject)
    assert manager.claim(r['id']) is None
    assert manager.get(r['id'])['state']=='PAUSED'


def test_windows_com_enumeration_uses_local_os(monkeypatch):
    from types import SimpleNamespace
    from gui_test.adapters import windows_ports
    import serial.tools.list_ports
    monkeypatch.setattr(windows_ports.platform,'system',lambda:'Windows')
    monkeypatch.setattr(serial.tools.list_ports,'comports',lambda:[SimpleNamespace(device='COM7',description='Synthetic serial')])
    assert windows_ports.enumerate_ports()=={'status':'ENUMERATED','ports':[{'com':'COM7','description':'Synthetic serial'}]}


def test_single_failed_case_retest_preserves_original(manager):
    r = start(manager)
    tc_id = r['tests'][1]['id']
    original = complete(manager, r, {tc_id: 'FAIL'})
    child = start(manager, tc_ids=[tc_id], parent_run_id=r['id'], suite_revision='')
    child = complete(manager, child)
    assert child['parent_run_id'] == original['id']
    assert list(child['results']) == [tc_id]
    assert child['overall_result'] == 'PASS'
    assert manager.get(r['id'])['attempts'] == original['attempts']
    assert manager.get(r['id'])['results'][tc_id] == 'FAIL'


def test_usage_snapshots_models_unknown_cost_and_replay(manager):
    r = start(manager)
    claim = manager.claim(r['id'])
    aid = claim['attempt']['id']
    rows = [{'provider': 'fixture', 'model': 'model-a', 'input_tokens': 100, 'output_tokens': 20, 'cost_usd': '0.0012'},
            {'provider': 'fixture', 'model': 'model-b', 'input_tokens': 50, 'output_tokens': 10, 'cost_usd': None}]
    assert manager.record_usage(r['id'], aid, 1, rows)
    assert not manager.record_usage(r['id'], aid, 1, rows)
    assert not manager.record_usage(r['id'], aid, 0, rows)
    assert not manager.record_usage(r['id'], aid, 2, [{**rows[0], 'cost_usd': 'NaN'}])
    rows[0]['input_tokens'] = 150
    assert manager.record_usage(r['id'], aid, 3, rows)
    usage = manager.get(r['id'])['progress']['usage']
    assert usage['models'][0]['input_tokens'] == 150
    assert usage['models'][0]['cost_usd'] == '0.0012'
    assert usage['models'][1]['cost_usd'] is None
    manager.emit(r['id'], aid, 'stdout', 'Test Result: PASS\n')
    assert manager.finish(claim, {'exit_code': 0, 'terminated': True, 'usage': rows})
    assert not manager.finish(claim, {'exit_code': 0, 'terminated': True, 'usage': rows})
    assert not manager.record_usage(r['id'], aid, 4, rows)
    complete(manager, r)
    saved = Manager(Store(manager.store.path), 'standalone')
    usage = saved.get(r['id'])['progress']['usage']
    assert usage['status'] == 'partial'
    assert usage['models'][0]['input_tokens'] == 150
    assert usage['cases'][0]['models'][1]['cost_usd'] is None


def test_repetitions_cycles_progress_and_failure_are_preserved(manager):
    ids = request(manager)['tc_ids'][:2]
    r = start(manager, tc_ids=ids, tc_repeats={ids[0]: 2}, cycles=2)
    assert [s['tc_id'] for s in r['plan']] == [ids[0], ids[0], ids[1]] * 2
    assert r['progress']['total'] == 6
    for index in range(6):
        claim = manager.claim(r['id'])
        state = 'FAIL' if index == 0 else 'PASS'
        manager.emit(r['id'], claim['attempt']['id'], 'stdout', 'Test Result: '+state+'\n')
        manager.finish(claim, {'exit_code': 0, 'terminated': True})
        assert manager.get(r['id'])['progress']['done'] == index+1
    final = manager.get(r['id'])
    assert final['overall_result'] == 'FAIL' and final['results'][ids[0]] == 'FAIL'
    assert final['progress']['counts']['FAIL'] == 1 and final['progress']['counts']['PASS'] == 5
    assert [(a['cycle'], a['iteration']) for a in final['attempts']] == [(1,1),(1,2),(1,1),(2,1),(2,2),(2,1)]
    assert Manager(Store(manager.store.path)).get(r['id'])['plan'] == r['plan']
    # Retry of one failed TC is a fresh single execution, not the parent's entire repeat plan.
    child = start(manager, tc_ids=[ids[0]], parent_run_id=r['id'])
    assert len(child['plan']) == 1
    complete(manager, child)
    assert manager.get(r['id'])['overall_result'] == 'FAIL'


def test_repeat_recovery_retries_same_slot_without_double_progress(manager):
    tc_id = request(manager)['tc_ids'][0]
    r = start(manager, tc_ids=[tc_id], tc_repeats={tc_id: 2}, cycles=2)
    claim = manager.claim(r['id'])
    manager.finish(claim, {'exit_code': -1, 'terminated': True, 'forced_state': 'TIMEOUT'})
    assert manager.get(r['id'])['progress']['done'] == 0
    action(manager, r, 'demo-recover');action(manager, r, 'resume')
    final = complete(manager, r)
    assert final['overall_result'] == 'PASS'
    assert len(final['attempts']) == 5
    assert [a['slot_index'] for a in final['attempts']] == [0,0,1,2,3]
    assert final['progress']['done'] == final['progress']['total'] == 4


@pytest.mark.parametrize('count', [0, -1, 101, True, 1.5, '2'])
def test_invalid_repeat_count_rejected(manager, count):
    tc_id = request(manager)['tc_ids'][0]
    with pytest.raises(ValidationError):start(manager, tc_repeats={tc_id: count})
    with pytest.raises(ValidationError):start(manager, cycles=count)


def test_repeat_budget_unknown_id_and_suite_snapshot(manager):
    ids = request(manager)['tc_ids']
    with pytest.raises(ValidationError):start(manager, tc_repeats={'unknown': 2})
    with pytest.raises(ValidationError):start(manager, tc_repeats={i: 100 for i in ids}, cycles=100)
    suite = manager.save_document('suite', 'repeated', {'tc_ids': ids, 'tc_repeats': {ids[0]: 2}, 'cycles': 3})
    assert suite['cycles'] == 3 and suite['tc_repeats'][ids[0]] == 2
    with pytest.raises(TestError):start(manager, suite_revision=suite['revision'])
    r = start(manager, tc_repeats=suite['tc_repeats'], cycles=3, suite_revision=suite['revision'])
    assert r['progress']['total'] == 18
    action(manager, r, 'cancel')


def test_repeat_restart_tracks_slot_and_cancel_stays_incomplete(manager):
    tc_id = request(manager)['tc_ids'][0]
    r = start(manager, tc_ids=[tc_id], cycles=2)
    manager.claim(r['id'])
    manager.recover()
    recovered = manager.get(r['id'])
    assert recovered['slot_results']['0'] == 'ERROR'
    assert recovered['progress']['total'] == 2
    action(manager, r, 'cancel')
    assert manager.get(r['id'])['overall_result'] == 'INCOMPLETE'


def test_actual_target_names_single_dual_and_local_are_snapshotted(manager):
    catalog = manager.catalog()['tests']
    single = next(t['id'] for t in catalog if t['kind'] == 'Single')
    dual = next(t['id'] for t in catalog if t['kind'] == 'Dual')
    r = start(manager, tc_ids=[single, dual])
    first = manager.claim(r['id'])
    assert manager.record_target(r['id'], first['attempt']['id'], {'kind': 'local'})
    manager.emit(r['id'], first['attempt']['id'], 'stdout', 'Test Result: PASS\n')
    manager.finish(first, {'exit_code': 0, 'terminated': True})
    claim = manager.claim(r['id'])
    boards = [{'role': role, 'board_name': 'BCM fixture '+role.upper(), **r['connection_snapshot'][role]} for role in ('a','b')]
    wrong = copy.deepcopy(boards);wrong[0]['board_id'] = 'different-board'
    assert not manager.record_target(r['id'], claim['attempt']['id'], {'kind': 'board', 'boards': wrong})
    assert manager.record_target(r['id'], claim['attempt']['id'], {'kind': 'board', 'boards': boards})
    assert not manager.record_target(r['id'], claim['attempt']['id'], {'kind': 'local'})
    manager.emit(r['id'], claim['attempt']['id'], 'stdout', 'Test Result: PASS\n')
    manager.finish(claim, {'exit_code': 0, 'terminated': True})
    saved = Manager(Store(manager.store.path)).get(r['id'])
    assert saved['execution_targets']['labels'] == ['local', 'A: BCM fixture A / B: BCM fixture B']
    assert saved['targets_by_tc'][single]['labels'] == ['local']
    assert saved['targets_by_tc'][dual]['labels'] == ['A: BCM fixture A / B: BCM fixture B']
    assert not manager.record_target(r['id'], claim['attempt']['id'], {'kind': 'local'})


def test_missing_target_is_not_guessed_from_selected_board(manager):
    r = complete(manager, start(manager))
    assert r['execution_targets'] == {'labels': [], 'incomplete': True}
    assert all(value['incomplete'] for value in r['targets_by_tc'].values())
