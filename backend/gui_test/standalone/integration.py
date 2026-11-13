"""GUI-only persistent real-hardware host; contains no BSP scheduler imports."""
import argparse
from contextlib import asynccontextmanager
import ipaddress
import json
import hashlib
import secrets
import time
from pathlib import Path
import threading

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from urllib.parse import parse_qs
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .server import ProcessLock
from ..api.router import router
from ..core.integration import CONTRACT_VERSION
from ..core.models import TestError, digest, now, uid
from ..core.worker import Worker
from ..runtime import make_manager

PACKAGE_VERSION = '0.1.0'


class ServiceRegistry:
    def __init__(self, manager, runtime, principal):
        self.manager = manager
        self.runtime_id = digest(str(Path(runtime).resolve()))
        with manager.store.transaction() as c:
            c.execute("INSERT OR IGNORE INTO meta VALUES('integration_service_instance',?)", (uid(),))
            self.instance = c.execute("SELECT value FROM meta WHERE key='integration_service_instance'").fetchone()[0]
        self.principal = principal
        self.epoch = None

    def start(self):
        # Called only while holding the OS worker lock, never from HTTP health.
        with self.manager.store.transaction() as c:
            row = c.execute("SELECT value FROM meta WHERE key='integration_worker_epoch'").fetchone()
            self.epoch = int(row[0]) + 1 if row else 1
            c.execute("INSERT INTO meta VALUES('integration_worker_epoch',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(self.epoch),))

    def snapshot(self, running):
        cfg = self.manager.integration.frozen_config()
        return {'status': 'ok' if running else 'degraded', 'mode': 'integration', 'simulation': self.manager.simulation,
                'runtime_id': self.runtime_id, 'service_instance_id': self.instance, 'package_version': PACKAGE_VERSION,
                'integration_contract_version': CONTRACT_VERSION, 'config_revision': cfg['config_revision'],
                'controller_principal_id': self.principal, 'worker_epoch': self.epoch, 'runner_id': cfg['runner_id'],
                'worker_running': running}


def create_app(runtime, token=None, principal='bsp-upgrade', *, manager=None, start_worker=True, static_dir=None):
    if not principal or len(principal) > 100:
        raise ValueError('Configure a stable integration principal')
    manager = manager or make_manager(runtime, 'integration')
    if getattr(manager, 'integration', None) is None:
        raise ValueError('IntegrationService must be configured')
    manager.integration.controller_resolver = lambda target: target == principal
    registry = ServiceRegistry(manager, runtime, principal)
    stop = threading.Event()

    def browser_session(value):
        if not value:
            return False
        key = hashlib.sha256(value.encode()).hexdigest()
        with manager.store.connection() as c:
            row = c.execute("SELECT data FROM documents WHERE kind='integration-browser-session' AND name=?", (key,)).fetchone()
        return bool(row and json.loads(row[0])['expires_at'] > time.time())

    @asynccontextmanager
    async def lifespan(app):
        if not start_worker:
            yield
            return
        # Same database lock is used by the Dashboard GUI worker when attached.
        with ProcessLock(manager.store.path.with_suffix('.lock')):
            registry.start()
            manager.recover()
            worker = Worker(manager)
            def loop():
                app.state.worker_running = True
                try:
                    while not stop.wait(.1):
                        worker.tick()
                except Exception:
                    app.state.worker_error = True
                finally:
                    app.state.worker_running = False
                    worker.close()
            thread = threading.Thread(target=loop, name='gui-integration-worker', daemon=False)
            thread.start()
            try:
                yield
            finally:
                stop.set()
                thread.join()  # Active flash supervision is never killed on shutdown.

    app = FastAPI(title='GUI Test integration', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager
    app.state.registry = registry
    app.state.worker_running = False
    app.state.worker_error = False
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])

    @app.exception_handler(TestError)
    async def error(request, exc):
        return JSONResponse({'code': exc.code, 'message': exc.message,
                             **({'diagnostic': exc.diagnostic} if getattr(exc, 'diagnostic', None) else {})}, status_code=exc.status)

    @app.middleware('http')
    async def boundary(request, call_next):
        try:
            peer = ipaddress.ip_address(request.client.host)
            local = peer.is_loopback or bool(getattr(peer, 'ipv4_mapped', None) and peer.ipv4_mapped.is_loopback)
        except (ValueError, AttributeError):
            local = False
        if not local:
            return JSONResponse({'message': 'Loopback/SSH tunnel required'}, status_code=403)
        if request.url.path.startswith('/api/'):
            service_request = request.headers.get('x-bsp-service') == 'plugin'
            viewer = not service_request and browser_session(request.cookies.get('gui_test_viewer'))
            if service_request and (request.headers.get('origin') or request.headers.get('sec-fetch-site')):
                return JSONResponse({'message': 'Plugin requests require a non-browser client'}, status_code=403)
            if not service_request and not viewer:
                return JSONResponse({'message': 'Use the plugin client or read-only browser session'}, status_code=401)
            if viewer:
                origin = request.headers.get('origin')
                if ((origin and origin != str(request.base_url).rstrip('/')) or
                        request.headers.get('sec-fetch-site') in {'cross-site', 'same-site'}):
                    return JSONResponse({'message': 'Cross-origin browser request rejected'}, status_code=403)
                if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                    return JSONResponse({'message': 'Browser session is read-only'}, status_code=403)
            if service_request:
                request.state.gui_principal = principal
            if request.method not in {'GET', 'HEAD', 'OPTIONS'} and '/integration/' not in request.url.path:
                return JSONResponse({'message': 'Use the integration contract for service mutations'}, status_code=403)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 65536:
                return JSONResponse({'message': 'Request too large'}, status_code=413)
        request._body = bytes(data)
        response = await call_next(request)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'})
        response.headers.setdefault('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'")
        return response

    @app.get('/api/v1/health')
    def health():
        return registry.snapshot(app.state.worker_running and not app.state.worker_error)

    @app.post('/api/v1/gui-test/live/integration/browser-session')
    def create_browser_session():
        grant = secrets.token_urlsafe(32)
        key = hashlib.sha256(grant.encode()).hexdigest()
        with manager.store.transaction() as c:
            manager.integration._write(c, 'integration-browser-grant', key, {'expires_at': time.time() + 60})
        return {'bootstrap_code': grant, 'expires_in': 60, 'path': '/auth#' + grant, 'access': 'read-only'}

    @app.get('/auth')
    def browser_login():
        # Fragment is never sent to HTTP logs/referrers. It is consumed once,
        # immediately removed from the URL, and exchanged for an HttpOnly cookie.
        return HTMLResponse('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>GUI Test access</title><body><h1>GUI Test details</h1><form method="post" action="/auth/session"><label>One-time access code <input name="code" type="password" autocomplete="off" required></label><button>Open read-only details</button></form><script>const code=location.hash.slice(1);history.replaceState(null,'','/auth');if(code){document.querySelector('input').value=code;document.querySelector('form').submit();}</script></body></html>''',
                            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                     'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"})

    @app.post('/auth/session')
    async def exchange_browser_grant(request: Request):
        if request.headers.get('origin') != str(request.base_url).rstrip('/'):
            return JSONResponse({'message': 'Same-origin form required'}, status_code=403)
        code = parse_qs((await request.body()).decode('utf-8', errors='replace')).get('code', [''])[0]
        if len(code) > 128:
            return JSONResponse({'message': 'Invalid access code'}, status_code=401)
        key = hashlib.sha256(code.encode()).hexdigest()
        session = secrets.token_urlsafe(32)
        with manager.store.transaction() as c:
            row = c.execute("SELECT data FROM documents WHERE kind='integration-browser-grant' AND name=?", (key,)).fetchone()
            if not row or json.loads(row[0])['expires_at'] <= time.time():
                return JSONResponse({'message': 'Access code is expired or already used'}, status_code=401)
            c.execute("DELETE FROM documents WHERE kind='integration-browser-grant' AND name=?", (key,))
            manager.integration._write(c, 'integration-browser-session', hashlib.sha256(session.encode()).hexdigest(),
                                       {'expires_at': time.time() + 1800})
        response = RedirectResponse('/?guiExecution=live', status_code=303)
        response.set_cookie('gui_test_viewer', session, max_age=1800, httponly=True, samesite='strict', path='/')
        return response

    app.include_router(router(manager, live=True))
    app.include_router(router(manager))  # Both existing UI execution views are read-only.
    static = Path(static_dir).resolve(strict=True) if static_dir is not None else Path(__file__).resolve().parents[1] / 'static'
    if static.exists():
        app.mount('/', StaticFiles(directory=static, html=True))
    return app


def main(argv=None):
    import uvicorn
    parser = argparse.ArgumentParser(description='Persistent GUI-only BSP plugin backend')
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--principal', default='bsp-upgrade')
    parser.add_argument('--static-dir')
    args = parser.parse_args(argv)
    uvicorn.run(create_app(args.runtime, principal=args.principal,
                           static_dir=args.static_dir), host='127.0.0.1', port=args.port,
                access_log=False, proxy_headers=False)


if __name__ == '__main__':
    main()
