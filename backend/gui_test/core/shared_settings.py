"""One revisioned configuration authority for plugin, host and connector clients.

Only future preparations read this document. Accepted runs keep their snapshots.
Windows local mapping is desired state until its owning connector reports receipt.
"""
import json
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator
from .models import StrictModel, Connection, TestError, digest, now
from .timeouts import TimeoutValues
from .integration import validate_patterns

FORMAT = 'gui-test-shared-settings-v1'


def linux_path(value):
    if (not value.startswith('/') or '\\' in value or '..' in value.split('/') or
            any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Use an absolute Linux path without traversal')
    return value


class IntegrationValues(StrictModel):
    installer_roots: list[str] = Field(default_factory=list, max_length=32)
    source_roots: list[str] = Field(default_factory=list, max_length=32)
    installer_path: str = Field(default='', max_length=4096)
    tc_root: str = Field(default='', max_length=4096)
    connection: Connection | None = None
    runner_id: str = Field(default='', max_length=160)
    command_profile: str = Field(default='', max_length=80)
    command_revision: str = Field(default='', max_length=256)
    flash_profile: str = Field(default='', max_length=160)
    flash_profile_revision: str | None = Field(default=None, max_length=256)
    module_defaults: dict[str, list[str]] = Field(default_factory=dict, max_length=1000)
    global_defaults: list[str] = Field(default_factory=list, max_length=100)
    metadata: dict = Field(default_factory=dict, max_length=10000)
    max_bundle_bytes: int = Field(default=2_147_483_648, strict=True, ge=1, le=1_099_511_627_776)

    @model_validator(mode='after')
    def safe(self):
        for value in self.installer_roots + self.source_roots:
            linux_path(value)
        for selected, roots in ((self.installer_path, self.installer_roots), (self.tc_root, self.source_roots)):
            if selected:
                linux_path(selected)
                if not any(PurePosixPath(selected).is_relative_to(PurePosixPath(root)) for root in roots):
                    raise ValueError('Selected path must be within an allowed root')
        if self.installer_path and PurePosixPath(self.installer_path).suffix.lower() != '.bat':
            raise ValueError('Installer must identify a BAT')
        if self.global_defaults:
            validate_patterns(self.global_defaults)
        for module, patterns in self.module_defaults.items():
            if not module.strip() or len(module) > 160:
                raise ValueError('Invalid module key')
            validate_patterns(patterns)
        return self


class SharedUpdate(StrictModel):
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    integration: IntegrationValues
    timeouts: TimeoutValues


class SettingsFile(SharedUpdate):
    format: Literal['gui-test-shared-settings-v1'] = FORMAT


class ConnectorDesired(StrictModel):
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    runner_id: str = Field(min_length=1, max_length=160)
    # Windows profile is validated by the owner before applying. Keep central
    # transport free of SSH credentials or arbitrary command execution settings.
    settings: dict = Field(max_length=16)

    @model_validator(mode='after')
    def safe(self):
        allowed = {'boards', 'console_observers', 'board_names', 'connector_inactive_boards',
                   'serial_transport', 'serial_settings', 'python', 'putty_path'}
        if set(self.settings) - allowed:
            raise ValueError('Unsupported Windows local settings')
        if len(json.dumps(self.settings)) > 32768:
            raise ValueError('Windows settings too large')
        return self


class ConnectorReceipt(StrictModel):
    runner_id: str = Field(min_length=1, max_length=160)
    desired_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    state: Literal['APPLIED', 'BLOCKED']
    reason: str = Field(default='', max_length=1000)
    applied_revision: str = Field(default='', max_length=256)


class SharedSettings:
    def __init__(self, manager, initial=None):
        self.manager, self.store = manager, manager.store
        initial = initial() if callable(initial) else initial or {}
        selected = {k: v for k, v in initial.items() if k in IntegrationValues.model_fields}
        # Previous configurations had only tc_root, without an allowed source
        # browser. Preserve that root as the initial permitted source scope.
        if selected.get('tc_root') and not selected.get('source_roots'):
            selected['source_roots'] = [selected['tc_root']]
        values = IntegrationValues.model_validate(selected).model_dump()
        with self.store.transaction() as c:
            c.execute("INSERT OR IGNORE INTO documents VALUES('shared-settings','current',?)", (json.dumps(values),))

    def _integration(self, c):
        row = c.execute("SELECT data FROM documents WHERE kind='shared-settings' AND name='current'").fetchone()
        return IntegrationValues.model_validate(json.loads(row[0])).model_dump()

    def read(self, c=None):
        if c is None:
            with self.store.connection() as connection:
                connection.execute('BEGIN')
                return self.read(connection)
        values = {'integration': self._integration(c), 'timeouts': self.manager.timeouts.read(c)}
        return values | {'revision': digest(values), 'connector_application': self.connector_application(c)}

    def save(self, body):
        update = SharedUpdate.model_validate(body)
        with self.store.transaction() as c:
            current = self.read(c)
            if update.expected_revision != current['revision']:
                raise TestError('Shared settings changed; reload before saving', 'SETTINGS_CHANGED', 409)
            self.manager.timeouts.save(update.timeouts.model_dump() | {'expected_revision': current['timeouts']['revision']}, c)
            c.execute("UPDATE documents SET data=? WHERE kind='shared-settings' AND name='current'",
                      (json.dumps(update.integration.model_dump()),))
            return self.read(c)

    def export(self):
        value = self.read()
        return {'format': FORMAT, 'expected_revision': value['revision'], 'integration': value['integration'],
                'timeouts': {k: v for k, v in value['timeouts'].items() if k != 'revision'}}

    def import_file(self, body):
        value = SettingsFile.model_validate(body)
        return self.save(value.model_dump(exclude={'format'}))

    def integration_config(self):
        # All readers use a fresh immutable object; no mutable config is shared
        # with previously accepted run snapshots.
        return self.read()['integration']

    def browse(self, kind, location=None):
        config = self.integration_config()
        roots = config['installer_roots' if kind == 'installer' else 'source_roots']
        if not location:
            return {'kind': kind, 'roots': roots, 'path': None, 'entries': []}
        try:
            linux_path(location)
            path = Path(location)
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise ValueError('Symbolic links are not browsable')
            resolved = path.resolve(strict=True)
            if not any(resolved.is_relative_to(Path(root).resolve(strict=True)) for root in roots):
                raise ValueError('Outside allowed roots')
            if not resolved.is_dir():
                raise ValueError('Directory required')
            entries = []
            for item in sorted(resolved.iterdir(), key=lambda p: p.name.casefold()):
                if item.name.startswith('.') or item.is_symlink():
                    continue
                if item.is_dir() or kind == 'source' and item.suffix == '.py' or kind == 'installer' and item.suffix.lower() == '.bat':
                    entries.append({'name': item.name, 'path': str(item), 'directory': item.is_dir()})
                if len(entries) >= 1000:
                    break
            return {'kind': kind, 'roots': roots, 'path': str(resolved), 'entries': entries}
        except (OSError, ValueError) as exc:
            raise TestError('Path is unavailable or outside the configured server roots', 'PATH_SCOPE', 422) from exc

    def connector_application(self, c=None):
        if c is None:
            with self.store.connection() as connection:
                return self.connector_application(connection)
        row = c.execute("SELECT data FROM documents WHERE kind='connector-desired' AND name='current'").fetchone()
        value = json.loads(row[0]) if row else {'runner_id': None, 'settings': {}, 'state': 'UNCONFIGURED', 'desired_revision': None}
        return value | {'revision': digest(value)}

    def desired(self, body):
        value = ConnectorDesired.model_validate(body)
        registry = getattr(self.manager.runner, 'registry', None)
        registered = registry.read() if registry else None
        if registered and registered['runner_id'] != value.runner_id:
            raise TestError('Original connector required', 'RUNNER_CHANGED', 409)
        with self.store.transaction() as c:
            current = self.connector_application(c)
            if value.expected_revision != current['revision']:
                raise TestError('Connector desired settings changed', 'SETTINGS_CHANGED', 409)
            payload = {'runner_id': value.runner_id, 'settings': value.settings}
            payload.update(desired_revision=digest(payload), state='PENDING', reason='', applied_revision='', updated_at=now())
            c.execute("INSERT INTO documents VALUES('connector-desired','current',?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data", (json.dumps(payload),))
            return self.connector_application(c)

    def receipt(self, body):
        receipt = ConnectorReceipt.model_validate(body)
        registry = getattr(self.manager.runner, 'registry', None)
        registered = registry.read() if registry else None
        if not registered or registered['runner_id'] != receipt.runner_id:
            raise TestError('Receipt requires the registered connector', 'RUNNER_CHANGED', 409)
        with self.store.transaction() as c:
            current = self.connector_application(c)
            if current['runner_id'] != receipt.runner_id or current['desired_revision'] != receipt.desired_revision:
                raise TestError('Connector receipt is stale', 'SETTINGS_CHANGED', 409)
            if receipt.state == 'APPLIED' and (not receipt.applied_revision or any(run['state'] not in {'COMPLETED', 'CANCELLED'} for run in self.store.all())):
                raise TestError('Local mapping application is blocked by an active/unknown Run', 'CONNECTOR_BUSY', 409)
            current.pop('revision', None)
            current.update(state=receipt.state, reason=receipt.reason, applied_revision=receipt.applied_revision, received_at=now())
            c.execute("UPDATE documents SET data=? WHERE kind='connector-desired' AND name='current'", (json.dumps(current),))
            return self.connector_application(c)


def attach_shared_settings(manager, initial=None):
    existing = getattr(manager, 'shared_settings', None)
    if existing is not None:
        return existing
    service = getattr(manager, 'integration', None)
    settings = SharedSettings(manager, initial if initial is not None else service.config if service else {})
    manager.shared_settings = settings
    if service is not None:
        service.config = settings.integration_config
    return settings
