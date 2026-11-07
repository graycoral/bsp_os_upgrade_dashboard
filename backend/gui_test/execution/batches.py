"""Persistent parent reservations shared by GUI TC, D-48 and integration callers."""
import hmac
import hashlib
import json
import secrets
import sqlite3

from ..core.models import Connection, TestError, digest, now


class BatchReservations:
    def __init__(self, host):
        self.host = host
        with sqlite3.connect(host.db) as c:
            c.execute('CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, data TEXT NOT NULL)')
            c.execute('INSERT OR IGNORE INTO runner_meta VALUES(?,?)', ('batch_owner_secret', secrets.token_hex(32)))
            self.secret = c.execute('SELECT value FROM runner_meta WHERE key=?', ('batch_owner_secret',)).fetchone()[0]

    def public(self, item):
        token = hmac.new(bytes.fromhex(self.secret), (item['id'] + ':' + str(item['epoch'])).encode(), hashlib.sha256).hexdigest()
        return item | {'token': token}

    def rows(self, c):
        return [json.loads(row[0]) for row in c.execute('SELECT data FROM batches')]

    def check_unowned(self, c):
        if any(item['state'] != 'RELEASED' for item in self.rows(c)):
            raise TestError('Windows parent batch reservation is held', 'RESERVATION_CONFLICT')

    def reserve(self, payload):
        if set(payload) != {'id', 'runner_id', 'request_id', 'connection'}:
            raise TestError('Invalid batch reservation fields', 'BATCH_REQUEST', 422)
        from .host import valid_identity
        valid_identity(payload['id'])
        if payload['runner_id'] != self.host.identity:
            raise TestError('Windows runner identity changed', 'RUNNER_CHANGED')
        if not isinstance(payload['request_id'], str) or not 1 <= len(payload['request_id']) <= 180:
            raise TestError('Invalid batch request identity', 'BATCH_REQUEST', 422)
        connection = Connection.model_validate(payload['connection']).model_dump()
        fingerprint = digest(payload | {'connection': connection})
        with self.host.lock, sqlite3.connect(self.host.db) as c:
            previous = c.execute('SELECT fingerprint,data FROM batches WHERE id=?', (payload['id'],)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise TestError('Batch identity conflicts with original request', 'IDEMPOTENCY_CONFLICT')
                return self.public(json.loads(previous[1]))
            self.check_unowned(c)
            if any(json.loads(row[0])['state'] in {'RUNNING', 'UNKNOWN'} for row in c.execute('SELECT data FROM jobs')):
                raise TestError('Windows execution is unresolved', 'RESERVATION_CONFLICT')
            self.host.verify(connection)
            epoch = int(c.execute("SELECT COALESCE(MAX(CAST(json_extract(data,'$.epoch') AS INTEGER)),0) FROM batches").fetchone()[0]) + 1
            item = {'id': payload['id'], 'batch_id': payload['id'], 'runner_id': self.host.identity,
                    'epoch': epoch, 'state': 'RESERVED',
                    'connection': connection, 'request_id': payload['request_id'], 'cancel_requested': False,
                    'created_at': now(), 'reason': '', 'prepare_id': None}
            item['owner_token_hash'] = hashlib.sha256(self.public(item)['token'].encode()).hexdigest()
            c.execute('INSERT INTO batches VALUES(?,?,?)', (item['id'], fingerprint, json.dumps(item)))
            return self.public(item)

    def status(self, identity):
        with self.host.lock, sqlite3.connect(self.host.db) as c:
            row = c.execute('SELECT data FROM batches WHERE id=?', (identity,)).fetchone()
            if not row: raise TestError('Batch reservation not found', 'NOT_FOUND', 404)
            return self.public(json.loads(row[0]))

    def validate(self, identity, token, epoch, *, allow_cancelled=False, allow_released=False):
        item = self.status(identity)
        if (not isinstance(token, str) or not hmac.compare_digest(item['token'], token) or
                type(epoch) is not int or epoch != item['epoch']):
            raise TestError('Stale batch owner or epoch', 'BATCH_STALE', 409)
        if item['state'] == 'RELEASED' and not allow_released:
            raise TestError('Batch reservation was released', 'BATCH_STALE', 409)
        if item['cancel_requested'] and not allow_cancelled:
            raise TestError('Batch cancellation requested', 'BATCH_CANCELLED', 409)
        return item

    def update(self, identity, **changes):
        with self.host.lock, sqlite3.connect(self.host.db) as c:
            item = self.status(identity)
            item.update(changes, updated_at=now())
            stored = {key: value for key, value in item.items() if key != 'token'}
            c.execute('UPDATE batches SET data=? WHERE id=?', (json.dumps(stored), identity))
            return item

    def child(self, c, payload):
        if not payload.get('batch_id'):
            self.check_unowned(c)
            return None
        item = self.validate(payload['batch_id'], payload.get('batch_token'), payload.get('batch_epoch'))
        if item['state'] != 'READY':
            raise TestError('Batch is not ready for TC execution', 'BATCH_NOT_READY')
        if Connection.model_validate(payload['connection']).model_dump() != item['connection']:
            raise TestError('Child connection differs from parent reservation', 'BOARD_MISMATCH')
        return item

    def cancel(self, identity, payload):
        with self.host.lock:
            self.validate(identity, payload.get('token'), payload.get('epoch'), allow_cancelled=True)
            return self.update(identity, cancel_requested=True)

    def children(self, identity):
        with sqlite3.connect(self.host.db) as c:
            return [item for row in c.execute('SELECT data FROM jobs')
                    if (item := json.loads(row[0])).get('batch_id') == identity]

    def release(self, identity, payload):
        with self.host.lock:
            item = self.validate(identity, payload.get('token'), payload.get('epoch'), allow_cancelled=True, allow_released=True)
            if item['state'] == 'RELEASED': return item
            evidence = self.host.flashing.observer_evidence(identity, fence=True)
            if evidence['unsafe']:
                self.update(identity, state='UNKNOWN', reason='CONSOLE_UNSAFE')
                raise TestError('Console evidence does not establish safe completion', 'HARDWARE_UNKNOWN')
            if item['state'] == 'UNKNOWN' or any(child['state'] in {'RUNNING', 'UNKNOWN'} or not child.get('terminated') for child in self.children(identity)):
                raise TestError('Physical/process state is not established; reservation retained', 'HARDWARE_UNKNOWN')
            # Stop RX acquisition, drain its writer and examine the final cut too:
            # evidence arriving between the first fence and handle close cannot vanish.
            final = self.host.flashing.close_observers(identity)
            if final['unsafe']:
                self.update(identity, state='UNKNOWN', reason='CONSOLE_UNSAFE', console=final)
                raise TestError('Final console evidence is unsafe; parent retained', 'HARDWARE_UNKNOWN')
            return self.update(identity, state='RELEASED', terminated=True, console=final, released_at=now())

    def recover(self):
        with self.host.lock, sqlite3.connect(self.host.db) as c:
            for item in self.rows(c):
                if item['state'] not in {'RELEASED', 'RESERVED'}:
                    item.update(state='UNKNOWN', reason='Runner restarted; reconcile durable child/console receipts')
                    c.execute('UPDATE batches SET data=? WHERE id=?', (json.dumps(item), item['id']))

    def reconcile(self, identity, payload):
        with self.host.lock:
            item = self.validate(identity, payload.get('token'), payload.get('epoch'), allow_cancelled=True, allow_released=True)
            if item['state'] == 'RELEASED': return item
            children = self.children(identity)
            if item['state'] == 'RESERVED' and payload.get('prepare_id'):
                from .host import valid_identity
                prepare_id = payload['prepare_id']; valid_identity(prepare_id)
                with sqlite3.connect(self.host.db) as c:
                    previous = c.execute('SELECT data FROM jobs WHERE id=?', (prepare_id,)).fetchone()
                    if not previous:
                        child = {'id': prepare_id, 'batch_id': identity, 'runner_id': self.host.identity,
                                 'kind': 'batch-prepare', 'state': 'DONE', 'phase': 'FAILED',
                                 'terminated': True, 'not_started': True, 'reason': 'RECONCILED_BEFORE_ACCEPTANCE'}
                        c.execute('INSERT INTO jobs VALUES(?,?,?)', (prepare_id, 'reconciled-before-acceptance', json.dumps(child)))
                        c.commit()
                        return self.update(identity, state='FAILED', prepare_id=prepare_id, reason=child['reason'])
            if self.host.flashing.observer_evidence(identity)['unsafe']:
                return self.update(identity, state='UNKNOWN', reason='CONSOLE_UNSAFE')
            # UNKNOWN is deliberately sticky. Process age, 404 or a dead worker is not physical proof.
            if any(child['state'] == 'UNKNOWN' for child in children):
                return self.update(identity, state='UNKNOWN', reason='Unresolved child process or hardware receipt')
            return item | {'children': [{'id': c['id'], 'state': c['state'], 'terminated': c.get('terminated', False)} for c in children]}
