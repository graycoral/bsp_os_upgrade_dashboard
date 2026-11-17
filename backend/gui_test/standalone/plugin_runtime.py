"""Copyable plugin control; one server authority, no execution engine or worker.

The host supplies its project, state directory and render/notify callbacks. UI
selection, drafts and uncertain request intents are local; settings and runs stay
in the existing server. Closing this facade stops observation only.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import os
import tempfile
import threading
import time
from uuid import uuid4

from ..core.connector_bootstrap import plain_path
from ..core.models import TestError


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def atomic_json(path, value):
    path = plain_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        plain_path(path)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


class SessionStore:
    """Cross-process intent lock; deliberately separate from service settings/DB."""
    def __init__(self, directory, context):
        self.directory = plain_path(directory)
        self.context = deepcopy(context)
        self.path = self.directory / (fingerprint(context) + '.json')
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self):
        import fcntl
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            lock_path = plain_path(self.path.with_suffix('.lock'))
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'a+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    value = json.loads(self.path.read_text()) if plain_path(self.path).exists() else {'context': self.context}
                    if value.get('context') != self.context:
                        raise TestError('Plugin context changed; use the matching project/service state', 'PLUGIN_CONTEXT_CHANGED', 409)
                    yield value
                    atomic_json(self.path, value)
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)


class PluginSession:
    def __init__(self, client, *, project, state_dir, notify=None, render=None):
        if not isinstance(project, str) or not project.strip(): raise ValueError('An explicit project context is required')
        self.client = client
        self.context = {'url': client.url, 'identity': deepcopy(client.expected), 'project': project}
        self.store = SessionStore(state_dir, self.context)
        self.notify, self.render = notify or (lambda event: None), render or (lambda snapshot: None)
        self._poll_lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._connection = None
        self.snapshot = None

    def refresh(self):
        """Single-flight, read-only poll, including settings without erasing drafts."""
        with self._poll_lock:
            try:
                health = self.client.health()
                mirror = self.client.connector_mirror()
                settings = self.client.settings()
                inventory = mirror.get('inventory') or self.client.connector_inventory()
                runner = inventory.get('runner_id')
                fresh = mirror.get('fresh') is True and inventory.get('fresh') is True
                with self.store.transaction() as state:
                    pinned = state.get('runner_id')
                    if pinned and runner and pinned != runner:
                        raise TestError('Registered connector changed', 'RUNNER_CHANGED', 409)
                    if runner: state['runner_id'] = runner
                    state['latest_settings'] = settings
                    draft = deepcopy(state.get('settings_draft'))
                    selected = state.get('selected_run')
                connection = 'READY' if fresh and runner else 'WAITING_CONNECTOR'
                snapshot = {'connection': connection, 'connection_ready': connection == 'READY',
                            'execution_ready': False, 'execution_readiness': 'CHECK_AT_PREVIEW_OR_START',
                            'message': '보드 커넥터 연결됨 · 연결 준비 완료' if connection == 'READY' else '서비스 준비 · 보드 커넥터 연결 대기',
                            'health': health, 'connector': mirror, 'inventory': inventory, 'settings': settings,
                            'settings_draft': draft, 'selected_run': selected, 'observed_at': time.time()}
                if selected:
                    try: snapshot['run'] = self.client.run(selected)
                    except TestError as exc: snapshot['run_error'] = {'code': exc.code, 'message': exc.message}
            except TestError as exc:
                connection = 'UNAVAILABLE'
                snapshot = {'connection': connection, 'connection_ready': False, 'execution_ready': False,
                            'code': exc.code, 'message': exc.message, 'observed_at': time.time()}
                with self.store.transaction() as state:
                    snapshot['settings_draft'] = deepcopy(state.get('settings_draft'))
            self.snapshot = snapshot
            if connection != self._connection:
                self._connection = connection
                self.notify({'type': 'connection', 'state': connection, 'message': snapshot['message']})
            self.render(deepcopy(snapshot))
            return deepcopy(snapshot)

    def watch(self, *, interval=3, stop=None):
        """Blocking observation hook; failure backoff, no start/restart/board claim."""
        if not .1 <= interval <= 30: raise ValueError('Polling interval must be between 0.1 and 30 seconds')
        stop = stop or self._stop
        delay = interval
        while not stop.is_set():
            value = self.refresh()
            delay = min(30, max(interval, delay * 2)) if value['connection'] == 'UNAVAILABLE' else interval
            stop.wait(delay)

    def start_watch(self, *, interval=3):
        with self._poll_lock:
            if self._thread is not None and self._thread.is_alive(): return
            self._stop.clear()
            self._thread = threading.Thread(target=self.watch, kwargs={'interval': interval}, daemon=True)
            self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread is not None: self._thread.join(timeout=20)
        # The shared service and Windows Manager deliberately outlive this UI.

    def begin_edit(self):
        with self.store.transaction() as state:
            if state.get('settings_draft') is None:
                state['settings_draft'] = {'base': self.client.settings(), 'value': None, 'conflict': False}
                state['settings_draft']['value'] = deepcopy(state['settings_draft']['base'])
            return deepcopy(state['settings_draft'])

    def edit(self, value):
        with self.store.transaction() as state:
            draft = state.get('settings_draft')
            if draft is None: raise TestError('Open the settings draft before editing', 'SETTINGS_DRAFT_REQUIRED', 409)
            if value.get('revision') != draft['base']['revision'] or value.get('expected_revision', draft['base']['revision']) != draft['base']['revision']:
                raise TestError('Keep the revision from the original draft', 'SETTINGS_CHANGED', 409)
            draft['value'] = deepcopy(value)
            return deepcopy(draft)

    def save_edit(self):
        with self.store.transaction() as state:
            draft = state.get('settings_draft')
            if draft is None: raise TestError('No settings draft', 'SETTINGS_DRAFT_REQUIRED', 409)
            try:
                result = self.client.save_settings(dict(draft['value'], expected_revision=draft['base']['revision']))
            except TestError as exc:
                draft['conflict'] = exc.code == 'SETTINGS_CHANGED'
                draft['error'] = exc.code
                # Persist even when the API rejects the save.
                error = exc
            else:
                state['latest_settings'] = result
                state.pop('settings_draft', None)
                error = None
        if error: raise error
        return result

    def discard_edit(self):
        with self.store.transaction() as state: state.pop('settings_draft', None)

    def _intent(self, kind, body, send):
        """Persist the original key/body before I/O, reuse after uncertain response."""
        error = None
        with self.store.transaction() as state:
            pending = state.setdefault('pending', {})
            original = pending.get(kind)
            if original is not None and original['body'] != body:
                raise TestError('An earlier request is unresolved; retry its original arguments', 'PLUGIN_INTENT_PENDING', 409)
            intent = original or {'key': uuid4().hex, 'body': deepcopy(body)}
            pending[kind] = intent
            # The durable write must happen before a process can disappear in I/O.
            atomic_json(self.store.path, state)
            try:
                result = send(intent['key'], deepcopy(intent['body']))
            except TestError as exc:
                error = exc
                # Transport/invalid response and duplicate-key conflicts may have
                # accepted work; never generate a replacement key for these.
                if 400 <= exc.status < 500 and exc.code not in {'IDEMPOTENCY_CONFLICT'}:
                    pending.pop(kind, None)
                    if kind == 'connector': state.pop('connector_apply', None)
            else:
                pending.pop(kind, None)
                state['last_receipt'] = deepcopy(result)
                if kind == 'start': state['selected_run'] = result['id']
                elif kind == 'connector': state['connector_apply']['receipt'] = deepcopy(result)
        if error: raise error
        return result

    def preview(self, installer=None, patterns=None):
        value = self.client.settings()['integration']
        installer = installer or value['installer_path']
        patterns = patterns or value.get('global_defaults')
        if not installer or not patterns: raise TestError('Set installer_path and TC patterns first', 'PLUGIN_INPUT_REQUIRED', 422)
        prepared = self.client.preview(installer, patterns)
        with self.store.transaction() as state:
            state['preview'] = {'installer': installer, 'patterns': patterns, 'receipt': prepared}
        return prepared

    def start(self, installer=None, patterns=None):
        with self.store.transaction() as state:
            pending = state.get('pending', {}).get('start')
            preview = deepcopy(state.get('preview'))
        if pending:
            body = pending['body']
            if installer is not None and installer != body['installer_path'] or patterns is not None and patterns != body['tc_patterns']:
                raise TestError('Retry the unresolved original execution first', 'PLUGIN_INTENT_PENDING', 409)
        else:
            settings = self.client.settings()['integration']
            body = {'installer_path': installer or settings['installer_path'], 'tc_patterns': patterns or settings.get('global_defaults')}
            if not body['installer_path'] or not body['tc_patterns']:
                raise TestError('Set installer_path and TC patterns first', 'PLUGIN_INPUT_REQUIRED', 422)
            if preview and (preview['installer'] != body['installer_path'] or preview['patterns'] != body['tc_patterns']):
                raise TestError('Preview inputs changed; preview the new selection explicitly', 'PREVIEW_CHANGED', 409)
            if preview:
                receipt = preview['receipt']
                if receipt.get('preparation_id'): receipt = self.client.preparation(receipt['preparation_id'])
                if receipt.get('prepared_token'): body['prepared_token'] = receipt['prepared_token']
                elif receipt.get('state') not in {'READY', 'COMPLETED'}:
                    raise TestError('Preview preparation has not completed', 'PREPARATION_PENDING', 409)
        result = self._intent('start', body, lambda key, request: self.client.start(key, request['installer_path'], request['tc_patterns'], request.get('prepared_token')))
        with self.store.transaction() as state: state.pop('preview', None)
        return result

    def runs(self):
        value = self.client.runs()
        rows = value if isinstance(value, list) else value.get('runs', [])
        result = []
        for row in rows:
            run = self.client.run(row['id'])
            if run.get('integration') and run.get('simulation') is not True: result.append(run)
        return result

    def _validate_run(self, run):
        if not run.get('integration') or run.get('simulation') is True:
            raise TestError('Choose a real integration Run', 'PLUGIN_RUN_REQUIRED', 409)
        pinned = run.get('integration', {}).get('config', {}).get('runner_id')
        with self.store.transaction() as state:
            if state.get('runner_id') and pinned != state['runner_id']:
                raise TestError('Run belongs to another connector', 'RUNNER_CHANGED', 409)
        return run

    def select(self, run_id):
        run = self._validate_run(self.client.run(run_id))
        with self.store.transaction() as state: state['selected_run'] = run_id
        return run

    def run(self, run_id=None):
        with self.store.transaction() as state: selected = run_id or state.get('selected_run')
        if not selected: raise TestError('Select an execution with test select <id>', 'PLUGIN_RUN_REQUIRED', 409)
        return self._validate_run(self.client.run(selected))

    def action(self, action, run_id=None):
        # If an action's response was lost, its original expected_version wins.
        with self.store.transaction() as state: pending = deepcopy(state.get('pending', {}).get('action'))
        if pending:
            body = pending['body']
            if body['action'] != action or run_id is not None and body['run_id'] != run_id:
                raise TestError('Retry the original pending action', 'PLUGIN_INTENT_PENDING', 409)
        else:
            run = self.run(run_id)
            body = {'run_id': run['id'], 'action': action, 'version': run['version']}
        return self._intent('action', body, lambda key, request: self.client.action(request['run_id'], request['action'], key=key, expected_version=request['version']))

    def connector_action(self, action):
        if action != 'restart': raise ValueError('Unsupported connector action')
        with self.store.transaction() as state:
            pending = deepcopy(state.get('pending', {}).get('connector-action'))
        body = pending['body'] if pending else {'action': action, 'snapshot': self.client.connector_mirror()}
        if body['action'] != action: raise TestError('Resolve the earlier connector action', 'PLUGIN_INTENT_PENDING', 409)
        return self._intent('connector-action', body, lambda key, request: self.client.connector_command(
            action, {}, key=key, snapshot=request['snapshot']))

    def apply_connector(self, value=None):
        """Persist desired before I/O; receipt lookup never re-enqueues a command."""
        with self.store.transaction() as state:
            saved = deepcopy(state.get('connector_apply'))
            if saved and saved.get('receipt'):
                receipt = self.client.connector_command_receipt(saved['receipt']['command_id'])
                if value is None or value == saved['value']: return receipt
                if receipt['state'] not in {'APPLIED', 'FAILED', 'EXPIRED', 'ABANDONED'}:
                    raise TestError('Resolve the earlier Windows settings request', 'PLUGIN_INTENT_PENDING', 409)
                state.setdefault('connector_history', []).append(saved['receipt'])
                state['connector_history'] = state['connector_history'][-32:]
                state.pop('connector_apply', None)
                saved = None
            if saved and value is not None and saved['value'] != value:
                raise TestError('Resolve the earlier Windows settings request', 'PLUGIN_INTENT_PENDING', 409)
            if saved is None:
                if value is None: raise TestError('Connector settings JSON required', 'PLUGIN_INPUT_REQUIRED', 422)
                saved = {'value': deepcopy(value), 'snapshot': self.client.connector_mirror()}
                state['connector_apply'] = saved
                atomic_json(self.store.path, state)
            if 'desired' not in saved:
                try:
                    saved['desired'] = self.client.save_connector_settings(saved['value'])
                except TestError as exc:
                    matched = False
                    if exc.code == 'SETTINGS_CHANGED':
                        current = self.client.settings()['connector_application']
                        fields = {'runner_id', 'settings', 'expected_profile_revision'} & saved['value'].keys()
                        matched = all(current.get(k) == saved['value'][k] for k in fields)
                        if matched: saved['desired'] = current
                    if not matched:
                        if 400 <= exc.status < 500:
                            state.pop('connector_apply', None)
                            atomic_json(self.store.path, state)
                        raise
                state['connector_apply'] = saved
                atomic_json(self.store.path, state)
        body = {'desired_revision': saved['desired']['desired_revision'], 'snapshot': saved['snapshot']}
        receipt = self._intent('connector', body, lambda key, request: self.client.connector_command(
            'apply-settings', {'desired_revision': request['desired_revision']}, key=key, snapshot=request['snapshot']))
        with self.store.transaction() as state: state['connector_apply']['receipt'] = receipt
        return receipt

    def connector_receipt(self, command_id=None):
        if command_id is not None: return self.client.connector_command_receipt(command_id)
        with self.store.transaction() as state:
            saved = deepcopy(state.get('connector_apply'))
            last = deepcopy(state.get('last_receipt'))
        if saved and saved.get('receipt'):
            receipt = self.client.connector_command_receipt(saved['receipt']['command_id'])
        elif last and last.get('command_id'):
            receipt = self.client.connector_command_receipt(last['command_id'])
        else: return self.client.settings()['connector_application']
        return {'command': receipt, 'application': self.client.settings()['connector_application']}
