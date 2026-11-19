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
import threading
import time
import urllib.error
import urllib.request
import uuid

from delivery import ROOT, MANIFEST, export, verify

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.gui_test.execution.force_stop import stop_recorded, require_force_complete
from backend.gui_test.execution.launch import process_identity, _lock_held


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
    require_force_complete(home / 'force-stop.json')
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


def install_step(argv, cwd, log_path, label):
    """Keep command stdout machine-readable and installation details local."""
    print(f'[Agent Monitor] {label} 시작. 로그 {log_path}', file=sys.stderr, flush=True)
    started = time.monotonic()
    finished = threading.Event()

    def report_wait():
        while not finished.wait(10):
            elapsed = int(time.monotonic() - started)
            print(f'[Agent Monitor] {label} 진행 중 · {elapsed}초 경과. 로그 {log_path}',
                  file=sys.stderr, flush=True)

    reporter = threading.Thread(target=report_wait, daemon=True)
    with Path(log_path).open('ab') as log:
        reporter.start()
        try:
            subprocess.run(argv, check=True, cwd=cwd, stdin=subprocess.DEVNULL,
                           stdout=log, stderr=log)
        except subprocess.CalledProcessError as exc:
            print(f'[Agent Monitor] {label} 실패 · 종료 코드 {exc.returncode}. 로그 {log_path}',
                  file=sys.stderr, flush=True)
            raise
        except KeyboardInterrupt:
            print(f'[Agent Monitor] {label} 중단. 같은 실행 명령으로 다시 시도하세요.',
                  file=sys.stderr, flush=True)
            raise
        finally:
            finished.set()
            reporter.join()
    print(f'[Agent Monitor] {label} 완료.', file=sys.stderr, flush=True)


def prepare(source,home,python=None,include_ui=True):
    home=Path(home).resolve();source=Path(source).resolve();home.mkdir(parents=True,exist_ok=True)
    if os.name=='nt': raise RuntimeError('Agent Monitor 서버는 Linux에서 실행합니다. Windows에서는 board-connector.cmd를 사용하세요.')
    with lock(home/'install.lock'):
        require_reset_complete(home)
        staging=Path(tempfile.mkdtemp(prefix='.install-',dir=home))
        atomic(staging/'INSTALL_STAGE.json',{'format':'agent-monitor-install-stage-v1','path':str(staging)})
        try:
            print('[Agent Monitor] 설치 소스·기존 환경 확인 중.', file=sys.stderr, flush=True)
            manifest=export(source,staging/'source',include_ui)
            verify(staging/'source')
            target=home/'releases'/manifest['release']
            if target.exists() and valid_environment(target):
                verify(target)
                applied=activate(home,manifest['release'],target)
                print('[Agent Monitor] 기존 설치 환경 사용.', file=sys.stderr, flush=True)
                return {'release':manifest['release'],'path':str(target),'state':'REUSED' if applied else 'UPDATE_PENDING'}
            if target.exists():
                # Never delete/repair an environment that may be in use.
                target=target.with_name(target.name+'-'+uuid.uuid4().hex[:8])
            target.parent.mkdir(parents=True,exist_ok=True)
            os.replace(staging/'source',target)
            selected=python or shutil.which('python3.13') or sys.executable
            install_step([selected,'-m','venv',str(target/'.venv')], target,
                         home/'install.log', 'Python 가상환경 준비')
            install_step([str(environment_python(target)),'-m','pip','install','-r',str(target/'requirements.lock')],
                         target, home/'install.log', 'Python 패키지 설치')
            print('[Agent Monitor] 설치 결과 확인 중.', file=sys.stderr, flush=True)
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
            from recovery import offline_locks, inspect
            with offline_locks(runtime_path(home),lock):
                if has_work(runtime_path(home)):
                    if existing is not None: return False
                    print('[Agent Monitor] 일시정지 예약의 이관 조건 확인 중.', file=sys.stderr, flush=True)
                    report = inspect(runtime_path(home))
                    if not report['adoptable'] or not any(item['preservable_resources'] for item in report['reservation_summaries']):
                        return False
                    record_adoption(home, release, target, report, automatic=True)
                    print('[Agent Monitor] 일시정지 세션·예약을 백업하고 기존 runtime을 연결했습니다.',
                          file=sys.stderr, flush=True)
                    return True
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


def start(home,source=ROOT,port=8766,python=None,runtime=None,*,restart=False):
    home=Path(home).resolve();home.mkdir(parents=True,exist_ok=True)
    with lock(home/'start.lock'):
        require_reset_complete(home)
        bind_runtime(home,runtime)
        running=active(home)
        if running:
            value=status(home)
            if value.get('url')!=f'http://127.0.0.1:{port}': raise RuntimeError('기존 Agent Monitor가 다른 포트에서 실행 중입니다: '+str(value.get('url')))
            if not restart:
                print('[Agent Monitor] 실행 중인 설치본을 사용합니다. 소스 갱신을 적용하려면 ./run.sh restart를 실행하세요.',
                      file=sys.stderr, flush=True)
                return value
        if restart and not (Path(source)/MANIFEST).is_file() and (Path(source)/'apps/web/package.json').is_file():
            install_step(['bash',str(Path(source).resolve()/'scripts/build-ui.sh'),'dashboard'],
                         Path(source).resolve(),home/'ui-build.log','Agent Monitor UI 갱신')
        installed=prepare(source,home,python)
        if restart:
            if running:
                service=read(home/'service.json')
                if not service or not service.get('instance'):
                    raise RuntimeError('RESTART_BLOCKED: 서비스 소유권을 확인할 수 없습니다.')
                print('[Agent Monitor] 새 설치본 준비 완료. 기존 API·Worker 종료를 기다립니다.', file=sys.stderr, flush=True)
                (home/'stop-result.json').unlink(missing_ok=True)
                stop(home)
                deadline=time.monotonic()+45
                while active(home):
                    result=read(home/'stop-result.json')
                    if result and result.get('instance')==service['instance'] and result.get('state')=='BLOCKED':
                        raise RuntimeError('RESTART_BLOCKED: '+result.get('reason','기존 실행 상태를 확인하세요.'))
                    if time.monotonic()>=deadline:
                        raise RuntimeError('RESTART_PENDING: 기존 프로세스 종료를 기다리고 있습니다. 같은 명령으로 다시 확인하세요.')
                    time.sleep(.2)
            if not activate(home,installed['release'],installed['path']):
                raise RuntimeError('RESTART_BLOCKED: 새 설치본을 적용할 수 없습니다. ./run.sh doctor로 실행 상태를 확인하세요.')
            installed=dict(installed,state='REUSED')
        if installed['state']=='UPDATE_PENDING':
            if read(home/'current.json') is None:
                from recovery import inspect, offline_locks, diagnostic_summary, diagnostic_text
                try:
                    print('[Agent Monitor] 기존 runtime의 이관 차단 사유 확인 중.', file=sys.stderr, flush=True)
                    with lock(home/'service.lock'), offline_locks(runtime_path(home), lock):
                        details = diagnostic_text(diagnostic_summary(inspect(runtime_path(home), include_revision=False)))
                except (OSError, ValueError, RuntimeError):
                    details = '진단 보류 · 기존 실행 관리자의 소유권 또는 runtime 접근 상태를 확인하세요.'
                raise RuntimeError('INITIAL_RUNTIME_ADOPTION_BLOCKED\n' + details +
                                   '\n다시 검사 · bash run.sh doctor')
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


def force_stop(home):
    """Explicit user emergency command; no DB changes or normal-stop gates."""
    home = Path(home).resolve()
    with lock(home / 'start.lock'):
        receipt = read(home / 'service.json') or {}
        if not isinstance(receipt, dict) or not isinstance(receipt.get('children', {}), dict):
            raise ValueError('Invalid service process receipt')
        owner = receipt.get('owner')
        children = receipt.get('children', {})
        targets = [item for item in [owner, *children.values()] if item is not None]
        if (receipt or active(home) or _lock_held(runtime_path(home) / 'worker.lock')) and not owner:
            raise RuntimeError('FORCE_STOP_BLOCKED: 실행본에 OS 소유권 기록이 없습니다. 이전 버전을 안전 종료하고 갱신하세요.')
        result = stop_recorded(home / 'force-stop.json', targets)
        if active(home) or _lock_held(runtime_path(home) / 'worker.lock'):
            result['state'] = 'FORCE_STOP_PENDING'
            atomic(home / 'force-stop.json', result)
            raise RuntimeError('FORCE_STOP_PENDING: 서비스 잠금의 종료를 확인할 수 없습니다.')
        return result


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
    from recovery import process_receipt_stopped
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
                        if not process_receipt_stopped(json.loads(row[0])): return True
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
        require_reset_complete(home)
        require_force_complete(home / 'force-stop.json')
        runtime=runtime_path(home)
        runtime.mkdir(parents=True,exist_ok=True)
        # Resolve activation only after owning the service lock. An installer
        # cannot switch current.json underneath a live supervisor.
        installed=current(home)
        if expected_release is not None and installed['release']!=expected_release:
            raise RuntimeError('활성 버전이 변경되었습니다. start를 다시 실행하세요.')
        release=Path(installed['path']);instance=uuid.uuid4().hex
        receipt={'instance':instance,'release':installed['release'],'runtime':str(runtime),'port':port,
                 'owner':process_identity(os.getpid())}
        env=dict(os.environ,AGENT_MONITOR_INSTANCE=instance,AGENT_MONITOR_RELEASE=installed['release'],BSP_RUNTIME=str(runtime))
        pending_stop=False
        def request_stop(signum, frame):
            nonlocal pending_stop
            pending_stop=True
        handlers={number:signal.signal(number,request_stop) for number in (signal.SIGINT,signal.SIGTERM)}
        worker=None;api=None;safe_exit=False;child_identities={}
        def remember(name, child):
            # Capture while Popen still owns the unreaped child. Never refresh a
            # receipt later by a numeric PID that might have been recycled.
            identity = None
            if getattr(child, 'pid', None) is not None and child.poll() is None:
                identity = process_identity(child.pid)
                if child.poll() is not None: identity = None
            child_identities[name] = identity
        def publish(**changes):
            receipt.update(changes)
            receipt['children'] = dict(child_identities)
            try: atomic(home/'service.json',receipt)
            except OSError as exc: print('Service receipt unavailable: '+type(exc).__name__,file=sys.stderr,flush=True)
        def launch_api():
            child = subprocess.Popen([str(environment_python(release)),str(release/'scripts/serve_monitor.py'),
                                     '--runtime',str(runtime),'--port',str(port)],cwd=release,env=env,stdin=subprocess.DEVNULL,start_new_session=True)
            remember('api', child)
            return child
        def stop_result(reason):
            atomic(home/'stop-result.json',{'state':'BLOCKED','instance':instance,'reason':reason})
        try:
            publish(state='STARTING')
            worker=subprocess.Popen([str(environment_python(release)),'-m','backend.worker.main','--runtime',str(runtime)],
                                    cwd=release,env=env,stdin=subprocess.DEVNULL,start_new_session=True)
            remember('worker', worker)
            publish()
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


def diagnose_runtime(home, requested=None):
    from recovery import inspect, offline_locks, diagnostic_summary
    home = Path(home).resolve()
    runtime = runtime_path(home)
    if requested is not None:
        if not Path(requested).is_absolute():
            raise ValueError('runtime 경로는 절대 경로여야 합니다.')
        requested = Path(requested).resolve()
        if (home/'runtime-location.json').exists() and requested != runtime:
            raise ValueError('기존 runtime 경로와 다릅니다. 기존 경로를 사용하세요.')
        runtime = requested
    with lock(home/'start.lock'), lock(home/'service.lock'), offline_locks(runtime, lock):
        return diagnostic_summary(inspect(runtime, include_revision=False))


def require_reset_complete(home):
    receipt = read(Path(home)/'runtime-reset.json')
    if receipt and receipt.get('state') != 'RESET':
        raise RuntimeError('RESET_PENDING: bash run.sh reset을 다시 실행해 초기화를 완료하세요.')


def reset_backup(home, runtime, state):
    from recovery import backup, digest, file_hash
    receipt = read(home/'runtime-reset.json')
    if receipt and receipt.get('state') in {'RESET_PENDING', 'RESET_DRAINING'}:
        if receipt.get('runtime') != str(runtime):
            raise RuntimeError('RESET_BLOCKED: 초기화 중인 runtime 경로와 다릅니다.')
        for saved in [receipt['backup'], *receipt.get('pre_stop_archives', [])]:
            snapshot = Path(saved['path'])
            manifest = read(snapshot/'BACKUP.json')
            if (not manifest or digest(manifest['files']) != saved['revision'] or
                    any(file_hash(snapshot/name) != expected for name, expected in manifest['files'].items())):
                raise RuntimeError('RESET_BLOCKED: 초기화 백업 검증에 실패했습니다.')
    else:
        print('[Agent Monitor] 초기화 전 runtime 백업 중.', file=sys.stderr, flush=True)
        snapshot = backup(runtime, home/'backups'/('reset-'+uuid.uuid4().hex))
        receipt = {'runtime': str(runtime), 'backup': snapshot, 'settings_preserved': True}
    receipt = receipt | {'state': state}
    atomic(home/'runtime-reset.json', receipt)
    return receipt


def reset_request(service, path, payload=None, controller=None):
    value = health(service['port'])
    if not value or any(value.get('managed_'+key) != service[key] for key in ('instance', 'release', 'runtime')):
        raise RuntimeError('RESET_BLOCKED: 실행 중인 Agent Monitor의 소유권을 확인할 수 없습니다.')
    origin = 'http://127.0.0.1:' + str(service['port'])
    headers = {'X-Bsp-Client': 'dashboard', 'Origin': origin}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers.update({'Content-Type': 'application/json', 'Idempotency-Key': 'reset-'+uuid.uuid4().hex,
                        'X-Gui-Session': controller})
    request = urllib.request.Request(origin+path, data=data, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=5) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError('RESET_BLOCKED: 세션 정리 API가 상태 변경을 거부했습니다. 같은 reset 명령으로 재시도하세요. HTTP '+str(exc.code)) from None


def cancel_reset_sessions(service):
    from urllib.parse import quote
    print('[Agent Monitor] 일시정지·대기 세션 취소와 예약 해제 확인 중.', file=sys.stderr, flush=True)
    pending = []
    requested = set()
    # With a configured connector both routers can share one store. Integration
    # mutations belong to the live route, so drain it before the legacy route.
    for prefix in ('/api/v1/gui-test/live', '/api/v1/gui-test'):
        for item in reset_request(service, prefix+'/runs'):
            if item['id'] in requested:
                continue
            path = prefix+'/runs/'+quote(item['id'], safe='')
            run = reset_request(service, path)
            if run['state'] in {'COMPLETED', 'CANCELLED'}:
                meta = run.get('integration') or {}
                if meta.get('batch') and not meta.get('batch_released'):
                    pending.append(path)
                continue
            if run['state'] not in {'PAUSED', 'QUEUED'}:
                raise RuntimeError('RESET_BLOCKED: 실행 중이거나 종료가 확인되지 않은 세션이 있습니다.')
            action = path+'/actions/cancel'
            if run.get('integration'):
                action = prefix+'/integration/runs/'+quote(run['id'], safe='')+'/actions/cancel'
            reset_request(service, action, {'expected_version': run['version']}, run['controller'])
            requested.add(run['id'])
            pending.append(path)
    deadline = time.monotonic()+30
    while pending:
        remaining = []
        for path in pending:
            run = reset_request(service, path)
            meta = run.get('integration') or {}
            if run['state'] not in {'COMPLETED', 'CANCELLED'} or (meta.get('batch') and not meta.get('batch_released')):
                remaining.append(path)
        pending = remaining
        if pending:
            if time.monotonic() >= deadline:
                raise RuntimeError('RESET_BLOCKED: 세션 취소·예약 해제 대기 중입니다. 같은 reset 명령으로 이어서 처리하세요.')
            time.sleep(.2)


def reset_runtime(home, requested=None):
    from recovery import archive_idle_records, clear_runtime_records, offline_locks, reset_plan
    home = Path(home).resolve()
    with lock(home/'start.lock'), lock(home/'install.lock'):
        runtime = bind_runtime(home, requested)
        if active(home):
            # Use the running release's existing cancellation contract. This
            # also works with supervisors installed before reset was added.
            service = read(home/'service.json')
            if not service:
                raise RuntimeError('RESET_BLOCKED: 서비스 소유권을 확인할 수 없습니다.')
            reset_plan(runtime, allow_batch_release=True)
            receipt = reset_backup(home, runtime, 'RESET_DRAINING')
            cancel_reset_sessions(service)
            def record_archive(snapshot):
                receipt.setdefault('pre_stop_archives', []).append(snapshot)
                atomic(home/'runtime-reset.json', receipt)
            archived = archive_idle_records(runtime, receipt['backup']['path'], record_archive)
            if archived:
                print('[Agent Monitor] 실행이 종료된 기록을 백업하고 초기화했습니다. DB '+str(archived)+'개.',
                      file=sys.stderr, flush=True)
            (home/'stop-result.json').unlink(missing_ok=True)
            stop(home)
            deadline = time.monotonic() + 15
            while active(home):
                result = read(home/'stop-result.json')
                if result and result.get('instance') == service['instance'] and result.get('state') == 'BLOCKED':
                    raise RuntimeError('RESET_BLOCKED: ' + result['reason'])
                if time.monotonic() >= deadline:
                    raise RuntimeError('RESET_BLOCKED: 서비스 종료 대기 중입니다. 종료 후 같은 명령을 실행하세요.')
                time.sleep(.2)
        with lock(home/'service.lock'), offline_locks(runtime, lock):
            plan = reset_plan(runtime)
            receipt = reset_backup(home, runtime, 'RESET_PENDING')
            clear_runtime_records(runtime, plan)
            receipt = receipt | {'state': 'RESET'}
            atomic(home/'runtime-reset.json', receipt)
            print('[Agent Monitor] 세션·시험 기록·예약 초기화 완료. 백업 ' + receipt['backup']['path'],
                  file=sys.stderr, flush=True)
            return receipt


def adopt_runtime(home,release,expected_revision):
    from recovery import inspect,offline_locks
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
            return record_adoption(home, release, target, report)


def record_adoption(home, release, target, report, *, automatic=False):
    """Called with installation/service/runtime ownership held by the caller."""
    from recovery import backup
    if verify(target)['release'] != release or not valid_environment(target):
        raise RuntimeError('ADOPTION_BLOCKED: 설치 소스·실행 환경 확인에 실패했습니다.')
    runtime = runtime_path(home)
    print('[Agent Monitor] 기존 runtime 백업 중.', file=sys.stderr, flush=True)
    snapshot = backup(runtime, home/'backups'/('adoption-'+uuid.uuid4().hex))
    receipt = {'release': release, 'path': str(target), 'runtime': str(runtime),
               'inspection_revision': report['revision'], 'backup': snapshot,
               'supported_contracts': report['supported_contracts'], 'automatic': automatic}
    atomic(home/'runtime-adoption.json', receipt)
    atomic(home/'current.json', {'release': release, 'path': str(target), 'previous': None,
                                'adoption': report['revision']})
    return receipt | {'state': 'ADOPTED', 'started': False}


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
    parser.add_argument('action',choices=['install','prepare-env','start','restart','status','stop','force-stop','_serve','doctor','reset','inspect-runtime','adopt','rollback','cleanup','tools'])
    parser.add_argument('--home',type=Path,default=Path.home()/'.local/share/bsp-agent-monitor')
    parser.add_argument('--source',type=Path,default=ROOT);parser.add_argument('--port',type=int)
    parser.add_argument('--runtime',type=Path,help='기존 runtime 절대 경로를 처음 한 번 연결합니다.')
    parser.add_argument('--python');parser.add_argument('--release')
    parser.add_argument('--inspection-revision');parser.add_argument('--apply',action='store_true')
    parser.add_argument('--keep',type=int,default=2)
    parser.add_argument('--artifact-manifest',type=Path);parser.add_argument('--artifact-signature',type=Path)
    parser.add_argument('--trusted-keyring',type=Path);parser.add_argument('--wheelhouse',type=Path)
    args=parser.parse_args(argv)
    if args.port is not None and not 1<=args.port<=65535: parser.error('Invalid port')
    try:
        if args.action == 'doctor':
            from recovery import diagnostic_text
            result = diagnose_runtime(args.home, args.runtime)
            print(diagnostic_text(result), file=sys.stderr)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.action == 'reset':
            print(json.dumps(reset_runtime(args.home, args.runtime), ensure_ascii=False))
            return 0
        if args.action in {'install','start','restart'}:
            with lock(args.home/'start.lock'):
                bind_runtime(args.home,args.runtime)
            from prerequisites import prepare as prepare_tools
            with lock(args.home/'prerequisites.lock'):
                tools_result=prepare_tools(args.home,apply=True)
            if tools_result['state']=='BLOCKED':
                raise RuntimeError('PREREQUISITES_BLOCKED: '+tools_result.get('reason','')+' '+tools_result.get('log',''))
        if args.action=='prepare-env':
            with lock(args.home/'start.lock'):
                runtime=bind_runtime(args.home,args.runtime)
                cur=read(args.home/'current.json')
                lock_src=args.source/'requirements.lock'
                if isinstance(cur,dict) and cur.get('path'):
                    rel_dir=Path(cur['path'])
                    if (rel_dir.is_dir() and valid_environment(rel_dir) and
                            (not lock_src.is_file() or (rel_dir/'requirements.lock').is_file() and
                             (rel_dir/'requirements.lock').read_bytes()==lock_src.read_bytes())):
                        result={'state':'REUSED','release':cur.get('release'),'path':str(rel_dir),'runtime':str(runtime)}
                    else:
                        result=prepare(args.source,args.home,args.python)|{'runtime':str(runtime)}
                else:
                    result=prepare(args.source,args.home,args.python)|{'runtime':str(runtime)}
        elif args.action=='install':
            with lock(args.home/'start.lock'):
                bind_runtime(args.home,args.runtime)
                result=prepare(args.source,args.home,args.python)
        elif args.action=='start': result=start(args.home,args.source,args.port or 8766,args.python,args.runtime)
        elif args.action=='restart':
            service=read(args.home/'service.json') or {}
            port=args.port if args.port is not None else service.get('port',8766)
            if type(port) is not int or not 1<=port<=65535:
                raise ValueError('저장된 서비스 포트를 확인하세요. --port로 지정할 수 있습니다.')
            result=start(args.home,args.source,port,args.python,args.runtime,restart=True)
        else:
            if args.runtime is not None and (not args.runtime.is_absolute() or args.runtime.resolve()!=runtime_path(args.home)):
                raise ValueError('설치된 서비스의 runtime 경로와 다릅니다.')
            if args.action=='status': result=status(args.home)
            elif args.action=='stop': result=stop(args.home)
            elif args.action=='force-stop': result=force_stop(args.home)
            elif args.action=='_serve': result=serve(args.home,args.port or 8766,args.release)
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
