"""Loopback browser UI sessions, isolated from the manager's bearer IPC."""
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from ..core.models import TestError
from .logs import redact

ASSETS = {'host.mjs': 'text/javascript', 'view.mjs': 'text/javascript', 'style.css': 'text/css'}


def asset_file(name):
    if name not in {*ASSETS, 'index.html'}:
        raise TestError('Unknown UI asset', status=404)
    installed = Path(__file__).parent / 'web_assets' / name
    if installed.is_file():
        return installed
    shared = Path(__file__).resolve().parents[3] / 'packages/gui-test-ui/src/connector_web' / name
    if shared.is_file():
        return shared
    raise TestError('웹 화면 파일이 없습니다. 전체 소스 또는 같은 버전 배포본을 갱신하세요.', 'UI_ASSET_MISSING', 503)


class BrowserUI:
    def __init__(self, actions, origin, clock=time.monotonic):
        parsed = urlsplit(origin)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.port is None or parsed.path:
            raise ValueError('Browser UI requires an exact loopback origin and port')
        self.actions, self.origin, self.clock = actions, origin, clock
        self.instance = secrets.token_hex(12)
        self.prefix = '/ui/' + self.instance
        self.cookie = 'bcui_' + self.instance
        self.lock = threading.RLock()
        self.tickets, self.sessions = {}, {}

    def _prune(self):
        current = self.clock()
        self.tickets = {k: v for k, v in self.tickets.items() if v > current}
        self.sessions = {k: v for k, v in self.sessions.items() if v['until'] > current}

    def ticket(self):
        for name in ('index.html', *ASSETS):
            asset_file(name)
        with self.lock:
            self._prune()
            if len(self.tickets) >= 16:
                self.tickets.pop(next(iter(self.tickets)))
            ticket = secrets.token_urlsafe(32)
            self.tickets[ticket] = self.clock() + 60
        return {'url': self.origin + self.prefix + '/#ticket=' + ticket, 'capability': 'connector_browser_v1'}

    def session(self, request):
        with self.lock:
            self._prune()
            return self.sessions.get(request.cookies.get(self.cookie, ''))

    async def guard(self, request, call_next):
        def denied(message='브라우저 세션이 만료됐습니다. CMD로 화면을 다시 여세요.', code=401):
            return self.headers(JSONResponse({'code': 'BROWSER_AUTH', 'message': message}, status_code=code))
        if (request.client is None or request.client.host not in {'127.0.0.1', '::1'} or
                request.headers.get('host') != urlsplit(self.origin).netloc or
                str(request.url).split('/ui/', 1)[0] != self.origin):
            return denied('허용되지 않은 접속 주소입니다.', 403)
        if not request.url.path.startswith(self.prefix + '/'):
            return denied('현재 Manager의 화면 주소가 아닙니다.', 404)
        origin = request.headers.get('origin')
        site = request.headers.get('sec-fetch-site')
        if (origin is not None and origin != self.origin) or site not in {None, 'same-origin', 'none'}:
            return denied('다른 사이트의 요청은 허용하지 않습니다.', 403)
        relative = request.url.path[len(self.prefix):]
        public = request.method == 'GET' and relative in {'/', *( '/' + name for name in ASSETS)}
        redeem = request.method == 'POST' and relative == '/session'
        session = self.session(request)
        if not public and not redeem and session is None:
            return denied()
        if request.method not in {'GET', 'HEAD'}:
            if origin != self.origin or site not in {None, 'same-origin'} or request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return denied('쓰기 요청의 출처를 확인할 수 없습니다.', 403)
            if not redeem and (session is None or not secrets.compare_digest(request.headers.get('x-connector-csrf', '').encode('utf-8'), session['csrf'].encode('utf-8'))):
                return denied('요청 확인값이 다릅니다. 화면을 새로 고치세요.', 403)
        length = request.headers.get('content-length', '0')
        if not length.isdigit() or int(length) > 65536:
            return denied('요청 크기가 너무 큽니다.', 413)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 65536:
                return denied('요청 크기가 너무 큽니다.', 413)
        request._body = bytes(data)
        try:
            response = await call_next(request)
        except TestError as exc:
            response = JSONResponse({'code': exc.code, 'message': redact(exc.message)}, status_code=exc.status)
        return self.headers(response)

    @staticmethod
    def headers(response):
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
                                 'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
        return response

    def routes(self, app):
        @app.get(self.prefix + '/')
        def index():
            return HTMLResponse(asset_file('index.html').read_text(encoding='utf-8'))

        @app.get(self.prefix + '/{name}')
        def asset(name: str):
            if name not in ASSETS:
                raise TestError('Unknown UI asset', status=404)
            return Response(asset_file(name).read_bytes(), media_type=ASSETS[name])

        @app.post(self.prefix + '/session')
        def redeem(body: dict, request: Request):
            if set(body) != {'ticket'} or not isinstance(body['ticket'], str):
                raise TestError('Invalid browser ticket', status=422)
            with self.lock:
                self._prune()
                if self.tickets.pop(body['ticket'], None) is None:
                    raise TestError('화면 열기 요청이 만료됐습니다. CMD를 다시 실행하세요.', 'BROWSER_TICKET', 401)
                # Cookies are shared by tabs. A newly opened tab must not rotate
                # the existing tab's session/CSRF or destroy an unsaved form.
                session = request.cookies.get(self.cookie, '')
                existing = self.sessions.get(session)
                if existing:
                    csrf = existing['csrf']
                    existing['until'] = self.clock() + 8 * 3600
                else:
                    if len(self.sessions) >= 32:
                        self.sessions.pop(next(iter(self.sessions)))
                    session = secrets.token_urlsafe(32)
                    csrf = secrets.token_urlsafe(32)
                    self.sessions[session] = {'csrf': csrf, 'until': self.clock() + 8 * 3600}
            response = JSONResponse({'csrf': csrf, 'preview': self.actions.preview})
            response.set_cookie(self.cookie, session, path=self.prefix + '/', httponly=True, samesite='strict', max_age=8 * 3600)
            return response

        @app.get(self.prefix + '/api/session')
        def current(request: Request):
            return {'csrf': self.session(request)['csrf'], 'preview': self.actions.preview}

        @app.get(self.prefix + '/api/status')
        def status(): return self.actions.status()

        @app.get(self.prefix + '/api/settings')
        def settings(): return self.actions.settings()

        @app.post(self.prefix + '/api/settings')
        def save(body: dict): return self.actions.save(body)

        @app.get(self.prefix + '/api/ports')
        def ports(): return self.actions.ports()

        @app.post(self.prefix + '/api/action')
        def action(body: dict):
            if set(body) != {'action', 'payload'} or not isinstance(body['action'], str) or not isinstance(body['payload'], dict):
                raise TestError('Invalid browser action', status=422)
            return self.actions.action(body['action'], body['payload'])

        @app.post(self.prefix + '/api/pick')
        def pick(body: dict): return self.actions.pick(body)

        @app.get(self.prefix + '/api/storage')
        def storage(): return self.actions.storage()

        @app.post(self.prefix + '/api/storage')
        def save_storage(body: dict): return self.actions.storage(body)

        @app.post(self.prefix + '/api/storage-cleanup')
        def clean_storage(body: dict): return self.actions.storage(body, cleanup=True)

        @app.get(self.prefix + '/api/shared')
        def shared(): return self.actions.shared()

        @app.post(self.prefix + '/api/shared')
        def save_shared(body: dict): return self.actions.shared(body)

        @app.post(self.prefix + '/api/server-paths')
        def paths(body: dict): return self.actions.server_paths(body)


def preview_app(adapter, origin, clock=time.monotonic):
    from fastapi import FastAPI
    from .web_actions import PreviewActions
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    ui = BrowserUI(PreviewActions(adapter), origin, clock)
    app.middleware('http')(ui.guard)
    @app.exception_handler(TestError)
    async def error(request, exc):
        return JSONResponse({'code': exc.code, 'message': redact(exc.message)}, status_code=exc.status)
    ui.routes(app)
    app.state.browser_ui = ui
    return app


def open_browser(url):
    import webbrowser
    if not webbrowser.open(url):
        raise TestError('기본 브라우저를 열지 못했습니다. Windows 기본 브라우저를 설정한 뒤 CMD를 다시 실행하세요. 기존 작업은 계속됩니다.', 'BROWSER_OPEN_FAILED')


def run_preview(home):
    import uvicorn
    from ..execution.launch import bind_loopback
    from .preview import MockConnector
    listener = bind_loopback(0, allow_fallback=False)
    origin = 'http://127.0.0.1:' + str(listener.getsockname()[1])
    app = preview_app(MockConnector(home), origin)
    url = app.state.browser_ui.ticket()['url']
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', access_log=False, log_level='warning'))
    errors = []
    def launch():
        try:
            open_browser(url)
        except Exception as exc:
            errors.append(exc)
            server.should_exit = True
    timer = threading.Timer(.5, launch)
    timer.daemon = True
    timer.start()
    try:
        server.run(sockets=[listener])
        if errors:
            raise errors[0]
    finally:
        timer.cancel()
