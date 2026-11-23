"""Standalone Linux shared-settings.db store (DELETE + flock + CAS).

Shared in-process by the plugin CLI/runtime and Agent Monitor without
requiring Agent Monitor to be running.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from pydantic import Field, StrictInt, model_validator

from .models import StrictModel, TestError, digest
from .retention import StoragePolicy, StorageUpdate
from .shared_settings import IntegrationValues, SharedUpdate, SettingsFile, FORMAT
from .timeouts import TimeoutValues, TimeoutUpdate


DEFAULT_CONNECTOR_PORT = 8771
_RUNNER_ID_RE = re.compile(r'^[a-f0-9]{32}$')


def resolve_runtime_dir(home=None, runtime=None):
    """Resolve the authoritative Linux <runtime> directory.

    Precedence: explicit --runtime -> <home>/runtime-location.json -> <home>/runtime.
    """
    if runtime is not None:
        return Path(runtime).expanduser().resolve()
    base = Path(home).expanduser().resolve() if home is not None else (Path.home() / '.local/share/bsp-agent-monitor').resolve()
    location = base / 'runtime-location.json'
    if location.is_file() and not location.is_symlink():
        try:
            saved = json.loads(location.read_text(encoding='utf-8'))
            if isinstance(saved, dict) and isinstance(saved.get('path'), str) and Path(saved['path']).is_absolute():
                return Path(saved['path']).resolve()
        except (OSError, ValueError):
            pass
    return (base / 'runtime').resolve()


class ConnectorPreferences(StrictModel):
    preferred_connector_port: StrictInt = Field(default=DEFAULT_CONNECTOR_PORT, ge=1, le=65535)
    expected_runner_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')

    @model_validator(mode='after')
    def valid_port(self):
        if self.preferred_connector_port < 1 or self.preferred_connector_port > 65535:
            raise ValueError('Invalid connector port')
        return self


class SharedSettingsStore:
    """SQLite DELETE + flock + revision CAS store at <runtime>/shared-settings.db."""

    def __init__(self, runtime):
        self.runtime = Path(runtime).expanduser().resolve()
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.path = self.runtime / 'shared-settings.db'
        self.lock_path = self.runtime / 'shared-settings.lock'
        self._init_db()

    @contextmanager
    def _locked(self):
        if any(p.is_symlink() for p in (self.runtime, self.path, self.lock_path) if p.exists()):
            raise TestError('Symlinks are not permitted for shared-settings paths', 'SHARED_SETTINGS_UNSAFE', 422)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | (getattr(os, 'O_NOFOLLOW', 0)), 0o600)
        with os.fdopen(fd, 'a+') as handle:
            if os.name != 'nt':
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name != 'nt':
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA journal_mode=DELETE')
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._locked():
            existed = self.path.exists()
            with self._connection() as c:
                c.execute('BEGIN IMMEDIATE')
                try:
                    c.executescript('''
                        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                        INSERT OR IGNORE INTO meta VALUES('schema_version', '1');
                        CREATE TABLE IF NOT EXISTS shared_settings(id INTEGER PRIMARY KEY CHECK(id=1), revision TEXT NOT NULL, data_json TEXT NOT NULL);
                        CREATE TABLE IF NOT EXISTS timeouts(id INTEGER PRIMARY KEY CHECK(id=1), revision TEXT NOT NULL, data_json TEXT NOT NULL);
                        CREATE TABLE IF NOT EXISTS command_profiles(name TEXT PRIMARY KEY, revision TEXT NOT NULL, data_json TEXT NOT NULL);
                        CREATE TABLE IF NOT EXISTS sources(id INTEGER PRIMARY KEY CHECK(id=1), revision TEXT NOT NULL, data_json TEXT NOT NULL);
                        CREATE TABLE IF NOT EXISTS storage_policy(id INTEGER PRIMARY KEY CHECK(id=1), revision TEXT NOT NULL, data_json TEXT NOT NULL);
                        CREATE TABLE IF NOT EXISTS connector_preferences(id INTEGER PRIMARY KEY CHECK(id=1), data_json TEXT NOT NULL);
                    ''')
                    ver = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                    if not ver or ver[0] != '1':
                        raise RuntimeError('Unsupported shared-settings.db schema version')
                    if not existed:
                        self._migrate_once(c)
                    self._ensure_defaults(c)
                    c.commit()
                except BaseException:
                    c.rollback()
                    raise

    def _migrate_once(self, c):
        sources_checked = []
        candidates = [
            self.runtime / 'gui-test-dashboard-windows' / 'runs.db',
            self.runtime / 'runs.db',
        ]
        for db_path in candidates:
            if not db_path.is_file() or db_path.is_symlink():
                continue
            try:
                ro = sqlite3.connect(f'{db_path.resolve().as_uri()}?mode=ro', uri=True)
            except sqlite3.Error:
                continue
            try:
                tables = {r[0] for r in ro.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if 'documents' not in tables:
                    continue
                row = ro.execute("SELECT data FROM documents WHERE kind='shared-settings' AND name='current'").fetchone()
                if row and not c.execute('SELECT 1 FROM shared_settings WHERE id=1').fetchone():
                    try:
                        val = IntegrationValues.model_validate(json.loads(row[0])).model_dump()
                        c.execute('INSERT OR IGNORE INTO shared_settings VALUES(1,?,?)', (digest(val), json.dumps(val, ensure_ascii=False)))
                    except Exception:
                        pass
                row = ro.execute("SELECT data FROM documents WHERE kind='execution-timeouts' AND name='current'").fetchone()
                if row and not c.execute('SELECT 1 FROM timeouts WHERE id=1').fetchone():
                    try:
                        val = TimeoutValues.model_validate(json.loads(row[0])).model_dump()
                        c.execute('INSERT OR IGNORE INTO timeouts VALUES(1,?,?)', (digest(val), json.dumps(val, ensure_ascii=False)))
                    except Exception:
                        pass
                for name_row in ro.execute("SELECT name, data FROM documents WHERE kind='command'"):
                    try:
                        cmd = json.loads(name_row[1])
                        rev = cmd.get('revision') or digest(cmd)
                        c.execute('INSERT OR IGNORE INTO command_profiles VALUES(?,?,?)',
                                  (name_row[0], rev, json.dumps(cmd, ensure_ascii=False)))
                    except Exception:
                        pass
                row = ro.execute("SELECT data FROM documents WHERE kind='source-state' AND name='current'").fetchone()
                if row and not c.execute('SELECT 1 FROM sources WHERE id=1').fetchone():
                    try:
                        src = json.loads(row[0])
                        c.execute('INSERT OR IGNORE INTO sources VALUES(1,?,?)', (digest(src), json.dumps(src, ensure_ascii=False)))
                    except Exception:
                        pass
                row = ro.execute("SELECT data FROM documents WHERE kind='storage-policy' AND name='current'").fetchone()
                if row and not c.execute('SELECT 1 FROM storage_policy WHERE id=1').fetchone():
                    try:
                        pol = StoragePolicy.model_validate(json.loads(row[0])).model_dump()
                        c.execute('INSERT OR IGNORE INTO storage_policy VALUES(1,?,?)', (digest(pol), json.dumps(pol, ensure_ascii=False)))
                    except Exception:
                        pass
                sources_checked.append(str(db_path.relative_to(self.runtime)))
            finally:
                ro.close()
        gui_settings = self.runtime / 'gui-test-settings.json'
        if gui_settings.is_file() and not gui_settings.is_symlink():
            sources_checked.append('gui-test-settings.json')
        gui_json = self.runtime / 'gui-test.json'
        if gui_json.is_file() and not gui_json.is_symlink():
            try:
                cfg = json.loads(gui_json.read_text(encoding='utf-8-sig'))
                if isinstance(cfg, dict):
                    url = cfg.get('url', '')
                    m = re.fullmatch(r'http://127\.0\.0\.1:([0-9]+)', str(url).rstrip('/'))
                    if m:
                        port = int(m.group(1))
                        if 1 <= port <= 65535:
                            prefs = ConnectorPreferences(preferred_connector_port=port).model_dump()
                            c.execute('INSERT OR IGNORE INTO connector_preferences VALUES(1,?)', (json.dumps(prefs),))
                    sources_checked.append('gui-test.json')
            except Exception:
                pass
        if sources_checked:
            c.execute("INSERT OR REPLACE INTO meta VALUES('migrated_from', ?)", (json.dumps(sources_checked),))

    def _ensure_defaults(self, c):
        if not c.execute('SELECT 1 FROM shared_settings WHERE id=1').fetchone():
            val = IntegrationValues().model_dump()
            c.execute('INSERT INTO shared_settings VALUES(1,?,?)', (digest(val), json.dumps(val, ensure_ascii=False)))
        if not c.execute('SELECT 1 FROM timeouts WHERE id=1').fetchone():
            val = TimeoutValues().model_dump()
            c.execute('INSERT INTO timeouts VALUES(1,?,?)', (digest(val), json.dumps(val, ensure_ascii=False)))
        if not c.execute('SELECT 1 FROM sources WHERE id=1').fetchone():
            val = {'active': {'kind': 'legacy', 'location': ''}, 'version': 1}
            c.execute('INSERT INTO sources VALUES(1,?,?)', (digest(val), json.dumps(val, ensure_ascii=False)))
        if not c.execute('SELECT 1 FROM storage_policy WHERE id=1').fetchone():
            val = StoragePolicy().model_dump()
            c.execute('INSERT INTO storage_policy VALUES(1,?,?)', (digest(val), json.dumps(val, ensure_ascii=False)))
        if not c.execute('SELECT 1 FROM connector_preferences WHERE id=1').fetchone():
            val = ConnectorPreferences().model_dump()
            c.execute('INSERT INTO connector_preferences VALUES(1,?)', (json.dumps(val, ensure_ascii=False),))

    def _read_locked(self, c):
        integ = IntegrationValues.model_validate(json.loads(c.execute('SELECT data_json FROM shared_settings WHERE id=1').fetchone()[0])).model_dump()
        tmo = TimeoutValues.model_validate(json.loads(c.execute('SELECT data_json FROM timeouts WHERE id=1').fetchone()[0])).model_dump()
        tmo_full = tmo | {'revision': digest(tmo)}
        values = {'integration': integ, 'timeouts': tmo_full}
        return values | {'revision': digest(values)}

    def read(self):
        with self._locked(), self._connection() as c:
            return self._read_locked(c)

    def save(self, body):
        update = SharedUpdate.model_validate(body)
        with self._locked(), self._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                current = self._read_locked(c)
                if update.expected_revision != current['revision']:
                    err = TestError('Shared settings changed; reload before saving', 'SETTINGS_CHANGED', 409)
                    err.diagnostic = {'current_revision': current['revision']}
                    raise err
                integ = update.integration.model_dump()
                tmo = update.timeouts.model_dump()
                c.execute('UPDATE shared_settings SET revision=?, data_json=? WHERE id=1',
                          (digest(integ), json.dumps(integ, ensure_ascii=False)))
                c.execute('UPDATE timeouts SET revision=?, data_json=? WHERE id=1',
                          (digest(tmo), json.dumps(tmo, ensure_ascii=False)))
                result = self._read_locked(c)
                c.commit()
                return result
            except BaseException:
                c.rollback()
                raise

    def export(self):
        value = self.read()
        return {'format': FORMAT, 'expected_revision': value['revision'], 'integration': value['integration'],
                'timeouts': {k: v for k, v in value['timeouts'].items() if k != 'revision'}}

    def import_file(self, body):
        value = SettingsFile.model_validate(body)
        return self.save(value.model_dump(exclude={'format'}))

    def read_timeouts(self):
        with self._locked(), self._connection() as c:
            val = TimeoutValues.model_validate(json.loads(c.execute('SELECT data_json FROM timeouts WHERE id=1').fetchone()[0])).model_dump()
            return val | {'revision': digest(val)}

    def save_timeouts(self, body):
        update = TimeoutUpdate.model_validate(body)
        val = TimeoutValues.model_validate(update.model_dump(exclude={'expected_revision'})).model_dump()
        with self._locked(), self._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                cur = TimeoutValues.model_validate(json.loads(c.execute('SELECT data_json FROM timeouts WHERE id=1').fetchone()[0])).model_dump()
                if digest(cur) != update.expected_revision:
                    raise TestError('TC 제한시간 설정이 변경되었습니다. 다시 불러오고 Preflight를 검사하세요.', 'TC_TIMEOUT_CHANGED', 409)
                rev = digest(val)
                c.execute('UPDATE timeouts SET revision=?, data_json=? WHERE id=1', (rev, json.dumps(val, ensure_ascii=False)))
                c.commit()
                return val | {'revision': rev}
            except BaseException:
                c.rollback()
                raise

    def read_command_profiles(self):
        with self._locked(), self._connection() as c:
            rows = c.execute('SELECT name, revision, data_json FROM command_profiles ORDER BY name').fetchall()
            return [json.loads(r['data_json']) | {'name': r['name'], 'revision': r['revision']} for r in rows]

    def save_command_profile(self, name, template, *, expected_revision=None):
        from ..adapters.runner import validate_command_template
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', name):
            raise TestError('Invalid command profile name', 'COMMAND_INVALID', 422)
        clean = validate_command_template(template)
        rev = digest(clean)
        payload = {'name': name, 'revision': rev, **clean}
        with self._locked(), self._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                row = c.execute('SELECT revision FROM command_profiles WHERE name=?', (name,)).fetchone()
                current_rev = row['revision'] if row else None
                if expected_revision != current_rev:
                    raise TestError('Command profile changed; reload before saving', 'SETTINGS_CHANGED', 409)
                c.execute('INSERT INTO command_profiles VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET revision=excluded.revision, data_json=excluded.data_json',
                          (name, rev, json.dumps(payload, ensure_ascii=False)))
                c.commit()
                return payload
            except BaseException:
                c.rollback()
                raise

    def read_storage_policy(self):
        with self._locked(), self._connection() as c:
            val = StoragePolicy.model_validate(json.loads(c.execute('SELECT data_json FROM storage_policy WHERE id=1').fetchone()[0])).model_dump()
            return val | {'revision': digest(val)}

    def save_storage_policy(self, body):
        update = StorageUpdate.model_validate(body)
        val = update.model_dump(exclude={'expected_revision'})
        with self._locked(), self._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                cur = StoragePolicy.model_validate(json.loads(c.execute('SELECT data_json FROM storage_policy WHERE id=1').fetchone()[0])).model_dump()
                if digest(cur) != update.expected_revision:
                    raise TestError('Storage policy changed; reload settings', 'STORAGE_POLICY_CHANGED', 409)
                rev = digest(val)
                c.execute('UPDATE storage_policy SET revision=?, data_json=? WHERE id=1', (rev, json.dumps(val, ensure_ascii=False)))
                c.commit()
                return val | {'revision': rev}
            except BaseException:
                c.rollback()
                raise

    def read_preferences(self):
        with self._locked(), self._connection() as c:
            val = ConnectorPreferences.model_validate(json.loads(c.execute('SELECT data_json FROM connector_preferences WHERE id=1').fetchone()[0])).model_dump()
            return val | {'revision': digest(val)}

    def save_preferences(self, patch, *, expected_revision=None):
        with self._locked(), self._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                cur = ConnectorPreferences.model_validate(json.loads(c.execute('SELECT data_json FROM connector_preferences WHERE id=1').fetchone()[0])).model_dump()
                if expected_revision is not None and digest(cur) != expected_revision:
                    raise TestError('Connector preferences changed; reload before saving', 'SETTINGS_CHANGED', 409)
                merged = dict(cur, **{k: v for k, v in patch.items() if k in ConnectorPreferences.model_fields})
                validated = ConnectorPreferences.model_validate(merged).model_dump()
                c.execute('UPDATE connector_preferences SET data_json=? WHERE id=1', (json.dumps(validated, ensure_ascii=False),))
                c.commit()
                return validated | {'revision': digest(validated)}
            except BaseException:
                c.rollback()
                raise

    def pin_runner_if_unset(self, runner_id):
        if not isinstance(runner_id, str) or not _RUNNER_ID_RE.fullmatch(runner_id):
            raise TestError('Invalid runner_id format', 'RUNNER_INVALID', 422)
        with self._locked(), self._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                cur = ConnectorPreferences.model_validate(json.loads(c.execute('SELECT data_json FROM connector_preferences WHERE id=1').fetchone()[0])).model_dump()
                expected = cur.get('expected_runner_id')
                if expected is None:
                    cur['expected_runner_id'] = runner_id
                    c.execute('UPDATE connector_preferences SET data_json=? WHERE id=1', (json.dumps(cur, ensure_ascii=False),))
                    c.commit()
                    return cur | {'revision': digest(cur), 'pinned': 'tofu'}
                if expected != runner_id:
                    raise TestError('Connected runner_id differs from pinned expected_runner_id', 'RUNNER_CHANGED', 409)
                c.commit()
                return cur | {'revision': digest(cur), 'pinned': 'matched'}
            except BaseException:
                c.rollback()
                raise

    def rebind_runner(self, runner_id):
        if runner_id is not None and (not isinstance(runner_id, str) or not _RUNNER_ID_RE.fullmatch(runner_id)):
            raise TestError('Invalid runner_id format', 'RUNNER_INVALID', 422)
        return self.save_preferences({'expected_runner_id': runner_id})

    def sync_from_store_if_newer(self, integration_dict, timeouts_dict):
        """Sync values written via legacy SharedSettings(Store) into shared-settings.db."""
        integ = IntegrationValues.model_validate(integration_dict).model_dump()
        tmo = TimeoutValues.model_validate({k: v for k, v in timeouts_dict.items() if k != 'revision'}).model_dump()
        with self._locked(), self._connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                c.execute('UPDATE shared_settings SET revision=?, data_json=? WHERE id=1',
                          (digest(integ), json.dumps(integ, ensure_ascii=False)))
                c.execute('UPDATE timeouts SET revision=?, data_json=? WHERE id=1',
                          (digest(tmo), json.dumps(tmo, ensure_ascii=False)))
                c.commit()
            except BaseException:
                c.rollback()
                raise
