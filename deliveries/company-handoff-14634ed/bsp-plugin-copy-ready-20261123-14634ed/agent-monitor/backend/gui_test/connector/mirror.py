"""Durable Manager projection and one-shot control requests, never a TC scheduler.

The authenticated host routes own transport access. This store additionally pins
every request to a verified runner, Manager boot session and published revision.
Only an actual Manager acknowledgement can report APPLIED or FAILED.
"""
from contextlib import contextmanager
import json
import math
import secrets

from ..core.models import TestError, digest, uid
from .logs import redact
from .paths import display_path


PROFILE_KEYS = {'python', 'boards', 'console_observers', 'board_names',
                'connector_inactive_boards', 'serial_transport', 'serial_settings', 'putty_path'}
BOARD_KEYS = {'board_id', 'host', 'com', 'node'}
RECORD_KEYS = {'id', 'execution_id', 'batch_id', 'kind', 'state', 'working_directory',
               'board_id', 'created_at', 'updated_at', 'started_at', 'finished_at'}
ACTIVE = {'QUEUED', 'RUNNING', 'UNKNOWN'}


def _text(value, limit=4096):
    return display_path(value)[:limit] if isinstance(value, str) else ''


def _scalar(value):
    return _text(value) if isinstance(value, str) else value if type(value) in {bool, int, float} or value is None else None


def _fields(value, keys):
    return {key: _scalar(item) for key, item in value.items() if key in keys} if isinstance(value, dict) else {}


def _observer(config):
    result = _fields(config, {'port', 'baudrate', 'rts', 'dtr', 'rx_only_confirmed', 'control_lines_isolated',
                              'tail_bytes', 'rotate_bytes', 'rotate_count', 'queue_bytes'})
    if isinstance(config, dict):
        for field in ('panic_signatures', 'boot_signatures', 'login_markers'):
            if isinstance(config.get(field), list):
                result[field] = [_text(v, 1024) for v in config[field][:32] if isinstance(v, str)]
    return result


def public_profile(value):
    """Explicit nested allowlists keep SSH setup, argv and future secrets private."""
    if not isinstance(value, dict):
        raise TestError('Invalid connector profile projection', status=422)
    result = {}
    for key, item in value.items():
        if key not in PROFILE_KEYS:
            continue
        if key == 'boards':
            result[key] = [_fields(b, BOARD_KEYS) for b in item[:32] if isinstance(b, dict)] if isinstance(item, list) else []
        elif key == 'connector_inactive_boards':
            # Web and Qt both store inactive editor drafts with nested boards.
            result[key] = []
            for draft in item[:32] if isinstance(item, list) else []:
                if not isinstance(draft, dict):
                    continue
                if 'board' not in draft:  # Legacy direct Board snapshots.
                    result[key].append(_fields(draft, BOARD_KEYS))
                else:
                    result[key].append(_fields(draft, {'name', 'baudrate'}) | {
                        'board': _fields(draft['board'], BOARD_KEYS), 'observer': _observer(draft.get('observer'))})
        elif key == 'board_names':
            result[key] = {_text(k, 80): _text(v, 160) for k, v in list(item.items())[:32]} if isinstance(item, dict) else {}
        elif key in {'console_observers', 'serial_settings'}:
            result[key] = {_text(k, 80): (_observer(v) if key == 'console_observers' else _fields(v, {'baudrate', 'rts', 'dtr'}))
                           for k, v in list(item.items())[:32]} if isinstance(item, dict) else {}
        else:
            result[key] = _scalar(item)
    return result


def _records(value, *, executions=False):
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:8 if executions else 64]:
        if not isinstance(item, dict):
            continue
        record = _fields(item, RECORD_KEYS | ({'reason'} if executions else set()))
        if executions:
            for stream in ('stdout', 'stderr'):
                text = item.get(stream, '')
                record[stream] = redact(text)[-16_384:] if isinstance(text, str) else ''
            boards = item.get('board_ids', [])
            record['board_ids'] = [_text(board, 80) for board in boards[:32] if isinstance(board, str)] if isinstance(boards, list) else []
        result.append(record)
    return result


def public_executions(value):
    return _records(value, executions=True)


def _server_paths(value):
    if not isinstance(value, dict):
        return None
    result = _fields(value, {'selected_tc_source'})
    run = value.get('run')
    result['run'] = _fields(run, {'id', 'state', 'historical', 'installer', 'tc_source', 'batch_id'}) if isinstance(run, dict) else None
    if result['run'] is not None:
        ids = run.get('execution_ids', [])
        result['run']['execution_ids'] = [_text(v, 160) for v in ids[:32]] if isinstance(ids, list) else []
    return result


def _identifier(value, name):
    if not isinstance(value, str) or not 1 <= len(value) <= 256 or any(ord(c) < 32 for c in value):
        raise TestError('Invalid ' + name, status=422)
    return value


class ConnectorMirror:
    def __init__(self, registry):
        self.registry, self.clock = registry, registry.clock
        with registry.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS manager_projection(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS manager_sessions(session_id TEXT PRIMARY KEY)')
            c.execute('CREATE TABLE IF NOT EXISTS manager_commands(command_id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, data TEXT NOT NULL)')

    @contextmanager
    def _locked(self):
        with self.registry.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                yield c
            except TestError:
                # Expiration/session fences are durable even when a new request
                # is rejected. Validation always precedes request mutations.
                c.commit()
                raise

    @staticmethod
    def _read(c, table):
        row = c.execute('SELECT data FROM ' + table + ' WHERE id=1').fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _save(c, command):
        c.execute('UPDATE manager_commands SET data=? WHERE command_id=?',
                  (json.dumps(command), command['command_id']))

    def _expire(self, c, projection=None, registration=None):
        now = self.clock()
        for (data,) in c.execute('SELECT data FROM manager_commands').fetchall():
            command = json.loads(data)
            state = command['state']
            if state not in {'QUEUED', 'RUNNING'}:
                continue
            replaced = projection is not None and command['session_id'] != projection['session_id']
            changed = state == 'QUEUED' and (
                (projection is not None and command['revision'] != projection['revision']) or
                (registration is not None and any(command.get(key) != registration.get(key) for key in
                                                  ('runner_id', 'config_revision', 'transport_generation'))))
            if (state in {'QUEUED', 'RUNNING'} and now >= command['expires_at']) or replaced or changed:
                command.update(state='EXPIRED' if state == 'QUEUED' else 'UNKNOWN', updated_at=now)
                self._save(c, command)

    def _fresh(self, registration, projection, console):
        now = self.clock()
        return bool(registration and projection and projection.get('state') == 'CONNECTED' and
                    self.registry.is_fresh(registration, console or {}) and
                    all(registration.get(key) == projection.get(key) for key in
                        ('runner_id', 'config_revision', 'transport_generation')) and
                    all(type(value) in {int, float} and 0 <= now - value <= 15
                        for value in (registration.get('verified_at'), projection.get('received_at'))))

    @staticmethod
    def _public(command):
        return {key: value for key, value in command.items() if key not in
                {'claim_token', 'idempotency_key', 'request_digest', 'config_revision', 'transport_generation', 'receipt_digest'}}

    def publish(self, value, *, expected_registration=None):
        if not isinstance(value, dict):
            raise TestError('Invalid Manager projection', status=422)
        for key in ('runner_id', 'session_id', 'revision'):
            _identifier(value.get(key), key)
        if not isinstance(value.get('ports', []), list):
            raise TestError('Invalid Manager port projection', status=422)
        safe = {key: value[key] for key in ('runner_id', 'session_id', 'revision')}
        safe.update(profile=public_profile(value.get('profile', {})),
                    ports=[_fields(p, {'com', 'description'}) for p in value.get('ports', [])[:64] if isinstance(p, dict)],
                    state=_text(value.get('state', 'DISCONNECTED'), 64), error=_text(value.get('error', ''), 1024),
                    executions=public_executions(value.get('executions', [])), execution_paths=_records(value.get('execution_paths', [])),
                    server_paths=_server_paths(value.get('server_paths')), received_at=self.clock())
        records = value.get('executions', [])
        safe['logs_truncated'] = (value.get('logs_truncated') is True or
                                  isinstance(records, list) and (len(records) > 8 or any(
                                      isinstance(row, dict) and any(len(str(row.get(key, ''))) > 16_384 for key in ('stdout', 'stderr'))
                                      for row in records)))
        if safe['revision'] != digest(safe['profile']):
            raise TestError('Manager profile revision does not match its public profile', 'SETTINGS_CONFLICT', 409)
        with self._locked() as c:
            registration = self._read(c, 'registration')
            expected = expected_registration or registration
            if not registration or not expected or safe['runner_id'] != registration['runner_id']:
                raise TestError('Manager belongs to another runner', 'RUNNER_CHANGED', 409)
            if any(registration.get(key) != expected.get(key) for key in ('runner_id', 'config_revision', 'transport_generation')):
                raise TestError('Manager publication belongs to an older registration', 'CONNECTOR_STALE', 409)
            previous = self._read(c, 'manager_projection')
            if previous and previous['session_id'] != safe['session_id'] and c.execute(
                    'SELECT 1 FROM manager_sessions WHERE session_id=?', (safe['session_id'],)).fetchone():
                raise TestError('Manager session has been replaced', 'MANAGER_CHANGED', 409)
            safe.update({key: registration[key] for key in ('config_revision', 'transport_generation')})
            c.execute('INSERT OR IGNORE INTO manager_sessions VALUES(?)', (safe['session_id'],))
            c.execute('INSERT INTO manager_projection VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data', (json.dumps(safe),))
            self._expire(c, safe, registration)
        return self.snapshot()

    def snapshot(self):
        with self._locked() as c:
            projection, registration = self._read(c, 'manager_projection'), self._read(c, 'registration')
            console = self._read(c, 'console_projection')
            self._expire(c, projection, registration)
            rows = c.execute('SELECT data FROM manager_commands ORDER BY rowid DESC LIMIT 32').fetchall()
        public = {key: value for key, value in projection.items() if key not in {'config_revision', 'transport_generation'}} if projection else None
        return {'schema': 'connector-mirror-v1', 'fresh': self._fresh(registration, projection, console),
                'projection': public, 'commands': [self._public(json.loads(row[0])) for row in rows]}

    def create(self, value, *, validate=None):
        expected = {'idempotency_key', 'runner_id', 'session_id', 'revision', 'action', 'body'}
        if not isinstance(value, dict) or set(value) != expected or not isinstance(value['body'], dict):
            raise TestError('Invalid Manager command', status=422)
        for key in ('idempotency_key', 'runner_id', 'session_id', 'revision'):
            _identifier(value[key], key)
        action, body = value['action'], value['body']
        keys = {'putty': {'board_id'}, 'manual': {'board_id', 'manual'}, 'apply-settings': {'desired_revision'}, 'restart': set()}
        if not isinstance(action, str) or action not in keys or set(body) != keys[action]:
            raise TestError('Unsupported Manager action', status=422)
        if action == 'manual' and type(body['manual']) is not bool:
            raise TestError('Invalid manual control flag', status=422)
        if action != 'restart':
            _identifier(body.get('desired_revision') if action == 'apply-settings' else body.get('board_id'), 'action target')
        fingerprint = digest(value)
        with self._locked() as c:
            projection, registration = self._read(c, 'manager_projection'), self._read(c, 'registration')
            self._expire(c, projection, registration)
            row = c.execute('SELECT data FROM manager_commands WHERE idempotency_key=?', (value['idempotency_key'],)).fetchone()
            if row:
                command = json.loads(row[0])
                if command['request_digest'] != fingerprint:
                    raise TestError('Idempotency key already names a different command', 'IDEMPOTENCY_CONFLICT', 409)
                return self._public(command)
            if not self._fresh(registration, projection, self._read(c, 'console_projection')):
                raise TestError('Reconnect and refresh the Manager before control', 'CONNECTOR_STALE', 409)
            if any(value[key] != projection[key] for key in ('runner_id', 'session_id', 'revision')):
                raise TestError('Manager session or profile changed', 'MANAGER_CHANGED', 409)
            if action in {'putty', 'manual'} and body['board_id'] not in {
                    b.get('board_id') for b in projection['profile'].get('boards', [])}:
                raise TestError('Unknown Manager board', 'BOARD_NOT_FOUND', 409)
            if any(json.loads(data)['state'] in ACTIVE for (data,) in c.execute('SELECT data FROM manager_commands')):
                raise TestError('An earlier Manager command is pending or unresolved', 'CONNECTOR_BUSY', 409)
            if validate is not None:
                # The host may check its central desired settings only for new
                # requests; HTTP retries must still return the original receipt.
                validate(value)
            now = self.clock()
            command = dict(value, command_id=uid(), request_digest=fingerprint, state='QUEUED',
                           created_at=now, updated_at=now, expires_at=now + 60, result=None,
                           config_revision=registration['config_revision'], transport_generation=registration['transport_generation'])
            c.execute('INSERT INTO manager_commands VALUES(?,?,?)',
                      (command['command_id'], value['idempotency_key'], json.dumps(command)))
            return self._public(command)

    def claim(self, value):
        if not isinstance(value, dict) or set(value) != {'runner_id', 'session_id'}:
            raise TestError('Invalid Manager claim', status=422)
        for key in value:
            _identifier(value[key], key)
        with self._locked() as c:
            projection, registration = self._read(c, 'manager_projection'), self._read(c, 'registration')
            self._expire(c, projection, registration)
            if not projection or any(value[key] != projection[key] for key in value):
                raise TestError('Manager session changed', 'MANAGER_CHANGED', 409)
            if not self._fresh(registration, projection, self._read(c, 'console_projection')):
                raise TestError('Manager projection is stale', 'CONNECTOR_STALE', 409)
            for (data,) in c.execute('SELECT data FROM manager_commands ORDER BY rowid').fetchall():
                command = json.loads(data)
                if command['state'] != 'QUEUED':
                    continue
                now = self.clock()
                command.update(state='RUNNING', claim_token=secrets.token_urlsafe(32), updated_at=now,
                               expires_at=now + (180 if command['action'] in {'apply-settings', 'restart'} else 60))
                self._save(c, command)
                return {'command': self._public(command) | {'claim_token': command['claim_token']}}
            return {'command': None}

    def get(self, command_id):
        with self._locked() as c:
            self._expire(c, self._read(c, 'manager_projection'), self._read(c, 'registration'))
            row = c.execute('SELECT data FROM manager_commands WHERE command_id=?', (command_id,)).fetchone()
        if not row:
            raise TestError('Manager command not found', 'NOT_FOUND', 404)
        return self._public(json.loads(row[0]))

    def abandon(self, command_id, value):
        """Acknowledge an unknown outcome only after the old Manager is gone.

        Manager boot IDs are produced under its exclusive process lock. A fresh
        replacement session plus idle Host/UART observations can release this UI
        command gate; it never proves what the old command actually did.
        """
        fields = {'runner_id', 'session_id', 'expected_updated_at'}
        if (not isinstance(value, dict) or set(value) != fields or
                type(value.get('expected_updated_at')) not in {int, float} or
                type(value['expected_updated_at']) is float and not math.isfinite(value['expected_updated_at'])):
            raise TestError('Invalid unknown-command acknowledgement', status=422)
        for key in ('runner_id', 'session_id'):
            _identifier(value[key], key)
        with self._locked() as c:
            projection, registration = self._read(c, 'manager_projection'), self._read(c, 'registration')
            self._expire(c, projection, registration)
            row = c.execute('SELECT data FROM manager_commands WHERE command_id=?', (command_id,)).fetchone()
            if not row:
                raise TestError('Manager command not found', 'NOT_FOUND', 404)
            command = json.loads(row[0])
            if command['state'] != 'UNKNOWN':
                raise TestError('Only an unknown Manager command can be acknowledged', 'COMMAND_NOT_UNKNOWN', 409)
            if command['updated_at'] != value['expected_updated_at']:
                raise TestError('Manager command changed; reload before acknowledging', 'COMMAND_CHANGED', 409)
            if not self._fresh(registration, projection, self._read(c, 'console_projection')):
                raise TestError('Refresh the replacement Manager and board observations first', 'CONNECTOR_STALE', 409)
            if (value['runner_id'] != command['runner_id'] or
                    any(value[key] != projection[key] for key in ('runner_id', 'session_id'))):
                raise TestError('Replacement Manager identity changed', 'MANAGER_CHANGED', 409)
            if value['session_id'] == command['session_id']:
                raise TestError('Restart the Windows Manager before acknowledging this unknown command',
                                'MANAGER_RESTART_REQUIRED', 409)
            inventory = registration.get('inventory', {})
            inventory = inventory if isinstance(inventory, dict) else {}
            boards = inventory.get('boards')
            safe = inventory.get('host_busy') is False and inventory.get('reserved') is False and isinstance(boards, list)
            if safe:
                observed = {board.get('board_id') for board in boards if isinstance(board, dict) and isinstance(board.get('board_id'), str)}
                safe = {board.get('board_id') for board in projection['profile'].get('boards', [])} <= observed
                for board in boards:
                    if (not isinstance(board, dict) or not isinstance(board.get('state'), str) or
                            board['state'] not in {'CONNECTED', 'DISCONNECTED', 'ERROR'}):
                        safe = False
                        break
                    proxy = board.get('serial_proxy')
                    if (proxy is not None or projection['profile'].get('serial_transport') == 'proxy') and (
                            not isinstance(proxy, dict) or 'owner' not in proxy or proxy['owner'] or
                            proxy.get('putty_connected') is not False):
                        safe = False
                        break
            if not safe:
                raise TestError('Confirm that Host, boards and PuTTY have no active or uncertain owner', 'CONNECTOR_BUSY', 409)
            now = self.clock()
            command.update(state='ABANDONED', updated_at=now, abandoned_at=now,
                           abandoned_by_session_id=value['session_id'], result={
                               'code': 'UNKNOWN_ACKNOWLEDGED',
                               'message': '이전 요청의 결과는 알 수 없습니다. 새 Windows Manager와 장비의 유휴 상태를 확인했으며 자동으로 다시 실행하지 않습니다.',
                               'outcome_unknown': True})
            self._save(c, command)
            return self._public(command)

    def finish(self, command_id, value):
        fields = {'runner_id', 'session_id', 'claim_token', 'state', 'result'}
        if not isinstance(value, dict) or set(value) != fields or not isinstance(value.get('state'), str) or value.get('state') not in {'APPLIED', 'FAILED', 'UNKNOWN'} or not isinstance(value.get('result'), dict):
            raise TestError('Invalid Manager receipt', status=422)
        for key in ('runner_id', 'session_id', 'claim_token'):
            _identifier(value[key], key)
        # Keep acknowledgement metadata only, never raw action return/profile/argv.
        result = _fields(value['result'], {'code', 'message', 'opened', 'manual', 'applied', 'desired_revision', 'revision', 'board_id', 'scope', 'previous_launch_id', 'launch_id'})
        fingerprint = digest({'state': value['state'], 'result': result})
        with self._locked() as c:
            projection, registration = self._read(c, 'manager_projection'), self._read(c, 'registration')
            self._expire(c, projection, registration)
            row = c.execute('SELECT data FROM manager_commands WHERE command_id=?', (command_id,)).fetchone()
            if not row:
                raise TestError('Manager command not found', 'NOT_FOUND', 404)
            command = json.loads(row[0])
            if value['state'] == 'UNKNOWN' and command['action'] != 'restart':
                raise TestError('Only restart can report an unconfirmed outcome', status=422)
            # A persisted actual receipt may arrive after a Manager restart. It
            # must prove the original boot session and unguessable claim, while
            # the current registry still trusts the same runner. A new session
            # cannot claim the old command or invent its token.
            if not registration or value['runner_id'] != registration.get('runner_id') or any(
                    value[key] != command.get(key) for key in ('runner_id', 'session_id')) or not secrets.compare_digest(
                        value['claim_token'].encode('utf-8'), command.get('claim_token', '').encode('utf-8')):
                raise TestError('Receipt belongs to another Manager claim', 'MANAGER_CHANGED', 409)
            if command['state'] in {'APPLIED', 'FAILED'}:
                if command.get('receipt_digest') != fingerprint:
                    raise TestError('Receipt already recorded with different outcome', 'RECEIPT_CONFLICT', 409)
                return self._public(command)
            if command['state'] not in {'RUNNING', 'UNKNOWN', 'ABANDONED'}:
                raise TestError('Command has no active Manager claim', 'COMMAND_NOT_CLAIMED', 409)
            command.update(state=value['state'], result=result, receipt_digest=fingerprint, updated_at=self.clock())
            self._save(c, command)
            return self._public(command)
