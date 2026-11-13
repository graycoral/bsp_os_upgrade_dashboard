"""Persistent loopback runner discovery shared by API and the existing worker.

Transport generations may change. A registry never silently replaces its trusted
runner identity. Existing runs remain pinned to that identity and their connection.
"""
import json
import sqlite3
import time
from pathlib import Path

from ..adapters.windows_remote import WindowsRemote
from ..core.models import TestError, digest


class ConnectorRegistry:
    def __init__(self, runtime, *, token=None, factory=None, clock=time.time):
        self.path = Path(runtime) / 'connector-registry.db'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.factory = factory or (lambda url: WindowsRemote(url))
        self.clock = clock
        with self.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS connector_errors(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, data TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS console_projection(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS registration(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')

    def connection(self):
        return sqlite3.connect(self.path, timeout=10)

    def read(self):
        with self.connection() as c:
            row = c.execute('SELECT data FROM registration WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    def register(self, url, runner_id):
        # WindowsRemote validates scheme, credentials, path and loopback before I/O.
        remote = self.factory(url)
        identity = remote.request('/identity')
        if identity.get('runner_id') != runner_id or identity.get('connector_inventory_v1') is not True:
            raise TestError('Connector identity/capability verification failed', 'RUNNER_CHANGED', 409)
        inventory = remote.request('/inventory')
        if inventory.get('runner_id') != runner_id:
            raise TestError('Reverse connector identity changed', 'RUNNER_CHANGED', 409)
        semantic = digest({'runner_id': runner_id, 'mapping_revision': inventory['mapping_revision']})
        with self.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT data FROM registration WHERE id=1').fetchone()
            previous = json.loads(row[0]) if row else None
            if previous and previous['runner_id'] != runner_id:
                raise TestError('A different trusted runner requires explicit offline migration', 'RUNNER_CHANGED', 409)
            value = {'runner_id': runner_id, 'url': url.rstrip('/'), 'verified_at': self.clock(),
                     'transport_generation': (previous or {}).get('transport_generation', 0) + int(not previous or previous['url'] != url.rstrip('/')),
                     'config_revision': semantic, 'inventory': inventory}
            c.execute('INSERT INTO registration VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (json.dumps(value),))
        return value

    def save_console(self, value, linker=None):
        registration = self.read()
        if not registration or value.get('runner_id') != registration['runner_id']:
            raise TestError('Console belongs to another runner', 'RUNNER_CHANGED', 409)
        boards = {b['board_id'] for b in registration['inventory']['boards']}
        if any(b.get('board_id') not in boards for b in value.get('boards', [])):
            raise TestError('Unknown console board', 'BOARD_MISMATCH', 409)
        from .logs import redact
        def clean(item):
            if isinstance(item,str): return redact(item)
            if isinstance(item,list): return [clean(v) for v in item]
            if isinstance(item,dict): return {k:clean(v) for k,v in item.items()}
            return item
        safe = clean(value)
        safe['received_at']=self.clock()
        with self.connection() as c:
            c.execute('INSERT INTO console_projection VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (json.dumps(safe),))
            for error in (safe.get('error_events', []) if 'error_events' in safe else safe.get('errors', [])):
                refs = error.get('run_ids', [])
                links = linker(refs) if linker else []
                event = dict(error, runner_id=registration['runner_id'], source='board-console', severity='ERROR',
                             observer_epoch=error.get('observer_epoch') or value.get('epoch'), links=links, evidence_ref={'epoch': value.get('epoch'), 'record_seq': value.get('cursor'),
                             'source_byte_offset': (error.get('evidence') or {}).get('end_offset')})
                identity = error.get('event_id') or digest({k: event[k] for k in ('runner_id', 'board_id', 'code', 'observer_epoch', 'links', 'evidence_ref') if k in event})
                event.update(event_id=identity, time=error.get('time',self.clock()))
                c.execute('INSERT OR IGNORE INTO connector_errors(event_id,data) VALUES(?,?)', (identity, json.dumps(event)))
        return safe

    def delete_run_events(self, run_id):
        with self.connection() as c:
            for seq,data in c.execute('SELECT seq,data FROM connector_errors').fetchall():
                if any(link.get('run_id')==run_id for link in json.loads(data).get('links',[])):
                    c.execute('DELETE FROM connector_errors WHERE seq=?',(seq,))

    def errors(self, after=0):
        with self.connection() as c:
            rows = c.execute('SELECT seq,data FROM connector_errors WHERE seq>? ORDER BY seq LIMIT 100', (after,)).fetchall()
        return {'events': [dict(json.loads(data), seq=seq) for seq, data in rows], 'cursor': rows[-1][0] if rows else after}

    def console(self):
        with self.connection() as c:
            row = c.execute('SELECT data FROM console_projection WHERE id=1').fetchone()
        value=json.loads(row[0]) if row else {'boards': [], 'errors': [], 'cursor': 0}
        registration=self.read()
        fresh=bool(registration and value.get('received_at') is not None and self.clock()-registration['verified_at']<=15 and self.clock()-value['received_at']<=15)
        return dict(value,fresh=fresh,stale=not fresh)


class RegisteredWindows:
    simulation = False
    branches = ['shared']

    def __init__(self, registry, fallback=None):
        self.registry, self.fallback = registry, fallback

    def __setattr__(self, name, value):
        fallback = self.__dict__.get('fallback')
        if fallback is not None and name in {'client', 'request'}:
            setattr(fallback, name, value)
        else: object.__setattr__(self, name, value)

    def target(self, expected=None, *, fresh=False):
        value = self.registry.read()
        if value is None:
            if self.fallback is not None:
                remote = self.fallback
            else:
                raise TestError('TEST BOARD CONNECTOR 연결을 등록하세요.', 'RUNNER_NOT_CONFIGURED', 503)
        else:
            if expected and expected != value['runner_id']:
                raise TestError('Original connector required', 'RUNNER_CHANGED', 409)
            if fresh and self.registry.clock() - value['verified_at'] > 15:
                raise TestError('Connector status is stale; reconnect before starting', 'CONNECTOR_STALE', 503)
            remote = self.registry.factory(value['url'])
            expected = expected or value['runner_id']
        if expected is None: return remote  # legacy transport retains its original request contract
        identity = remote.request('/identity')
        if identity.get('runner_id') != expected:
            raise TestError('Original connector required', 'RUNNER_CHANGED', 409)
        return remote

    def readiness(self):
        try:
            return self.target(fresh=True).readiness()
        except TestError as exc:
            return {'ready': False, 'code': exc.code, 'message': exc.message, 'capabilities': {}}

    def inventory(self):
        value = self.registry.read()
        if not value:
            return {'boards': [], 'fresh': False, 'runner_id': None}
        try:
            result = self.target().request('/inventory')
            return result | {'fresh': self.registry.clock() - value['verified_at'] <= 15}
        except TestError:
            return value['inventory'] | {'fresh': False}

    def execute(self, tc, connections, timeout, context, emit, cancelled):
        return self.target(context.get('runner_id_snapshot'), fresh=True).execute(tc, connections, timeout, context, emit, cancelled)

    def delete_session(self, run):
        return self.target(run.get('runner_id_snapshot') or run.get('integration', {}).get('config', {}).get('runner_id')).delete_session(run)

    def __getattr__(self, name):
        if name.startswith('_'): raise AttributeError(name)
        def call(*args, **kwargs):
            expected = None
            if name in {'reconcile_integration', 'finish_integration'}:
                receipt = args[-1]
                expected = receipt.get('runner_id')
            elif name == 'begin_integration': expected = args[1]['config']['runner_id']
            elif name == 'integration_identity' and args: expected = args[0]
            return getattr(self.target(expected, fresh=name in {'boards', 'verify', 'reserve_batch'}), name)(*args, **kwargs)
        return call
