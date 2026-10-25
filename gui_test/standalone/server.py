import argparse
import ipaddress
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from gui_test.api.router import router
from gui_test.core.models import TestError, digest
from gui_test.core.worker import Worker
from gui_test.runtime import make_manager


class ProcessLock:
    """OS-owned lock: released by process death, no stale PID expiration guesses."""
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('a+b')
        self.file.seek(0)
        if os.name == 'nt':
            import msvcrt
            self.file.write(b'0'); self.file.flush(); self.file.seek(0)
            try:
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self.file.close()
                raise RuntimeError('GUI Test manager already running')
        else:
            import fcntl
            try:
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.file.close()
                raise RuntimeError('GUI Test manager already running')
        return self

    def __exit__(self, *args):
        self.file.close()


def create_app(runtime, start_worker=True):
    manager = make_manager(runtime, 'standalone')
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(app):
        if not start_worker:
            yield
            return
        with ProcessLock(manager.store.path.with_suffix('.lock')):
            manager.recover()
            worker = Worker(manager)
            def loop():
                try:
                    while not stop.wait(.1):
                        worker.tick()
                except Exception:
                    # Stop scheduling on DB/manager failures; recovery never assumes completion.
                    app.state.worker_error = True
                finally:
                    worker.close()
            thread = threading.Thread(target=loop, daemon=True)
            thread.start()
            try:
                yield
            finally:
                stop.set()
                thread.join(timeout=30)

    app = FastAPI(title='GUI Test standalone', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.manager = manager
    app.state.worker_error = False
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.exception_handler(TestError)
    async def error(request, exc):
        return JSONResponse({'code': exc.code, 'message': exc.message}, status_code=exc.status)

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
            origin = request.headers.get('origin')
            if (origin and origin != f'{request.url.scheme}://{request.headers.get("host")}') or request.headers.get('sec-fetch-site') in {'cross-site', 'same-site'}:
                return JSONResponse({'message': 'Cross-origin request blocked'}, status_code=403)
            if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('x-bsp-client') != 'dashboard':
                return JSONResponse({'message': 'Application request header required'}, status_code=403)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 2_097_152:
                return JSONResponse({'message': 'Request exceeds 2 MB'}, status_code=413)
        request._body = bytes(raw)
        response = await call_next(request)
        response.headers.update({'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"})
        return response

    @app.get('/api/v1/health')
    def health():
        return {'status': 'degraded' if app.state.worker_error else 'ok', 'mode': 'standalone', 'simulation': True,
                'runtime_id': digest(str(Path(runtime).resolve()))}

    app.include_router(router(manager))
    static = Path(__file__).resolve().parents[1] / 'static'
    if static.exists():
        app.mount('/', StaticFiles(directory=static, html=True))
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', default=str(Path.home() / '.gui-test'))
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    uvicorn.run(create_app(args.runtime), host='127.0.0.1', port=args.port, proxy_headers=False)


if __name__ == '__main__':
    main()
