"""Authenticated loopback TC execution host. Expose through an SSH reverse tunnel only."""
import argparse
import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
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
from .source import snapshot, source_path
from .source_snapshots import copy_snapshot, receive_archive, MAX_ARCHIVE
from .git_info import inspect_git
from .process import ProcessTree
from .capture import Capture
from .bundle import runtime_mode, validate_external_python
from ..standalone.server import ProcessLock


def valid_identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise TestError('Invalid execution identity', status=422)


class Execute(StrictModel):
    id: str = Field(pattern=r'^[a-f0-9]{32}$')
    tc_id: str = Field(min_length=1, max_length=1024)
    source_revision: str = Field(min_length=1, max_length=256)
    connection: Connection
    template: CommandTemplate
    snapshot_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    batch_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    batch_token: str | None = Field(default=None, min_length=32, max_length=128)
    batch_epoch: int | None = Field(default=None, ge=1)


class Host:
    def __init__(self, config, runtime, ports=None):
        self.root = Path(config['source_root']).resolve(strict=True)
        self.runtime = Path(runtime).resolve()
        if self.runtime.is_relative_to(self.root) or self.root.is_relative_to(self.runtime):
            raise ValueError('Runner runtime and TC source must be separate directory trees')
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.python = (validate_external_python(config.get('python')) if runtime_mode() != 'source' else
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
        from .batches import BatchReservations
        self.batches = BatchReservations(self)
        self.flashing = FlashService(self, config.get('flashing', {}))
        self.installer_limit = config.get('flashing', {}).get('max_bundle_bytes', 64 * 1024**3)
        if type(self.installer_limit) is not int or not 1 <= self.installer_limit <= 1024**4:
            raise ValueError('Invalid installer byte limit')

    def recover(self):
        # Only the process holding runner.lock may reconcile a previous process.
        with self.lock, sqlite3.connect(self.db) as c:
            for row in c.execute('SELECT id,data FROM jobs').fetchall():
                item = json.loads(row[1])
                if item['state'] == 'RUNNING':
                    item.update(state='UNKNOWN', terminated=False, reason='Execution host restarted; termination not established')
                    c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(item), row[0]))
        self.batches.recover()

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
        value = req.model_dump(exclude_none=False)
        if req.snapshot_id is None:
            value.pop('snapshot_id')
        for key in ('batch_id', 'batch_token', 'batch_epoch'):
            if value[key] is None: value.pop(key)
        fingerprint = digest(value)
        with self.lock, sqlite3.connect(self.db) as c:
            if req.batch_id:
                self.batches.validate(req.batch_id, req.batch_token, req.batch_epoch)
            previous = c.execute('SELECT fingerprint,data FROM jobs WHERE id=?', (req.id,)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise TestError('Execution ID reused with different content', 'IDEMPOTENCY_CONFLICT')
                return json.loads(previous[1])
            batch = self.batches.child(c, value)
            if batch:
                self.flashing.check_batch(batch['id'])
            if any(json.loads(row[0])['state'] in {'RUNNING', 'UNKNOWN'} for row in c.execute('SELECT data FROM jobs')):
                raise TestError('Windows host is busy or has unresolved execution', 'RESERVATION_CONFLICT')
            template = validate_command_template(req.template.model_dump())
            # No arbitrary executable, shell, python -c, or extra launch options from the Dashboard.
            validate_windows_command(template)
            connection = self.verify(req.connection.model_dump())
            directory = self.runtime / 'snapshots' / req.id
            if req.snapshot_id and os.name == 'nt' and len(str(directory)) >= 248:
                directory = source_path(directory)
            catalog = (copy_snapshot(self.runtime / 'source-snapshots' / req.snapshot_id, directory, req.source_revision)
                       if req.snapshot_id else snapshot(self.root, directory, self.metadata, req.source_revision))
            # Server controls predecessor ordering; here validate the selected file identity and usability.
            tc = next((t for t in catalog['tests'] if t['id'] == req.tc_id and not t['disabled_reason']), None)
            if not tc: raise TestError('Unknown/disabled TC', 'TC_NOT_FOUND')
            argv = resolve_argv(template[tc['kind'].lower()], tc, connection)
            argv[0] = self.python
            script = directory / tc['path']
            argv[1] = str(source_path(script) if req.snapshot_id and os.name == 'nt' and len(str(script)) >= 260 else script)
            item = {'id': req.id, 'request_hash': fingerprint, 'state': 'RUNNING', 'terminated': False, 'exit_code': None,
                    'stdout': '', 'stderr': '', 'reason': '', 'argv': argv, 'source_revision': catalog['revision']}
            if batch:
                item.update(batch_id=batch['id'], batch_epoch=batch['epoch'], console_start=self.flashing.observer_evidence(batch['id']))
                for observer in self.flashing.observers.get(batch['id'], []): observer.boundary('TC:' + req.id)
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

    def poll(self, identity, cancel=False, batch_auth=None):
        with self.lock:
            item = self.get(identity)
            if item.get('batch_id') and item.get('kind') != 'batch-prepare':
                auth = batch_auth or {}
                self.batches.validate(item['batch_id'], auth.get('token'), auth.get('epoch'), allow_cancelled=True)
            if item.get('kind') in {'flash-test', 'batch-prepare'}:
                if cancel:
                    raise TestError('Flash pipelines cannot be forcibly cancelled through the TC endpoint', 'FLASH_ACTIVE')
                return item
            if item['state'] == 'RUNNING':
                self.leases[identity] = time.monotonic()
                if cancel: self.cancelled.add(identity)
            elif item.get('batch_id') and item.get('kind') != 'batch-prepare':
                self.final_console(item)
                self.save(item)
            return item

    def final_console(self, item):
        if not item.get('batch_id'): return
        if self.batches.status(item['batch_id'])['state'] == 'RELEASED': return
        evidence = self.flashing.observer_evidence(item['batch_id'], fence=True)
        item.update(console=evidence, panic=evidence['panic'], console_failure=evidence['unsafe'])
        if evidence['unsafe']:
            item.update(forced_state='ERROR', reason='CONSOLE_UNSAFE')
            self.batches.update(item['batch_id'], state='UNKNOWN', reason='CONSOLE_UNSAFE')

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
                if item.get('batch_id'):
                    evidence = self.flashing.observer_evidence(item['batch_id'])
                    item['console'] = evidence
                    if evidence['unsafe']:
                        forced = 'ERROR'; item['reason'] = 'CONSOLE_UNSAFE'
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
            self.final_console(item)
            if overflow:
                forced = 'ERROR'; item['forced_state'] = 'ERROR'
            item['exit_code'] = tree.process.poll()
            item['state'] = 'DONE' if item['terminated'] else 'UNKNOWN'
            item['reason'] = item.get('reason') or forced or ''
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
        for identity in list(self.flashing.observers): self.flashing.close_observers(identity)


def create_app(host, token):
    if len(token) < 32: raise ValueError('GUI_TEST_RUNNER_TOKEN must contain at least 32 characters')
    @asynccontextmanager
    async def lifespan(app):
        with ProcessLock(host.runtime / 'runner.lock'):
            host.recover()
            try: yield
            finally: host.close()
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    installer_upload_lock = asyncio.Lock()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @app.middleware('http')
    async def authenticate(request: Request, call_next):
        try: local = ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError, AttributeError): local = False
        if not local or request.headers.get('origin') or request.headers.get('sec-fetch-site'):
            return JSONResponse({'message': 'Runner accepts local non-browser clients only'}, status_code=403)
        if not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + token):
            return JSONResponse({'message': 'Runner authentication required'}, status_code=401)
        # This authenticated endpoint owns a bounded disk stream; all JSON endpoints
        # retain the original 64 KiB boundary and buffering behavior.
        if request.method == 'PUT' and re.fullmatch(r'/v1/(?:source|installer)-snapshots/[a-f0-9]{64}', request.url.path):
            return await call_next(request)
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
    def identity(): return {'runner_id': host.identity, 'source_snapshot_v1': True,
                           'installer_stream_v1': True, 'batch_reservation_v1': True,
                           'bsp_upgrade_integration_v1': True}

    @app.get('/v1/flash-profiles/{name}')
    def flash_profile(name: str): return host.flashing.profile_info(name)

    from . import installer_snapshots

    def transfer_paths(identity):
        if not re.fullmatch('[a-f0-9]{64}', identity): raise TestError('Invalid installer identity', status=422)
        root = host.runtime / 'installer-transfers'; root.mkdir(exist_ok=True)
        return root / (identity + '.partial'), root / (identity + '.json')

    @app.get('/v1/installer-snapshots/{identity}')
    def installer_status(identity: str):
        partial, receipt = transfer_paths(identity)
        if receipt.exists():
            value = json.loads(receipt.read_text(encoding='utf-8'))
            if value['state'] != 'READY': value['offset'] = partial.stat().st_size if partial.exists() else 0
            return value
        return {'snapshot_id': identity, 'state': 'PARTIAL', 'offset': 0}

    @app.put('/v1/installer-snapshots/{identity}')
    async def prepare_installer(identity: str, request: Request):
        if request.headers.get('content-type', '').split(';')[0].strip() != 'application/zip':
            raise TestError('Installer snapshot requires application/zip', status=415)
        partial, receipt_path = transfer_paths(identity)
        range_value = re.fullmatch(r'bytes ([0-9]+)-([0-9]+)/([0-9]+)', request.headers.get('content-range', ''))
        sha = request.headers.get('x-archive-sha256', '')
        if not range_value or not re.fullmatch('[a-f0-9]{64}', sha):
            raise TestError('Installer requires range and archive SHA256', 'IMAGE_TRANSPORT', 422)
        start, end, total = map(int, range_value.groups())
        length = request.headers.get('content-length', '')
        if (not length.isdigit() or int(length) != end - start + 1 or not (start <= end < total or start == total and end == total - 1) or
                total > host.installer_limit + 32 * 1024**2 or end != total - 1):
            raise TestError('Invalid installer stream bounds', 'IMAGE_SPACE', 413)
        async with installer_upload_lock:
            previous = installer_status(identity)
            if previous.get('archive_sha256') not in {None, sha} or previous.get('archive_size') not in {None, total}:
                raise TestError('Installer transfer content changed', 'IMAGE_CHANGED')
            if previous['state'] == 'READY': return previous
            offset = partial.stat().st_size if partial.exists() else 0
            if start != offset: raise TestError('Installer resume offset mismatch', 'IMAGE_OFFSET', 409)
            if shutil.disk_usage(host.runtime).free < 3 * total - start + installer_snapshots.RESERVE:
                raise TestError('Insufficient installer staging capacity', 'IMAGE_SPACE', 413)
            value = {'snapshot_id': identity, 'state': 'PARTIAL', 'archive_size': total, 'archive_sha256': sha, 'offset': offset}

            def save_receipt():
                temporary = receipt_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(value), encoding='utf-8'); os.replace(temporary, receipt_path)

            save_receipt()
            try:
                with partial.open('ab') as output:
                    async for chunk in request.stream():
                        if value['offset'] + len(chunk) > total:
                            raise TestError('Installer stream exceeded declared length', 'IMAGE_SPACE', 413)
                        output.write(chunk); value['offset'] += len(chunk)
                    output.flush(); os.fsync(output.fileno())
            finally:
                save_receipt()
            if value['offset'] != total: raise TestError('Incomplete installer upload; resume same transfer', 'IMAGE_INCOMPLETE')
            from starlette.concurrency import run_in_threadpool
            actual = await run_in_threadpool(installer_snapshots.file_hash, partial)
            if actual != sha: raise TestError('Installer archive hash mismatch', 'IMAGE_CHANGED')
            received = await run_in_threadpool(installer_snapshots.receive_archive, partial, identity,
                                               host.runtime / 'installer-snapshots', host.installer_limit)
            value.update(received); save_receipt()
            partial.unlink()
            return value

    @app.post('/v1/batches')
    def reserve_batch(body: dict): return host.batches.reserve(body)

    @app.get('/v1/batches/{identity}')
    def batch_status(identity: str):
        value = host.batches.status(identity)
        evidence = host.flashing.observer_evidence(identity)
        if evidence['unsafe'] and value['state'] not in {'RELEASED', 'UNKNOWN'}:
            value = host.batches.update(identity, state='UNKNOWN', reason='CONSOLE_UNSAFE')
        return value | {'console': evidence}

    from .flashing import PrepareBatch

    @app.post('/v1/batches/{identity}/prepare')
    def prepare_batch(identity: str, body: PrepareBatch): return host.flashing.start_prepare(identity, body.model_dump())

    @app.post('/v1/batches/{identity}/cancel')
    def cancel_batch(identity: str, body: dict): return host.batches.cancel(identity, body)

    @app.post('/v1/batches/{identity}/release')
    def release_batch(identity: str, body: dict): return host.batches.release(identity, body)

    @app.post('/v1/batches/{identity}/reconcile')
    def reconcile_batch(identity: str, body: dict): return host.batches.reconcile(identity, body)

    @app.put('/v1/source-snapshots/{identity}')
    async def prepare_source(identity: str, request: Request):
        if request.headers.get('content-type', '').split(';')[0].strip() != 'application/zip':
            raise TestError('Source snapshot requires application/zip', status=415)
        length = request.headers.get('content-length')
        if length is not None and (not length.isdigit() or int(length) > MAX_ARCHIVE):
            raise TestError('Source snapshot request too large', 'SOURCE_LIMIT', 413)
        with tempfile.TemporaryDirectory(dir=source_path(host.runtime), prefix='upload-') as temp:
            archive = Path(temp) / 'source.zip'
            total = 0
            with archive.open('wb') as output:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > MAX_ARCHIVE:
                        raise TestError('Source snapshot request too large', 'SOURCE_LIMIT', 413)
                    output.write(chunk)
            # Hashing and publication do not hold the execution DB/COM lock.
            from starlette.concurrency import run_in_threadpool
            return await run_in_threadpool(receive_archive, archive, identity, host.runtime / 'source-snapshots')

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
        if body.snapshot_id is None:
            payload.pop('snapshot_id')
        for key in ('batch_id', 'batch_token', 'batch_epoch'):
            if payload[key] is None: payload.pop(key)
        try: return host.start(payload)
        except TestError as exc: return host.reject(payload, exc)

    @app.get('/v1/executions/{identity}')
    def status(identity: str): return host.get(identity)

    @app.post('/v1/executions/{identity}/poll')
    def poll(identity: str, body: dict | None = None): return host.poll(identity, batch_auth=body)

    @app.post('/v1/executions/{identity}/cancel')
    def cancel(identity: str, body: dict | None = None): return host.poll(identity, cancel=True, batch_auth=body)

    @app.post('/v1/executions/{identity}/reconcile')
    def reconcile(identity: str): return host.reconcile(identity)

    return app


def main(argv=None):
    import uvicorn
    parser = argparse.ArgumentParser(description='Run shared-folder TC on this Windows PC; Linux connects through SSH -R')
    parser.add_argument('--config', required=True)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--port', type=int, default=8771)
    parser.add_argument('--launch-id')
    parser.add_argument('--startup-receipt', type=Path)
    parser.add_argument('--owner-pid', type=int)
    parser.add_argument('--owner-created')
    parser.add_argument('--allow-port-fallback', action='store_true')
    args = parser.parse_args(argv)
    if os.name != 'nt': parser.error('The execution host must run on Windows; Linux runs the Dashboard')
    from .launch import bind_loopback, process_identity, write_receipt, _nonce, _plain_path
    launch = (args.launch_id, args.startup_receipt, args.owner_pid, args.owner_created)
    if any(item is not None for item in launch):
        if not all(item is not None for item in launch):
            parser.error('All launch receipt and owner arguments are required together')
        _nonce(args.launch_id)
        runtime = _plain_path(args.runtime)
        expected = runtime / f'launch-{args.launch_id}.json'
        if not Path(args.runtime).is_absolute() or not args.startup_receipt.is_absolute() or args.startup_receipt != expected:
            parser.error('Startup receipt must be the nonce-named file in the absolute runtime directory')
        owner = {'pid': args.owner_pid, 'creation_time': args.owner_created}
        if process_identity(args.owner_pid) != owner:
            parser.error('Launch owner is not alive with the expected creation time')
    elif args.allow_port_fallback:
        parser.error('Port fallback requires a complete owned launch')
    token = os.environ.get('GUI_TEST_RUNNER_TOKEN', '')
    config = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
    host = Host(config, args.runtime)
    if args.launch_id is None:
        uvicorn.run(create_app(host, token), host='127.0.0.1', port=args.port, access_log=False)
        return
    # Retain this exact exclusive socket through Uvicorn startup. The lifespan's
    # existing runner.lock remains the final authority before requests are served.
    with bind_loopback(args.port, allow_fallback=args.allow_port_fallback) as listener:
        write_receipt(args.startup_receipt, {
            'version': 1, 'launch_id': args.launch_id, 'owner': owner,
            'runner': process_identity(os.getpid()), 'runner_id': host.identity,
            'runner_port': listener.getsockname()[1]})
        server = uvicorn.Server(uvicorn.Config(create_app(host, token), host='127.0.0.1',
                                               port=listener.getsockname()[1], access_log=False))
        server.run(sockets=[listener])
        if not server.started:
            raise RuntimeError('Runner failed to start; host lock may already be held')


if __name__ == '__main__': main()
