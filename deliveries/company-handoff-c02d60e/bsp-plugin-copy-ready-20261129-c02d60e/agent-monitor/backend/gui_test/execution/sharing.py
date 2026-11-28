"""Persistent Windows Host principals, task scopes, ownership and Monitor grants."""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
from time import time as now

from ..core.models import TestError, digest

CAPABILITY = 'multi-plugin-ownership-v1'
TASK_ID = re.compile(r'[a-f0-9]{32}')
HEX_PROOF = re.compile(r'[a-f0-9]{64}')
TOKEN = re.compile(r'[A-Za-z0-9_-]{32,128}')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}')
VIEW_TICKET_TTL = 45
VIEW_SESSION_TTL = 900

_SCHEMA = '''
CREATE TABLE IF NOT EXISTS sharing_principals(
    role TEXT NOT NULL CHECK(role IN ('account', 'service')),
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    revoked_at REAL,
    trusted_tc_author INTEGER NOT NULL DEFAULT 0 CHECK(trusted_tc_author IN (0,1)),
    PRIMARY KEY(role, name)
);
CREATE TABLE IF NOT EXISTS sharing_monitor_keys(
    monitor_id TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    protected_listener INTEGER NOT NULL DEFAULT 0 CHECK(protected_listener IN (0,1))
);
CREATE TABLE IF NOT EXISTS sharing_monitors(
    monitor_id TEXT NOT NULL,
    account TEXT NOT NULL,
    ssh_profile TEXT NOT NULL,
    monitor_port INTEGER NOT NULL CHECK(monitor_port BETWEEN 1 AND 65535),
    PRIMARY KEY(monitor_id,account)
);
CREATE TABLE IF NOT EXISTS sharing_tasks(
    task_id TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    project TEXT NOT NULL,
    monitor_id TEXT NOT NULL,
    last_seen_at REAL NOT NULL,
    view_epoch INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(monitor_id,account) REFERENCES sharing_monitors(monitor_id,account)
);
CREATE TABLE IF NOT EXISTS sharing_execution_approvals(
    task_id TEXT NOT NULL REFERENCES sharing_tasks(task_id),
    input_hash TEXT NOT NULL,
    approved_at REAL NOT NULL,
    PRIMARY KEY(task_id,input_hash)
);
CREATE TABLE IF NOT EXISTS sharing_run_owners(
    run_id TEXT PRIMARY KEY REFERENCES connector_runs(run_id),
    task_id TEXT NOT NULL REFERENCES sharing_tasks(task_id),
    monitor_id TEXT NOT NULL,
    epoch INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sharing_runs_by_task ON sharing_run_owners(task_id);
CREATE TABLE IF NOT EXISTS sharing_run_enrollments(
    run_id TEXT NOT NULL REFERENCES connector_runs(run_id),
    task_id TEXT NOT NULL REFERENCES sharing_tasks(task_id),
    input_hash TEXT NOT NULL,
    PRIMARY KEY(run_id,task_id,input_hash)
);
CREATE TABLE IF NOT EXISTS sharing_handoffs(
    run_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    old_task_id TEXT,
    new_task_id TEXT NOT NULL,
    changed_at REAL NOT NULL,
    PRIMARY KEY(run_id, epoch)
);
CREATE TABLE IF NOT EXISTS sharing_snapshots(
    scope TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('source', 'installer')),
    snapshot_id TEXT NOT NULL,
    PRIMARY KEY(scope, kind, snapshot_id)
);
CREATE TABLE IF NOT EXISTS sharing_service_batches(
    batch_id TEXT PRIMARY KEY REFERENCES batches(id),
    service TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sharing_view_grants(
    token_hash TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('ticket', 'view')),
    task_id TEXT NOT NULL REFERENCES sharing_tasks(task_id),
    monitor_id TEXT NOT NULL,
    view_epoch INTEGER NOT NULL,
    expires_at REAL NOT NULL
);
'''


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode('ascii')).hexdigest()


def _admin_store(runtime: Path):
    from .connector_runs import BridgeTokenStore
    return BridgeTokenStore(Path(runtime) / 'sharing-operator')


def load_admin_token(runtime: Path) -> str | None:
    """Read the current Windows user's local operator key. Never creates a key."""
    return _admin_store(runtime).load(readonly=True)


def execution_input_hash(request):
    return digest(request.model_dump(exclude={'run_id', 'request_hash', 'origin', 'parent_run_id', 'retry_chain'}))


def approval_required():
    return TestError('The operator must approve this prepared Run before execution', 'SHARING_EXECUTION_APPROVAL_REQUIRED', 403)


def unavailable():
    return TestError('Shared Host credential data is unavailable', 'SHARING_UNAVAILABLE', 503)


def auth_required():
    return TestError('Shared Host credential required or invalid', 'SHARING_AUTH_REQUIRED', 401)


def denied():
    return TestError('This credential cannot use this route', 'SHARING_FORBIDDEN', 403)


def not_found():
    return TestError('Resource not found', 'NOT_FOUND', 404)


def invalid_value(message):
    return TestError(message, 'SHARING_INVALID_INPUT', 422)


@dataclass(frozen=True)
class Access:
    role: str
    name: str = ''
    token_hash: str = ''
    task_id: str = ''
    key_hash: str = ''

    @property
    def scope(self):
        return 'task:' + self.task_id if self.task_id else 'service:' + self.name


class SharedHost:
    def __init__(self, runtime):
        self.runtime = Path(runtime)
        self.db = self.runtime / 'executions.db'
        self.admin = _admin_store(self.runtime)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def init_schema(self):
        with self.connect() as db:
            db.executescript(_SCHEMA)
            db.execute('BEGIN IMMEDIATE')
            migrations = (('sharing_monitor_keys', 'protected_listener'), ('sharing_principals', 'trusted_tc_author'))
            for table, column in migrations:
                columns = {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}
                if column not in columns:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0 CHECK({column} IN (0,1))')

    def mode(self, db):
        row = db.execute("SELECT value FROM runner_meta WHERE key='sharing_admin_hash'").fetchone()
        try:
            token = self.admin.load(readonly=True)
        except (OSError, ValueError):
            raise unavailable() from None
        if row is None and token is None:
            return 'individual'
        if row is None or not isinstance(row['value'], str) or not token or not hmac.compare_digest(row['value'], secret_hash(token)):
            raise unavailable()
        return 'shared'

    def mode_and_access(self, bearer):
        with self.connect() as db:
            mode = self.mode(db)
            if mode == 'individual' or not bearer or not TOKEN.fullmatch(bearer):
                return mode, None
            fingerprint = secret_hash(bearer)
            try:
                operator = self.admin.load()
            except (OSError, ValueError):
                raise unavailable() from None
            if not operator:
                raise unavailable()
            if hmac.compare_digest(operator, bearer):
                return mode, Access('admin', token_hash=fingerprint)
            row = db.execute('SELECT role, name FROM sharing_principals WHERE token_hash=? AND revoked_at IS NULL',
                             (fingerprint,)).fetchone()
            return mode, Access(row['role'], row['name'], fingerprint) if row else None

    def enable(self, db):
        if self.mode(db) == 'shared':
            return
        busy = (
            db.execute("SELECT 1 FROM jobs WHERE json_extract(data,'$.state') IN ('RUNNING','UNKNOWN') LIMIT 1").fetchone()
            or db.execute("SELECT 1 FROM batches WHERE json_extract(data,'$.state')!='RELEASED' LIMIT 1").fetchone()
            or db.execute("SELECT 1 FROM connector_runs WHERE state NOT IN ('COMPLETED','DELETED') OR analysis_latched=1 LIMIT 1").fetchone()
        )
        if busy:
            raise TestError('Shared mode requires an idle execution Host', 'CONNECTOR_BUSY', 409)
        token = self.admin.ensure()
        db.execute("INSERT INTO runner_meta VALUES('sharing_admin_hash',?)", (secret_hash(token),))

    def issue(self, db, role, name, *, trusted_tc_author=False):
        if (role not in {'account', 'service'} or not isinstance(name, str) or not LABEL.fullmatch(name)
                or type(trusted_tc_author) is not bool or (trusted_tc_author and role != 'account')):
            raise invalid_value('Invalid principal name or execution privilege')
        if db.execute('SELECT 1 FROM sharing_principals WHERE role=? AND name=? AND revoked_at IS NULL',
                      (role, name)).fetchone():
            raise TestError('Principal already has a credential', 'SHARING_PRINCIPAL_EXISTS', 409)
        token = secrets.token_urlsafe(36)
        db.execute('INSERT INTO sharing_principals(role,name,token_hash,trusted_tc_author) VALUES(?,?,?,?) '
                   'ON CONFLICT(role,name) DO UPDATE SET token_hash=excluded.token_hash,revoked_at=NULL,'
                   'trusted_tc_author=excluded.trusted_tc_author',
                   (role, name, secret_hash(token), int(trusted_tc_author)))
        runner_id = db.execute("SELECT value FROM runner_meta WHERE key='identity'").fetchone()[0]
        document = {'schema_version': 1, 'account': name, 'token': token, 'runner_id': runner_id}
        if role == 'service':
            document['role'] = 'service'
        return document

    def revoke(self, db, role, name):
        if role not in {'account', 'service'} or not isinstance(name, str) or not LABEL.fullmatch(name):
            raise invalid_value('Invalid principal name')
        changed = db.execute('UPDATE sharing_principals SET revoked_at=? WHERE role=? AND name=? AND revoked_at IS NULL',
                             (now(), role, name)).rowcount
        if not changed:
            raise not_found()
        if role == 'account':
            db.execute('UPDATE sharing_tasks SET view_epoch=view_epoch+1 WHERE account=?', (name,))
            self.revoke_leases(db, 'SELECT o.run_id FROM sharing_run_owners o JOIN sharing_tasks t USING(task_id) WHERE t.account=?', name)

    def _monitor_store(self, monitor_id):
        from .connector_runs import BridgeTokenStore
        return BridgeTokenStore(self.runtime / 'sharing-monitors' / secret_hash(monitor_id))

    def approve_monitor(self, db, account, monitor_id, ssh_profile, monitor_port, *, issue_key=True, protected_listener=False):
        if protected_listener is not True:
            raise invalid_value('Approval requires an operator-protected Monitor browser listener')
        if (not all(isinstance(item, str) and LABEL.fullmatch(item) for item in (account, monitor_id, ssh_profile))
                or type(monitor_port) is not int or not 1 <= monitor_port <= 65535):
            raise invalid_value('Invalid Monitor approval')
        if not db.execute("SELECT 1 FROM sharing_principals WHERE role='account' AND name=? AND revoked_at IS NULL",
                          (account,)).fetchone():
            raise not_found()
        conflict = db.execute('SELECT 1 FROM sharing_monitors WHERE monitor_id=? AND account!=? AND monitor_port!=?',
                              (monitor_id, account, monitor_port)).fetchone()
        if conflict:
            raise TestError('Monitor instance approvals must target the same port', 'SHARING_MONITOR_CONFLICT', 409)
        key = db.execute('SELECT protected_listener FROM sharing_monitor_keys WHERE monitor_id=?', (monitor_id,)).fetchone()
        if not key or not key['protected_listener']:
            if not issue_key:
                raise invalid_value('First protected approval requires a private Monitor credential output file')
            token = self._monitor_store(monitor_id).save(secrets.token_urlsafe(36))
            db.execute(
                'INSERT INTO sharing_monitor_keys VALUES(?,?,1) ON CONFLICT(monitor_id) DO UPDATE '
                'SET token_hash=excluded.token_hash,protected_listener=1', (monitor_id, secret_hash(token)),
            )
            db.execute('UPDATE sharing_tasks SET view_epoch=view_epoch+1 WHERE monitor_id=?', (monitor_id,))
        existing = db.execute('SELECT * FROM sharing_monitors WHERE monitor_id=? AND account=?', (monitor_id, account)).fetchone()
        db.execute('INSERT INTO sharing_monitors(monitor_id,account,ssh_profile,monitor_port) VALUES(?,?,?,?) '
                   'ON CONFLICT(monitor_id,account) DO UPDATE SET ssh_profile=excluded.ssh_profile,monitor_port=excluded.monitor_port',
                   (monitor_id, account, ssh_profile, monitor_port))
        if existing and (existing['ssh_profile'], existing['monitor_port']) != (ssh_profile, monitor_port):
            db.execute('UPDATE sharing_tasks SET view_epoch=view_epoch+1 WHERE monitor_id=? AND account=?', (monitor_id, account))
        if issue_key:
            runner_id = db.execute("SELECT value FROM runner_meta WHERE key='identity'").fetchone()[0]
            return {'schema_version': 1, 'monitor_id': monitor_id, 'protected_listener': True,
                    'token': self._monitor_token(db, monitor_id), 'runner_id': runner_id}
        return None

    def _monitor_token(self, db, monitor_id):
        row = db.execute('SELECT token_hash FROM sharing_monitor_keys WHERE monitor_id=? AND protected_listener=1',
                         (monitor_id,)).fetchone()
        try:
            token = self._monitor_store(monitor_id).load()
        except (OSError, ValueError):
            raise unavailable() from None
        if not row or not token or not hmac.compare_digest(row['token_hash'], secret_hash(token)):
            raise unavailable()
        return token

    def _verify_monitor_proof(self, db, monitor_id, purpose, value, proof):
        if not isinstance(proof, str) or not HEX_PROOF.fullmatch(proof):
            raise denied()
        token = self._monitor_token(db, monitor_id)
        expected = hmac.digest(token.encode('ascii'), f'{purpose}:{monitor_id}:{value}'.encode('ascii'), 'sha256').hex()
        if not hmac.compare_digest(expected, proof):
            raise denied()

    def verify_task_monitor(self, db, access, task_id, challenge, proof):
        if not isinstance(challenge, str) or not HEX_PROOF.fullmatch(challenge):
            raise invalid_value('Invalid Monitor proof challenge')
        if access.role == 'admin':
            task = db.execute('SELECT monitor_id FROM sharing_tasks WHERE task_id=?', (task_id,)).fetchone()
        else:
            task = self.require_task(db, access)
            if task['task_id'] != task_id:
                raise not_found()
        if not task:
            raise not_found()
        self._verify_monitor_proof(db, task['monitor_id'], 'bsp-monitor-v1', challenge, proof)

    def require_principal(self, db, access):
        if not access or access.role not in {'account', 'service'}:
            raise denied()
        row = db.execute('SELECT token_hash,trusted_tc_author FROM sharing_principals WHERE role=? AND name=? AND revoked_at IS NULL',
                         (access.role, access.name)).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'], access.token_hash):
            raise auth_required()
        return row

    def require_task(self, db, access):
        principal = self.require_principal(db, access)
        if access.role != 'account' or not access.task_id:
            raise denied()
        task = db.execute('SELECT * FROM sharing_tasks WHERE task_id=? AND account=?',
                          (access.task_id, access.name)).fetchone()
        if not task or not hmac.compare_digest(task['key_hash'], access.key_hash):
            raise auth_required()
        return dict(task) | {'trusted_tc_author': bool(principal['trusted_tc_author'])}

    def task_access(self, access, task_id, key):
        if (not access or access.role != 'account' or not task_id or not TASK_ID.fullmatch(task_id)
                or not key or not TOKEN.fullmatch(key)):
            raise auth_required()
        return Access(access.role, access.name, access.token_hash, task_id, secret_hash(key))

    def bind_task(self, db, access, project, monitor_id):
        self.require_principal(db, access)
        if (not isinstance(project, str) or not project.strip() or len(project) > 1024
                or any(ord(char) < 32 for char in project)
                or not isinstance(monitor_id, str) or not LABEL.fullmatch(monitor_id)):
            raise invalid_value('Invalid task project or Monitor identity')
        approved = db.execute(
            'SELECT 1 FROM sharing_monitors JOIN sharing_monitor_keys USING(monitor_id) '
            'WHERE monitor_id=? AND account=? AND protected_listener=1', (monitor_id, access.name),
        ).fetchone()
        if not approved:
            raise TestError('Protected Monitor listener is not approved for this account', 'MONITOR_NOT_APPROVED', 403)
        existing = db.execute('SELECT * FROM sharing_tasks WHERE task_id=?', (access.task_id,)).fetchone()
        if existing:
            task = self.require_task(db, access)
            if task['project'] != project or task['monitor_id'] != monitor_id:
                raise TestError('Existing task has different registration metadata', 'SHARING_TASK_CONFLICT', 409)
        else:
            db.execute('INSERT INTO sharing_tasks(task_id,account,key_hash,project,monitor_id,last_seen_at) VALUES(?,?,?,?,?,?)',
                       (access.task_id, access.name, access.key_hash, project, monitor_id, now()))
        self.touch(db, access.task_id)

    def touch(self, db, task_id):
        db.execute('UPDATE sharing_tasks SET last_seen_at=? WHERE task_id=?', (now(), task_id))

    def task_rows(self, db, access):
        sql = ('SELECT t.task_id,t.account,t.project,t.monitor_id,t.last_seen_at,m.monitor_port,m.ssh_profile '
               'FROM sharing_tasks t JOIN sharing_monitors m USING(monitor_id,account) '
               'JOIN sharing_monitor_keys k ON k.monitor_id=t.monitor_id AND k.protected_listener=1 '
               "JOIN sharing_principals p ON p.role='account' AND p.name=t.account AND p.revoked_at IS NULL")
        params = ()
        if access.role == 'account':
            self.require_principal(db, access)
            sql += ' WHERE t.account=?'
            params = (access.name,)
            if access.task_id:
                self.require_task(db, access)
                sql += ' AND t.task_id=?'
                params += (access.task_id,)
        rows = [dict(row) for row in db.execute(sql + ' ORDER BY t.last_seen_at DESC, t.task_id', params)]
        if access.role != 'admin':
            for row in rows:
                row.pop('ssh_profile', None)
        return rows

    def owner(self, db, run_id, task_id, epoch=None):
        row = db.execute('SELECT * FROM sharing_run_owners WHERE run_id=? AND task_id=?',
                         (run_id, task_id)).fetchone()
        if not row:
            raise not_found()
        if epoch is not None and str(row['epoch']) != epoch:
            raise TestError('Run ownership changed; reload Run state', 'RUN_OWNERSHIP_CHANGED', 409)
        return row

    def require_replay_owner(self, db, run_id, task_id, matches):
        owner = db.execute('SELECT task_id,epoch FROM sharing_run_owners WHERE run_id=?', (run_id,)).fetchone()
        if owner and owner['task_id'] == task_id and owner['epoch'] == 1:
            return
        if matches and owner and owner['epoch'] > 1:
            # Epoch two records the original accepted owner. An epoch-one
            # handoff instead denotes explicit ownership of a pre-sharing Run.
            transferred = db.execute(
                'SELECT 1 FROM sharing_handoffs WHERE run_id=? AND epoch=2 AND old_task_id=? '
                'AND NOT EXISTS(SELECT 1 FROM sharing_handoffs WHERE run_id=? AND epoch=1)',
                (run_id, task_id, run_id),
            ).fetchone()
            if transferred:
                raise TestError('The accepted Run ownership was transferred', 'OWNERSHIP_TRANSFERRED', 409)
        raise not_found()

    def approved_execution(self, db, task, request, *, prior_run_id=None):
        if task['trusted_tc_author']:
            return True
        fingerprint = execution_input_hash(request)
        if prior_run_id and db.execute(
            'SELECT 1 FROM sharing_run_enrollments WHERE run_id=? AND task_id=? AND input_hash=?',
            (prior_run_id, task['task_id'], fingerprint),
        ).fetchone():
            return True
        return db.execute(
            'SELECT 1 FROM sharing_execution_approvals WHERE task_id=? AND input_hash=?',
            (task['task_id'], fingerprint),
        ).fetchone() is not None

    def enroll_execution(self, db, run_id, task_id, request):
        db.execute('INSERT OR IGNORE INTO sharing_run_enrollments VALUES(?,?,?)',
                   (run_id, task_id, execution_input_hash(request)))

    def has_admission_permit(self, db, run_id, request):
        # An already admitted Run carries this execution permit through handoff.
        return db.execute('SELECT 1 FROM sharing_run_enrollments WHERE run_id=? AND input_hash=?',
                          (run_id, execution_input_hash(request))).fetchone() is not None

    def approve_execution(self, db, task_id, request):
        fingerprint = execution_input_hash(request)
        db.execute('INSERT OR IGNORE INTO sharing_execution_approvals VALUES(?,?,?)', (task_id, fingerprint, now()))
        return fingerprint

    def bind_run(self, db, run_id, task):
        db.execute('INSERT INTO sharing_run_owners(run_id,task_id,monitor_id,epoch) VALUES(?,?,?,1)',
                   (run_id, task['task_id'], task['monitor_id']))

    def revoke_leases(self, db, subquery, arg):
        db.execute(
            "UPDATE connector_analyses SET status='PENDING',lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,updated_at=? "
            f"WHERE status='ANALYZING' AND run_id IN ({subquery})", (now(), arg),
        )

    def handoff(self, db, run_id, expected_epoch, task_id):
        if (not isinstance(run_id, str) or not TASK_ID.fullmatch(run_id)
                or not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id)
                or type(expected_epoch) is not int or expected_epoch < 0):
            raise invalid_value('Invalid Run handoff')
        run = db.execute("SELECT state FROM connector_runs WHERE run_id=? AND state!='DELETED'", (run_id,)).fetchone()
        if not run:
            raise not_found()
        target = db.execute(
            "SELECT t.* FROM sharing_tasks t JOIN sharing_principals p ON p.role='account' AND p.name=t.account "
            "WHERE t.task_id=? AND p.revoked_at IS NULL", (task_id,),
        ).fetchone()
        if not target:
            raise not_found()
        previous = db.execute('SELECT * FROM sharing_run_owners WHERE run_id=?', (run_id,)).fetchone()
        old = previous['task_id'] if previous else None
        epoch = previous['epoch'] if previous else 0
        if epoch != expected_epoch or old == task_id:
            raise TestError('Run ownership changed or target already owns the Run', 'RUN_OWNERSHIP_CHANGED', 409)
        db.execute('INSERT INTO sharing_run_owners(run_id,task_id,monitor_id,epoch) VALUES(?,?,?,?) '
                   'ON CONFLICT(run_id) DO UPDATE SET task_id=excluded.task_id, monitor_id=excluded.monitor_id, epoch=excluded.epoch',
                   (run_id, task_id, target['monitor_id'], epoch + 1))
        db.execute('UPDATE sharing_tasks SET view_epoch=view_epoch+1 WHERE task_id=?', (old,))
        self.revoke_leases(db, 'SELECT ?', run_id)
        db.execute('INSERT INTO sharing_handoffs VALUES(?,?,?,?,?)', (run_id, epoch + 1, old, task_id, now()))
        return {'run_id': run_id, 'ownership_epoch': epoch + 1, 'previous_task_id': old, 'task_id': task_id}

    def can_read_snapshot(self, db, access, kind, identity):
        if db.execute('SELECT 1 FROM sharing_snapshots WHERE scope=? AND kind=? AND snapshot_id=?',
                      (access.scope, kind, identity)).fetchone():
            return True
        if not access.task_id:
            return False
        column = {'source': 'source_snapshot_id', 'installer': 'installer_snapshot_id'}[kind]
        return bool(db.execute(
            f"SELECT 1 FROM connector_runs JOIN sharing_run_owners USING(run_id) WHERE {column}=? AND task_id=? AND state!='DELETED'",
            (identity, access.task_id),
        ).fetchone())

    def require_snapshot(self, db, access, kind, identity):
        if not self.can_read_snapshot(db, access, kind, identity):
            raise TestError('Task snapshot has not been uploaded', 'SNAPSHOT_NOT_READY', 422)

    def bind_snapshot(self, db, access, kind, identity):
        db.execute('INSERT OR IGNORE INTO sharing_snapshots VALUES(?,?,?)', (access.scope, kind, identity))

    def require_batch(self, db, access, identity):
        self.require_principal(db, access)
        if not db.execute('SELECT 1 FROM sharing_service_batches WHERE batch_id=? AND service=?',
                          (identity, access.name)).fetchone():
            raise not_found()

    def require_job(self, db, access, identity):
        row = db.execute("SELECT json_extract(data,'$.batch_id') FROM jobs WHERE id=?", (identity,)).fetchone()
        self.require_batch(db, access, row[0] if row else None)

    def mint_view(self, db, task_id, *, access=None, monitor_id=None, ticket=None, monitor_proof=None):
        ts = now()
        db.execute('DELETE FROM sharing_view_grants WHERE expires_at<=?', (ts,))
        if ticket is not None:
            grant = self.require_view(db, ticket, 'ticket', task_id=task_id, monitor_id=monitor_id)
            task_id = grant['task_id']
            self._verify_monitor_proof(db, grant['monitor_id'], 'bsp-monitor-redeem-v1', ticket, monitor_proof)
            db.execute('DELETE FROM sharing_view_grants WHERE token_hash=?', (secret_hash(ticket),))
            kind, ttl = 'view', VIEW_SESSION_TTL
        else:
            if access.role != 'admin' and self.require_task(db, access)['task_id'] != task_id:
                raise not_found()
            kind, ttl = 'ticket', VIEW_TICKET_TTL
        task = db.execute(
            'SELECT t.*,m.monitor_port,m.ssh_profile FROM sharing_tasks t JOIN sharing_monitors m USING(monitor_id,account) '
            'JOIN sharing_monitor_keys k ON k.monitor_id=t.monitor_id AND k.protected_listener=1 '
            "JOIN sharing_principals p ON p.role='account' AND p.name=t.account AND p.revoked_at IS NULL WHERE t.task_id=?",
            (task_id,),
        ).fetchone()
        if not task:
            raise not_found()
        token = secrets.token_urlsafe(36)
        db.execute('INSERT INTO sharing_view_grants VALUES(?,?,?,?,?,?)',
                   (secret_hash(token), kind, task_id, task['monitor_id'], task['view_epoch'], ts + ttl))
        result = {'ticket' if kind == 'ticket' else 'view_token': token,
                  'task_id': task_id, 'monitor_id': task['monitor_id'],
                  'monitor_port': task['monitor_port'], 'expires_at': ts + ttl}
        if access and access.role == 'admin':
            result['ssh_profile'] = task['ssh_profile']
        return result

    def require_view(self, db, token, kind, *, task_id=None, monitor_id=None):
        if not token or not TOKEN.fullmatch(token):
            raise auth_required()
        row = db.execute(
            'SELECT g.task_id,t.account,t.project,t.monitor_id,t.last_seen_at FROM sharing_view_grants g '
            "JOIN sharing_tasks t USING(task_id) JOIN sharing_principals p ON p.role='account' AND p.name=t.account "
            'JOIN sharing_monitor_keys k ON k.monitor_id=t.monitor_id AND k.protected_listener=1 '
            'WHERE g.token_hash=? AND g.kind=? AND g.expires_at>? AND g.view_epoch=t.view_epoch '
            'AND g.monitor_id=t.monitor_id AND p.revoked_at IS NULL',
            (secret_hash(token), kind, now()),
        ).fetchone()
        if not row or (task_id is not None and task_id != row['task_id']) or (monitor_id is not None and monitor_id != row['monitor_id']):
            raise auth_required()
        return row
