"""Install/reuse and supervise the complete monitor independently of plugin windows.

The plugin invokes this public command; runtime and releases live outside its source.
No model, board or test is started by installation or health checks.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

from delivery import ROOT, MANIFEST, export, verify


def atomic(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,indent=2)+'\n');os.replace(temporary,path)


@contextmanager
def lock(path):
    import fcntl
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+') as handle:
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Agent Monitor 작업이 이미 진행 중입니다.') from None
        yield


def read(path):
    try: return json.loads(Path(path).read_text())
    except FileNotFoundError: return None


def runtime_path(home):
    home = Path(home).resolve()
    saved = read(home / 'runtime-location.json')
    if saved is None:
        return home / 'runtime'
    if not isinstance(saved, dict) or not isinstance(saved.get('path'), str) or not Path(saved['path']).is_absolute():
        raise ValueError('Invalid saved runtime location')
    return Path(saved['path']).resolve()


def bind_runtime(home, requested=None):
    """A managed installation keeps one runtime, including across source releases."""
    home = Path(home).resolve()
    if requested is not None and not Path(requested).is_absolute():
        raise ValueError('runtime 경로는 절대 경로여야 합니다.')
    target = Path(requested).resolve() if requested is not None else runtime_path(home)
    if target.is_relative_to(home/'releases') or (target.is_relative_to(home) and target.relative_to(home).parts and target.relative_to(home).parts[0].startswith('.install-')):
        raise ValueError('runtime은 release/staging 폴더와 분리해야 합니다.')
    if home.is_relative_to(target):
        raise ValueError('runtime은 설치 home 자체나 그 상위 폴더일 수 없습니다.')
    try:
        with lock(home / 'service.lock'):
            existing = runtime_path(home)
            if (home / 'runtime-location.json').exists() or (home / 'current.json').exists() or existing.exists():
                if existing != target:
                    raise ValueError('기존 runtime 경로와 다릅니다. 기존 경로를 사용하거나 별도 --home을 지정하세요.')
            atomic(home / 'runtime-location.json', {'path': str(target)})
    except RuntimeError:
        if target != runtime_path(home):
            raise ValueError('실행 중인 서비스의 runtime은 변경할 수 없습니다.') from None
    return target


def health(port):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        req=urllib.request.Request(f'http://127.0.0.1:{port}/api/v1/health',headers={'X-Bsp-Service':'plugin'})
        with opener.open(req,timeout=2) as response: return json.load(response)
    except (OSError,ValueError,urllib.error.URLError): return None


def environment_python(release): return Path(release)/'.venv/bin/python'


def valid_environment(release):
    python=environment_python(release)
    if not python.is_file(): return False
    check="import sys,fastapi,uvicorn,httpx,pydantic; from importlib.metadata import version; from pathlib import Path; from backend.api.main import create_app; assert sys.version_info>=(3,11); lines=Path('requirements.lock').read_text().splitlines(); assert all(version(x.split('==')[0])==x.split('==')[1] for x in lines if '==' in x and not x.startswith('#'))"
    return subprocess.run([str(python),'-c',check],cwd=release,stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0


def prepare(source,home,python=None,include_ui=True):
    home=Path(home).resolve();source=Path(source).resolve();home.mkdir(parents=True,exist_ok=True)
    if os.name=='nt': raise RuntimeError('Agent Monitor 서버는 Linux에서 실행합니다. Windows에서는 board-connector.cmd를 사용하세요.')
    with lock(home/'install.lock'):
        staging=Path(tempfile.mkdtemp(prefix='.install-',dir=home))
        atomic(staging/'INSTALL_STAGE.json',{'format':'agent-monitor-install-stage-v1','path':str(staging)})
        try:
            manifest=export(source,staging/'source',include_ui)
            verify(staging/'source')
            target=home/'releases'/manifest['release']
            if target.exists() and valid_environment(target):
                verify(target)
                applied=activate(home,manifest['release'],target)
                return {'release':manifest['release'],'path':str(target),'state':'REUSED' if applied else 'UPDATE_PENDING'}
            if target.exists():
                # Never delete/repair an environment that may be in use.
                target=target.with_name(target.name+'-'+uuid.uuid4().hex[:8])
            target.parent.mkdir(parents=True,exist_ok=True)
            os.replace(staging/'source',target)
            selected=python or shutil.which('python3.13') or sys.executable
            subprocess.run([selected,'-m','venv',str(target/'.venv')],check=True)
            with (home/'install.log').open('ab') as log:
                subprocess.run([str(environment_python(target)),'-m','pip','install','-r',str(target/'requirements.lock')],
                               check=True,cwd=target,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
            if not valid_environment(target): raise RuntimeError('설치 환경 확인 실패. install.log를 확인하세요.')
            result={'release':manifest['release'],'path':str(target),'state':'INSTALLED'}
            return result if activate(home,manifest['release'],target) else result|{'state':'UPDATE_PENDING'}
        finally:
            shutil.rmtree(staging,ignore_errors=True)


def activate(home,release,target):
    """Activation and supervisor ownership share the same lock and runtime gate."""
    home=Path(home);target=str(Path(target).resolve())
    def same(value):
        return bool(value and value.get('release')==release and value.get('path')==target)
    try:
        with lock(home/'service.lock'):
            existing=read(home/'current.json')
            if same(existing): return True
            # A stopped supervisor is not proof that its persisted physical work
            # ended. Keep the old source/config available for recovery.
            from recovery import offline_locks
            with offline_locks(runtime_path(home),lock):
                if has_work(runtime_path(home)): return False
                previous={k:existing[k] for k in ('release','path') if k in existing} if existing else None
                atomic(home/'current.json',{'release':release,'path':target,'previous':previous})
                return True
    except RuntimeError:
        # Existing owner may reuse the exact current release, never activate a
        # replacement environment or source while holding active reservations.
        return same(read(home/'current.json'))


def active(home):
    try:
        with lock(Path(home)/'service.lock'): return False
    except RuntimeError: return True


def current(home):
    value=read(Path(home)/'current.json')
    if not value: raise RuntimeError('설치 정보가 없습니다. install 또는 start를 실행하세요.')
    verify(value['path'])
    return value


def status(home):
    home=Path(home).resolve();receipt=read(home/'service.json')
    if not receipt or not active(home): return {'state':'STOPPED'}
    value=health(receipt['port'])
    matching=bool(value and value.get('managed_instance')==receipt['instance'] and
                  value.get('managed_release')==receipt['release'] and value.get('managed_runtime')==receipt['runtime'])
    return {'state':'DEGRADED' if receipt.get('worker_exited') or receipt.get('state')=='DEGRADED' else
                    'READY' if matching and value.get('worker_running') else 'STARTING',
            'url':f"http://127.0.0.1:{receipt['port']}", 'release':receipt['release'],
            'runtime':receipt['runtime'],'health':value if matching else None, 'reason':receipt.get('reason','')}


def start(home,source=ROOT,port=8766,python=None,runtime=None):
    home=Path(home).resolve();home.mkdir(parents=True,exist_ok=True)
    with lock(home/'start.lock'):
        bind_runtime(home,runtime)
        if active(home):
            value=status(home)
            if value.get('url')!=f'http://127.0.0.1:{port}': raise RuntimeError('기존 Agent Monitor가 다른 포트에서 실행 중입니다: '+str(value.get('url')))
            return value
        installed=prepare(source,home,python)
        if installed['state']=='UPDATE_PENDING':
            if read(home/'current.json') is None:
                raise RuntimeError('INITIAL_RUNTIME_ADOPTION_BLOCKED: 기존 runtime의 미완료·종료 불명 작업을 확인해야 첫 관리 설치로 옮길 수 있습니다. 기존 소스로 복구한 뒤 다시 시작하세요. runtime: '+str(runtime_path(home)))
            installed=current(home)
        release=Path(installed['path'])
        # Do not replace a listener, silently select a new port, or assume it is ours.
        with socket.socket() as listener:
            try: listener.bind(('127.0.0.1',port))
            except OSError: raise RuntimeError(f'127.0.0.1:{port} 포트를 다른 서비스가 사용 중입니다.') from None
        log=(home/'service.log').open('ab')
        owner=subprocess.Popen([str(environment_python(release)),str(release/'apps/agent-monitor/manage.py'),
                          '_serve','--home',str(home),'--port',str(port),'--release',installed['release']],cwd=release,
                         stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,close_fds=True)
        log.close()
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            value=status(home)
            if value['state']=='READY': return value
            if owner.poll() is not None: raise RuntimeError('Agent Monitor 소유 프로세스가 시작되지 않았습니다. '+str(home/'service.log'))
            time.sleep(.2)
        raise RuntimeError('Agent Monitor 준비 시간 초과. '+str(home/'service.log'))


def stop(home):
    home=Path(home).resolve()
    if not active(home): return {'state':'STOPPED'}
    receipt=read(home/'service.json')
    if not receipt: raise RuntimeError('서비스 소유권을 확인할 수 없습니다.')
    # Supervisor, not the caller, checks the persisted runtime and stops its children.
    atomic(home/'stop-request.json',{'instance':receipt['instance']})
    return {'state':'STOP_REQUESTED'}


def bsp_finished(job):
    """BSP jobs have no top-level state; use their actual final-review contract."""
    if not isinstance(job, dict): return False
    review=job.get('final_review')
    modules=job.get('modules')
    if (not isinstance(review,dict) or not job.get('fingerprint') or
            review.get('fingerprint')!=job['fingerprint'] or not review.get('reviewer') or not review.get('evidence') or
            not isinstance(modules,list) or not modules or job.get('integration',{}).get('status')!='SUCCEEDED'):
        return False
    required={'analysis','design','code','build','verification','device_test'}
    for module in modules:
        if not isinstance(module,dict): return False
        if module.get('active',True) is False: continue
        stages=module.get('stages',{})
        if not required<=stages.keys() or any(stage.get('status')!='SUCCEEDED' or stage.get('validity')!='CURRENT' for stage in stages.values()):
            return False
    if any(d.get('status')!='APPLIED' for d in job.get('decisions',[])): return False
    if any(p.get('status') not in {'SUCCEEDED','FAILED','CANCELLED','RECORDED'} for p in job.get('prompts',[])): return False
    return True


def has_work(runtime):
    """Read-only, fail-closed proof; corrupt or unknown records defer shutdown."""
    import sqlite3
    try:
        for path in Path(runtime).glob('**/*.db'):
            if path.name not in {'dashboard.db','runs.db'}: continue
            with sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro',uri=True) as c:
                c.execute('BEGIN')
                tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'runs' in tables:
                    for row in c.execute('SELECT data FROM runs'):
                        run=json.loads(row[0]);integration=run.get('integration') or {}
                        if run.get('state') not in {'COMPLETED','CANCELLED'}: return True
                        if any(a.get('state') in {'RUNNING','UNKNOWN'} or a.get('terminated') is False for a in run.get('attempts',[])): return True
                        if integration.get('batch') and not integration.get('batch_released'): return True
                for table in ('reservations','leases','coordinator_lanes'):
                    if table in tables and c.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone(): return True
                if 'jobs' in tables:
                    cols={r[1] for r in c.execute('PRAGMA table_info(jobs)')}
                    if 'data' not in cols:
                        if c.execute('SELECT 1 FROM jobs LIMIT 1').fetchone(): return True
                    elif any(not bsp_finished(json.loads(r[0])) for r in c.execute('SELECT data FROM jobs')): return True
                if 'orchestration_runs' in tables and c.execute("SELECT 1 FROM orchestration_runs WHERE status NOT IN ('SUCCEEDED','FAILED','CANCELLED') LIMIT 1").fetchone(): return True
                if 'launch_receipts' in tables:
                    for row in c.execute('SELECT data FROM launch_receipts'):
                        receipt=json.loads(row[0]); process=receipt.get('process_receipt') or {}; proof=receipt.get('not_launched') or {}
                        not_launched=(receipt.get('status')=='NOT_LAUNCHED' and not process and
                                      proof.get('launch_id')==receipt.get('id') and proof.get('intent_nonce')==receipt.get('nonce') and
                                      proof.get('source')=='server-adapter-unentered-branch' and bool(proof.get('reason')))
                        simulated=not process and receipt.get('result_envelope',{}).get('transport',{}).get('simulation') is True
                        if process.get('phase')!='TERMINATED' and not not_launched and not simulated: return True
        return False
    except (OSError,ValueError,TypeError,AttributeError,sqlite3.Error):
        return True


def interrupt_api(api, timeout=10):
    """Close admission first; never hard-kill a process or signal the worker."""
    if api is None or api.poll() is not None: return True
    try: api.send_signal(signal.SIGINT)
    except ProcessLookupError: return True
    try: api.wait(timeout=timeout)
    except subprocess.TimeoutExpired: return False
    return True


def serve(home,port,expected_release=None):
    home=Path(home).resolve()
    with lock(home/'service.lock'):
        runtime=runtime_path(home)
        runtime.mkdir(parents=True,exist_ok=True)
        # Resolve activation only after owning the service lock. An installer
        # cannot switch current.json underneath a live supervisor.
        installed=current(home)
        if expected_release is not None and installed['release']!=expected_release:
            raise RuntimeError('활성 버전이 변경되었습니다. start를 다시 실행하세요.')
        release=Path(installed['path']);instance=uuid.uuid4().hex
        receipt={'instance':instance,'release':installed['release'],'runtime':str(runtime),'port':port}
        env=dict(os.environ,AGENT_MONITOR_INSTANCE=instance,AGENT_MONITOR_RELEASE=installed['release'],BSP_RUNTIME=str(runtime))
        pending_stop=False
        def request_stop(signum, frame):
            nonlocal pending_stop
            pending_stop=True
        handlers={number:signal.signal(number,request_stop) for number in (signal.SIGINT,signal.SIGTERM)}
        worker=None;api=None;safe_exit=False
        def publish(**changes):
            receipt.update(changes)
            try: atomic(home/'service.json',receipt)
            except OSError as exc: print('Service receipt unavailable: '+type(exc).__name__,file=sys.stderr,flush=True)
        def launch_api():
            return subprocess.Popen([str(environment_python(release)),str(release/'scripts/serve_monitor.py'),
                                     '--runtime',str(runtime),'--port',str(port)],cwd=release,env=env,stdin=subprocess.DEVNULL,start_new_session=True)
        def stop_result(reason):
            atomic(home/'stop-result.json',{'state':'BLOCKED','instance':instance,'reason':reason})
        try:
            publish(state='STARTING')
            worker=subprocess.Popen([str(environment_python(release)),'-m','backend.worker.main','--runtime',str(runtime)],
                                    cwd=release,env=env,stdin=subprocess.DEVNULL,start_new_session=True)
            while True:
                try:
                    if worker.poll() is not None and not receipt.get('worker_exited'):
                        # Restarting could duplicate an unresolved physical job.
                        # Keep the API and supervisor ownership for inspection.
                        publish(state='DEGRADED',worker_exited=True,reason='실행 관리자가 종료되었습니다. 저장된 작업을 확인하세요.')
                    try: request=read(home/'stop-request.json')
                    except (OSError,ValueError):
                        request=None;publish(state='DEGRADED',reason='종료 요청을 읽을 수 없습니다. 실행 관리자는 유지합니다.')
                    from_file=bool(request and request.get('instance')==instance)
                    if pending_stop or from_file:
                        pending_stop=False
                        if from_file: (home/'stop-request.json').unlink(missing_ok=True)
                        # No new acceptance is possible after the owned API has
                        # fully exited. Recheck the DB only after that barrier.
                        if not interrupt_api(api):
                            stop_result('API가 아직 요청을 처리 중입니다. 실행 관리자는 유지합니다.')
                        elif has_work(runtime):
                            api=None
                            stop_result('진행·대기·일시정지·종료 불명 작업이 남아 있습니다.')
                        else:
                            if worker.poll() is None:
                                worker.send_signal(signal.SIGINT)
                            worker.wait()  # Drain only; no hard-kill escalation.
                            safe_exit=True
                            atomic(home/'stop-result.json',{'state':'STOPPED','instance':instance})
                            return {'state':'STOPPED'}
                    if api is None or api.poll() is not None:
                        # API failure never stops the independent worker. A new
                        # API uses the same instance/runtime and owns no worker.
                        if api is not None: api.wait()
                        try:
                            api=launch_api()
                            publish(state='DEGRADED' if worker.poll() is not None else 'STARTING',
                                    worker_exited=worker.poll() is not None,
                                    reason=receipt.get('reason','') if worker.poll() is not None else '')
                        except OSError as exc:
                            api=None;publish(state='DEGRADED',reason='API 시작 실패: '+type(exc).__name__)
                            time.sleep(1)
                    time.sleep(.25)
                except (OSError,ValueError,TypeError,AttributeError) as exc:
                    # A malformed request/DB or transient file error cannot
                    # turn into permission to stop the execution manager.
                    publish(state='DEGRADED',reason='상태 확인 실패: '+type(exc).__name__)
                    time.sleep(1)
        finally:
            for number,handler in handlers.items(): signal.signal(number,handler)
            if safe_exit: (home/'service.json').unlink(missing_ok=True)



def installed_release(home, release):
    import re
    if not isinstance(release,str) or not re.fullmatch(r'[a-f0-9]{64}',release):
        raise ValueError('A verified release SHA256 is required')
    base=Path(home).resolve()/'releases'
    candidates=[]
    for path in base.glob(release+'*'):
        if path.is_symlink() or not path.is_dir() or path.resolve().parent!=base: continue
        try:
            manifest=verify(path)
            if manifest['release']==release and valid_environment(path): candidates.append(path)
        except (OSError,ValueError,subprocess.SubprocessError): continue
    if not candidates: raise RuntimeError('검증된 설치 버전을 찾을 수 없습니다: '+release)
    return max(candidates,key=lambda p:p.stat().st_mtime_ns)


def rollback(home, release=None):
    from recovery import offline_locks
    home=Path(home).resolve()
    with lock(home/'start.lock'),lock(home/'install.lock'),lock(home/'service.lock'):
        existing=current(home)
        selected=release or (existing.get('previous') or {}).get('release')
        target=installed_release(home,selected)
        with offline_locks(runtime_path(home),lock):
            if has_work(runtime_path(home)):
                raise RuntimeError('ROLLBACK_BLOCKED: 진행·종료 불명 작업 또는 실행 중 서비스가 있습니다.')
            previous={k:existing[k] for k in ('release','path')}
            atomic(home/'current.json',{'release':selected,'path':str(target),'previous':previous})
        return {'state':'ROLLED_BACK','release':selected,'path':str(target),'runtime':str(runtime_path(home))}


def inspect_runtime(home):
    from recovery import inspect,offline_locks
    home=Path(home).resolve()
    with lock(home/'start.lock'),lock(home/'service.lock'),offline_locks(runtime_path(home),lock):
        return inspect(runtime_path(home))


def adopt_runtime(home,release,expected_revision):
    from recovery import inspect,backup,offline_locks
    home=Path(home).resolve()
    with lock(home/'start.lock'),lock(home/'install.lock'),lock(home/'service.lock'):
        if read(home/'current.json') is not None:
            raise RuntimeError('ADOPTION_BLOCKED: 최초 runtime 연결에만 사용합니다. 기존 설치는 rollback/update 절차를 사용하세요.')
        target=installed_release(home,release);runtime=runtime_path(home)
        with offline_locks(runtime,lock):
            report=inspect(runtime)
            if report['revision']!=expected_revision:
                raise RuntimeError('INSPECTION_CHANGED: runtime을 다시 검사하세요.')
            if not report['adoptable']:
                raise RuntimeError('ADOPTION_BLOCKED: 미지원 계약·실행 중·UNKNOWN·종료 불명 기록은 원본 실행 코드에서 복구해야 합니다.')
            snapshot=backup(runtime,home/'backups'/('adoption-'+uuid.uuid4().hex))
            # Explicit compatible adoption changes only the installation pointer.
            # It neither rewrites Run states nor starts an API/Worker/hardware.
            receipt={'release':release,'path':str(target),'runtime':str(runtime),
                     'inspection_revision':expected_revision,'backup':snapshot,'supported_contracts':report['supported_contracts']}
            atomic(home/'runtime-adoption.json',receipt)
            atomic(home/'current.json',{'release':release,'path':str(target),'previous':None,'adoption':expected_revision})
            return receipt|{'state':'ADOPTED','started':False}


def cleanup_releases(home,apply=False,keep=2):
    if type(keep) is not int or keep<0: raise ValueError('keep must be nonnegative')
    home=Path(home).resolve()
    from recovery import release_references,offline_locks
    with lock(home/'start.lock'),lock(home/'install.lock'),lock(home/'service.lock'),offline_locks(runtime_path(home),lock):
        if has_work(runtime_path(home)):
            raise RuntimeError('CLEANUP_BLOCKED: 진행·종료 불명 작업이 남아 있습니다.')
        try: release_pins=release_references(runtime_path(home))
        except Exception as exc:
            raise RuntimeError('CLEANUP_BLOCKED: runtime 참조를 검증할 수 없습니다.') from exc
        pins=set()
        for file in ('current.json','service.json','runtime-adoption.json'):
            value=read(home/file) or {}
            for item in (value,value.get('previous') or {}):
                if item.get('path'): pins.add(str(Path(item['path']).resolve()))
                if item.get('release'): release_pins.add(item['release'])
        candidates=[];skipped=[]
        base=home/'releases'
        for path in base.iterdir() if base.exists() else []:
            if path.is_symlink() or not path.is_dir() or path.resolve().parent!=base:
                skipped.append(path.name);continue
            if str(path.resolve()) in pins: continue
            try:
                manifest=verify(path)
                if manifest['release'] in release_pins:
                    pins.add(str(path.resolve()));continue
            except (OSError,ValueError):
                # Unknown/corrupt folders are retained for manual inspection.
                skipped.append(path.name);continue
            candidates.append(path)
        candidates.sort(key=lambda p:p.stat().st_mtime_ns,reverse=True)
        removal=candidates[keep:]
        stages=[]
        for path in home.glob('.install-*'):
            if path.is_symlink() or not path.is_dir() or runtime_path(home).is_relative_to(path): continue
            try: marker=read(path/'INSTALL_STAGE.json')
            except (OSError,ValueError): continue
            if marker=={'format':'agent-monitor-install-stage-v1','path':str(path)}: stages.append(path)
            else: skipped.append(path.name)
        if apply:
            for path in removal+stages: shutil.rmtree(path)
        return {'state':'CLEANED' if apply else 'PLANNED','removed':[p.name for p in removal],'staging_removed':[p.name for p in stages],
                'retained_pins':sorted(pins),'retained_unverified':skipped,'runtime':str(runtime_path(home))}

def main(argv=None):
    parser=argparse.ArgumentParser(description='Agent Monitor 설치·실행·상태')
    parser.add_argument('action',choices=['install','start','status','stop','_serve','inspect-runtime','adopt','rollback','cleanup','tools'])
    parser.add_argument('--home',type=Path,default=Path.home()/'.local/share/bsp-agent-monitor')
    parser.add_argument('--source',type=Path,default=ROOT);parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--runtime',type=Path,help='기존 runtime 절대 경로를 처음 한 번 연결합니다.')
    parser.add_argument('--python');parser.add_argument('--release')
    parser.add_argument('--inspection-revision');parser.add_argument('--apply',action='store_true')
    parser.add_argument('--keep',type=int,default=2)
    parser.add_argument('--artifact-manifest',type=Path);parser.add_argument('--artifact-signature',type=Path)
    parser.add_argument('--trusted-keyring',type=Path);parser.add_argument('--wheelhouse',type=Path)
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535: parser.error('Invalid port')
    try:
        if args.action in {'install','start'}:
            with lock(args.home/'start.lock'):
                bind_runtime(args.home,args.runtime)
            from prerequisites import prepare as prepare_tools
            with lock(args.home/'prerequisites.lock'):
                tools_result=prepare_tools(args.home,apply=True)
            if tools_result['state']=='BLOCKED':
                raise RuntimeError('PREREQUISITES_BLOCKED: '+tools_result.get('reason','')+' '+tools_result.get('log',''))
        if args.action=='install':
            with lock(args.home/'start.lock'):
                bind_runtime(args.home,args.runtime)
                result=prepare(args.source,args.home,args.python)
        elif args.action=='start': result=start(args.home,args.source,args.port,args.python,args.runtime)
        else:
            if args.runtime is not None and (not args.runtime.is_absolute() or args.runtime.resolve()!=runtime_path(args.home)):
                raise ValueError('설치된 서비스의 runtime 경로와 다릅니다.')
            if args.action=='status': result=status(args.home)
            elif args.action=='stop': result=stop(args.home)
            elif args.action=='_serve': result=serve(args.home,args.port,args.release)
            elif args.action=='inspect-runtime': result=inspect_runtime(args.home)
            elif args.action=='adopt': result=adopt_runtime(args.home,args.release,args.inspection_revision)
            elif args.action=='rollback': result=rollback(args.home,args.release)
            elif args.action=='cleanup': result=cleanup_releases(args.home,args.apply,args.keep)
            else:
                from prerequisites import prepare as prepare_tools,install_supplied
                with lock(args.home/'prerequisites.lock'):
                    result=prepare_tools(args.home,apply=args.apply)
                if args.apply and result['state']=='BLOCKED':
                    raise RuntimeError('PREREQUISITES_BLOCKED: '+result.get('reason',''))
                if args.artifact_manifest:
                    def supplied():
                        return install_supplied(args.artifact_manifest,args.artifact_signature,args.trusted_keyring,
                                                args.home,wheelhouse=args.wheelhouse,apply=args.apply)
                    if args.apply:
                        from recovery import offline_locks
                        with lock(args.home/'start.lock'),lock(args.home/'install.lock'),lock(args.home/'service.lock'),offline_locks(runtime_path(args.home),lock):
                            if has_work(runtime_path(args.home)):
                                raise RuntimeError('SUPPLIED_INSTALL_BLOCKED: 작업/서비스 종료 후 장비 패키지를 설치하세요.')
                            result['supplied']=supplied()
                    else: result['supplied']=supplied()
        print(json.dumps(result,ensure_ascii=False))
    except (OSError,ValueError,RuntimeError,subprocess.CalledProcessError) as exc:
        print(str(exc),file=sys.stderr);return 1
    return 0


if __name__=='__main__': raise SystemExit(main())
