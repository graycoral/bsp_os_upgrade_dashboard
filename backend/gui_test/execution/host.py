"""Authenticated loopback TC execution host. Expose through an SSH reverse tunnel only."""
import argparse
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..core.models import StrictModel, Connection, CommandTemplate, TestError, digest, uid
from ..adapters.runner import resolve_argv, validate_command_template, validate_windows_command
from .source import snapshot
from .git_info import inspect_git
from .process import ProcessTree
from .capture import Capture
from .bundle import is_frozen, validate_external_python
from ..standalone.server import ProcessLock


class Execute(StrictModel):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    tc_id: str = Field(min_length=1, max_length=1024)
    source_revision: str = Field(min_length=1, max_length=256)
    connection: Connection
    template: CommandTemplate


class Host:
    def __init__(self, config, runtime, ports=None):
        self.root = Path(config['source_root']).resolve(strict=True)
        self.runtime = Path(runtime).resolve()
        if self.runtime.is_relative_to(self.root) or self.root.is_relative_to(self.runtime):
            raise ValueError('Runner runtime and TC source must be separate directory trees')
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.python = (validate_external_python(config.get('python')) if is_frozen() else
                       str(Path(config.get('python', sys.executable)).resolve(strict=True)))
        self.metadata = config.get('metadata', {})
        self.configured_boards = [Connection.model_validate({'a': board}).a.model_dump() for board in config['boards']]
        if not self.configured_boards: raise ValueError('Configure at least one Windows board/COM mapping')
        for board in self.configured_boards:
            Connection.model_validate({'a': board})
        if len({(b['host'].casefold(), b['com']) for b in self.configured_boards}) != len(self.configured_boards):
            raise ValueError('Board COM mappings must be unique')
        if len({b['host'].casefold() for b in self.configured_boards}) != 1:
            raise ValueError('An execution host serves one Windows PC')
        nodes = [b['node'].casefold() for b in self.configured_boards if b.get('node')]
        if len(nodes) != len(set(nodes)):
            raise ValueError('Board node names must be unique')
        self.ports = ports or self.system_ports
        self.lock = threading.RLock()
        self.threads = []
        self.leases = {}
        self.cancelled = set()
        self.db = self.runtime / 'executions.db'
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, fingerprint TEXT, data TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS runner_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            c.execute('INSERT OR IGNORE INTO runner_meta VALUES(?,?)', ('identity', uid()))
            self.identity = c.execute('SELECT value FROM runner_meta WHERE key=?', ('identity',)).fetchone()[0]
        from .flashing import FlashService
        self.flashing = FlashService(self, config.get('flashing', {}))

    def recover(self):
        # Only the process holding runner.lock may reconcile a previous process.
        with self.lock, sqlite3.connect(self.db) as c:
            for row in c.execute('SELECT id,data FROM jobs').fetchall():
                item = json.loads(row[1])
                if item['state'] == 'RUNNING':
                    item.update(state='UNKNOWN', terminated=False, reason='Execution host restarted; termination not established')
                    c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(item), row[0]))

    @staticmethod
    def system_ports():
        from serial.tools.list_ports import comports
        return {p.device.upper() for p in comports()}

    def boards(self):
        ports = self.ports()
        return [b for b in self.configured_boards if b['com'] in ports]

    def verify(self, connection):
        value = Connection.model_validate(connection)
        for board in [value.a] + ([value.b] if value.b else []):
            if board.model_dump() not in self.boards():
                raise TestError('Configured Windows board/COM is unavailable', 'BOARD_MISMATCH')
        return value.model_dump()

    def catalog(self):
        with tempfile.TemporaryDirectory(dir=self.runtime, prefix='catalog-') as temp:
            return snapshot(self.root, Path(temp) / 'source', self.metadata) | {'git': inspect_git(self.root)}

    def get(self, identity):
        with self.lock, sqlite3.connect(self.db) as c:
            row = c.execute('SELECT data FROM jobs WHERE id=?', (identity,)).fetchone()
            if not row: raise TestError('Execution not found', 'NOT_FOUND', 404)
            return json.loads(row[0]) | {'runner_id': self.identity}

    def save(self, item):
        with self.lock, sqlite3.connect(self.db) as c:
            c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(item), item['id']))

    def start(self, payload):
        req = Execute.model_validate(payload)
        value = req.model_dump(); fingerprint = digest(value)
        with self.lock, sqlite3.connect(self.db) as c:
            previous = c.execute('SELECT fingerprint,data FROM jobs WHERE id=?', (req.id,)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise TestError('Execution ID reused with different content', 'IDEMPOTENCY_CONFLICT')
                return json.loads(previous[1])
            if any(json.loads(row[0])['state'] in {'RUNNING', 'UNKNOWN'} for row in c.execute('SELECT data FROM jobs')):
                raise TestError('Windows host is busy or has unresolved execution', 'RESERVATION_CONFLICT')
            template = validate_command_template(req.template.model_dump())
            # No arbitrary executable, shell, python -c, or extra launch options from the Dashboard.
            validate_windows_command(template)
            connection = self.verify(req.connection.model_dump())
            directory = self.runtime / 'snapshots' / req.id
            catalog = snapshot(self.root, directory, self.metadata, req.source_revision)
            # Server controls predecessor ordering; here validate the selected file identity and usability.
            tc = next((t for t in catalog['tests'] if t['id'] == req.tc_id and not t['disabled_reason']), None)
            if not tc: raise TestError('Unknown/disabled TC', 'TC_NOT_FOUND')
            argv = resolve_argv(template[tc['kind'].lower()], tc, connection)
            argv[0] = self.python
            argv[1] = str(directory / tc['path'])
            item = {'id': req.id, 'request_hash': fingerprint, 'state': 'RUNNING', 'terminated': False, 'exit_code': None,
                    'stdout': '', 'stderr': '', 'reason': '', 'argv': argv, 'source_revision': catalog['revision']}
            c.execute('INSERT INTO jobs VALUES(?,?,?)', (req.id, fingerprint, json.dumps(item)))
            c.commit()
            self.leases[req.id] = time.monotonic()
            thread = threading.Thread(target=self.execute, args=(item, directory, tc['timeout']), daemon=True)
            self.threads.append(thread); thread.start()
            return item

    def reject(self, payload, exc):
        """Persist proof of non-execution so retries cannot later start a rejected request."""
        fingerprint = digest(payload)
        with self.lock, sqlite3.connect(self.db) as c:
            row = c.execute('SELECT fingerprint,data FROM jobs WHERE id=?', (payload['id'],)).fetchone()
            if row:
                if row[0] != fingerprint: raise exc
                return json.loads(row[1])
            item = {'id': payload['id'], 'request_hash': fingerprint, 'source_revision': payload['source_revision'],
                    'state': 'DONE', 'terminated': True, 'exit_code': None, 'forced_state': 'ERROR',
                    'stdout': '', 'stderr': exc.message, 'reason': exc.code, 'not_started': True}
            c.execute('INSERT INTO jobs VALUES(?,?,?)', (item['id'], fingerprint, json.dumps(item)))
            return item

    def poll(self, identity, cancel=False):
        with self.lock:
            item = self.get(identity)
            if item.get('kind') == 'flash-test':
                if cancel:
                    raise TestError('Flash pipelines cannot be forcibly cancelled through the TC endpoint', 'FLASH_ACTIVE')
                return item
            if item['state'] == 'RUNNING':
                self.leases[identity] = time.monotonic()
                if cancel: self.cancelled.add(identity)
            return item

    def reconcile(self, identity):
        if not re.fullmatch(r'[a-f0-9]{32}', identity): raise TestError('Invalid execution ID', status=422)
        with self.lock, sqlite3.connect(self.db) as c:
            row = c.execute('SELECT data FROM jobs WHERE id=?', (identity,)).fetchone()
            if row: return json.loads(row[0]) | {'runner_id': self.identity}
            item = {'id': identity, 'runner_id': self.identity, 'state': 'DONE', 'terminated': True, 'exit_code': None,
                    'forced_state': 'ERROR', 'not_started': True, 'stdout': '', 'stderr': '',
                    'reason': 'Reconciled before execution was accepted'}
            c.execute('INSERT INTO jobs VALUES(?,?,?)', (identity, 'reconciled-before-acceptance', json.dumps(item)))
            return item

    def execute(self, item, directory, timeout):
        tree = capture = None
        try:
            tree = ProcessTree(item['argv'], directory, subprocess.PIPE, subprocess.PIPE)
            capture = Capture(tree.process.stdout, tree.process.stderr)
            start = time.monotonic(); forced = None
            while True:
                texts, overflow = capture.snapshot(); item.update(texts)
                with self.lock:
                    cancel = item['id'] in self.cancelled
                    lost = time.monotonic() - self.leases[item['id']] > 10
                forced = 'ERROR' if overflow or lost else 'CANCELLED' if cancel else 'TIMEOUT' if time.monotonic()-start > timeout else None
                if forced:
                    item['terminated'] = tree.stop()
                    item['forced_state'] = forced
                    break
                if tree.stopped():
                    item['terminated'] = True
                    break
                self.save(item); time.sleep(.05)
            # Final verdict uses both EOFs after confirmed process-tree termination.
            if not capture.drain(): item['terminated'] = False
            texts, overflow = capture.snapshot(); item.update(texts)
            if overflow:
                forced = 'ERROR'; item['forced_state'] = 'ERROR'
            item['exit_code'] = tree.process.poll()
            item['state'] = 'DONE' if item['terminated'] else 'UNKNOWN'
            item['reason'] = forced or ''
        except Exception:
            stopped = tree.stop() if tree else True
            item.update(state='DONE' if stopped else 'UNKNOWN', terminated=stopped, forced_state='ERROR', reason='Windows execution failed')
        finally:
            if tree: tree.close()
            self.save(item)

    def close(self):
        with self.lock:
            self.cancelled.update(self.leases)
        for thread in self.threads: thread.join(timeout=7)
        # Flash threads are non-daemon and own their Job Objects until completion.
        # A lost HTTP connection or normal service shutdown never kills a flash.
        for thread in self.threads:
            if not thread.daemon: thread.join()


def create_app(host, token):
    if len(token) < 32: raise ValueError('GUI_TEST_RUNNER_TOKEN must contain at least 32 characters')
    @asynccontextmanager
    async def lifespan(app):
        with ProcessLock(host.runtime / 'runner.lock'):
            host.recover()
            try: yield
            finally: host.close()
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def authenticate(request: Request, call_next):
        try: local = ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError, AttributeError): local = False
        if not local or request.headers.get('origin') or request.headers.get('sec-fetch-site'):
            return JSONResponse({'message': 'Runner accepts local non-browser clients only'}, status_code=403)
        if not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + token):
            return JSONResponse({'message': 'Runner authentication required'}, status_code=401)
        length = request.headers.get('content-length', '0')
        if not length.isdigit() or int(length) > 65536:
            return JSONResponse({'message': 'Request too large'}, status_code=413)
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 65536: return JSONResponse({'message': 'Request too large'}, status_code=413)
        request._body = bytes(data)
        return await call_next(request)

    @app.exception_handler(TestError)
    async def error(request, exc):
        return JSONResponse({'message': exc.message, 'code': exc.code}, status_code=exc.status)

    @app.get('/v1/catalog')
    def catalog(): return host.catalog()

    @app.get('/v1/identity')
    def identity(): return {'runner_id': host.identity}

    from .flashing import FlashRequest

    @app.post('/v1/flash-tests')
    def flash_test(body: FlashRequest):
        payload = body.model_dump()
        try: return host.flashing.start(payload)
        except TestError as exc: return host.reject(payload, exc)

    @app.get('/v1/boards')
    def boards(): return {'boards': host.boards()}

    @app.post('/v1/verify')
    def verify(body: Connection): return host.verify(body.model_dump())

    @app.post('/v1/executions')
    def execute(body: Execute):
        payload = body.model_dump()
        try: return host.start(payload)
        except TestError as exc: return host.reject(payload, exc)

    @app.get('/v1/executions/{identity}')
    def status(identity: str): return host.get(identity)

    @app.post('/v1/executions/{identity}/poll')
    def poll(identity: str): return host.poll(identity)

    @app.post('/v1/executions/{identity}/cancel')
    def cancel(identity: str): return host.poll(identity, cancel=True)

    @app.post('/v1/executions/{identity}/reconcile')
    def reconcile(identity: str): return host.reconcile(identity)

    return app


def main(argv=None):
    import uvicorn
    parser = argparse.ArgumentParser(description='Run shared-folder TC on this Windows PC; Linux connects through SSH -R')
    parser.add_argument('--config', required=True)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--port', type=int, default=8771)
    args = parser.parse_args(argv)
    if os.name != 'nt': parser.error('The execution host must run on Windows; Linux runs the Dashboard')
    token = os.environ.get('GUI_TEST_RUNNER_TOKEN', '')
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    host = Host(config, args.runtime)
    uvicorn.run(create_app(host, token), host='127.0.0.1', port=args.port, access_log=False)


if __name__ == '__main__': main()
