"""Detached per-home manager; GUI close never owns Host/SSH lifetime."""
import argparse
import copy
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

from ..core.models import TestError
from ..execution.launch import LaunchLock, process_identity, bind_loopback
from .settings import Settings
from .logs import logger, redact


def storage_usage(root, protected=False):
    total=0; count=0; partial=False; started=time.monotonic()
    for base, dirs, files in os.walk(root,followlinks=False):
        dirs[:]=[name for name in dirs if not (Path(base)/name).is_symlink()]
        for name in files:
            file=Path(base)/name
            if file.is_symlink(): continue
            try: total+=file.stat().st_size; count+=1
            except OSError: partial=True
            if count>=10000 or time.monotonic()-started>.25: partial=True;break
        if count>=10000 or time.monotonic()-started>.25: break
    return {'runtime_bytes':total,'partial':partial,'protected':bool(protected),'automatic_cleanup':False}


def stale_display(cached,error):
    return dict(cached,state='ERROR',error=redact(error),console=dict(cached.get('console',{}),fresh=False,stale=True),fresh=False,
                boards=[dict(board,last_known_state=board.get('last_known_state',board['state']),state='UNKNOWN',stale=True) for board in cached.get('boards',[])])


class Manager:
    def __init__(self, home):
        self.home = Path(home); self.settings = Settings(home); self.log = logger(home)
        self.console_cursor=0; self.console_epoch=None; self.storage_cache=None; self.storage_checked=0
        self.control_lock=threading.RLock()
        self.thread = None; self.wizard = None; self.error = ''; self.stop_event = threading.Event()
        self.shutdown = threading.Event()
        self.cached = {'state': 'DISCONNECTED', 'boards': [], 'error': '', 'stages': {}, 'console': {'boards': [], 'errors': []}, 'executions': []}
        def monitor():
            while not self.shutdown.is_set():
                try: self.cached = self.probe()
                except Exception as exc:
                    if str(exc)!=self.cached.get('error'): self.log.error('STATUS_UNAVAILABLE %s',redact(str(exc)))
                    self.cached = stale_display(self.cached,str(exc))
                self.shutdown.wait(3)
        self.monitor = threading.Thread(target=monitor, name='connector-heartbeat', daemon=True); self.monitor.start()

    def connect(self):
        with self.control_lock: return self._connect()

    def _connect(self):
        from ..execution.launch import read_active
        if read_active(self.home/'runtime') is not None: return {'state':'CONNECTING'}
        if self.thread and self.thread.is_alive(): return {'state': 'CONNECTING'}
        from .shared_control import apply_pending
        apply_pending(self.home)
        self.stop_event.clear(); self.error = ''
        def run():
            try:
                from scripts.setup_runtime import Wizard
                wizard = Wizard(home=self.home, windows=True, remote_dashboard_port=self.settings.read().get('_setup', {}).get('remote_dashboard_port'))
                wizard.python = Path(sys.executable)  # GUI runtime provisioned once; external TC Python stays in the profile
                wizard.connector_stop_requested = self.stop_event.is_set
                wizard.connector_noninteractive = True
                self.wizard = wizard
                wizard.start()
            except Exception as exc:
                self.error = redact(str(exc)); self.log.error('CONNECT_FAILED %s', self.error)
        self.thread = threading.Thread(target=run, daemon=False, name='connector-owner'); self.thread.start()
        return {'state': 'CONNECTING'}

    def status(self): return copy.deepcopy(self.cached)

    def probe(self):
        from ..execution.launch import read_active
        receipt = read_active(self.home / 'runtime')
        result = {'state': 'ERROR' if self.error else 'CONNECTING' if self.thread and self.thread.is_alive() else 'DISCONNECTED',
                  'error': self.error, 'boards': [], 'stages': {}, 'dashboard_url': '', 'console': {'boards': [], 'errors': []}, 'executions': []}
        if not receipt: return result
        import httpx
        with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
            response = client.get(receipt['runner_url'] + '/v1/inventory'); response.raise_for_status()
            inventory = response.json()
            if inventory['runner_id'] != receipt['runner_id']: raise TestError('Runner receipt identity mismatch', 'RUNNER_CHANGED')
            result.update(boards=inventory['boards'], dashboard_url=receipt['dashboard_url'], fresh=True,last_checked_at=inventory['checked_at'])
            if self.storage_cache is None or time.monotonic()-self.storage_checked>=60:
                self.storage_cache=storage_usage(self.home/'runtime'); self.storage_checked=time.monotonic()
            result['storage']=dict(self.storage_cache,protected=inventory['host_busy'] or inventory['reserved'])
            result['stages']['local'] = 'READY'; result['stages']['ssh'] = receipt['phase']
            for path, key in (('/console', 'console'), ('/recent-executions', 'recent')):
                if path=='/console': path+='?after='+str(self.console_cursor)+('&epoch='+self.console_epoch if self.console_epoch else '')
                r = client.get(receipt['runner_url'] + '/v1' + path); r.raise_for_status()
                value = r.json()
                if key == 'recent':
                    result['executions'] = value['executions']
                    result['execution_paths'] = value.get('execution_paths', [])
                else:
                    result[key] = value; self.console_cursor=value.get('cursor',0); self.console_epoch=value.get('epoch')
            r = client.post(receipt['dashboard_url'] + '/api/v1/gui-test/live/connector/register',
                            json={'url': 'http://127.0.0.1:' + str(receipt['remote_runner_port']), 'runner_id': receipt['runner_id']})
            if r.status_code != 200:
                result['stages']['roundtrip'] = 'REGISTRATION_FAILED'; result['state'] = 'ERROR'
                result['error'] = '역방향 등록 실패 HTTP ' + str(r.status_code)
            else:
                result['server_paths'] = r.json().get('server_paths')
                try:
                    from .shared_control import request, remember_desired, acknowledge
                    shared = request(self.home, 'settings')
                    result['shared_settings'] = shared
                    application = shared.get('connector_application', {})
                    remember_desired(self.home, application, receipt['runner_id'])
                    acknowledge(self.home, application, inventory)
                    result['analyses'] = request(self.home, 'analyses')
                except Exception as exc:
                    result['shared_error'] = redact(str(exc))
                result['stages'].update(dashboard='READY', roundtrip='READY'); result['state'] = 'CONNECTED'; result['source_ready']=r.json().get('source_ready',False)
        return result

    def serial_control(self, board_id, manual):
        from ..execution.launch import read_active
        import httpx
        receipt = read_active(self.home/'runtime')
        if not receipt: raise TestError('보드를 먼저 연결하세요.', 'SERIAL_UNAVAILABLE', 409)
        with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
            response = client.post(receipt['runner_url']+'/v1/serial-control', json={'board_id':board_id, 'manual':manual})
            if response.status_code != 200: raise TestError(redact(response.text), 'SERIAL_BUSY', 409)
            return response.json()

    def open_putty(self, board_id):
        import shutil
        value = self.probe()
        board = next((b for b in value['boards'] if b['board_id'] == board_id), None)
        proxy = board.get('serial_proxy', {}) if board else {}
        port = proxy.get('putty_port')
        if proxy.get('state') != 'READY' or type(port) is not int or not 1 <= port <= 65535:
            raise TestError('보드 프록시가 준비되지 않았습니다.', 'SERIAL_UNAVAILABLE', 409)
        if proxy.get('putty_connected'): raise TestError('이 보드의 PuTTY 연결이 이미 열려 있습니다.', 'SERIAL_BUSY', 409)
        configured = self.settings.read().get('putty_path')
        candidates = [configured, shutil.which('putty.exe')]
        for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            if os.environ.get(variable): candidates.append(str(Path(os.environ[variable])/'PuTTY'/'putty.exe'))
        executable = next((p for p in candidates if p and Path(p).is_file()), None)
        if not executable: raise TestError('PuTTY를 찾을 수 없습니다. 고급 연결 설정에서 putty.exe를 선택하세요.', 'PUTTY_NOT_FOUND')
        subprocess.Popen([executable, '-raw', '127.0.0.1', '-P', str(port)], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return {'opened':True}

    def disconnect(self):
        with self.control_lock:
            return self._disconnect()

    def _disconnect(self):
        value = self.probe()
        if any(b['state'] in {'RUNNING', 'UNKNOWN', 'RESERVED'} for b in value['boards']):
            raise TestError('진행·예약·종료 불명 작업이 있어 연결을 종료할 수 없습니다.', 'CONNECTOR_BUSY', 409)
        if value.get('dashboard_url'):
            import httpx
            with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
                response = client.get(value['dashboard_url'] + '/api/v1/gui-test/live/connector/stop-readiness')
                response.raise_for_status()
                if response.json().get('safe') is not True: raise TestError('대시보드 예약·일시정지·삭제가 남아 있습니다.', 'CONNECTOR_BUSY', 409)
        elif self.thread and self.thread.is_alive():
            raise TestError('연결 준비 상태를 확인한 후 종료하세요.', 'CONNECTOR_BUSY', 409)
        if value.get('dashboard_url'):
            from ..execution.launch import read_active
            receipt = read_active(self.home/'runtime')
            with httpx.Client(timeout=3,trust_env=False,follow_redirects=False) as client:
                response=client.post(receipt['runner_url']+'/v1/connection-stop')
                response.raise_for_status()
        self.stop_event.set()
        return {'state': 'DISCONNECTING'}


def serve(home):
    if os.name != 'nt': raise SystemExit('Production connector requires Windows; use --preview on Mac')
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from scripts.setup_runtime import TokenStore, atomic_write
    home = Path(home)
    with LaunchLock(home / 'runtime' / 'connector-manager.lock'):
        credentials = TokenStore(home / 'manager-control', True)
        if not credentials.path.exists(): credentials.save(secrets.token_urlsafe(48))
        token = credentials.load()
        manager = Manager(home)
        listener = bind_loopback(8773, allow_fallback=True)
        app = create_manager_app(manager, token, browser_origin='http://127.0.0.1:' + str(listener.getsockname()[1]))
        atomic_write(home / 'runtime' / 'connector-manager.json', json.dumps({'owner': process_identity(os.getpid()), 'port': listener.getsockname()[1]}).encode())
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', access_log=False, log_level='warning'))
        server.run(sockets=[listener])


def create_manager_app(manager, token, *, browser_origin=None):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    if not hasattr(manager, 'control_lock'):
        manager.control_lock = threading.RLock()
    from .web import BrowserUI
    from .web_actions import ManagerActions, save_profile
    browser = BrowserUI(ManagerActions(manager), browser_origin) if browser_origin else None
    app.state.browser_ui = browser
    @app.middleware('http')
    async def auth(request: Request, call_next):
        if browser and request.url.path.startswith('/ui/'):
            return await browser.guard(request, call_next)
        if (request.client.host not in {'127.0.0.1', '::1'} or request.headers.get('origin') or request.headers.get('sec-fetch-site') or
                not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + token)):
            return JSONResponse({'message': 'Manager authentication required'}, status_code=401)
        length=request.headers.get('content-length','0')
        if not length.isdigit() or int(length)>65536: return JSONResponse({},status_code=413)
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>65536: return JSONResponse({},status_code=413)
        request._body=bytes(data)
        return await call_next(request)
    @app.exception_handler(TestError)
    async def error(request, exc): return JSONResponse({'code': exc.code, 'message': exc.message}, status_code=exc.status)
    @app.get('/status')
    def status(): return manager.status()
    @app.get('/settings')
    def settings(): return manager.settings.read()
    @app.post('/settings')
    def save(body: dict):
        return save_profile(manager, body)
    @app.post('/browser-ticket')
    def browser_ticket():
        if not browser:
            raise TestError('웹 화면을 지원하는 커넥터 Manager로 업데이트하세요. 기존 작업은 유지됩니다.', 'BROWSER_UNAVAILABLE', 409)
        return browser.ticket()
    @app.get('/shared-settings')
    def shared_settings():
        from .shared_control import request
        return request(manager.home, 'settings')
    @app.post('/shared-settings')
    def save_shared_settings(body: dict):
        from .shared_control import request
        return request(manager.home, 'settings', 'PUT', body)
    @app.get('/storage-policy')
    def storage_policy():
        from .shared_control import request
        return request(manager.home, 'storage-policy')
    @app.post('/storage-policy')
    def save_storage_policy(body: dict):
        from .shared_control import request
        return request(manager.home, 'storage-policy', 'PUT', body)
    @app.post('/storage-cleanup')
    def storage_cleanup(body: dict):
        from .shared_control import request
        return request(manager.home, 'storage-cleanup', 'POST', body)
    @app.post('/server-paths')
    def server_paths(body: dict):
        from .shared_control import paths
        if set(body) - {'kind', 'path'}: raise TestError('Invalid server path request', status=422)
        return paths(manager.home, body.get('kind'), body.get('path', ''))
    @app.post('/connect')
    def connect(): return manager.connect()
    @app.post('/serial-control')
    def serial_control(body: dict):
        if set(body) != {'board_id','manual'} or type(body['manual']) is not bool: raise TestError('Invalid control request', status=422)
        return manager.serial_control(body['board_id'], body['manual'])
    @app.post('/putty')
    def putty(body: dict):
        if set(body) != {'board_id'}: raise TestError('Invalid PuTTY request', status=422)
        return manager.open_putty(body['board_id'])
    @app.post('/disconnect')
    def disconnect(): return manager.disconnect()
    if browser:
        browser.routes(app)
    return app


class Client:
    preview = False
    def __init__(self, home): self.home = Path(home)
    def request(self, path, data=None):
        from scripts.setup_runtime import TokenStore
        import httpx
        from ..execution.launch import _lock_held
        if not _lock_held(self.home/'runtime'/'connector-manager.lock'): raise TestError('Manager receipt is stale','CONNECTOR_STALE')
        receipt = json.loads((self.home / 'runtime' / 'connector-manager.json').read_text())
        if process_identity(receipt['owner']['pid']) != receipt['owner']: raise TestError('Manager receipt is stale', 'CONNECTOR_STALE')
        token = TokenStore(self.home / 'manager-control', True).load(readonly=True)
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
            try: response = client.request('GET' if data is None else 'POST', 'http://127.0.0.1:' + str(receipt['port']) + path,
                                      headers={'Authorization': 'Bearer ' + token}, **({'json': data} if data is not None else {}))
            except httpx.HTTPError as exc: raise TestError('Manager connection failed; check its log','CONNECTOR_UNAVAILABLE') from exc
            if response.status_code != 200:
                try: detail = response.json()
                except ValueError: detail = {}
                raise TestError(redact(detail.get('message', response.text)), detail.get('code', 'CONNECTOR_REQUEST'), response.status_code)
            return response.json()
    def status(self): return self.request('/status')
    def settings(self): return self.request('/settings')
    def save(self, value): return self.request('/settings', value)
    def browser_ticket(self):
        try:
            value = self.request('/browser-ticket', {})
        except TestError as exc:
            if exc.status != 404 and exc.code != 'BROWSER_UNAVAILABLE':
                raise
            raise TestError('실행 중인 Manager의 웹 화면을 열지 못했습니다. 기존 작업을 완료한 뒤 커넥터를 안전 종료하고 같은 버전으로 다시 시작하세요. 작업을 강제 종료하거나 두 번째 Manager를 만들지 않습니다.', 'BROWSER_UNAVAILABLE', 409) from exc
        if value.get('capability') != 'connector_browser_v1':
            raise TestError('Manager의 웹 화면 버전이 일치하지 않습니다.', 'BROWSER_UNAVAILABLE', 409)
        return value
    def storage_policy(self): return self.request('/storage-policy')
    def save_storage_policy(self, value): return self.request('/storage-policy', value)
    def cleanup_snapshots(self, *, dry_run=True): return self.request('/storage-cleanup', {'dry_run': dry_run})
    def shared_settings(self): return self.request('/shared-settings')
    def save_shared_settings(self, value): return self.request('/shared-settings', value)
    def server_paths(self, kind, path=''): return self.request('/server-paths', {'kind': kind, 'path': path})
    def connect(self): return self.request('/connect', {})
    def disconnect(self): return self.request('/disconnect', {})
    def manual(self, board_id, enabled): return self.request('/serial-control', {'board_id':board_id, 'manual':enabled})
    def putty(self, board_id): return self.request('/putty', {'board_id':board_id})
    def ports(self):
        from ..adapters.windows_ports import enumerate_ports
        return enumerate_ports()['ports']


def ensure_manager(home):
    if os.name != 'nt': raise TestError('Windows production only. Mac: --preview', 'WINDOWS_REQUIRED')
    client = Client(home)
    try: client.settings(); return client
    except (OSError, ValueError, TestError): pass
    subprocess.Popen([sys.executable, '-B', '-m', __package__ + '.supervisor', '--home', str(home)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
    for _ in range(100):
        try: client.settings(); return client
        except (OSError, ValueError, TestError): time.sleep(.1)
    raise TestError('Manager did not start. Check dependencies and user profile.', 'CONNECTOR_START')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--home', required=True)
    serve(parser.parse_args().home)
