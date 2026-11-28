"""Shared external JSON exchange: the existing service DB remains authoritative."""
from copy import deepcopy
import hashlib
import json
import os
from uuid import uuid4

from ..core.connector_bootstrap import plain_path
from ..core.models import TestError
from .plugin_runtime import SessionStore, atomic_json


def strict_json(data):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('Duplicate settings JSON field')
            value[key] = item
        return value
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique)


def content(value):
    return {key: deepcopy(value[key]) for key in ('integration', 'timeouts')}


class SettingsFileBridge:
    def __init__(self, client, path):
        self.client, self.path = client, plain_path(path)
        self.binding = {'url': client.url, 'identity': client.expected}
        # Same file => same writer lock, even across dashboard/plugin projects.
        self.store = SessionStore(self.path.parent / '.plugin-file-state', {'path': str(self.path)})

    def _read(self):
        path = plain_path(self.path)
        if not path.exists(): return None
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream: return stream.read()

    @staticmethod
    def _hash(data):
        return hashlib.sha256(data).hexdigest() if data is not None else None

    def _bind(self, state):
        if state.get('service', self.binding) != self.binding:
            raise TestError('Shared settings file belongs to another service', 'PLUGIN_CONTEXT_CHANGED', 409)
        state['service'] = deepcopy(self.binding)

    def _write(self, state, remote, before):
        if self._read() != before:
            return {'state': 'CONFLICT', 'reason': 'FILE_CHANGED_DURING_SYNC'}
        # Preserve the previous bytes before replacing, including an external edit
        # that occurred before our final check. SSH credentials are not exported.
        if before is not None:
            backup = plain_path(self.path.with_name(self.path.name + '.' + uuid4().hex + '.bak'))
            fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as stream: stream.write(before)
        written = (json.dumps(remote, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        atomic_json(self.path, remote)
        state.update(file_hash=self._hash(written), revision=remote['expected_revision'])
        if self._read() != written:
            return {'state': 'CONFLICT', 'reason': 'FILE_EDITED_AFTER_SYNC', 'path': str(self.path)}
        return {'state': 'SYNCED', 'path': str(self.path), 'revision': state['revision']}

    def sync(self):
        """Poll remote into a clean file. Local edits require explicit push."""
        with self.store.transaction() as state:
            self._bind(state)
            before = self._read()
            remote = self.client.export_settings()
            if before is None: return self._write(state, remote, before)
            local = strict_json(before)
            from ..core.shared_settings import SettingsFile
            try: SettingsFile.model_validate(local)
            except ValueError: raise ValueError('Invalid shared settings JSON schema') from None
            if local.get('expected_revision') == remote['expected_revision'] and content(local) == content(remote):
                state.update(file_hash=self._hash(before), revision=remote['expected_revision'])
                return {'state': 'SYNCED', 'path': str(self.path), 'revision': remote['expected_revision']}
            changed = self._hash(before) != state.get('file_hash')
            if changed:
                both = local.get('expected_revision') != remote['expected_revision']
                return {'state': 'CONFLICT' if both else 'LOCAL_EDIT', 'path': str(self.path),
                        'server_revision': remote['expected_revision'], 'file_revision': local.get('expected_revision')}
            if state.get('revision') != remote['expected_revision']:
                return self._write(state, remote, before)
            return {'state': 'SYNCED', 'path': str(self.path), 'revision': remote['expected_revision']}

    def push(self):
        """Apply exactly the edited revision; reconcile an uncertain response."""
        with self.store.transaction() as state:
            self._bind(state)
            before = self._read()
            if before is None: raise ValueError('Shared settings file does not exist')
            local = strict_json(before)
            validation = self.client.import_settings(local, validate_only=True)
            if validation.get('revision_matches') is True:
                try:
                    self.client.import_settings(local)
                except TestError as exc:
                    if exc.code not in {'SERVICE_CONNECTION_FAILED', 'SERVICE_RESPONSE_INVALID'}: raise
                    remote = self.client.export_settings()
                    if content(remote) != content(local):
                        return {'state': 'UNCERTAIN', 'reason': exc.code, 'path': str(self.path)}
            remote = self.client.export_settings()
            if content(remote) != content(local):
                return {'state': 'CONFLICT', 'reason': 'SERVER_CHANGED', 'path': str(self.path)}
            # Only the exact content read back from the service is acknowledged.
            return self._write(state, remote, before)
