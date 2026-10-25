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
