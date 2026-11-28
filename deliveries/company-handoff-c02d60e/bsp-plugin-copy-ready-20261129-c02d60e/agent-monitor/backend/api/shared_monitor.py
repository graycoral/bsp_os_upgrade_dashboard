"""Task-only Monitor. The Windows Host is the authority for every read."""
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time

import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.gui_test.core.monitor_identity import CHALLENGE, TOKEN, monitor_proof, redeem_proof

ASSETS = Path(__file__).with_name('shared_monitor_assets')
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
BEARER = re.compile(r'[A-Za-z0-9_.~-]{16,512}')


def create_shared_monitor(runtime, monitor_id, connector_port, *, monitor_token, protected_listener=False, transport=None,
                          socket_path=None, socket_owner_uid=None, trust_protected_loopback=False):
    if not isinstance(monitor_id, str) or not IDENTIFIER.fullmatch(monitor_id):
        raise ValueError('Invalid shared Monitor identity')
    if type(connector_port) is not int or not 1 <= connector_port <= 65535:
        raise ValueError('Invalid shared Monitor connector port')
    if not isinstance(monitor_token, str) or not TOKEN.fullmatch(monitor_token):
        raise ValueError('Invalid shared Monitor installation credential')
    if protected_listener is not True:
        raise ValueError('The shared Monitor requires explicit approval of its protected listener.')
    if transport is None and bool(socket_path) == bool(trust_protected_loopback):
        raise ValueError('Choose a protected Host socket or explicitly approve an isolated loopback TCP transport.')
    if socket_path and (os.name != 'posix' or not Path(socket_path).is_absolute()):
        raise ValueError('The shared Host socket must be an absolute path on Unix.')
    if socket_owner_uid is not None and (type(socket_owner_uid) is not int or socket_owner_uid < 0):
        raise ValueError('The shared Host socket owner must be a valid Unix UID.')
    app = FastAPI(title='Agent Monitor', docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])
    host = f'http://127.0.0.1:{connector_port}/v1/sharing'
    views = {}
    views_lock = threading.Lock()

    def unavailable(message, status):
        return JSONResponse({'message': message}, status_code=status)

    @app.middleware('http')
    async def browser_limits(request, call_next):
        try:
            peer = ipaddress.ip_address(request.client.host)
            local = peer.is_loopback or bool(getattr(peer, 'ipv4_mapped', None) and peer.ipv4_mapped.is_loopback)
        except (ValueError, AttributeError):
            local = False
        origin = request.headers.get('origin')
        if (not local or (origin and origin != str(request.base_url).rstrip('/'))
                or request.headers.get('sec-fetch-site') in {'cross-site', 'same-site'} and
                request.url.path.startswith('/api/v1/plugin-task/')):
            response = unavailable('작업 Monitor에 접근할 수 없습니다.', 403)
        else:
            response = await call_next(request)
        response.headers.update({
            'Cache-Control': 'no-store',
            'Referrer-Policy': 'no-referrer',
            'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        })
        return response

    def host_call(method, path, *, body=None, token=None):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        try:
            request_transport = transport
            if socket_path:
                from backend.gui_test.core.shared_transport import shared_uds_transport
                uid = socket_owner_uid if socket_owner_uid is not None else os.geteuid()
                request_transport = shared_uds_transport(socket_path, uid)
            with httpx.Client(timeout=3, trust_env=False, follow_redirects=False, transport=request_transport) as client:
                reply = client.request(method, host + path, json=body, headers=headers)
            if reply.status_code in {400, 401, 403, 404, 409, 410, 422}:
                return None, 403
            reply.raise_for_status()
            result = reply.json()
            if not isinstance(result, dict):
                return None, 503
            return result, 200
        except (httpx.HTTPError, OSError, ValueError):
            return None, 503

    def view_access(request, *identifiers):
        scheme, _, token = request.headers.get('authorization', '').partition(' ')
        if scheme.lower() == 'bearer' and BEARER.fullmatch(token) and all(
                IDENTIFIER.fullmatch(value) for value in identifiers):
            with views_lock:
                view = views.get(token)
                if view and view[2] <= time.time():
                    views.pop(token)
                    view = None
            return (view[1], 200) if view and view[0] == identifiers[0] else (None, 403)
        return None, 401

    def blocked_view(status):
        return (unavailable('작업 권한 서버에 연결할 수 없습니다.', 503) if status == 503 else
                unavailable('현재 작업의 조회 권한이 없습니다. 커넥터에서 다시 여세요.', 403))

    @app.get('/api/v1/health')
    def health(request: Request):
        result = {'status': 'ok', 'mode': 'shared-task-monitor', 'monitor_id': monitor_id}
        challenge = request.headers.get('x-bsp-monitor-challenge', '')
        if CHALLENGE.fullmatch(challenge):
            result['monitor_proof'] = monitor_proof(monitor_token, monitor_id, challenge)
        instance = os.environ.get('AGENT_MONITOR_INSTANCE')
        if instance and request.headers.get('x-bsp-service') == 'plugin' and hmac.compare_digest(
                request.headers.get('x-bsp-monitor-instance', '').encode(), instance.encode()):
            release = os.environ.get('AGENT_MONITOR_RELEASE')
            result.update(managed_instance=instance,
                          managed_release=release, managed_runtime=str(runtime),
                          managed_source=str(Path(__file__).resolve().parents[2]) if release else None)
        return result

    @app.api_route('/plugin-task/', methods=['GET', 'HEAD'])
    def view_page():
        return FileResponse(ASSETS / 'index.html')

    @app.get('/plugin-task/{asset}')
    def asset_file(asset: str):
        media = {'task.mjs': 'text/javascript', 'style.css': 'text/css'}.get(asset)
        return FileResponse(ASSETS / asset, media_type=media) if media else unavailable('페이지를 찾을 수 없습니다.', 404)

    @app.post('/api/v1/plugin-task/{task_id}/session')
    async def redeem(task_id: str, request: Request):
        if (not IDENTIFIER.fullmatch(task_id) or request.headers.get('origin') != str(request.base_url).rstrip('/')
                or request.headers.get('content-type', '').split(';')[0] != 'application/json'):
            return unavailable('작업 열기 요청이 유효하지 않습니다.', 403)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > 1024:
                return unavailable('작업 열기 요청이 유효하지 않습니다.', 413)
            body.extend(chunk)
        try:
            data = json.loads(body)
            ticket = data.get('ticket') if isinstance(data, dict) else None
        except (ValueError, UnicodeError):
            ticket = None
        if not isinstance(ticket, str) or not BEARER.fullmatch(ticket):
            return unavailable('작업 열기 요청이 유효하지 않습니다.', 403)
        from starlette.concurrency import run_in_threadpool
        proof = redeem_proof(monitor_token, monitor_id, ticket)
        result, status = await run_in_threadpool(host_call, 'POST', '/view-tickets/redeem',
                                                 body={'ticket': ticket, 'monitor_id': monitor_id, 'task_id': task_id,
                                                       'monitor_proof': proof})
        if status == 503:
            return unavailable('작업 권한 서버에 연결할 수 없습니다.', 503)
        token = (result or {}).get('view_token')
        expiry = (result or {}).get('expires_at')
        if (not isinstance(token, str) or not BEARER.fullmatch(token)
                or type(expiry) not in {int, float} or not time.time() < expiry <= time.time() + 1200
                or result.get('monitor_id') != monitor_id or result.get('task_id') != task_id):
            return unavailable('작업 열기 권한이 만료되었거나 거부되었습니다. 커넥터에서 다시 여세요.', 403)
        session = secrets.token_urlsafe(32)
        with views_lock:
            for previous in [key for key, view in views.items() if view[2] <= time.time()]:
                del views[previous]
            if len(views) >= 512:
                views.pop(next(iter(views)))
            views[session] = task_id, token, expiry
        return {'view_token': session}

    @app.get('/api/v1/plugin-task/{task_id}')
    def read_task(task_id: str, request: Request, run_id: str | None = None):
        token, access_status = view_access(request, task_id, *([run_id] if run_id is not None else []))
        if token is None:
            return unavailable('해당 작업의 열기 권한이 필요합니다.', access_status)
        path = '/tasks/' + task_id + '/view' + ('?run_id=' + run_id if run_id else '')
        result, status = host_call('GET', path, token=token)
        task = (result or {}).get('task')
        if not isinstance(task, dict) or task.get('task_id') != task_id or task.get('monitor_id') != monitor_id:
            return blocked_view(status)
        return result

    @app.get('/api/v1/plugin-task/{task_id}/runs/{run_id}/attempts/{attempt_id}/logs')
    def read_log(task_id: str, run_id: str, attempt_id: str, request: Request,
                 stream: str = 'stdout', offset: int = Query(0, ge=0, le=2**53 - 1)):
        token, access_status = view_access(request, task_id, run_id, attempt_id)
        if not token or stream not in {'stdout', 'stderr'}:
            return unavailable('해당 작업의 로그 조회 권한이 필요합니다.', access_status if not token else 422)
        path = f'/tasks/{task_id}/view/runs/{run_id}/attempts/{attempt_id}/logs?stream={stream}&offset={offset}&limit=32768'
        result, status = host_call('GET', path, token=token)
        if (not result or result.get('monitor_id') != monitor_id or result.get('run_id') != run_id
                or result.get('attempt_id') != attempt_id):
            return blocked_view(status)
        return result

    return app
