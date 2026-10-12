"""Offline CLI simulators: no vendor model, login, BSP or Jira calls."""
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from backend.adapters.bridge import Bridge
from backend.adapters.native import (Native, REQUIRED_FLAGS, discover, instruction_bundle, normalize,
                                     resolve_tools, workspace_revision)
from backend.adapters.process import run_process
from backend.domain.engine import Engine
from backend.domain.policy import Conflict, uid, implementation_tool
from backend.settings import Profile, Settings, bridge_defaults, prepare_job_profile, validate_live
from backend.storage.store import Store
from backend.worker.main import Worker


@pytest.fixture
def native(tmp_path, monkeypatch):
    workspace = tmp_path / 'work with spaces'; workspace.mkdir()
    (workspace / 'driver.c').write_text('old code\n')
    source = tmp_path / 'sources'; source.mkdir()
    cli = tmp_path / 'bin'; cli.mkdir()
    flags = ' '.join(set(flag for flags in REQUIRED_FLAGS.values() for flag in flags))
    code = r'''
import json,sys,os
from pathlib import Path
args=sys.argv[1:]; tool=Path(sys.argv[0]).name
if '--version' in args: print('fixture 1.2.3'); sys.exit()
if '--help' in args: print(FLAGS); sys.exit()
if args[:2]==['auth','status']: print(json.dumps({'loggedIn':True})); sys.exit()
if args[:2]==['login','status']: print('Logged in'); sys.exit()
request=json.loads(sys.stdin.read().split('\n',1)[1])
p=request['request']
Path('.bsp-dashboard').mkdir(exist_ok=True)
Path('.bsp-dashboard/calls.jsonl').open('a').write(json.dumps({'tool':tool,'args':args,'request':request,'opencode_config':os.environ.get('OPENCODE_CONFIG_CONTENT')})+'\n')
r={'outcome':'SUCCEEDED','evidence':'fixture evidence','source_revision':p.get('source_revision',''), 'error_class':'','cause_key':''}
for key in ('attempt_id','fingerprint'):
 if key in p:r[key]=p[key]
sid=args[args.index('--session-id')+1] if '--session-id' in args else 'b027c9f4-f1c5-49c4-8155-1a3986e5d620'
if tool=='claude': print(json.dumps({'subtype':'success','is_error':False,'session_id':sid,'structured_output':r}))
if tool=='codex':
 for event in [{'type':'thread.started','thread_id':'codex-session'}, {'type':'item.completed','item':{'type':'agent_message','text':json.dumps(r)}},{'type':'turn.completed'}]:print(json.dumps(event))
if tool=='opencode':
 for event in [{'type':'text','sessionID':'opencode-session','part':{'text':json.dumps(r)}},{'type':'step_finish','sessionID':'opencode-session','part':{'reason':'stop'}}]:print(json.dumps(event))
'''.replace('FLAGS',repr(flags))
    for tool in ('claude','opencode','codex'):
        path=cli/tool; path.write_text('#!'+sys.executable+'\n'+code); path.chmod(0o700)
    monkeypatch.setenv('PATH', str(cli)+os.pathsep+'/usr/bin:/bin')
    p = Profile(execution='bridge', workspace=str(workspace), source_revision='a'*40,
                old_base=str(source),vendor_tree=str(source),new_base=str(source),
                build_command='mkdir -p out; printf image > "$BSP_ARTIFACT_PATH"', artifact_path='out/{attempt_id}.img',
                verification_command='test -d out', integration_command='test -f driver.c').model_dump()
    p['agents'], p['tool_checks'] = resolve_tools(p)
    return p


def payload(stage='analysis'):
    return {'schema_version':1,'job_id':'job','module_id':'module','stage':stage,'attempt_id':uid(),
            'session_id':uid(),'fingerprint':'input','source_revision':'a'*40,'model_policy':'configured',
            'module':{'stages':{'analysis':{'attempts':[{'token':'PRIVATE_TOKEN','owner':'private'}]}}}}


def test_t96_native_default_and_legacy_json_preserved():
    assert Profile().runner=='native'
    p=Profile(agents={'claude':['/custom/wrapper']},build_argv=['/custom/build'])
    assert p.runner=='bridge' and p.agents['claude']==['/custom/wrapper']
    assert Profile(runner='native',agents={'claude':['/obsolete']}).runner=='native'


def test_t96_settings_migrates_only_uninstalled_generated_paths(tmp_path):
    store=Store(tmp_path/'db'); settings=Settings(store)
    workspace=str(tmp_path/'work')
    legacy=Profile(workspace=workspace, runner='bridge', **bridge_defaults(workspace)).model_dump()
    legacy.pop('runner')
    def rawsave(data):
        with store.transaction() as c:c.execute('UPDATE config SET data=?', (json.dumps(data),))
    rawsave(legacy)
    assert settings.get()['profile']['runner']=='native'
    wrapper=Path(legacy['agents']['claude'][0]); wrapper.parent.mkdir(parents=True);wrapper.write_text('installed')
    assert settings.get()['profile']['runner']=='bridge'
    legacy['agents']['claude']=['/custom/script'];rawsave(legacy)
    assert settings.get()['profile']['runner']=='bridge'


def test_t97_probe_is_read_only_and_missing_tools_fallback(native):
    checks=discover(native)
    assert all(x['status']=='CLI_READY' and x['version']=='1.2.3' for x in checks)
    assert checks[1]['auth']=='UNVERIFIED'
    assert not (Path(native['workspace'])/'.bsp-dashboard/calls.jsonl').exists()
    Path(native['agents']['opencode'][0]).unlink()
    Path(native['agents']['codex'][0]).unlink()
    agents,_=resolve_tools(native)
    assert agents['opencode']==[] and agents['codex']==[]
    assert implementation_tool([], {key:bool(v) for key,v in agents.items()})[0]=='claude'


@pytest.mark.parametrize('case',['login','unsupported','bad_override'])
def test_t97_failure_is_not_silent_fallback(native,case):
    path=Path(native['agents']['claude'][0])
    if case=='login':path.write_text(path.read_text().replace("'loggedIn':True","'loggedIn':False"))
    if case=='unsupported':path.write_text(path.read_text().replace('--json-schema','--old-schema'))
    if case=='bad_override':native['tool_paths']['claude']='/missing/tool'
    with pytest.raises(Conflict):resolve_tools(native)
    assert not (Path(native['workspace'])/'.bsp-dashboard/calls.jsonl').exists()


def test_t97_disabled_optional_overrides_explicit_path(native):
    native['tool_paths']['codex']='/missing';native['disabled_tools']=['codex']
    assert resolve_tools(native)[0]['codex']==[]


@pytest.mark.parametrize('tool,stage',[('claude','analysis'),('claude','code'),('codex','review'),('opencode','code')])
def test_t98_native_exec_in_workdir_no_bridge_and_correlated_result(native,tool,stage):
    request=payload(stage)
    result=Native().invoke(native,tool,request)
    assert result['outcome']=='SUCCEEDED',result
    assert result['attempt_id']==request['attempt_id'] and result['external_session_id']
    calls=[json.loads(s) for s in (Path(native['workspace'])/'.bsp-dashboard/calls.jsonl').read_text().splitlines()]
    call=calls[-1]
    assert 'PRIVATE_TOKEN' not in json.dumps(call)
    assert not (Path(native['workspace'])/'.bsp-dashboard/bridges').exists()
    assert '--last' not in call['args'] and '--continue' not in call['args']
    if tool=='claude':
        assert '--permission-mode' in call['args'] and 'dontAsk' in call['args']
        assert 'bypassPermissions' not in call['args']
        if stage=='analysis':assert call['args'][call['args'].index('--tools')+1]=='Read,Glob,Grep'
    if tool=='codex':assert call['args'][call['args'].index('--sandbox')+1]=='read-only'
    if tool=='opencode':
        config=json.loads(call['opencode_config']);assert config['permission']['*']=='deny'
        assert 'bash' not in config['permission']
    if stage=='code':assert result['revision_kind']=='workspace-content-sha256' and len(result['source_revision'])==64


def test_t98_opus_only_on_implementation_and_explicit_session(native):
    request=payload('code')|{'model_policy':'opus'}
    assert Native().invoke(native,'claude',request)['outcome']=='SUCCEEDED'
    call=json.loads((Path(native['workspace'])/'.bsp-dashboard/calls.jsonl').read_text().splitlines()[-1])
    assert call['args'][call['args'].index('--model')+1]=='opus'
    assert call['args'][call['args'].index('--session-id')+1].replace('-','')==request['session_id']


@pytest.mark.parametrize('case',['wrong_id','plain','exit','permission','missing_session','missing_evidence'])
def test_t98_bad_cli_result_never_succeeds(native,case):
    cli=Path(native['agents']['claude'][0]);script=cli.read_text()
    if case=='wrong_id':script=script.replace('r[key]=p[key]',"r[key]='wrong'")
    if case=='plain':script=script.replace("if tool=='claude': print", "if tool=='claude': print('not json'); print")
    if case=='exit':script=script.replace("request=json.loads", "sys.exit(1)\nrequest=json.loads")
    if case=='permission':script=script.replace("'subtype':'success'", "'permission_denials':[{'tool':'Edit'}],'subtype':'success'")
    if case=='missing_session':script=script.replace("'session_id':sid,",'')
    if case=='missing_evidence':script=script.replace("'fixture evidence'","''")
    cli.write_text(script)
    r=Native().invoke(native,'claude',payload())
    assert r['outcome']=='FAILED' and r['error_class'] in {'CONTRACT','ENVIRONMENT'}


def test_t98_instruction_mapping_and_traversal(native,tmp_path):
    root=tmp_path/'agent project';root.mkdir();(root/'roles').mkdir()
    (root/'CLAUDE.md').write_text('Common instructions')
    (root/'roles/custom.md').write_text('Custom module role')
    native.update(agent_instructions=str(root),role_instructions={'analysis':'roles/custom.md'})
    original=(root/'CLAUDE.md').read_bytes()
    assert len(instruction_bundle(native,'analysis'))==2
    assert Native().invoke(native,'claude',payload())['outcome']=='SUCCEEDED'
    assert (root/'CLAUDE.md').read_bytes()==original
    native['role_instructions']['analysis']='../escape.md'
    with pytest.raises(ValueError):instruction_bundle(native,'analysis')
    with pytest.raises(Conflict):validate_live(native)


def test_t99_plain_build_and_artifact_import(native,tmp_path):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    request=payload('build')
    result=Native().command(native,request)
    assert result['outcome']=='SUCCEEDED',result
    assert result['artifact']['sha256']
    claim={'job':{'id':'job','profile':native,'source_revision':'a'*40}}
    worker=Worker(engine)
    imported=worker.import_artifact(claim,result)
    assert (engine.artifacts/'job'/imported['artifact']['id']).read_bytes()==b'image'
    worker.pool.shutdown()


@pytest.mark.parametrize('case',['missing','stale','outside','symlink','exit','timeout'])
def test_t99_invalid_build_artifacts_and_failures(native,tmp_path,case):
    if case=='missing':native['build_command']='true'
    if case=='stale':
        native['artifact_path']='image.bin'; (Path(native['workspace'])/'image.bin').write_bytes(b'old');native['build_command']='true'
    if case=='outside':native['artifact_path']='../image.bin'
    if case=='symlink':
        (Path(native['workspace'])/'out').symlink_to(tmp_path,target_is_directory=True)
    if case=='exit':native['build_command']='exit 7'
    if case=='timeout':native['build_command']='sleep 10';native['timeout_seconds']=.05
    assert Native().command(native,payload('build'))['outcome']=='FAILED'


def test_t99_initialization_env_and_no_agent_shell_interpolation(native):
    root=Path(native['workspace']);script=root/'env with spaces.sh';script.write_text('export BOARD=fixture\n')
    native.update(build_env_script=str(script),verification_command='test "$BOARD" = fixture')
    assert Native().command(native,payload('verification'))['outcome']=='SUCCEEDED'
    request=payload('integration')|{'module_id':'$(touch INJECTED)'}
    native['integration_command']='test "$BSP_MODULE_ID" = \'$(touch INJECTED)\''
    assert Native().command(native,request)['outcome']=='SUCCEEDED'
    assert not (root/'INJECTED').exists()


def test_t100_new_job_freezes_resolved_paths(native,tmp_path,monkeypatch):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    original=deepcopy(native)
    job_id=engine.create('once',native,'native test','linux')['job_id']
    job=engine.snapshot(job_id)
    assert job['profile']['agents']['claude']==native['agents']['claude']
    monkeypatch.setenv('PATH','/nowhere')
    assert engine.create('once',native,'native test','linux')['job_id']==job_id
    assert engine.snapshot(job_id)['profile']==job['profile']
    assert native==original


def test_t100_unknown_coordinator_never_restarts(native,tmp_path,monkeypatch):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    job_id=engine.create('start',native,'test','linux')['job_id']
    with engine.store.transaction() as c:
        job=engine.store.get(c,job_id);job['session']['status']='READY';engine.store.save(c,job,'FIXTURE')
    engine.recover()
    worker=Worker(engine)
    monkeypatch.setattr(Bridge,'invoke',lambda *a,**k:pytest.fail('UNKNOWN must not invoke'))
    worker.initialize_session(engine.snapshot(job_id))
    assert engine.snapshot(job_id)['session']['status']=='NEEDS_RECONCILIATION'
    with pytest.raises(Conflict):engine.act(job_id,uid(),engine.snapshot(job_id)['version'],'retry-session',{})
    worker.pool.shutdown()


def test_t100_failed_session_retry_preserves_evidence(native,tmp_path):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    job_id=engine.create('start',native,'test','linux')['job_id']
    with engine.store.transaction() as c:
        job=engine.store.get(c,job_id);job['session'].update(status='FAILED',evidence='auth error');engine.store.save(c,job,'FIXTURE')
    engine.act(job_id,uid(),engine.snapshot(job_id)['version'],'retry-session',{})
    session=engine.snapshot(job_id)['session']
    assert session['status']=='NOT_CONNECTED' and session['history'][0]['evidence']=='auth error'


def test_t100_workspace_digest_detects_content(native):
    before=workspace_revision(native)
    (Path(native['workspace'])/'driver.c').write_text('new code')
    assert workspace_revision(native)!=before


def test_t100_process_timeout_and_output_bound(tmp_path):
    r=run_process([sys.executable,'-c','import time; time.sleep(10)'],cwd=str(tmp_path),timeout=.05)
    assert '시간 초과' in r.error
    r=run_process([sys.executable,'-c','print("x"*100000)'],cwd=str(tmp_path),timeout=3,limit=100)
    assert '크기 제한' in r.error


def test_t100_worker_native_pipeline_retains_gates_and_cross_review(native,tmp_path):
    native['modules']=[{'name':'Boot','group':'boot'},{'name':'Ethernet','group':'main'}]
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    job_id=engine.create('start',native,'fixture','linux')['job_id']
    worker=Worker(engine)
    worker.initialize_session(engine.snapshot(job_id))
    assert engine.snapshot(job_id)['session']['status']=='READY'
    def execute(module_id,stage):
        claim=engine.claim(job_id,module_id,stage,'fixture')
        assert claim is not None
        result=worker.execute(claim)
        assert result['outcome']=='SUCCEEDED',result
        assert engine.finish(job_id,module_id,stage,claim['attempt']['id'],claim['attempt']['token'],result)
        assert engine.snapshot(job_id)['modules'][0 if module_id==boot else 1]['stages'][stage]['status']=='SUCCEEDED'
        return result
    boot,main=[m['id'] for m in engine.snapshot(job_id)['modules']]
    execute(main,'analysis');execute(boot,'analysis')
    assert engine.claim(job_id,boot,'design','fixture') is None
    engine.act(job_id,uid(),engine.snapshot(job_id)['version'],'confirm',{'plan_version':1})
    assert engine.claim(job_id,main,'design','fixture') is None
    for stage in ('design','code','build','verification'):execute(boot,stage)
    assert engine.claim(job_id,main,'design','fixture') is None
    assert engine.snapshot(job_id)['modules'][0]['stages']['code']['result']['review']['tool']=='claude'
    assert not engine.snapshot(job_id)['final_review']
    worker.pool.shutdown()


def test_t100_claude_writer_uses_codex_review_separate_session(native,tmp_path):
    native['disabled_tools']=['opencode'];native['agents'],_=resolve_tools(native)
    request=payload('code')
    claim={'job':{'id':'job','profile':native,'source_revision':'a'*40},
           'module':{'id':'module','stages':{},'name':'Boot'},'stage':'code',
           'attempt':{'id':request['attempt_id'],'session_id':request['session_id'],
                      'fingerprint':request['fingerprint'],'tool':'claude','model':'opus'}}
    result=Bridge().execute(claim)
    assert result['outcome']=='SUCCEEDED' and result['review']['outcome']=='PASS',result
    assert result['review']['tool']=='codex' and result['review']['session_id']!=request['session_id']


def test_t100_native_verification_shares_writer_lock(native,tmp_path):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    job_id=engine.create('start',native,'test','linux')['job_id']
    with engine.store.transaction() as c:
        job=engine.store.get(c,job_id);job['session']['status']='READY';job['confirmed_plan']=1
        module=job['modules'][0]
        for stage in ('analysis','design','code','build'):
            module['stages'][stage].update(status='SUCCEEDED',validity='CURRENT')
        engine.store.save(c,job,'FIXTURE')
    module_id=engine.snapshot(job_id)['modules'][0]['id']
    verification=engine.claim(job_id,module_id,'verification','fixture')
    assert verification
    with engine.store.connection() as c:
        assert c.execute('SELECT 1 FROM leases WHERE attempt=?',(verification['attempt']['id'],)).fetchone()


def test_t100_job_freezes_role_instruction_contents(native):
    root=Path(native['workspace']);(root/'CLAUDE.md').write_text('original role')
    prepared=prepare_job_profile(native)
    (root/'CLAUDE.md').write_text('changed role')
    assert Native().invoke(prepared,'claude',payload())['outcome']=='SUCCEEDED'
    call=json.loads((root/'.bsp-dashboard/calls.jsonl').read_text().splitlines()[-1])
    assert call['request']['role_instructions'][0]['text']=='original role'


def test_t98_runtime_environment_failure_does_not_count_as_fix(native):
    cli=Path(native['agents']['opencode'][0])
    cli.write_text('#!'+sys.executable+'\nraise SystemExit(2)\n')
    result=Native().invoke(native,'opencode',payload('code'))
    attempts=[{'status':'FAILED',**result} for _ in range(3)]
    assert result['error_class']=='ENVIRONMENT'
    assert implementation_tool(attempts,{'opencode':True,'claude':True})[0]=='opencode'


@pytest.mark.parametrize('tool,raw',[
    ('codex',b'{"type":"thread.started","thread_id":"x"}\n{"type":"turn.failed"}'),
    ('opencode',b'{"type":"step_finish","sessionID":"x","part":{"reason":"tool-calls"}}'),
    ('opencode',b'{"type":"text","sessionID":"x","part":{"text":"done"}}'),
    ('claude',b'{"subtype":"success","session_id":"x","result":"done"}'),
])
def test_t98_incomplete_events_and_unstructured_prose_rejected(tool,raw):
    with pytest.raises(ValueError):normalize(tool,raw)


def test_t100_completed_process_is_not_signalled(tmp_path,monkeypatch):
    import backend.adapters.process as process
    monkeypatch.setattr(process.os,'killpg',lambda *args:pytest.fail('Do not signal a completed process group'))
    assert run_process([sys.executable,'-c','print("ok")'],cwd=str(tmp_path),timeout=3).code==0


def test_t100_kill_permission_failure_reports_unknown(tmp_path,monkeypatch):
    import backend.adapters.process as process
    def denied(*args):raise PermissionError('fixture denial')
    monkeypatch.setattr(process.os,'killpg',denied)
    result=run_process([sys.executable,'-c','import time; time.sleep(30)'],cwd=str(tmp_path),timeout=.1)
    assert result.unknown and result.error


def test_t100_unknown_result_retains_lease_and_blocks_retry(native,tmp_path):
    engine=Engine(Store(tmp_path/'db'),tmp_path/'artifacts')
    job_id=engine.create('start',native,'test','linux')['job_id']
    with engine.store.transaction() as c:
        job=engine.store.get(c,job_id);job['session']['status']='READY';job['confirmed_plan']=1
        for stage in ('analysis','design'):
            job['modules'][0]['stages'][stage].update(status='SUCCEEDED',validity='CURRENT')
        engine.store.save(c,job,'FIXTURE')
    mid=engine.snapshot(job_id)['modules'][0]['id'];claim=engine.claim(job_id,mid,'code','fixture');a=claim['attempt']
    assert engine.finish(job_id,mid,'code',a['id'],a['token'],{'outcome':'UNKNOWN','evidence':'termination unconfirmed'})
    with engine.store.connection() as c:assert c.execute('SELECT 1 FROM leases WHERE attempt=?',(a['id'],)).fetchone()
    with pytest.raises(Conflict):engine.act(job_id,uid(),engine.snapshot(job_id)['version'],'retry',{'module_id':mid,'stage':'code','previous_attempt_id':a['id']})
