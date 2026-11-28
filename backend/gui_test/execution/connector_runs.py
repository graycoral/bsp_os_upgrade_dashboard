"""Direct Connector v1 engine: autonomous run bundles, fail-stop latch, bridge, diagnostics, and projections."""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from typing import Annotated, Any, Literal

from pydantic import Field, StrictBool, StrictInt, ValidationError

from ..adapters.runner import resolve_argv, validate_command_template, validate_windows_command
from ..connector.logs import redact
from ..core.failure_analysis import normalized_cause
from ..core.models import CommandTemplate, Connection, StrictModel, TestError, digest, uid
from ..core.results import parse_result


now = time.time
from ..core.retention import StoragePolicy, StorageUpdate
from . import failure_evidence, installer_snapshots, retention, sharing
from .capture import Capture
from .path_runs import PathRunRequest, adb_target, is_adb_tc, plan_path, suite_group
from .console_observer import ConsoleObserver
from .flashing import UnknownHardware, relative as valid_bundle_relative
from .process import ProcessTree
from .source import snapshot as source_snapshot, source_path
from .source_snapshots import checked_files, materialize_snapshot, load_manifest as load_source_manifest
from ..core.discovery import discover, discover_contents

CONNECTOR_SCHEMA_VERSION = '4'
CONNECTOR_DEFAULT_TC_TIMEOUT_SECONDS = 600
ADB_READY_TIMEOUT_S = 30
MAX_PEER_OBSERVATIONS = 16
MAX_TC_PROJECTION_ITEMS = 2000
MAX_TC_PROJECTION_BYTES = 512 * 1024
MAX_RETRY_CHAIN_DEFAULT = 3
DEFAULT_ANALYSIS_LEASE_TTL_S = 120
TC_PROJECTION_STALE_SECONDS = 900
MANAGER_HEARTBEAT_TTL_S = 20.0

ACTIVE_RUN_STATES = (
    'QUEUED',
    'FLASHING',
    'RUNNING',
    'PAUSED',
    'PAUSE_REQUESTED',
    'CANCEL_REQUESTED',
    'FINALIZING',
    'UNKNOWN',
)
ACTIVE_RUN_STATES_SQL = ','.join('?' for _ in ACTIVE_RUN_STATES)
IN_FLIGHT_RECOVERY_STATES = (
    'FLASHING',
    'RUNNING',
    'PAUSE_REQUESTED',
    'CANCEL_REQUESTED',
    'FINALIZING',
)
TERMINAL_OUTCOMES = {'PASSED', 'FAILED', 'CANCELLED', 'SUPERSEDED_BY_REPREPARE', 'ABORTED'}
VALID_LOG_STREAMS = {'uart', 'installer', 'stdout', 'stderr', 'events'}


def make_error(message: str, code: str = 'CONFLICT', status: int = 409, **extra: Any) -> TestError:
    exc = TestError(message, code, status)
    if extra:
        exc.extra = extra
    return exc


def _dpapi_crypt(data: bytes, decrypt: bool = False) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_byte))]

    buf = ctypes.create_string_buffer(data, len(data))
    inp = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    fn = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    args = ([ctypes.byref(inp), None, None, None, None, 1, ctypes.byref(out)]
            if decrypt else [ctypes.byref(inp), None, None, None, None, 1, ctypes.byref(out)])
    if not fn(*args):
        raise OSError('Windows DPAPI token operation failed')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


class BridgeTokenStore:
    """Shared local manager-bridge token using Windows DPAPI (or chmod 600 on POSIX)."""

    def __init__(self, directory: Path, windows: bool | None = None):
        self.directory = Path(directory)
        self.windows = (os.name == 'nt') if windows is None else bool(windows)
        self.path = self.directory / ('runner-token.dpapi' if self.windows else 'runner-token')
        self._cached: tuple[int, int, str] | None = None

    def load(self, readonly: bool = True) -> str | None:
        if not self.path.exists():
            self._cached = None
            if readonly:
                return None
            return self.ensure()
        info = self.path.stat()
        if not self.windows:
            if info.st_uid != os.getuid() or (info.st_mode & 0o077):
                raise ValueError('Manager bridge token permissions must be owner-only (600)')
        cached = self._cached
        if cached is not None and cached[0] == info.st_mtime_ns and cached[1] == info.st_size:
            return cached[2]
        raw = self.path.read_bytes()
        data = _dpapi_crypt(raw, decrypt=True) if self.windows else raw
        token = data.decode('ascii').strip()
        if not re.fullmatch(r'[A-Za-z0-9._~+/=-]{32,128}', token):
            raise ValueError('Invalid manager bridge token format')
        self._cached = (info.st_mtime_ns, info.st_size, token)
        return token

    def save(self, token: str) -> str:
        if not re.fullmatch(r'[A-Za-z0-9._~+/=-]{32,128}', token):
            raise ValueError('Invalid manager bridge token format')
        self.directory.mkdir(parents=True, exist_ok=True)
        if not self.windows:
            try:
                os.chmod(self.directory, 0o700)
            except OSError:
                pass
        raw = token.encode('ascii')
        encoded = _dpapi_crypt(raw, decrypt=False) if self.windows else raw
        tmp = self.path.with_suffix('.tmp')
        if self.windows:
            tmp.write_bytes(encoded)
        else:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'wb') as out:
                out.write(encoded)
        os.replace(tmp, self.path)
        try:
            info = self.path.stat()
            self._cached = (info.st_mtime_ns, info.st_size, token)
        except OSError:
            self._cached = None
        return token

    def ensure(self) -> str:
        existing = self.load(readonly=True)
        if existing:
            return existing
        return self.save(secrets.token_urlsafe(36))


def resolve_step_timeout(
    tc_id: str,
    timeout_snapshot: dict | None = None,
    metadata_timeout: int | None = None,
) -> int:
    """Precedence: per-TC override -> explicit default_seconds -> TC metadata timeout -> 600s."""
    snap = timeout_snapshot if isinstance(timeout_snapshot, dict) else {}
    overrides = snap.get('overrides') if isinstance(snap.get('overrides'), dict) else {}
    override = overrides.get(tc_id)
    if type(override) is int and 1 <= override <= 86400:
        return override
    default_s = snap.get('default_seconds')
    if type(default_s) is int and 1 <= default_s <= 86400:
        return default_s
    if type(metadata_timeout) is int and 1 <= metadata_timeout <= 86400:
        return metadata_timeout
    return CONNECTOR_DEFAULT_TC_TIMEOUT_SECONDS


def slice_utf8_complete(raw: bytes) -> tuple[str, int]:
    """Decode complete UTF-8 sequences from raw bytes, returning (text, consumed_byte_count)."""
    if not raw:
        return '', 0
    end = len(raw)
    # Trim up to 3 trailing bytes if they form an incomplete multi-byte UTF-8 sequence.
    start_check = max(0, end - 3)
    cut = end
    for idx in range(end - 1, start_check - 1, -1):
        b = raw[idx]
        if (b & 0x80) == 0:
            break
        if (b & 0xC0) == 0xC0:
            # Leading byte: determine expected UTF-8 length.
            if (b & 0xE0) == 0xC0:
                needed = 2
            elif (b & 0xF0) == 0xE0:
                needed = 3
            elif (b & 0xF8) == 0xF0:
                needed = 4
            else:
                needed = 1
            if end - idx < needed:
                cut = idx
            break
    valid = raw[:cut]
    return valid.decode('utf-8', errors='replace'), len(valid)


def _utc_iso(ts: float | None = None) -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now() if ts is None else ts))


class PeerHelloRequest(StrictModel):
    peer_type: Literal['plugin', 'agent_monitor']
    peer_instance_id: str = Field(min_length=1, max_length=128)
    peer_version: str = Field(min_length=1, max_length=64)
    target_port: Annotated[StrictInt, Field(ge=1, le=65535)]
    expected_runner_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    linux_host: str = Field(min_length=1, max_length=160)
    client_status: Literal['OK', 'MISMATCH', 'INCOMPATIBLE'] = 'OK'
    client_issue: dict | None = None
    linux_diagnostics: dict | None = None


def build_tc_projection(root: Path, t_doc: dict) -> tuple[dict, dict]:
    catalog = discover(root, include_linux_shell=True)
    tests = catalog.get('tests', [])
    truncated = len(tests) > MAX_TC_PROJECTION_ITEMS
    selected = tests[:MAX_TC_PROJECTION_ITEMS]
    items = []
    for tc in selected:
        explicit_timeout = tc.get('timeout') if tc.get('timeout_explicit', True) else None
        eff = resolve_step_timeout(tc['id'], t_doc, explicit_timeout)
        items.append({
            'tc_id': tc['id'],
            'path': tc['path'],
            'name': tc.get('name') or Path(tc['path']).stem,
            'module': tc.get('module'),
            'kind': tc['kind'],
            'effective_timeout_s': eff,
            'source_timeout_s': explicit_timeout,
            'disabled_reason': tc.get('disabled_reason'),
            'after': list(tc.get('after', [])),
        })
    payload = {
        'tc_root': str(root.resolve()),
        'catalog_revision': catalog['revision'],
        'generated_at': time.time(),
        'truncated': truncated,
        'total_count': len(tests),
        'items': [],
    }
    # The Host checks the size using the same json.dumps formatting.
    size = len(json.dumps(payload).encode())
    for item in items:
        size += len(json.dumps(item).encode()) + (2 if payload['items'] else 0)
        if size > MAX_TC_PROJECTION_BYTES:
            payload['truncated'] = True
            break
        payload['items'].append(item)
    return payload, catalog


class TcProjectionItem(StrictModel):
    tc_id: str = Field(min_length=1, max_length=1024)
    path: str = Field(min_length=1, max_length=1024)
    name: str | None = Field(default=None, max_length=256)
    module: str | None = Field(default=None, max_length=160)
    kind: Literal['Single', 'Dual']
    effective_timeout_s: Annotated[StrictInt, Field(ge=1, le=86400)]
    source_timeout_s: Annotated[StrictInt, Field(ge=1, le=86400)] | None = None
    disabled_reason: str | None = Field(default=None, max_length=512)
    after: list[str] = Field(default_factory=list, max_length=64)


class TcCatalogProjectionRequest(StrictModel):
    tc_root: str = Field(min_length=1, max_length=1024)
    catalog_revision: str = Field(min_length=1, max_length=256)
    generated_at: float
    truncated: StrictBool = False
    total_count: Annotated[StrictInt, Field(ge=0, le=100000)]
    items: list[TcProjectionItem] = Field(default_factory=list, max_length=MAX_TC_PROJECTION_ITEMS)


class ControlSettingsRequest(StrictModel):
    expected_revision: str | None = Field(default=None, min_length=1, max_length=128)
    expected_runner_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    source: Literal['linux', 'windows'] = 'linux'
    base_linux_revision: str | None = Field(default=None, max_length=128)
    patch: dict[str, Any]


class SettingsAckSyncRequest(StrictModel):
    expected_runner_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    expected_windows_revision: str | None = Field(default=None, max_length=128)
    base_linux_revision: str = Field(min_length=1, max_length=128)
    resolved_by: str = Field(default='linux', max_length=64)


class ManagerHeartbeatRequest(StrictModel):
    manager_pid: Annotated[StrictInt, Field(ge=1)]
    local_port: Annotated[StrictInt, Field(ge=1, le=65535)] | None = None
    remote_runner_port: Annotated[StrictInt, Field(ge=1, le=65535)] | None = None
    ssh_snapshot: dict | None = None
    preflight: dict | None = None
    putty_active: StrictBool = False


class ManagerTaskResultRequest(StrictModel):
    state: Literal['COMPLETED', 'FAILED']
    result: dict | None = None
    error: str | None = Field(default=None, max_length=1024)


class VerifyConnectionRequest(StrictModel):
    wait: StrictBool = False
    timeout_seconds: Annotated[StrictInt, Field(ge=1, le=30)] = 6
    check_linux: StrictBool = True


class CommandSnapshotModel(StrictModel):
    name: str | None = Field(default=None, max_length=128)
    revision: str = Field(min_length=1, max_length=128)
    template: CommandTemplate


class InstallerSpecModel(StrictModel):
    installer_snapshot_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    flash_profile: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,80}$')
    flash_profile_revision: str = Field(pattern=r'^[a-f0-9]{64}$')


class ConnectorRunStepInput(StrictModel):
    step_index: Annotated[StrictInt, Field(ge=0, le=10000)]
    tc_id: str = Field(min_length=1, max_length=1024)
    path: str = Field(min_length=1, max_length=1024)
    kind: Literal['Single', 'Dual']
    effective_timeout_s: Annotated[StrictInt, Field(ge=1, le=86400)] | None = None
    metadata_timeout_s: Annotated[StrictInt, Field(ge=1, le=86400)] | None = None
    adb_serial: str | None = Field(default=None, max_length=160, exclude_if=lambda v: v is None)
    parser: dict = Field(default_factory=dict)
    after: list[str] = Field(default_factory=list, max_length=64)


class FailurePolicyModel(StrictModel):
    mode: Literal['fail-stop-analysis-v1'] = 'fail-stop-analysis-v1'
    max_retry_chain: Annotated[StrictInt, Field(ge=1, le=10)] = MAX_RETRY_CHAIN_DEFAULT
    stop_on_same_cause: StrictBool = True
    verifier_required: StrictBool = True


class OriginModel(StrictModel):
    project: str | None = Field(default=None, min_length=1, max_length=1024, exclude_if=lambda value: value is None)
    client: Literal['plugin', 'agent_monitor', 'connector'] = 'plugin'
    session_id: str = Field(default='default', min_length=1, max_length=128)


class ConnectorRunRequest(StrictModel):
    run_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    request_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    execution_mode: Literal['flash_and_test', 'tc_only']
    connection: Connection
    source_snapshot_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_revision: str = Field(min_length=1, max_length=256)
    command_snapshot: CommandSnapshotModel
    installer: InstallerSpecModel | None = None
    tests: list[ConnectorRunStepInput] = Field(min_length=1, max_length=2000)
    timeout_settings_snapshot: dict = Field(default_factory=dict)
    failure_policy: FailurePolicyModel = Field(default_factory=FailurePolicyModel)
    origin: OriginModel = Field(default_factory=OriginModel)
    parent_run_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    retry_chain: dict | None = None


class ConnectorRunReconcileRequest(StrictModel):
    action: Literal['MARK_ABORTED', 'MARK_FAILED_FOR_ANALYSIS']
    reason: str = Field(default='', max_length=512)


class AnalysisClaimRequest(StrictModel):
    lease_owner: str = Field(min_length=1, max_length=128)
    lease_ttl_s: Annotated[StrictInt, Field(ge=10, le=600)] = DEFAULT_ANALYSIS_LEASE_TTL_S


class AnalysisHeartbeatRequest(StrictModel):
    lease_token: str = Field(min_length=16, max_length=128)
    lease_ttl_s: Annotated[StrictInt, Field(ge=10, le=600)] = DEFAULT_ANALYSIS_LEASE_TTL_S


class ReprepareInputModel(StrictModel):
    source_snapshot_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    source_revision: str | None = Field(default=None, min_length=1, max_length=256)
    installer: InstallerSpecModel | None = None
    command_snapshot: CommandSnapshotModel | None = None
    timeout_settings_snapshot: dict | None = None


class AnalysisDecisionRequest(StrictModel):
    lease_token: str = Field(min_length=16, max_length=128)
    expected_evidence_revision: Annotated[StrictInt, Field(ge=1)]
    verdict: Literal['HOLD', 'RETRY', 'REPREPARE']
    cause_key: str = Field(min_length=1, max_length=256)
    summary: str = Field(min_length=1, max_length=2000)
    verifier_status: Literal['PASSED', 'FAILED', 'SKIPPED', 'ERROR']
    reprepare: ReprepareInputModel | None = None
    analyzer_evidence: dict | None = None


class AcknowledgeHoldRequest(StrictModel):
    operator: str = Field(default='operator', min_length=1, max_length=128)
    note: str = Field(default='', max_length=1000)


class ConnectorEngine:
    """Autonomous connector execution, fail-stop analysis latch, bridge, and diagnostics."""

    def __init__(self, host, config: dict | None = None, config_path: Path | None = None):
        self.host = host
        self.config = dict(config or {})
        self.config_path = Path(config_path) if config_path else None
        raw_home = (
            self.config.get('connector_home')
            or self.config.get('home')
            or os.environ.get('BSP_CONNECTOR_HOME')
            or str(self.host.runtime.parent)
        )
        self.home = Path(raw_home).resolve()
        self.bridge_dir = self.home / 'manager-bridge'
        self.bridge_tokens = BridgeTokenStore(self.bridge_dir, windows=(os.name == 'nt'))
        self.started_at = _utc_iso()
        self.started_epoch = now()
        self.local_port = self.config.get('_runtime_local_port')
        self.remote_runner_port = self.config.get('_runtime_remote_runner_port', 8771)

        self._bridge_lock = threading.RLock()
        self._manager_state: dict[str, Any] = {
            'attached': False,
            'last_heartbeat_at': None,
            'manager_pid': None,
            'local_port': None,
            'remote_runner_port': None,
            'ssh_snapshot': None,
            'preflight': None,
            'putty_active': False,
        }
        self._worker_wake = threading.Event()
        self._worker_stop = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._active_lock = threading.RLock()
        self._active_trees: dict[str, ProcessTree] = {}
        self._run_observers: dict[str, list[Any]] = {}
        self.init_schema()
        sharing.SharedHost(self.host.runtime).init_schema()

    def _connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.host.db, timeout=30.0)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA foreign_keys=ON')
        return c

    def init_schema(self) -> None:
        with self.host.lock, self._connect() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS connector_runs (
                  run_id TEXT PRIMARY KEY,
                  idempotency_key TEXT UNIQUE NOT NULL,
                  request_hash TEXT NOT NULL,
                  body_fingerprint TEXT,
                  parent_run_id TEXT,
                  child_run_id TEXT,
                  execution_mode TEXT NOT NULL CHECK(execution_mode IN ('flash_and_test','tc_only')),
                  state TEXT NOT NULL,
                  outcome TEXT,
                  pause_reason TEXT,
                  recovery_reason TEXT,
                  analysis_latched INTEGER NOT NULL DEFAULT 0,
                  pause_requested INTEGER NOT NULL DEFAULT 0,
                  cancel_requested INTEGER NOT NULL DEFAULT 0,
                  current_step_index INTEGER NOT NULL DEFAULT 0,
                  version INTEGER NOT NULL DEFAULT 1,
                  source_snapshot_id TEXT NOT NULL,
                  installer_snapshot_id TEXT,
                  flash_profile TEXT,
                  request_json TEXT NOT NULL,
                  retry_chain_json TEXT NOT NULL,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL,
                  ended_at REAL
                );

                CREATE TABLE IF NOT EXISTS connector_run_steps (
                  run_id TEXT NOT NULL,
                  step_index INTEGER NOT NULL,
                  tc_id TEXT NOT NULL,
                  path TEXT NOT NULL,
                  kind TEXT NOT NULL,
                  effective_timeout_s INTEGER NOT NULL,
                  state TEXT NOT NULL,
                  latest_attempt_id TEXT,
                  result_reason TEXT,
                  PRIMARY KEY (run_id, step_index)
                );

                CREATE TABLE IF NOT EXISTS connector_run_attempts (
                  attempt_id TEXT PRIMARY KEY,
                  run_id TEXT NOT NULL,
                  step_index INTEGER,
                  phase TEXT NOT NULL CHECK(phase IN ('FLASHING','TC')),
                  ordinal INTEGER NOT NULL,
                  state TEXT NOT NULL,
                  exit_code INTEGER,
                  terminated INTEGER NOT NULL DEFAULT 0,
                  reason TEXT,
                  console_evidence_json TEXT,
                  started_at REAL NOT NULL,
                  ended_at REAL
                );

                CREATE TABLE IF NOT EXISTS connector_failure_evidence (
                  attempt_id TEXT PRIMARY KEY REFERENCES connector_run_attempts(attempt_id),
                  run_id TEXT NOT NULL,
                  status TEXT NOT NULL,
                  data_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS connector_run_events (
                  seq INTEGER PRIMARY KEY AUTOINCREMENT,
                  run_id TEXT NOT NULL,
                  event_type TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS connector_analyses (
                  analysis_id TEXT PRIMARY KEY,
                  run_id TEXT NOT NULL,
                  attempt_id TEXT,
                  phase TEXT NOT NULL CHECK(phase IN ('FLASHING','TC','UNKNOWN')),
                  failed_step_index INTEGER,
                  evidence_revision INTEGER NOT NULL,
                  status TEXT NOT NULL CHECK(status IN ('PENDING','ANALYZING','HOLD','RETRY_READY','CHILD_CREATED','STOPPED','SUPERSEDED_BY_CANCEL')),
                  lease_token TEXT,
                  lease_owner TEXT,
                  lease_expires_at REAL,
                  decision_json TEXT,
                  cause_key TEXT,
                  verifier_status TEXT,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tc_catalog_projection (
                  id INTEGER PRIMARY KEY CHECK(id = 1),
                  data_json TEXT NOT NULL,
                  updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS manager_tasks (
                  task_id TEXT PRIMARY KEY,
                  action TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  state TEXT NOT NULL CHECK(state IN ('QUEUED','RUNNING','COMPLETED','FAILED')),
                  result_json TEXT,
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS peer_observations (
                  peer_instance_id TEXT PRIMARY KEY,
                  peer_type TEXT NOT NULL,
                  client_status TEXT NOT NULL,
                  data_json TEXT NOT NULL,
                  last_seen_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings_sync_state (
                  id INTEGER PRIMARY KEY CHECK(id = 1),
                  data_json TEXT NOT NULL,
                  updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_connector_runs_state_updated
                  ON connector_runs(state, updated_at);
                CREATE INDEX IF NOT EXISTS idx_connector_runs_created
                  ON connector_runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_connector_attempts_run_ordinal
                  ON connector_run_attempts(run_id, ordinal);
                CREATE INDEX IF NOT EXISTS idx_connector_events_run_seq
                  ON connector_run_events(run_id, seq);
                CREATE INDEX IF NOT EXISTS idx_connector_analyses_status_lease
                  ON connector_analyses(status, lease_expires_at);
                CREATE INDEX IF NOT EXISTS idx_manager_tasks_state_created
                  ON manager_tasks(state, created_at);
                """
            )
            c.execute('BEGIN IMMEDIATE')
            columns = {row['name'] for row in c.execute('PRAGMA table_info(connector_runs)')}
            if 'evidence_serials_json' not in columns:
                c.execute('ALTER TABLE connector_runs ADD COLUMN evidence_serials_json TEXT')
            if 'body_fingerprint' not in columns:
                c.execute('ALTER TABLE connector_runs ADD COLUMN body_fingerprint TEXT')
            c.execute(
                "INSERT INTO runner_meta VALUES('connector_schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (CONNECTOR_SCHEMA_VERSION,),
            )
            c.execute(
                "INSERT OR IGNORE INTO runner_meta VALUES('connector_started_at', ?)",
                (self.started_at,),
            )
            c.commit()

    # ------------------------------------------------------------------
    # Lifecycle & Worker
    # ------------------------------------------------------------------
    def start_worker(self) -> None:
        with self._bridge_lock:
            if self._worker_thread and self._worker_thread.is_alive():
                return
            self._worker_stop.clear()
            self._worker_thread = threading.Thread(
                target=self._worker_loop,
                name='connector-run-worker',
                daemon=False,
            )
            self._worker_thread.start()

    def recover(self) -> None:
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows = c.execute(
                'SELECT run_id, state, version FROM connector_runs WHERE state IN (?,?,?,?,?)',
                IN_FLIGHT_RECOVERY_STATES,
            ).fetchall()
            ts = now()
            for row in rows:
                run_id = row['run_id']
                new_ver = row['version'] + 1
                c.execute(
                    "UPDATE connector_runs SET state='UNKNOWN', recovery_reason='HOST_RESTARTED_DURING_EXECUTION', "
                    'version=?, updated_at=? WHERE run_id=?',
                    (new_ver, ts, run_id),
                )
                c.execute(
                    "UPDATE connector_run_attempts SET state='UNKNOWN', reason='HOST_RESTARTED_DURING_EXECUTION', ended_at=COALESCE(ended_at, ?) "
                    "WHERE run_id=? AND state='RUNNING'",
                    (ts, run_id),
                )
                c.execute(
                    "UPDATE connector_run_steps SET state='UNKNOWN', result_reason='HOST_RESTARTED_DURING_EXECUTION' "
                    "WHERE run_id=? AND state='RUNNING'",
                    (run_id,),
                )
                self._append_event(
                    c,
                    run_id,
                    'RUN_RECOVERED_UNKNOWN',
                    {'previous_state': row['state'], 'recovery_reason': 'HOST_RESTARTED_DURING_EXECUTION'},
                )
            # Keep the original snapshot. Reading dmesg after restarting would capture a different time.
            c.execute("UPDATE connector_failure_evidence SET status='INTERRUPTED' WHERE status='PENDING'")
            # Expire stale analysis leases on startup.
            c.execute(
                "UPDATE connector_analyses SET status='PENDING', lease_token=NULL, lease_owner=NULL, lease_expires_at=NULL, updated_at=? "
                "WHERE status='ANALYZING'",
                (ts,),
            )
            c.commit()
        self.start_worker()
        self._worker_wake.set()

    def close(self) -> None:
        self._worker_stop.set()
        self._worker_wake.set()
        with self._active_lock:
            # Never force-kill FLASHING processes on close; only cancel non-flashing TC trees if stopping.
            for run_id, tree in list(self._active_trees.items()):
                try:
                    tree.stop()
                except Exception:
                    pass
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10.0)
        for run_id in list(self._run_observers):
            self._close_run_observers(run_id)

    def has_blocking_run(self, c: sqlite3.Connection | None = None) -> bool:
        def _query(conn: sqlite3.Connection) -> bool:
            row = conn.execute(
                f'SELECT 1 FROM connector_runs WHERE state IN ({ACTIVE_RUN_STATES_SQL}) OR analysis_latched=1 LIMIT 1',
                (*ACTIVE_RUN_STATES,),
            ).fetchone()
            return row is not None

        if c is not None:
            return _query(c)
        with self.host.lock, self._connect() as conn:
            return _query(conn)

    def has_active_execution_for_restart(self) -> bool:
        with self.host.lock, self._connect() as c:
            row = c.execute(
                "SELECT 1 FROM connector_runs WHERE state IN ('QUEUED','FLASHING','RUNNING','PAUSE_REQUESTED','CANCEL_REQUESTED','FINALIZING') LIMIT 1"
            ).fetchone()
            return row is not None

    def active_run_summary(self, c: sqlite3.Connection | None = None) -> dict | None:
        def _query(conn: sqlite3.Connection) -> dict | None:
            row = conn.execute(
                'SELECT run_id, execution_mode, state, outcome, pause_reason, recovery_reason, analysis_latched, '
                'current_step_index, version, created_at, updated_at FROM connector_runs '
                f"WHERE state!='DELETED' AND (state IN ({ACTIVE_RUN_STATES_SQL}) OR analysis_latched=1) "
                'ORDER BY updated_at DESC LIMIT 1',
                (*ACTIVE_RUN_STATES,),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT run_id, execution_mode, state, outcome, pause_reason, recovery_reason, analysis_latched, "
                    'current_step_index, version, created_at, updated_at FROM connector_runs '
                    "WHERE state!='DELETED' ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if not row:
                    return None
                if row['state'] in TERMINAL_OUTCOMES or row['state'] in {'COMPLETED', 'PAUSED'}:
                    # Include latest run only as summary; mark active boolean cleanly.
                    pass
            steps_count = conn.execute(
                'SELECT COUNT(*) FROM connector_run_steps WHERE run_id=?', (row['run_id'],)
            ).fetchone()[0]
            passed_count = conn.execute(
                "SELECT COUNT(*) FROM connector_run_steps WHERE run_id=? AND state='PASSED'", (row['run_id'],)
            ).fetchone()[0]
            return {
                'run_id': row['run_id'],
                'execution_mode': row['execution_mode'],
                'state': row['state'],
                'outcome': row['outcome'],
                'pause_reason': row['pause_reason'],
                'recovery_reason': row['recovery_reason'],
                'analysis_latched': bool(row['analysis_latched']),
                'current_step_index': row['current_step_index'],
                'total_steps': steps_count,
                'passed_steps': passed_count,
                'version': row['version'],
                'active': row['state'] in ACTIVE_RUN_STATES or bool(row['analysis_latched']),
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
            }

        if c is not None:
            return _query(c)
        with self.host.lock, self._connect() as conn:
            return _query(conn)

    def pending_analyses_count(self, c: sqlite3.Connection | None = None) -> int:
        def _query(conn: sqlite3.Connection) -> int:
            self._expire_stale_analysis_leases(conn)
            return int(
                conn.execute("SELECT COUNT(*) FROM connector_analyses WHERE status IN ('PENDING','ANALYZING','HOLD')").fetchone()[0]
            )

        if c is not None:
            return _query(c)
        with self.host.lock, self._connect() as conn:
            return _query(conn)

    # ------------------------------------------------------------------
    # DPAPI Manager Bridge & Control Tasks
    # ------------------------------------------------------------------
    def verify_manager_token(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            expected = self.bridge_tokens.load(readonly=True)
        except (ValueError, OSError):
            return False
        if not expected:
            return False
        return hmac.compare_digest(token.strip(), expected)

    def is_manager_attached(self) -> bool:
        with self._bridge_lock:
            last = self._manager_state.get('last_heartbeat_at')
            return bool(self._manager_state.get('attached') and last and (now() - last) <= MANAGER_HEARTBEAT_TTL_S)

    def manager_heartbeat(self, payload: dict) -> dict:
        req = ManagerHeartbeatRequest.model_validate(payload)
        with self._bridge_lock:
            if req.local_port is not None:
                self.local_port = req.local_port
            if req.remote_runner_port is not None:
                self.remote_runner_port = req.remote_runner_port
            self._manager_state.update(
                attached=True,
                last_heartbeat_at=now(),
                manager_pid=req.manager_pid,
                local_port=req.local_port or self.local_port,
                remote_runner_port=req.remote_runner_port or self.remote_runner_port,
                ssh_snapshot=req.ssh_snapshot,
                preflight=req.preflight,
                putty_active=req.putty_active,
            )
            return {
                'runner_id': self.host.identity,
                'manager_attached': True,
                'active_run_blocks_restart': self.has_active_execution_for_restart(),
            }

    def enqueue_manager_task(self, action: str, payload: dict | None = None, *, require_attached: bool = True) -> dict:
        if require_attached and not self.is_manager_attached():
            raise make_error(
                'Board Connector Manager is not attached to this headless Host',
                'MANAGER_NOT_ATTACHED',
                501,
            )
        task_id = uid()
        ts = now()
        body = dict(payload or {})
        with self.host.lock, self._connect() as c:
            c.execute(
                'INSERT INTO manager_tasks(task_id, action, payload_json, state, result_json, created_at, updated_at) '
                'VALUES(?,?,?,?,?,?,?)',
                (task_id, action, json.dumps(body), 'QUEUED', None, ts, ts),
            )
            c.commit()
        return {'task_id': task_id, 'action': action, 'state': 'QUEUED', 'created_at': ts}

    def claim_manager_tasks(self) -> list[dict]:
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows = c.execute(
                "SELECT task_id, action, payload_json, created_at FROM manager_tasks WHERE state='QUEUED' ORDER BY created_at ASC LIMIT 16"
            ).fetchall()
            ts = now()
            tasks = []
            for row in rows:
                c.execute(
                    "UPDATE manager_tasks SET state='RUNNING', updated_at=? WHERE task_id=?",
                    (ts, row['task_id']),
                )
                tasks.append(
                    {
                        'task_id': row['task_id'],
                        'action': row['action'],
                        'payload': json.loads(row['payload_json']),
                        'created_at': row['created_at'],
                    }
                )
            c.commit()
            return tasks

    def complete_manager_task(self, task_id: str, payload: dict) -> dict:
        req = ManagerTaskResultRequest.model_validate(payload)
        ts = now()
        with self.host.lock, self._connect() as c:
            row = c.execute('SELECT * FROM manager_tasks WHERE task_id=?', (task_id,)).fetchone()
            if not row:
                raise make_error('Manager task not found', 'NOT_FOUND', 404)
            result_data = req.result if req.result is not None else {}
            if req.error:
                result_data = dict(result_data, error=req.error)
            c.execute(
                'UPDATE manager_tasks SET state=?, result_json=?, updated_at=? WHERE task_id=?',
                (req.state, json.dumps(result_data), ts, task_id),
            )
            c.commit()
            return {
                'task_id': task_id,
                'action': row['action'],
                'state': req.state,
                'result': result_data,
                'updated_at': ts,
            }

    def get_control_task(self, task_id: str) -> dict:
        with self.host.lock, self._connect() as c:
            row = c.execute('SELECT * FROM manager_tasks WHERE task_id=?', (task_id,)).fetchone()
            if not row:
                raise make_error('Control task not found', 'NOT_FOUND', 404)
            return {
                'task_id': row['task_id'],
                'action': row['action'],
                'state': row['state'],
                'payload': json.loads(row['payload_json']),
                'result': json.loads(row['result_json']) if row['result_json'] else None,
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
            }

    def request_putty(self, board_id: str | None = None) -> dict:
        if not self.is_manager_attached():
            raise make_error('Manager is not attached', 'MANAGER_NOT_ATTACHED', 501)
        if not self.host.safe_to_stop():
            raise make_error('활성 작업 또는 예약이 있어 PuTTY를 실행할 수 없습니다.', 'CONNECTOR_BUSY', 409)
        return self.enqueue_manager_task('OPEN_PUTTY', {'board_id': board_id} if board_id else {})

    def request_restart(self) -> dict:
        if not self.is_manager_attached():
            raise make_error('Manager is not attached', 'MANAGER_NOT_ATTACHED', 501)
        inv = self.host.inventory()
        manual_busy = any(b.get('serial_proxy', {}).get('owner') == 'manual' for b in inv.get('boards', []))
        if self.has_active_execution_for_restart() or not self.host.safe_to_stop() or manual_busy:
            raise make_error(
                '실행 중이거나 미정리 작업 또는 PuTTY 제어가 있어 Host를 재시작할 수 없습니다.',
                'ACTIVE_RUN_BLOCKS_RESTART',
                409,
            )
        return self.enqueue_manager_task('RESTART_HOST', {})

    def request_reconnect_ssh(self) -> dict:
        if not self.is_manager_attached():
            raise make_error('Manager is not attached', 'MANAGER_NOT_ATTACHED', 501)
        return self.enqueue_manager_task('RECONNECT_SSH', {})

    def verify_connection(self, payload: dict | None = None) -> dict:
        req = VerifyConnectionRequest.model_validate(payload or {})
        if not self.is_manager_attached():
            snap = self.diagnostics_snapshot()
            snap['ssh_diagnostic'] = {
                'code': 'MANAGER_NOT_ATTACHED',
                'severity': 'WARNING',
                'summary': 'Headless Host 단독 실행 중입니다 (Manager 미부착).',
                'detail': 'Host는 127.0.0.1에서 동작 중이지만 SSH -R 터널 상태를 관리하는 Manager가 연결되어 있지 않습니다.',
                'recent_redacted_lines': [],
                'preflight': None,
            }
            return snap
        task = self.enqueue_manager_task('VERIFY_CONNECTION', {'check_linux': req.check_linux})
        if not req.wait:
            return {'task': task, 'diagnostics': self.diagnostics_snapshot()}
        deadline = time.monotonic() + req.timeout_seconds
        while time.monotonic() < deadline:
            cur = self.get_control_task(task['task_id'])
            if cur['state'] in {'COMPLETED', 'FAILED'}:
                snap = self.diagnostics_snapshot()
                return {'task': cur, 'diagnostics': snap, 'verify_result': cur.get('result')}
            time.sleep(0.1)
        return {'task': self.get_control_task(task['task_id']), 'diagnostics': self.diagnostics_snapshot(), 'timed_out': True}

    # ------------------------------------------------------------------
    # Mutual Diagnostics & Peer Observations
    # ------------------------------------------------------------------
    def record_peer_hello(self, payload: dict) -> dict:
        req = PeerHelloRequest.model_validate(payload)
        ts = now()
        data = req.model_dump()
        data['observed_at'] = ts
        with self.host.lock, self._connect() as c:
            c.execute(
                'INSERT INTO peer_observations(peer_instance_id, peer_type, client_status, data_json, last_seen_at) '
                'VALUES(?,?,?,?,?) '
                'ON CONFLICT(peer_instance_id) DO UPDATE SET '
                'peer_type=excluded.peer_type, client_status=excluded.client_status, '
                'data_json=excluded.data_json, last_seen_at=excluded.last_seen_at',
                (req.peer_instance_id, req.peer_type, req.client_status, json.dumps(data), ts),
            )
            c.execute(
                'DELETE FROM peer_observations WHERE peer_instance_id NOT IN '
                '(SELECT peer_instance_id FROM peer_observations ORDER BY last_seen_at DESC LIMIT ?)',
                (MAX_PEER_OBSERVATIONS,),
            )
            diag = self.diagnostics_snapshot(c=c)
            sync_state = self._read_settings_sync_state(c)
            proj_row = c.execute('SELECT updated_at FROM tc_catalog_projection WHERE id=1 AND data_json != ?', ('null',)).fetchone()
            c.commit()
        stale = (proj_row is None) or ((ts - proj_row['updated_at']) > TC_PROJECTION_STALE_SECONDS)
        return {
            'runner_id': self.host.identity,
            'overall_connection_state': diag['overall_connection_state'],
            'active_run_summary': diag['active_run'],
            'pending_analyses_count': diag['pending_analyses'],
            'settings_sync_needed': bool(sync_state.get('dirty_on_windows')),
            'tc_projection_stale': stale,
        }

    def readiness_snapshot(self) -> dict:
        ports = self.host.ports()
        configured = self.host.configured_boards
        detected_boards = [b for b in configured if b['com'] in ports]
        missing_boards = [b['board_id'] for b in configured if b['com'] not in ports]
        com_ok = bool(configured) and len(missing_boards) == 0
        python_ok = self.host.python is not None
        flash_setup = self.host.flash_setup(False)
        fastboot_path = flash_setup.get('fastboot', {}).get('path')
        enabled_profiles = [name for name, info in self.host.flash_profile_revisions.items() if info.get('enabled')]
        flash_ok = bool(fastboot_path and enabled_profiles)
        source_ok = self.host.root is not None
        return {
            'transport_ready': True,
            'execution_ready': bool(com_ok and python_ok),
            'com_port': {
                'ready': com_ok,
                'configured': len(configured),
                'detected': len(detected_boards),
                'missing_boards': missing_boards,
            },
            'tc_python': {
                'ready': python_ok,
                'configured': python_ok,
            },
            'flash_tools': {
                'ready': flash_ok,
                'fastboot_configured': bool(fastboot_path),
                'enabled_profiles': enabled_profiles,
            },
            'source': {
                'ready': source_ok,
                'mode': 'snapshot_or_root' if not source_ok else 'local_root_and_snapshot',
            },
        }

    def diagnostics_snapshot(self, c: sqlite3.Connection | None = None) -> dict:
        with self._bridge_lock:
            mgr = dict(self._manager_state)
        attached = self.is_manager_attached()
        ssh_snap = mgr.get('ssh_snapshot') if isinstance(mgr.get('ssh_snapshot'), dict) else {}
        local_state = 'READY'
        if attached:
            ssh_state = ssh_snap.get('ssh_state') or 'STARTING'
            overall = 'CONNECTED' if (local_state == 'READY' and ssh_state == 'CONNECTED') else ssh_state
            tunnel = ssh_snap.get('tunnel') or {
                'server': self.config.get('_setup', {}).get('server'),
                'ssh_port': self.config.get('_setup', {}).get('ssh_port', 22),
                'remote_runner_port': self.remote_runner_port,
                'actual_local_runner_port': self.local_port,
                'remote_dashboard_port': self.config.get('_setup', {}).get('remote_dashboard_port'),
                'optional_dashboard_forward': ssh_snap.get('optional_dashboard_forward'),
                'connected_since': ssh_snap.get('connected_since'),
                'reconnect_attempts': ssh_snap.get('reconnect_attempts', 0),
            }
            ssh_diag = ssh_snap.get('ssh_diagnostic') or {
                'code': 'SSH_CONNECTED' if ssh_state == 'CONNECTED' else 'SSH_PENDING',
                'severity': 'INFO' if ssh_state == 'CONNECTED' else 'WARNING',
                'summary': 'SSH -R 역방향 터널이 정상 연결되어 있습니다.' if ssh_state == 'CONNECTED' else 'SSH -R 연결 확인 중입니다.',
                'detail': '',
                'recent_redacted_lines': [],
                'preflight': mgr.get('preflight'),
            }
        else:
            ssh_state = 'MANAGER_NOT_ATTACHED'
            overall = 'HEADLESS_LOCAL'
            tunnel = {
                'server': self.config.get('_setup', {}).get('server'),
                'ssh_port': self.config.get('_setup', {}).get('ssh_port', 22),
                'remote_runner_port': self.remote_runner_port,
                'actual_local_runner_port': self.local_port,
                'remote_dashboard_port': None,
                'optional_dashboard_forward': None,
                'connected_since': None,
                'reconnect_attempts': 0,
            }
            ssh_diag = {
                'code': 'MANAGER_NOT_ATTACHED',
                'severity': 'WARNING',
                'summary': 'Headless Host 단독 실행 중입니다.',
                'detail': 'Manager 브리지 하트비트가 없어 SSH -R 상태를 관리하지 않습니다.',
                'recent_redacted_lines': [],
                'preflight': None,
            }

        def _query(conn: sqlite3.Connection) -> dict:
            rows = conn.execute(
                'SELECT peer_instance_id, peer_type, client_status, data_json, last_seen_at '
                'FROM peer_observations ORDER BY last_seen_at DESC LIMIT ?',
                (MAX_PEER_OBSERVATIONS,),
            ).fetchall()
            ts = now()
            peers: dict[str, Any] = {'plugin': None, 'agent_monitor': None, 'recent': []}
            warnings: list[dict] = []
            for row in rows:
                item = json.loads(row['data_json'])
                item['stale'] = (ts - row['last_seen_at']) > TC_PROJECTION_STALE_SECONDS
                peers['recent'].append(item)
                ptype = row['peer_type']
                if peers.get(ptype) is None:
                    peers[ptype] = item
                if row['client_status'] != 'OK' and not item['stale']:
                    warnings.append({
                        'peer_instance_id': row['peer_instance_id'],
                        'peer_type': ptype,
                        'client_status': row['client_status'],
                        'client_issue': item.get('client_issue'),
                        'last_seen_at': row['last_seen_at'],
                    })
            if peers['agent_monitor'] is None:
                peers['agent_monitor'] = {'client_status': 'OPTIONAL_OFFLINE', 'stale': True}
            active_run = self.active_run_summary(c=conn)
            pending = self.pending_analyses_count(c=conn)
            sync_state = self._read_settings_sync_state(conn)
            return {
                'runner_id': self.host.identity,
                'overall_connection_state': overall,
                'local_state': local_state,
                'ssh_state': ssh_state,
                'manager_attached': attached,
                'tunnel': tunnel,
                'ssh_diagnostic': ssh_diag,
                'readiness': self.readiness_snapshot(),
                'peers': peers,
                'peer_warnings': warnings,
                'active_run': active_run,
                'pending_analyses': pending,
                'settings_sync_state': sync_state,
                'checked_at': ts,
            }

        if c is not None:
            return _query(c)
        with self.host.lock, self._connect() as conn:
            return _query(conn)

    # ------------------------------------------------------------------
    # TC Catalog Projection & Test Status
    # ------------------------------------------------------------------
    def update_tc_projection(self, payload: dict | None, raw_size: int | None = None, *, observed=None,
                             conditional=False) -> dict:
        if raw_size is not None and raw_size > MAX_TC_PROJECTION_BYTES:
            raise make_error('TC catalog projection exceeds 512 KiB limit', 'PROJECTION_TOO_LARGE', 413)
        req = None if conditional and payload is None else TcCatalogProjectionRequest.model_validate(payload)
        encoded = json.dumps(req.model_dump() if req else None)
        if len(encoded.encode('utf-8')) > MAX_TC_PROJECTION_BYTES:
            raise make_error('TC catalog projection exceeds 512 KiB limit', 'PROJECTION_TOO_LARGE', 413)
        ts = now()
        with self.host.lock, self._connect() as c:
            if conditional:
                row = c.execute('SELECT updated_at FROM tc_catalog_projection WHERE id=1').fetchone()
                if (row[0] if row else None) != observed:
                    raise make_error('TC 목록이 이미 변경되었습니다.', 'CATALOG_CHANGED')
            c.execute(
                'INSERT INTO tc_catalog_projection(id, data_json, updated_at) VALUES(1, ?, ?) '
                'ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, updated_at=excluded.updated_at',
                (encoded, ts),
            )
            c.commit()
        return {'accepted': True, 'count': len(req.items) if req else 0,
                'catalog_revision': req.catalog_revision if req else None, 'updated_at': ts}

    def test_status(self) -> dict:
        ts = now()
        with self.host.lock, self._connect() as c:
            proj_row = c.execute('SELECT data_json, updated_at FROM tc_catalog_projection WHERE id=1').fetchone()
            proj = json.loads(proj_row['data_json']) if proj_row else None
            updated_at = proj_row['updated_at'] if proj_row else None
            recent_linux = c.execute(
                'SELECT 1 FROM peer_observations WHERE last_seen_at >= ? LIMIT 1',
                (ts - TC_PROJECTION_STALE_SECONDS,),
            ).fetchone()
            stale = (proj is None) or (updated_at is not None and (ts - updated_at) > TC_PROJECTION_STALE_SECONDS and recent_linux is None)
            active = self.active_run_summary(c=c)
            steps_by_tc: dict[str, dict] = {}
            steps_list: list[dict] = []
            if active:
                for s in c.execute(
                    'SELECT * FROM connector_run_steps WHERE run_id=? ORDER BY step_index ASC',
                    (active['run_id'],),
                ).fetchall():
                    item = dict(s)
                    steps_list.append(item)
                    steps_by_tc[s['tc_id']] = item
            items = []
            if proj:
                for entry in proj.get('items', []):
                    merged = dict(entry)
                    st = steps_by_tc.get(entry['tc_id'])
                    if st:
                        merged['run_step'] = st
                    items.append(merged)
            return {
                'runner_id': self.host.identity,
                'has_projection': proj is not None,
                'projection_stale': stale,
                'updated_at': updated_at,
                'tc_root': proj.get('tc_root') if proj else None,
                'catalog_revision': proj.get('catalog_revision') if proj else None,
                'truncated': proj.get('truncated', False) if proj else False,
                'total_count': proj.get('total_count', 0) if proj else 0,
                'items': items,
                'active_run': active,
                'steps': steps_list,
            }

    # ------------------------------------------------------------------
    # Settings Control & Offline Two-Way Sync
    # ------------------------------------------------------------------
    def _read_timeouts_doc(self, c: sqlite3.Connection) -> dict:
        row = c.execute("SELECT value FROM runner_meta WHERE key='connector_timeouts'").fetchone()
        if row:
            return json.loads(row[0])
        return {'default_seconds': CONNECTOR_DEFAULT_TC_TIMEOUT_SECONDS, 'overrides': {}}

    def _read_settings_sync_state(self, c: sqlite3.Connection) -> dict:
        row = c.execute('SELECT data_json FROM settings_sync_state WHERE id=1').fetchone()
        if row:
            return json.loads(row[0])
        return {
            'dirty_on_windows': False,
            'runner_id': self.host.identity,
            'base_linux_revision': None,
            'windows_revision': None,
            'patch': None,
            'updated_at': None,
        }

    def get_settings(self, c: sqlite3.Connection | None = None) -> dict:
        def _build(conn: sqlite3.Connection) -> dict:
            storage = retention.read_policy(self.host, conn)
            timeouts = self._read_timeouts_doc(conn)
            sync_state = self._read_settings_sync_state(conn)
            editable_config = {
                'server': self.config.get('_setup', {}).get('server'),
                'account': self.config.get('_setup', {}).get('account'),
                'ssh_port': self.config.get('_setup', {}).get('ssh_port', 22),
                'remote_runner_port': self.config.get('_setup', {}).get('remote_runner_port', 8771),
                'remote_dashboard_port': self.config.get('_setup', {}).get('remote_dashboard_port'),
                'python': self.config.get('python'),
                'putty_path': self.config.get('putty_path'),
                'serial_transport': self.config.get('serial_transport', 'native'),
                'serial_settings': self.config.get('serial_settings', {}),
                'boards': self.config.get('boards', []),
                'board_names': self.config.get('board_names', {}),
                'connector_inactive_boards': self.config.get('connector_inactive_boards', []),
                'timeouts': timeouts,
                'storage_policy': {k: storage[k] for k in StoragePolicy.model_fields},
            }
            revision = digest(editable_config)
            return {
                'runner_id': self.host.identity,
                'revision': revision,
                'settings': editable_config,
                'sync_state': sync_state,
            }

        if c is not None:
            return _build(c)
        with self.host.lock, self._connect() as conn:
            return _build(conn)

    def update_settings(self, payload: dict) -> dict:
        req = ControlSettingsRequest.model_validate(payload)
        if req.expected_runner_id and req.expected_runner_id != self.host.identity:
            raise make_error('Connector identity changed', 'RUNNER_CHANGED', 409)
        patch = dict(req.patch)
        allowed_keys = {
            'server', 'account', 'ssh_port', 'remote_runner_port', 'remote_dashboard_port',
            'python', 'putty_path', 'serial_transport', 'serial_settings', 'boards',
            'board_names', 'connector_inactive_boards', 'timeouts', 'storage_policy',
        }
        unknown = set(patch) - allowed_keys
        if unknown:
            raise make_error(f'Unsupported control settings keys: {sorted(unknown)}', 'INVALID_SETTINGS', 422)

        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            current = self.get_settings(c=c)
            if req.expected_revision is not None and current['revision'] != req.expected_revision:
                raise make_error(
                    'Settings changed; reload before saving',
                    'SETTINGS_REVISION_CONFLICT',
                    409,
                    current_revision=current['revision'],
                    current=current,
                )
            hardware_keys = {'server', 'account', 'ssh_port', 'remote_runner_port', 'remote_dashboard_port',
                             'python', 'serial_transport', 'serial_settings', 'boards'}
            if (set(patch) & hardware_keys) and self.has_blocking_run(c=c):
                raise make_error('활성 실행 또는 미정리 작업 중에는 하드웨어/SSH 설정을 변경할 수 없습니다.', 'CONNECTOR_BUSY', 409)

            timeouts_doc = self._read_timeouts_doc(c)
            if 'timeouts' in patch:
                t_val = patch['timeouts']
                if not isinstance(t_val, dict):
                    raise make_error('Invalid timeouts payload', 'INVALID_SETTINGS', 422)
                def_s = t_val.get('default_seconds', CONNECTOR_DEFAULT_TC_TIMEOUT_SECONDS)
                if type(def_s) is not int or not 1 <= def_s <= 86400:
                    raise make_error('Invalid default_seconds timeout', 'INVALID_SETTINGS', 422)
                overrides = t_val.get('overrides', {})
                if not isinstance(overrides, dict) or any(
                    not isinstance(k, str) or type(v) is not int or not 1 <= v <= 86400
                    for k, v in overrides.items()
                ):
                    raise make_error('Invalid timeout overrides', 'INVALID_SETTINGS', 422)
                timeouts_doc = {'default_seconds': def_s, 'overrides': dict(overrides)}
                c.execute(
                    "INSERT INTO runner_meta VALUES('connector_timeouts', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps(timeouts_doc),),
                )

            if 'storage_policy' in patch:
                sp = StoragePolicy.model_validate(patch['storage_policy']).model_dump()
                c.execute(
                    "INSERT INTO runner_meta VALUES('storage-policy', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (json.dumps(sp),),
                )
                c.execute(
                    "INSERT INTO runner_meta VALUES('storage-policy-origin', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    ('plugin' if req.source == 'linux' else 'connector',),
                )

            # Validate all connector-local fields BEFORE mutating self.config or self.host.
            new_config = json.loads(json.dumps(self.config))
            setup = dict(new_config.get('_setup', {}))
            for k in ('server', 'account', 'ssh_port', 'remote_runner_port', 'remote_dashboard_port'):
                if k in patch:
                    if k == 'ssh_port' and patch[k] is not None and (type(patch[k]) is not int or not 1 <= patch[k] <= 65535):
                        raise make_error('Invalid ssh_port', 'INVALID_SETTINGS', 422)
                    if k in {'remote_runner_port', 'remote_dashboard_port'} and patch[k] is not None and (type(patch[k]) is not int or not 1 <= patch[k] <= 65535):
                        raise make_error(f'Invalid {k}', 'INVALID_SETTINGS', 422)
                    setup[k] = patch[k]
            if setup:
                new_config['_setup'] = setup
            for k in ('python', 'putty_path', 'serial_transport', 'serial_settings', 'boards', 'board_names', 'connector_inactive_boards'):
                if k in patch:
                    new_config[k] = patch[k]
            validated_boards = None
            if 'boards' in patch:
                if not isinstance(patch['boards'], list):
                    raise make_error('Invalid boards list', 'INVALID_SETTINGS', 422)
                validated_boards = [Connection.model_validate({'a': b}).a.model_dump() for b in patch['boards']]
                new_config['boards'] = validated_boards
            if 'board_names' in patch and not isinstance(patch['board_names'], dict):
                raise make_error('Invalid board_names mapping', 'INVALID_SETTINGS', 422)

            if self.config_path is not None and self.config_path.parent.is_dir():
                tmp_cfg = self.config_path.with_suffix('.tmp')
                tmp_cfg.write_text(json.dumps(new_config, indent=2, ensure_ascii=False), encoding='utf-8')
                os.replace(tmp_cfg, self.config_path)

            self.config = new_config
            if 'remote_runner_port' in setup and setup['remote_runner_port'] is not None:
                self.remote_runner_port = int(setup['remote_runner_port'])
            if 'board_names' in patch:
                self.host.board_names = dict(patch['board_names'])
            if validated_boards is not None:
                self.host.configured_boards = validated_boards
            if 'python' in patch:
                self.host.python = patch['python']

            sync_prev = self._read_settings_sync_state(c)
            updated = self.get_settings(c=c)
            ts = now()
            if req.source == 'linux':
                new_sync = {
                    'dirty_on_windows': False,
                    'runner_id': self.host.identity,
                    'base_linux_revision': req.base_linux_revision or sync_prev.get('base_linux_revision'),
                    'windows_revision': updated['revision'],
                    'patch': None,
                    'updated_at': ts,
                }
            else:
                synced_subset = {k: patch[k] for k in ('timeouts', 'storage_policy') if k in patch}
                prev_patch = sync_prev.get('patch') if isinstance(sync_prev.get('patch'), dict) else {}
                merged_patch = dict(prev_patch)
                merged_patch.update(synced_subset)
                dirty = bool(merged_patch)
                new_sync = {
                    'dirty_on_windows': dirty,
                    'runner_id': self.host.identity,
                    'base_linux_revision': sync_prev.get('base_linux_revision'),
                    'windows_revision': updated['revision'],
                    'patch': merged_patch if dirty else None,
                    'updated_at': ts,
                }

            c.execute(
                'INSERT INTO settings_sync_state(id, data_json, updated_at) VALUES(1, ?, ?) '
                'ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, updated_at=excluded.updated_at',
                (json.dumps(new_sync), ts),
            )
            c.commit()

        if self.is_manager_attached():
            task = self.enqueue_manager_task('APPLY_SETTINGS', {'patch': patch, 'revision': updated['revision']})
            manager_reload: Any = {'queued': True, 'task_id': task['task_id']}
        else:
            manager_reload = 'skipped_headless'

        updated['sync_state'] = new_sync
        updated['manager_reload'] = manager_reload
        return updated

    def ack_settings_sync(self, payload: dict) -> dict:
        req = SettingsAckSyncRequest.model_validate(payload)
        if req.expected_runner_id and req.expected_runner_id != self.host.identity:
            raise make_error('Connector identity changed', 'RUNNER_CHANGED', 409)
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            cur_sync = self._read_settings_sync_state(c)
            if req.expected_windows_revision and cur_sync.get('windows_revision') != req.expected_windows_revision:
                raise make_error(
                    'Windows settings changed concurrently during sync acknowledgement',
                    'SETTINGS_SYNC_CONFLICT',
                    409,
                    sync_state=cur_sync,
                )
            ts = now()
            new_sync = {
                'dirty_on_windows': False,
                'runner_id': self.host.identity,
                'base_linux_revision': req.base_linux_revision,
                'windows_revision': cur_sync.get('windows_revision'),
                'patch': None,
                'resolved_by': req.resolved_by,
                'updated_at': ts,
            }
            c.execute(
                'INSERT INTO settings_sync_state(id, data_json, updated_at) VALUES(1, ?, ?) '
                'ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, updated_at=excluded.updated_at',
                (json.dumps(new_sync), ts),
            )
            c.commit()
        return {'acknowledged': True, 'sync_state': new_sync}

    # ------------------------------------------------------------------
    # Run Bundle Acceptance, State Queries & Controls
    # ------------------------------------------------------------------
    def _append_event(self, c: sqlite3.Connection, run_id: str, event_type: str, payload: dict) -> None:
        c.execute(
            'INSERT INTO connector_run_events(run_id, event_type, payload_json, created_at) VALUES(?,?,?,?)',
            (run_id, event_type, json.dumps(payload), now()),
        )

    def _log_file_path(self, run_id: str, attempt_id: str, stream: str) -> Path:
        if stream not in VALID_LOG_STREAMS:
            raise make_error('Invalid log stream', 'INVALID_LOG_STREAM', 422)
        return self.host.runtime / 'connector-run-logs' / run_id / attempt_id / f'{stream}.log'

    def _append_log(self, run_id: str, attempt_id: str, stream: str, text: str) -> None:
        if not text:
            return
        path = self._log_file_path(run_id, attempt_id, stream)
        path.parent.mkdir(parents=True, exist_ok=True)
        safe = redact(text)
        with path.open('ab') as out:
            out.write(safe.encode('utf-8', errors='replace'))

    def read_attempt_logs(self, run_id: str, attempt_id: str, stream: str = 'stdout', offset: int = 0, limit: int = 65536) -> dict:
        if not re.fullmatch(r'[a-f0-9]{32}', run_id) or not re.fullmatch(r'[a-f0-9]{32}', attempt_id):
            raise make_error('Invalid run or attempt identity', 'INVALID_ID', 422)
        if offset < 0 or not 1 <= limit <= 524288:
            raise make_error('Invalid log slice bounds', 'INVALID_LOG_BOUNDS', 422)
        with self.host.lock, self._connect() as c:
            row = c.execute('SELECT state FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                raise make_error('Connector run not found', 'NOT_FOUND', 404)
            if row['state'] == 'DELETED':
                raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
            att = c.execute(
                'SELECT state FROM connector_run_attempts WHERE attempt_id=? AND run_id=?',
                (attempt_id, run_id),
            ).fetchone()
            if not att:
                raise make_error('Attempt not found', 'NOT_FOUND', 404)
            att_state = att['state']

        path = self._log_file_path(run_id, attempt_id, stream)
        if not path.is_file():
            return {
                'run_id': run_id,
                'attempt_id': attempt_id,
                'stream': stream,
                'offset': offset,
                'next_offset': offset,
                'total_bytes': 0,
                'eof': att_state != 'RUNNING',
                'text': '',
            }
        total_bytes = path.stat().st_size
        if offset >= total_bytes:
            return {
                'run_id': run_id,
                'attempt_id': attempt_id,
                'stream': stream,
                'offset': offset,
                'next_offset': total_bytes,
                'total_bytes': total_bytes,
                'eof': att_state != 'RUNNING',
                'text': '',
            }
        with path.open('rb') as inp:
            inp.seek(offset)
            chunk = inp.read(limit)
        text, consumed = slice_utf8_complete(chunk)
        # If offset started inside a multibyte char and slice was empty because limit was tiny, consume safely.
        if consumed == 0 and chunk:
            text = chunk.decode('utf-8', errors='replace')
            consumed = len(chunk)
        next_offset = offset + consumed
        return {
            'run_id': run_id,
            'attempt_id': attempt_id,
            'stream': stream,
            'offset': offset,
            'next_offset': next_offset,
            'total_bytes': total_bytes,
            'eof': (att_state != 'RUNNING') and (next_offset >= total_bytes),
            'text': redact(text),
        }

    def _serialize_run(self, c: sqlite3.Connection, row: sqlite3.Row) -> dict:
        run_id = row['run_id']
        if row['state'] == 'DELETED':
            raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
        steps = [
            dict(r)
            for r in c.execute(
                'SELECT * FROM connector_run_steps WHERE run_id=? ORDER BY step_index ASC',
                (run_id,),
            ).fetchall()
        ]
        attempts = []
        for r in c.execute(
            'SELECT * FROM connector_run_attempts WHERE run_id=? ORDER BY ordinal ASC',
            (run_id,),
        ).fetchall():
            item = dict(r)
            item['terminated'] = bool(item['terminated'])
            item['console_evidence'] = json.loads(item.pop('console_evidence_json')) if item.get('console_evidence_json') else None
            attempts.append(item)
        analysis_row = c.execute(
            'SELECT * FROM connector_analyses WHERE run_id=? ORDER BY created_at DESC LIMIT 1',
            (run_id,),
        ).fetchone()
        active_analysis = None
        if analysis_row:
            active_analysis = dict(analysis_row)
            active_analysis['decision'] = (
                json.loads(active_analysis.pop('decision_json')) if active_analysis.get('decision_json') else None
            )
            active_analysis.pop('lease_token', None)
        events = [
            {
                'seq': e['seq'],
                'event_type': e['event_type'],
                'payload': json.loads(e['payload_json']),
                'created_at': e['created_at'],
            }
            for e in c.execute(
                'SELECT seq, event_type, payload_json, created_at FROM connector_run_events '
                'WHERE run_id=? ORDER BY seq DESC LIMIT 50',
                (run_id,),
            ).fetchall()
        ]
        events.reverse()
        owner = c.execute('SELECT task_id,epoch FROM sharing_run_owners WHERE run_id=?', (run_id,)).fetchone()
        installer_progress = None
        if row['installer_snapshot_id']:
            transfer_root = self.host.runtime / 'installer-transfers'
            if owner:
                transfer_root /= digest('task:' + owner['task_id'])
            receipt = transfer_root / f"{row['installer_snapshot_id']}.json"
            if receipt.is_file():
                try:
                    installer_progress = json.loads(receipt.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    pass
        req_doc = json.loads(row['request_json'])
        result = {
            'runner_id': self.host.identity,
            'run_id': run_id,
            'idempotency_key': row['idempotency_key'],
            'request_hash': row['request_hash'],
            'parent_run_id': row['parent_run_id'],
            'child_run_id': row['child_run_id'],
            'execution_mode': row['execution_mode'],
            'state': row['state'],
            'outcome': row['outcome'],
            'pause_reason': row['pause_reason'],
            'recovery_reason': row['recovery_reason'],
            'analysis_latched': bool(row['analysis_latched']),
            'pause_requested': bool(row['pause_requested']),
            'cancel_requested': bool(row['cancel_requested']),
            'current_step_index': row['current_step_index'],
            'version': row['version'],
            'source_snapshot_id': row['source_snapshot_id'],
            'installer_snapshot_id': row['installer_snapshot_id'],
            'flash_profile': row['flash_profile'],
            'connection': req_doc.get('connection'),
            'origin': req_doc.get('origin'),
            'failure_policy': req_doc.get('failure_policy'),
            'retry_chain': json.loads(row['retry_chain_json']),
            'steps': steps,
            'attempts': attempts,
            'active_analysis': active_analysis,
            'installer_progress': installer_progress,
            'events': events,
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'ended_at': row['ended_at'],
        }

        if owner:
            result['ownership_epoch'] = owner['epoch']
            result.pop('idempotency_key')
            for field in ('parent_run_id', 'child_run_id'):
                if result[field] and not self._owned_run(c, result[field], owner['task_id']):
                    result[field] = None
            if active_analysis:
                active_analysis['ownership_epoch'] = owner['epoch']
            result['retry_chain']['parent_runs'] = [
                parent for parent in result['retry_chain'].get('parent_runs', [])
                if self._owned_run(c, parent, owner['task_id'])
            ]
            for event in events:
                for field in ('parent_run_id', 'child_run_id'):
                    target = event['payload'].get(field)
                    if target and not self._owned_run(c, target, owner['task_id']):
                        event['payload'].pop(field)
        return result

    def _owned_run(self, c, run_id, task_id):
        return c.execute('SELECT 1 FROM sharing_run_owners WHERE run_id=? AND task_id=?', (run_id, task_id)).fetchone()

    def get_run(self, run_id: str) -> dict:
        if not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise make_error('Invalid run identity', 'INVALID_ID', 422)
        with self.host.lock, self._connect() as c:
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                raise make_error('Connector run not found', 'NOT_FOUND', 404)
            return self._serialize_run(c, row)

    def get_active_run(self, *, task_id=None) -> dict | None:
        query = (
            "SELECT * FROM connector_runs WHERE state!='DELETED' AND "
            f'(state IN ({ACTIVE_RUN_STATES_SQL}) OR analysis_latched=1)'
        )
        params = (*ACTIVE_RUN_STATES,)
        if task_id:
            query += ' AND run_id IN (SELECT run_id FROM sharing_run_owners WHERE task_id=?)'
            params += (task_id,)
        with self.host.lock, self._connect() as c:
            row = c.execute(query + ' ORDER BY updated_at DESC LIMIT 1', params).fetchone()
            return self._serialize_run(c, row) if row else None

    def list_runs(self, limit: int = 20, project: str | None = None, *, task_id=None) -> list[dict]:
        bounded = max(1, min(int(limit), 100))
        query = "SELECT * FROM connector_runs WHERE state!='DELETED'"
        params = []
        if task_id:
            query += ' AND run_id IN (SELECT run_id FROM sharing_run_owners WHERE task_id=?)'
            params.append(task_id)
        if project is not None and not task_id:
            query += " AND json_extract(request_json, '$.origin.project') = ?"
            params.append(project)
        with self.host.lock, self._connect() as c:
            rows = c.execute(query + ' ORDER BY created_at DESC LIMIT ?', (*params, bounded)).fetchall()
            return [self._serialize_run(c, r) for r in rows]

    def _require_run_snapshots(self, c, access, req):
        sh = self.host.sharing
        sh.require_snapshot(c, access, 'source', req.source_snapshot_id)
        if req.installer:
            sh.require_snapshot(c, access, 'installer', req.installer.installer_snapshot_id)

    def _validate_run_inputs(self, req: ConnectorRunRequest) -> tuple[list[dict], dict]:
        template = validate_command_template(req.command_snapshot.template.model_dump())
        validate_windows_command(template)
        if self.host.python is None and any(step.path.endswith('.py') and step.adb_serial is None for step in req.tests):
            raise make_error(
                'External TC Python is not configured on Windows Connector',
                'HARDWARE_NOT_READY',
                422,
                readiness=self.readiness_snapshot(),
            )
        try:
            connection = self.host.verify(req.connection.model_dump())
        except TestError as exc:
            if exc.code == 'BOARD_MISMATCH':
                raise make_error(exc.message, 'HARDWARE_NOT_READY', 422, readiness=self.readiness_snapshot()) from exc
            raise

        source_dir = self.host.runtime / 'source-snapshots' / req.source_snapshot_id
        if not source_dir.is_dir():
            raise make_error('Source snapshot has not been uploaded/committed', 'SNAPSHOT_NOT_READY', 422)
        manifest = load_source_manifest(source_dir, req.source_snapshot_id)
        if manifest['source_revision'] != req.source_revision:
            raise make_error('Source snapshot revision mismatch', 'IMAGE_CHANGED', 422)

        files = checked_files(source_dir, manifest)
        metadata = manifest['metadata']
        requested_ids = {step.tc_id for step in req.tests}
        # Include aliases outside the request when checking duplicate identities,
        # without cataloging unrelated scripts or copying the snapshot at admission.
        selected_texts = {}
        for path, content in files.items():
            if not (path.endswith('.py') or is_adb_tc(path)) or Path(path).name == '__init__.py':
                continue
            if metadata.get(path, {}).get('id', path) in requested_ids:
                try:
                    selected_texts[path] = content.decode('utf-8')
                except UnicodeDecodeError as exc:
                    raise make_error(f'Invalid UTF-8 TC: {path}', 'SOURCE_CHANGED', 422) from exc
        catalog = discover_contents(selected_texts, metadata, req.source_revision)
        by_id = {t['id']: t for t in catalog['tests']}
        seen_ids: set[str] = set()
        resolved_steps: list[dict] = []
        sorted_inputs = sorted(req.tests, key=lambda s: s.step_index)
        for idx, step in enumerate(sorted_inputs):
            if step.step_index != idx:
                raise make_error('Run step indices must be contiguous starting from 0', 'INVALID_STEPS', 422)
            tc = by_id.get(step.tc_id)
            if not tc or tc.get('disabled_reason'):
                raise make_error(f'Unknown or disabled TC: {step.tc_id}', 'TC_NOT_FOUND', 422)
            group = suite_group(tc['path'])
            expected_kind = ('Dual' if group == 'dual_board' else 'Single') if group else tc['kind']
            if tc['path'] != step.path or expected_kind != step.kind:
                raise make_error(f'TC metadata mismatch for {step.tc_id}', 'SOURCE_CHANGED', 422)
            use_adb = step.path.endswith('.sh') or step.adb_serial is not None
            if use_adb:
                if not is_adb_tc(step.path):
                    raise make_error('ADB TC must be in the linux directory', 'TC_NOT_FOUND', 422)
                _, serial = adb_target(self.host, req.connection.a.board_id)
                if step.adb_serial is not None and step.adb_serial != serial:
                    raise make_error('ADB target changed since preparation', 'BOARD_MISMATCH', 409)
            for dep in step.after:
                if dep not in seen_ids:
                    raise make_error(f'Missing predecessor {dep} before {step.tc_id}', 'INVALID_TC_ORDER', 422)
            for dep in tc.get('after', []):
                if dep not in seen_ids:
                    raise make_error(f'Catalog predecessor {dep} must run before {step.tc_id}', 'INVALID_TC_ORDER', 422)
            seen_ids.add(step.tc_id)
            tc_meta_timeout = tc.get('timeout') if tc.get('timeout_explicit', True) else None
            meta_timeout = step.metadata_timeout_s if step.metadata_timeout_s is not None else tc_meta_timeout
            eff_timeout = step.effective_timeout_s
            if eff_timeout is None:
                eff_timeout = resolve_step_timeout(
                    step.tc_id,
                    req.timeout_settings_snapshot,
                    meta_timeout,
                )
            resolved_steps.append({
                **({'adb_serial': serial} if use_adb else {}),
                'step_index': idx,
                'tc_id': step.tc_id,
                'path': step.path,
                'kind': step.kind,
                'effective_timeout_s': eff_timeout,
                'metadata_timeout_s': meta_timeout,
                'parser': dict(step.parser),
                'after': list(step.after),
            })

        if req.execution_mode == 'flash_and_test':
            if req.installer is None:
                raise make_error('flash_and_test requires installer specification', 'INVALID_REQUEST', 422)
            try:
                self.host.flashing.verify_profile_revision(req.installer.flash_profile, req.installer.flash_profile_revision)
            except TestError as exc:
                raise make_error(exc.message, 'HARDWARE_NOT_READY', 422, readiness=self.readiness_snapshot()) from exc
            inst_dir = self.host.runtime / 'installer-snapshots' / req.installer.installer_snapshot_id
            if not inst_dir.is_dir():
                raise make_error('Installer snapshot is not published', 'SNAPSHOT_NOT_READY', 422)
            inst_manifest = installer_snapshots.load_manifest(inst_dir, req.installer.installer_snapshot_id)
            legacy_manifest = {
                'schema_version': 1,
                'batch': inst_manifest['batch'],
                'files': {n: row['sha256'] for n, row in inst_manifest['files'].items()},
            }
            from types import SimpleNamespace
            profile = self.host.flashing.profile(
                SimpleNamespace(profile=req.installer.flash_profile, manifest=legacy_manifest, connection=req.connection),
                streamed=True,
            )
            valid_bundle_relative(inst_manifest['batch'])
            self.host.flashing.validate_observers(profile, req.connection)
            installer_snapshots.load_manifest(
                inst_dir,
                req.installer.installer_snapshot_id,
                profile.get('max_bundle_bytes', installer_snapshots.MAX_TOTAL),
            )
        else:
            if req.installer is not None:
                raise make_error('tc_only must not include installer', 'INVALID_REQUEST', 422)

        return resolved_steps, connection

    def _compatibility_request_hash(self, req: ConnectorRunRequest) -> str:
        payload = req.model_dump(exclude={'request_hash', 'run_id'})
        return req.request_hash or digest(payload)

    def _matches_legacy_request(self, row: sqlite3.Row, payload: dict) -> bool:
        # v2 persisted normalized fields with resolved/sorted steps. Its server
        # hash (when no hint was sent) covers the original normalized steps,
        # but excluded run_id. Bind the presented body only after verifying both.
        try:
            req = ConnectorRunRequest.model_validate(payload)
            stored = json.loads(row['request_json'])
        except (ValidationError, ValueError):
            return False
        if not isinstance(stored, dict) or 'run_id' not in stored or 'request_hash' not in stored:
            return False
        if req.run_id != stored['run_id'] or req.request_hash != stored['request_hash']:
            return False
        if req.request_hash is None:
            return self._compatibility_request_hash(req) == row['request_hash']
        # Official v2 clients hashed the input before attaching the hint.
        # A caller-chosen hint alone proves nothing. When normalized fields
        # differ from the retained record, the original input is ambiguous.
        unsigned = {k: v for k, v in payload.items() if k != 'request_hash'}
        return (
            req.request_hash == row['request_hash'] == digest(unsigned)
            and req.model_dump() == stored
        )

    def plan_path(self, payload, *, access=None, db=None):
        request = PathRunRequest.model_validate(payload)
        if access:
            self.host.sharing.require_snapshot(db, access, 'source', request.source_snapshot_id)
            if request.installer:
                installer_id = InstallerSpecModel.model_validate(request.installer).installer_snapshot_id
                self.host.sharing.require_snapshot(db, access, 'installer', installer_id)
        body = plan_path(self.host, request)
        if access:
            body['timeout_settings_snapshot'] = {}
        else:
            with self._connect() as c:
                body['timeout_settings_snapshot'] = self._read_timeouts_doc(c)
        for step in body['tests']:
            if is_adb_tc(step['path']):
                _, step['adb_serial'] = adb_target(self.host, body['connection']['a']['board_id'])
        base = ConnectorRunRequest.model_validate(body).model_dump(exclude_none=True)
        if request.expected_plan_revision and request.expected_plan_revision != digest(base):
            raise make_error('Connector path plan changed; prepare again', 'PREVIEW_CHANGED', 409)
        if request.connection and request.connection.model_dump(exclude_none=True) != base['connection']:
            raise make_error('Prepared target boards changed', 'BOARD_MISMATCH', 409)
        return base | {'execution_mode': request.execution_mode, 'installer': request.installer}


    @retention.snapshot_operation
    def create_run(self, payload: dict, idempotency_key: str | None, *, access=None, parent_id=None) -> tuple[dict, int]:
        if self.host.stopping:
            raise make_error('Connector is stopping', 'CONNECTOR_STOPPING', 409)
        if not idempotency_key or not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 180:
            raise make_error('Idempotency-Key header (1..180 chars) is required', 'MISSING_IDEMPOTENCY_KEY', 422)
        fingerprint = digest(payload)

        with self.host.lock, self._connect() as c:
            if self.host.stopping:
                raise make_error('Connector is stopping', 'CONNECTOR_STOPPING', 409)
            c.execute('BEGIN IMMEDIATE')
            task = self.host.sharing.require_task(c, access) if access else None
            if task:
                idempotency_key = 'shared:' + digest([task['task_id'], idempotency_key])
            existing = c.execute(
                'SELECT * FROM connector_runs WHERE idempotency_key=?', (idempotency_key,)
            ).fetchone()
            if existing:
                previous = existing['body_fingerprint']
                if task:
                    self.host.sharing.require_replay_owner(c, existing['run_id'], task['task_id'], previous == fingerprint)
                if existing['state'] == 'DELETED':
                    raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
                if previous is None and self._matches_legacy_request(existing, payload):
                    c.execute('UPDATE connector_runs SET body_fingerprint=? WHERE run_id=?', (fingerprint, existing['run_id']))
                elif previous != fingerprint:
                    raise make_error('Cannot match the accepted request. Query the existing Run ID.',
                                     'IDEMPOTENCY_CONFLICT', 409, run_id=existing['run_id'])
                return self._serialize_run(c, existing), 200

            if task and 'tc_path' in payload and not task['trusted_tc_author']:
                raise sharing.approval_required()
            body = self.plan_path(payload, access=access, db=c) if 'tc_path' in payload else payload
            req = ConnectorRunRequest.model_validate(body)
            if task:
                if req.parent_run_id != parent_id or req.retry_chain is not None:
                    raise sharing.invalid_value('Run lineage must be assigned by the execution Host')
                if parent_id is None and not self.host.sharing.approved_execution(c, task, req):
                    raise sharing.approval_required()
                self._require_run_snapshots(c, access, req)
                req.origin = OriginModel(project=task['project'], session_id=task['task_id'])
            req_hash = self._compatibility_request_hash(req)
            run_id = req.run_id or uid()
            by_id = c.execute('SELECT request_hash, state FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if by_id:
                if task and not self._owned_run(c, run_id, task['task_id']):
                    raise make_error('Requested Run ID is unavailable', 'IDEMPOTENCY_CONFLICT', 409)
                if by_id['state'] == 'DELETED':
                    raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
                raise make_error('Run ID already exists', 'IDEMPOTENCY_CONFLICT', 409)

            # Exclusion across connector_runs, legacy jobs, batches, and manual PuTTY.
            blocking = c.execute(
                'SELECT run_id, state, analysis_latched FROM connector_runs '
                f'WHERE state IN ({ACTIVE_RUN_STATES_SQL}) OR analysis_latched=1 LIMIT 1',
                (*ACTIVE_RUN_STATES,),
            ).fetchone()
            if blocking:
                if task and not self._owned_run(c, blocking['run_id'], task['task_id']):
                    raise make_error('The Windows Host is occupied', 'ACTIVE_RUN_EXISTS', 409)
                raise make_error(
                    f"Existing connector run {blocking['run_id']} ({blocking['state']}) blocks new run",
                    'ACTIVE_RUN_EXISTS',
                    409,
                    active_run_id=blocking['run_id'],
                )
            if any(json.loads(r[0])['state'] in {'RUNNING', 'UNKNOWN'} for r in c.execute('SELECT data FROM jobs')):
                raise make_error('Legacy execution job is active or unresolved', 'RESERVATION_CONFLICT', 409)
            if any(json.loads(r[0])['state'] != 'RELEASED' for r in c.execute('SELECT data FROM batches')):
                raise make_error('Active batch reservation blocks new run', 'RESERVATION_CONFLICT', 409)

            resolved_steps, _ = self._validate_run_inputs(req)
            retry_chain = req.retry_chain or {
                'chain_id': uid(),
                'depth': 0,
                'automatic_retries': 0,
                'causes': [],
                'parent_runs': [],
            }
            stored_req = req.model_dump()
            stored_req['tests'] = resolved_steps
            ts = now()

            c.execute(
                'INSERT INTO connector_runs('
                'run_id, idempotency_key, request_hash, body_fingerprint, parent_run_id, child_run_id, execution_mode, '
                'state, outcome, pause_reason, recovery_reason, analysis_latched, pause_requested, cancel_requested, '
                'current_step_index, version, source_snapshot_id, installer_snapshot_id, flash_profile, '
                'request_json, retry_chain_json, created_at, updated_at, ended_at'
                ') VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    run_id,
                    idempotency_key,
                    req_hash,
                    fingerprint,
                    req.parent_run_id,
                    None,
                    req.execution_mode,
                    'QUEUED',
                    None,
                    None,
                    None,
                    0,
                    0,
                    0,
                    0,
                    1,
                    req.source_snapshot_id,
                    req.installer.installer_snapshot_id if req.installer else None,
                    req.installer.flash_profile if req.installer else None,
                    json.dumps(stored_req),
                    json.dumps(retry_chain),
                    ts,
                    ts,
                    None,
                ),
            )
            if task:
                self.host.sharing.bind_run(c, run_id, task)
                self.host.sharing.touch(c, task['task_id'])
            self._pin_evidence_serials(c, run_id)
            for st in resolved_steps:
                c.execute(
                    'INSERT INTO connector_run_steps(run_id, step_index, tc_id, path, kind, effective_timeout_s, state, latest_attempt_id, result_reason) '
                    'VALUES(?,?,?,?,?,?,?,?,?)',
                    (run_id, st['step_index'], st['tc_id'], st['path'], st['kind'], st['effective_timeout_s'], 'PENDING', None, None),
                )
            self._append_event(c, run_id, 'RUN_QUEUED', {'execution_mode': req.execution_mode, 'steps': len(resolved_steps)})
            c.commit()
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            result = self._serialize_run(c, row)
        self.start_worker()
        self._worker_wake.set()
        return result, 201

    def pause_run(self, run_id: str) -> dict:
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                raise make_error('Connector run not found', 'NOT_FOUND', 404)
            if row['state'] == 'DELETED':
                raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
            if row['state'] == 'PAUSED':
                return self._serialize_run(c, row)
            if row['state'] not in {'QUEUED', 'FLASHING', 'RUNNING', 'PAUSE_REQUESTED'}:
                raise make_error(f"Cannot pause run in state {row['state']}", 'INVALID_RUN_STATE', 409)
            ts = now()
            if row['state'] == 'QUEUED':
                c.execute(
                    "UPDATE connector_runs SET state='PAUSED', pause_reason='OPERATOR_PAUSE', pause_requested=0, version=version+1, updated_at=? WHERE run_id=?",
                    (ts, run_id),
                )
                self._append_event(c, run_id, 'RUN_PAUSED', {'reason': 'OPERATOR_PAUSE'})
            else:
                c.execute(
                    "UPDATE connector_runs SET state='PAUSE_REQUESTED', pause_requested=1, version=version+1, updated_at=? WHERE run_id=?",
                    (ts, run_id),
                )
                self._append_event(c, run_id, 'RUN_PAUSE_REQUESTED', {'previous_state': row['state']})
            c.commit()
            return self._serialize_run(c, c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone())

    def resume_run(self, run_id: str) -> dict:
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                raise make_error('Connector run not found', 'NOT_FOUND', 404)
            if row['state'] == 'DELETED':
                raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
            if row['analysis_latched']:
                raise make_error(
                    '실패 분석 래치가 활성화되어 있어 수동 재개할 수 없습니다. 분석 결정 또는 Hold 확인/취소를 수행하세요.',
                    'ANALYSIS_LATCH_ACTIVE',
                    409,
                )
            if row['state'] == 'PAUSE_REQUESTED':
                flashing_active = c.execute(
                    "SELECT 1 FROM connector_run_attempts WHERE run_id=? AND phase='FLASHING' AND state='RUNNING' LIMIT 1",
                    (run_id,),
                ).fetchone()
                restored_state = 'FLASHING' if flashing_active else 'RUNNING'
                c.execute(
                    'UPDATE connector_runs SET state=?, pause_requested=0, version=version+1, updated_at=? WHERE run_id=?',
                    (restored_state, now(), run_id),
                )
                self._append_event(c, run_id, 'RUN_PAUSE_CLEARED', {'restored_state': restored_state})
                c.commit()
                return self._serialize_run(c, c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone())
            if row['state'] != 'PAUSED':
                raise make_error(f"Cannot resume run in state {row['state']}", 'INVALID_RUN_STATE', 409)
            c.execute(
                "UPDATE connector_runs SET state='QUEUED', pause_reason=NULL, pause_requested=0, version=version+1, updated_at=? WHERE run_id=?",
                (now(), run_id),
            )
            self._append_event(c, run_id, 'RUN_RESUMED', {'step_index': row['current_step_index']})
            c.commit()
            resumed = self._serialize_run(c, c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone())
        self.start_worker()
        self._worker_wake.set()
        return resumed

    def cancel_run(self, run_id: str) -> dict:
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                raise make_error('Connector run not found', 'NOT_FOUND', 404)
            if row['state'] == 'DELETED':
                raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
            if row['state'] == 'COMPLETED':
                return self._serialize_run(c, row)
            if row['state'] == 'UNKNOWN':
                raise make_error('UNKNOWN 상태 실행은 reconcile 로 먼저 정리해야 합니다.', 'RUN_UNKNOWN', 409)
            ts = now()
            if row['state'] in {'QUEUED', 'PAUSED'}:
                c.execute(
                    "UPDATE connector_runs SET state='COMPLETED', outcome='CANCELLED', pause_reason=NULL, "
                    'analysis_latched=0, cancel_requested=1, version=version+1, updated_at=?, ended_at=? WHERE run_id=?',
                    (ts, ts, run_id),
                )
                c.execute(
                    "UPDATE connector_analyses SET status='SUPERSEDED_BY_CANCEL', lease_token=NULL, updated_at=? "
                    "WHERE run_id=? AND status IN ('PENDING','ANALYZING','HOLD')",
                    (ts, run_id),
                )
                c.execute(
                    "UPDATE connector_run_steps SET state='CANCELLED' WHERE run_id=? AND state IN ('PENDING','RUNNING')",
                    (run_id,),
                )
                self._append_event(c, run_id, 'RUN_CANCELLED', {'from_state': row['state']})
            else:
                c.execute(
                    "UPDATE connector_runs SET state='CANCEL_REQUESTED', cancel_requested=1, version=version+1, updated_at=? WHERE run_id=?",
                    (ts, run_id),
                )
                self._append_event(c, run_id, 'RUN_CANCEL_REQUESTED', {'previous_state': row['state']})
            c.commit()
            return self._serialize_run(c, c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone())

    def reconcile_run(self, run_id: str, payload: dict) -> dict:
        req = ConnectorRunReconcileRequest.model_validate(payload)
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                raise make_error('Connector run not found', 'NOT_FOUND', 404)
            if row['state'] == 'DELETED':
                raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
            if row['state'] != 'UNKNOWN':
                raise make_error('Only UNKNOWN runs require reconciliation', 'INVALID_RUN_STATE', 409)
            ts = now()
            if req.action == 'MARK_ABORTED':
                c.execute(
                    "UPDATE connector_runs SET state='COMPLETED', outcome='ABORTED', recovery_reason=NULL, "
                    'analysis_latched=0, version=version+1, updated_at=?, ended_at=? WHERE run_id=?',
                    (ts, ts, run_id),
                )
                c.execute(
                    "UPDATE connector_analyses SET status='SUPERSEDED_BY_CANCEL', lease_token=NULL, updated_at=? "
                    "WHERE run_id=? AND status IN ('PENDING','ANALYZING','HOLD')",
                    (ts, run_id),
                )
                self._append_event(c, run_id, 'RUN_RECONCILED_ABORTED', {'reason': req.reason})
            else:
                new_ver = row['version'] + 1
                analysis_id = uid()
                c.execute(
                    "UPDATE connector_runs SET state='PAUSED', pause_reason='FAILURE_STOP_LATCH', "
                    'analysis_latched=1, version=?, updated_at=? WHERE run_id=?',
                    (new_ver, ts, run_id),
                )
                c.execute(
                    'INSERT INTO connector_analyses('
                    'analysis_id, run_id, attempt_id, phase, failed_step_index, evidence_revision, status, created_at, updated_at'
                    ') VALUES (?,?,?,?,?,?,?,?,?)',
                    (analysis_id, run_id, None, 'UNKNOWN', row['current_step_index'], new_ver, 'PENDING', ts, ts),
                )
                self._append_event(c, run_id, 'RUN_RECONCILED_ANALYSIS', {'analysis_id': analysis_id, 'reason': req.reason})
            c.commit()
            return self._serialize_run(c, c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone())

    @retention.snapshot_operation
    def delete_run(self, run_id: str) -> dict:
        if not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise make_error('Invalid run identity', 'INVALID_ID', 422)
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                raise make_error('Connector run not found', 'NOT_FOUND', 404)
            if row['state'] == 'DELETED':
                raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
            if row['state'] != 'COMPLETED' or row['analysis_latched']:
                raise make_error(
                    '완료되지 않았거나 분석 래치가 걸린 실행은 삭제할 수 없습니다.',
                    'DELETE_BLOCKED',
                    409,
                )
            ts = now()
            c.execute(
                "UPDATE connector_runs SET state='DELETED', updated_at=? WHERE run_id=?",
                (ts, run_id),
            )
            c.execute('DELETE FROM connector_failure_evidence WHERE run_id=?', (run_id,))
            c.commit()

        for directory in (
            self.host.runtime / 'connector-snapshots' / run_id,
            self.host.runtime / 'connector-run-logs' / run_id,
        ):
            if directory.exists() and not directory.is_symlink():
                shutil.rmtree(directory, ignore_errors=True)
        return {'deleted': True, 'run_id': run_id}

    def rerun(self, run_id: str, idempotency_key: str | None = None, *, access=None) -> tuple[dict, int]:
        if not re.fullmatch(r'[a-f0-9]{32}', run_id):
            raise make_error('Invalid run identity', 'INVALID_ID', 422)
        with self.host.lock, self._connect() as c:
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                raise make_error('Connector run not found', 'NOT_FOUND', 404)
            if row['state'] == 'DELETED':
                raise make_error('영구 삭제된 실행 ID입니다.', 'RUN_DELETED', 410)
            if row['state'] != 'COMPLETED' or row['analysis_latched']:
                raise make_error('완료된 실행만 재실행할 수 있습니다.', 'RERUN_BLOCKED', 409)
            req = json.loads(row['request_json'])
        req.pop('run_id', None)
        req.pop('retry_chain', None)
        req['parent_run_id'] = run_id
        req['request_hash'] = digest({k: v for k, v in req.items() if k != 'request_hash'})
        key = idempotency_key or f'rerun:{run_id}:{uid()}'
        return self.create_run(req, key, access=access, parent_id=run_id)

    # ------------------------------------------------------------------
    # Fail-Stop Analysis Lease, Trust Boundary & RETRY/REPREPARE
    # ------------------------------------------------------------------
    def _expire_stale_analysis_leases(self, c: sqlite3.Connection) -> None:
        ts = now()
        c.execute(
            "UPDATE connector_analyses SET status='PENDING', lease_token=NULL, lease_owner=NULL, lease_expires_at=NULL, updated_at=? "
            "WHERE status='ANALYZING' AND lease_expires_at IS NOT NULL AND lease_expires_at < ?",
            (ts, ts),
        )

    def _serialize_analysis(self, row: sqlite3.Row, *, include_lease_token: bool = False) -> dict:
        item = dict(row)
        item['decision'] = json.loads(item.pop('decision_json')) if item.get('decision_json') else None
        if not include_lease_token:
            item.pop('lease_token', None)
        return item

    def list_analyses(self, status: str | None = None, run_id: str | None = None, *, task_id=None) -> list[dict]:
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._expire_stale_analysis_leases(c)
            sql = 'SELECT * FROM connector_analyses WHERE 1=1'
            params: list[Any] = []
            if task_id:
                sql = ('SELECT a.*,o.epoch AS ownership_epoch FROM connector_analyses a '
                       'JOIN sharing_run_owners o USING(run_id) WHERE o.task_id=?')
                params.append(task_id)
            if status:
                sql += ' AND status=?'
                params.append(status)
            if run_id:
                sql += ' AND run_id=?'
                params.append(run_id)
            sql += ' ORDER BY created_at DESC LIMIT 50'
            rows = c.execute(sql, tuple(params)).fetchall()
            c.commit()
            return [self._serialize_analysis(r) for r in rows]

    def claim_analysis(self, analysis_id: str, payload: dict) -> dict:
        req = AnalysisClaimRequest.model_validate(payload)
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._expire_stale_analysis_leases(c)
            row = c.execute('SELECT * FROM connector_analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
            if not row:
                raise make_error('Analysis record not found', 'NOT_FOUND', 404)
            if row['status'] != 'PENDING':
                raise make_error(f"Analysis is in state {row['status']} and cannot be claimed", 'ANALYSIS_NOT_PENDING', 409)
            lease_token = secrets.token_urlsafe(24)
            ts = now()
            expires = ts + req.lease_ttl_s
            c.execute(
                "UPDATE connector_analyses SET status='ANALYZING', lease_token=?, lease_owner=?, lease_expires_at=?, updated_at=? "
                'WHERE analysis_id=?',
                (lease_token, req.lease_owner, expires, ts, analysis_id),
            )
            c.commit()
            updated = c.execute('SELECT * FROM connector_analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
            result = self._serialize_analysis(updated, include_lease_token=True)
            if c.execute('SELECT 1 FROM connector_failure_evidence WHERE attempt_id=?', (row['attempt_id'],)).fetchone():
                result['failure_evidence_available'] = True
            return result

    def heartbeat_analysis(self, analysis_id: str, payload: dict) -> dict:
        req = AnalysisHeartbeatRequest.model_validate(payload)
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM connector_analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
            if not row:
                raise make_error('Analysis record not found', 'NOT_FOUND', 404)
            if row['status'] != 'ANALYZING' or not row['lease_token'] or not hmac.compare_digest(row['lease_token'], req.lease_token):
                raise make_error('Invalid or expired analysis lease token', 'ANALYSIS_LEASE_INVALID', 409)
            ts = now()
            expires = ts + req.lease_ttl_s
            c.execute(
                'UPDATE connector_analyses SET lease_expires_at=?, updated_at=? WHERE analysis_id=?',
                (expires, ts, analysis_id),
            )
            c.commit()
            updated = c.execute('SELECT * FROM connector_analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
            return self._serialize_analysis(updated)

    def acknowledge_hold(self, analysis_id: str, payload: dict | None = None) -> dict:
        req = AcknowledgeHoldRequest.model_validate(payload or {})
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM connector_analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
            if not row:
                raise make_error('Analysis record not found', 'NOT_FOUND', 404)
            if row['status'] not in {'PENDING', 'ANALYZING', 'HOLD', 'STOPPED'}:
                raise make_error(f"Analysis {row['status']} cannot be acknowledged", 'INVALID_ANALYSIS_STATE', 409)
            run_row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (row['run_id'],)).fetchone()
            ts = now()
            decision = json.loads(row['decision_json']) if row['decision_json'] else {}
            decision['acknowledged_by'] = req.operator
            decision['acknowledged_note'] = req.note
            decision['acknowledged_at'] = ts
            c.execute(
                "UPDATE connector_analyses SET status='STOPPED', lease_token=NULL, lease_expires_at=NULL, decision_json=?, updated_at=? "
                'WHERE analysis_id=?',
                (json.dumps(decision), ts, analysis_id),
            )
            if run_row and run_row['state'] not in {'COMPLETED', 'DELETED'}:
                c.execute(
                    "UPDATE connector_runs SET state='COMPLETED', outcome='FAILED', pause_reason=NULL, "
                    'analysis_latched=0, version=version+1, updated_at=?, ended_at=? WHERE run_id=?',
                    (ts, ts, row['run_id']),
                )
                self._append_event(
                    c,
                    row['run_id'],
                    'HOLD_ACKNOWLEDGED',
                    {'analysis_id': analysis_id, 'operator': req.operator, 'note': req.note},
                )
            c.commit()
            return self._serialize_analysis(
                c.execute('SELECT * FROM connector_analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
            )

    def _processes_stopped_for_run(self, run_id: str) -> bool:
        with self._active_lock:
            tree = self._active_trees.get(run_id)
            if tree is not None and not tree.stopped():
                return False
        if getattr(self.host, 'flashing', None) and self.host.flashing.supervised:
            return False
        return True

    def _reprepare_inputs(self, run_req, reprepare):
        candidate = json.loads(json.dumps(run_req))
        for field in ('source_snapshot_id', 'source_revision', 'command_snapshot', 'installer', 'timeout_settings_snapshot'):
            value = getattr(reprepare, field)
            if value is not None:
                candidate[field] = value if isinstance(value, (str, dict)) else value.model_dump()
        if reprepare.timeout_settings_snapshot is not None:
            for step in candidate['tests']:
                step['effective_timeout_s'] = resolve_step_timeout(
                    step['tc_id'], reprepare.timeout_settings_snapshot, step.get('metadata_timeout_s'),
                )
        return candidate

    @retention.snapshot_operation
    def decide_analysis(self, analysis_id: str, payload: dict, *, access=None) -> dict:
        req = AnalysisDecisionRequest.model_validate(payload)
        cause = normalized_cause(req.cause_key)
        ts = now()
        wake_worker = False

        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            self._expire_stale_analysis_leases(c)
            row = c.execute('SELECT * FROM connector_analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
            if not row:
                raise make_error('Analysis record not found', 'NOT_FOUND', 404)
            if row['status'] != 'ANALYZING' or not row['lease_token'] or not hmac.compare_digest(row['lease_token'], req.lease_token):
                raise make_error('Analysis lease token is invalid or expired', 'ANALYSIS_LEASE_INVALID', 409)
            run_row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (row['run_id'],)).fetchone()
            if not run_row or run_row['state'] == 'DELETED':
                raise make_error('Associated connector run is unavailable', 'NOT_FOUND', 404)
            if run_row['cancel_requested'] or run_row['state'] == 'COMPLETED':
                c.execute(
                    "UPDATE connector_analyses SET status='SUPERSEDED_BY_CANCEL', lease_token=NULL, updated_at=? WHERE analysis_id=?",
                    (ts, analysis_id),
                )
                c.commit()
                return {'analysis': self._serialize_analysis(c.execute('SELECT * FROM connector_analyses WHERE analysis_id=?', (analysis_id,)).fetchone())}
            if req.expected_evidence_revision != run_row['version'] or row['evidence_revision'] != run_row['version']:
                raise make_error(
                    'Evidence revision mismatch; reload run and analysis state',
                    'EVIDENCE_REVISION_CONFLICT',
                    409,
                )

            run_req = json.loads(run_row['request_json'])
            policy = run_req.get('failure_policy', {})
            retry_chain = json.loads(run_row['retry_chain_json'])
            max_retries = int(policy.get('max_retry_chain', MAX_RETRY_CHAIN_DEFAULT))
            verifier_required = bool(policy.get('verifier_required', True))
            stop_on_same = bool(policy.get('stop_on_same_cause', True))

            enforced_verdict = req.verdict
            hold_reason = None
            if req.verdict in {'RETRY', 'REPREPARE'}:
                if verifier_required and req.verifier_status != 'PASSED':
                    enforced_verdict = 'HOLD'
                    hold_reason = 'VERIFIER_GATE_BLOCKED'
                elif not cause or (stop_on_same and cause in retry_chain.get('causes', [])):
                    enforced_verdict = 'HOLD'
                    hold_reason = 'REPEATED_ROOT_CAUSE'
                elif int(retry_chain.get('automatic_retries', 0)) >= max_retries:
                    enforced_verdict = 'HOLD'
                    hold_reason = 'MAX_RETRY_CHAIN_REACHED'
                elif not self._processes_stopped_for_run(run_row['run_id']):
                    enforced_verdict = 'HOLD'
                    hold_reason = 'PROCESS_NOT_STOPPED'
                else:
                    hw_ok = self.host.python is not None
                    if hw_ok:
                        try:
                            self.host.verify(run_req.get('connection') or {})
                        except TestError:
                            hw_ok = False
                    if hw_ok and run_req.get('execution_mode') == 'flash_and_test':
                        hw_ok = bool(self.readiness_snapshot().get('flash_tools'))
                    if not hw_ok:
                        enforced_verdict = 'HOLD'
                        hold_reason = 'HARDWARE_NOT_READY'

            task = self.host.sharing.require_task(c, access) if access else None
            if enforced_verdict == 'REPREPARE':
                child_req_dict = self._reprepare_inputs(run_req, req.reprepare or ReprepareInputModel())
                if task and not task['trusted_tc_author']:
                    original = ConnectorRunRequest.model_validate(run_req)
                    proposed = ConnectorRunRequest.model_validate(child_req_dict)
                    if (sharing.execution_input_hash(original) != sharing.execution_input_hash(proposed)
                            and not self.host.sharing.approved_execution(c, task, proposed)):
                        enforced_verdict = 'HOLD'
                        hold_reason = 'EXECUTION_INPUT_APPROVAL_REQUIRED'

            decision_record = {
                'requested_verdict': req.verdict,
                'enforced_verdict': enforced_verdict,
                'hold_reason': hold_reason,
                'cause_key': cause,
                'summary': req.summary,
                'verifier_status': req.verifier_status,
                'analyzer_evidence': req.analyzer_evidence,
                'decided_at': ts,
            }

            child_run_data = None
            if enforced_verdict == 'HOLD':
                a_status = 'STOPPED' if hold_reason in {'REPEATED_ROOT_CAUSE', 'MAX_RETRY_CHAIN_REACHED'} else 'HOLD'
                c.execute(
                    'UPDATE connector_analyses SET status=?, lease_token=NULL, lease_expires_at=NULL, '
                    'decision_json=?, cause_key=?, verifier_status=?, updated_at=? WHERE analysis_id=?',
                    (a_status, json.dumps(decision_record), cause, req.verifier_status, ts, analysis_id),
                )
                self._append_event(
                    c,
                    run_row['run_id'],
                    'ANALYSIS_HOLD',
                    {'analysis_id': analysis_id, 'reason': hold_reason or 'ANALYZER_HOLD', 'cause_key': cause},
                )
            elif enforced_verdict == 'RETRY':
                new_chain = dict(retry_chain)
                new_chain['automatic_retries'] = int(new_chain.get('automatic_retries', 0)) + 1
                new_chain['causes'] = list(dict.fromkeys(list(new_chain.get('causes', [])) + ([cause] if cause else [])))
                c.execute(
                    "UPDATE connector_analyses SET status='RETRY_READY', lease_token=NULL, lease_expires_at=NULL, "
                    'decision_json=?, cause_key=?, verifier_status=?, updated_at=? WHERE analysis_id=?',
                    (json.dumps(decision_record), cause, req.verifier_status, ts, analysis_id),
                )
                c.execute(
                    "UPDATE connector_runs SET state='QUEUED', pause_reason=NULL, analysis_latched=0, retry_chain_json=?, "
                    'version=version+1, updated_at=? WHERE run_id=?',
                    (json.dumps(new_chain), ts, run_row['run_id']),
                )
                if row['phase'] in {'TC', 'UNKNOWN'} and row['failed_step_index'] is not None:
                    c.execute(
                        "UPDATE connector_run_steps SET state='PENDING', result_reason=NULL WHERE run_id=? AND step_index=? AND state!='PASSED'",
                        (run_row['run_id'], row['failed_step_index']),
                    )
                self._append_event(
                    c,
                    run_row['run_id'],
                    'ANALYSIS_RETRY_ACCEPTED',
                    {'analysis_id': analysis_id, 'cause_key': cause, 'automatic_retries': new_chain['automatic_retries']},
                )
                wake_worker = True
            else:
                # REPREPARE: immutable parent closure + child run creation inside single transaction.
                child_id = uid()
                child_req_dict['run_id'] = child_id
                child_req_dict['parent_run_id'] = run_row['run_id']
                new_chain = dict(retry_chain)
                new_chain['depth'] = int(new_chain.get('depth', 0)) + 1
                new_chain['automatic_retries'] = int(new_chain.get('automatic_retries', 0)) + 1
                new_chain['causes'] = list(dict.fromkeys(list(new_chain.get('causes', [])) + ([cause] if cause else [])))
                new_chain['parent_runs'] = list(new_chain.get('parent_runs', [])) + [run_row['run_id']]
                child_req_dict['retry_chain'] = new_chain
                child_req_dict.pop('request_hash', None)
                child_model = ConnectorRunRequest.model_validate(child_req_dict)
                if task:
                    self._require_run_snapshots(c, access, child_model)
                    child_model.origin = OriginModel(project=task['project'], session_id=task['task_id'])
                resolved_steps, _ = self._validate_run_inputs(child_model)
                child_req_hash = self._compatibility_request_hash(child_model)
                stored_child = child_model.model_dump()
                stored_child['tests'] = resolved_steps

                c.execute(
                    "UPDATE connector_analyses SET status='CHILD_CREATED', lease_token=NULL, lease_expires_at=NULL, "
                    'decision_json=?, cause_key=?, verifier_status=?, updated_at=? WHERE analysis_id=?',
                    (json.dumps(decision_record), cause, req.verifier_status, ts, analysis_id),
                )
                c.execute(
                    "UPDATE connector_runs SET state='COMPLETED', outcome='SUPERSEDED_BY_REPREPARE', child_run_id=?, "
                    'pause_reason=NULL, analysis_latched=0, version=version+1, updated_at=?, ended_at=? WHERE run_id=?',
                    (child_id, ts, ts, run_row['run_id']),
                )
                c.execute(
                    'INSERT INTO connector_runs('
                    'run_id, idempotency_key, request_hash, body_fingerprint, parent_run_id, child_run_id, execution_mode, '
                    'state, outcome, pause_reason, recovery_reason, analysis_latched, pause_requested, cancel_requested, '
                    'current_step_index, version, source_snapshot_id, installer_snapshot_id, flash_profile, '
                    'request_json, retry_chain_json, created_at, updated_at, ended_at'
                    ') VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (
                        child_id,
                        f'reprepare:{analysis_id}:{child_id}',
                        child_req_hash,
                        digest(child_req_dict),
                        run_row['run_id'],
                        None,
                        child_model.execution_mode,
                        'QUEUED',
                        None,
                        None,
                        None,
                        0,
                        0,
                        0,
                        0,
                        1,
                        child_model.source_snapshot_id,
                        child_model.installer.installer_snapshot_id if child_model.installer else None,
                        child_model.installer.flash_profile if child_model.installer else None,
                        json.dumps(stored_child),
                        json.dumps(new_chain),
                        ts,
                        ts,
                        None,
                    ),
                )
                if task:
                    self.host.sharing.bind_run(c, child_id, task)
                    self.host.sharing.touch(c, task['task_id'])
                self._pin_evidence_serials(c, child_id)
                for st in resolved_steps:
                    c.execute(
                        'INSERT INTO connector_run_steps(run_id, step_index, tc_id, path, kind, effective_timeout_s, state, latest_attempt_id, result_reason) '
                        'VALUES(?,?,?,?,?,?,?,?,?)',
                        (child_id, st['step_index'], st['tc_id'], st['path'], st['kind'], st['effective_timeout_s'], 'PENDING', None, None),
                    )
                self._append_event(
                    c,
                    run_row['run_id'],
                    'RUN_SUPERSEDED_BY_REPREPARE',
                    {'child_run_id': child_id, 'analysis_id': analysis_id},
                )
                self._append_event(
                    c,
                    child_id,
                    'RUN_QUEUED',
                    {'parent_run_id': run_row['run_id'], 'execution_mode': child_model.execution_mode},
                )
                child_row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (child_id,)).fetchone()
                child_run_data = self._serialize_run(c, child_row)
                wake_worker = True

            c.commit()
            updated_analysis = self._serialize_analysis(
                c.execute('SELECT * FROM connector_analyses WHERE analysis_id=?', (analysis_id,)).fetchone()
            )
            updated_run = self._serialize_run(
                c,
                c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_row['run_id'],)).fetchone(),
            )

        if wake_worker:
            self.start_worker()
            self._worker_wake.set()
        return {
            'analysis': updated_analysis,
            'run': updated_run,
            'child_run': child_run_data,
        }

    # ------------------------------------------------------------------
    # Worker Execution Engine
    # ------------------------------------------------------------------
    def _worker_loop(self) -> None:
        while not self._worker_stop.is_set():
            run_id = None
            with self.host.lock, self._connect() as c:
                row = c.execute(
                    "SELECT run_id FROM connector_runs WHERE state='QUEUED' AND analysis_latched=0 ORDER BY created_at ASC LIMIT 1"
                ).fetchone()
                if row:
                    run_id = row['run_id']
            if run_id is not None:
                try:
                    self._execute_run(run_id)
                except Exception:
                    # Fallback safeguard if unexpected DB error occurred outside _execute_run latch.
                    self._trigger_fail_stop_latch(
                        run_id,
                        attempt_id=None,
                        phase='UNKNOWN',
                        failed_step_index=None,
                        reason='CONNECTOR_WORKER_EXCEPTION',
                        console_evidence=None,
                    )
                continue
            self._worker_wake.wait(timeout=0.5)
            self._worker_wake.clear()

    def _run_flags(self, run_id: str) -> tuple[bool, bool]:
        with self.host.lock, self._connect() as c:
            row = c.execute(
                'SELECT pause_requested, cancel_requested FROM connector_runs WHERE run_id=?',
                (run_id,),
            ).fetchone()
            if not row:
                return False, True
            return bool(row['pause_requested']), bool(row['cancel_requested'])

    def _pin_evidence_serials(self, c, run_id):
        mapping = self.host.path_run.get('adb_serials')
        pins = {}
        if isinstance(mapping, dict):
            pins = {k: v for k, v in mapping.items() if isinstance(v, str) and list(mapping.values()).count(v) == 1}
        c.execute('UPDATE connector_runs SET evidence_serials_json=? WHERE run_id=?', (json.dumps(pins), run_id))

    def _trigger_fail_stop_latch(
        self,
        run_id: str,
        *,
        attempt_id: str | None,
        phase: str,
        failed_step_index: int | None,
        reason: str,
        console_evidence: dict | None,
    ) -> None:
        ts = now()
        analysis_id = uid()
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row or row['state'] in {'COMPLETED', 'DELETED'}:
                c.commit()
                return
            if attempt_id:
                c.execute(
                    "UPDATE connector_run_attempts SET state='FAILED', reason=?, console_evidence_json=?, ended_at=COALESCE(ended_at, ?) "
                    'WHERE attempt_id=?',
                    (reason, json.dumps(console_evidence) if console_evidence else None, ts, attempt_id),
                )
            if failed_step_index is not None:
                c.execute(
                    "UPDATE connector_run_steps SET state='FAILED', result_reason=? WHERE run_id=? AND step_index=?",
                    (reason, run_id, failed_step_index),
                )
            new_ver = row['version'] + 1
            c.execute(
                "UPDATE connector_runs SET state='PAUSED', pause_reason='FAILURE_STOP_LATCH', "
                'analysis_latched=1, pause_requested=0, version=?, updated_at=? WHERE run_id=?',
                (new_ver, ts, run_id),
            )
            c.execute(
                'INSERT INTO connector_analyses('
                'analysis_id, run_id, attempt_id, phase, failed_step_index, evidence_revision, status, created_at, updated_at'
                ') VALUES (?,?,?,?,?,?,?,?,?)',
                (analysis_id, run_id, attempt_id, phase, failed_step_index, new_ver, 'PENDING', ts, ts),
            )
            self._append_event(
                c,
                run_id,
                'FAIL_STOP_LATCHED',
                {
                    'analysis_id': analysis_id,
                    'phase': phase,
                    'failed_step_index': failed_step_index,
                    'attempt_id': attempt_id,
                    'reason': reason,
                    'evidence_revision': new_ver,
                },
            )
            targets = []
            if phase == 'TC' and attempt_id is not None and failed_step_index is not None:
                req = json.loads(row['request_json'])
                step = req['tests'][failed_step_index]
                roles = ('a', 'b') if step['kind'] == 'Dual' else ('a',)
                pins = json.loads(row['evidence_serials_json'] or '{}')
                boards = {}
                for role in roles:
                    board = req['connection'][role]['board_id']
                    serial = step.get('adb_serial') or pins.get(board)
                    if serial:
                        targets.append((board, serial))
                        boards[board] = {'status': 'PENDING'}
                    else:
                        boards[board] = {'status': 'ADB_SERIAL_REQUIRED'}
                attempt = c.execute('SELECT exit_code FROM connector_run_attempts WHERE attempt_id=?',
                                    (attempt_id,)).fetchone()
                data = {'run_id': run_id, 'attempt_id': attempt_id, 'tc_id': step['tc_id'],
                        'failed_at': ts, 'reason': reason, 'exit_code': attempt['exit_code'],
                        'logs': None,
                        'dmesg': boards}
                c.execute('INSERT INTO connector_failure_evidence VALUES (?,?,?,?)',
                          (attempt_id, run_id, 'PENDING', json.dumps(data)))
            c.commit()
        for board, serial in targets:
            try:
                threading.Thread(target=self._collect_kernel_evidence, args=(attempt_id, board, serial),
                                 daemon=True, name='dmesg-' + board).start()
            except RuntimeError:
                self._save_evidence(attempt_id, board, {'status': 'COLLECTOR_UNAVAILABLE'})

        if phase == 'TC' and attempt_id is not None and failed_step_index is not None:
            # The failure is visible before reading logs or waiting for any board.
            logs = failure_evidence.log_tails(self._log_file_path(run_id, attempt_id, 'stdout').parent)
            self._save_evidence(attempt_id, None, logs)

    def _collect_kernel_evidence(self, attempt_id, board, pinned):
        try:
            adb, serial = adb_target(self.host, board)
            result = failure_evidence.kernel_tail(adb, serial) if serial == pinned else {'status': 'BOARD_MISMATCH'}
        except TestError as exc:
            result = {'status': exc.code}
        except Exception:
            result = {'status': 'COLLECTION_FAILED'}
        self._save_evidence(attempt_id, board, result)

    def _save_evidence(self, attempt_id, board, result):
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT data_json FROM connector_failure_evidence WHERE attempt_id=? AND status='PENDING'",
                            (attempt_id,)).fetchone()
            if not row:
                return
            data = json.loads(row['data_json'])
            if board is None:
                data['logs'] = result
            else:
                data['dmesg'][board] = {**result, 'collected_at': now()}
            states = {v['status'] for v in data['dmesg'].values()}
            status = 'PENDING'
            if data['logs'] is not None and 'PENDING' not in states:
                all_readable = all(v['status'] != 'UNAVAILABLE' for v in data['logs'].values())
                status = 'READY' if states == {'READY'} and all_readable else 'PARTIAL'
            c.execute('UPDATE connector_failure_evidence SET status=?, data_json=? WHERE attempt_id=?',
                      (status, json.dumps(data), attempt_id))
            c.commit()

    def read_failure_evidence(self, run_id, attempt_id, wait_ms=0, *, access=None):
        if not all(re.fullmatch(r'[a-f0-9]{32}', value) for value in (run_id, attempt_id)):
            raise make_error('Invalid run or attempt identity', 'INVALID_ID', 422)
        deadline = time.monotonic() + wait_ms / 1000
        while True:
            with self.host.lock, self._connect() as c:
                if access:
                    self.host.sharing.require_task(c, access)
                    self.host.sharing.owner(c, run_id, access.task_id)
                row = c.execute('SELECT r.state, e.status, e.data_json FROM connector_runs r '
                                'LEFT JOIN connector_failure_evidence e ON e.run_id=r.run_id AND e.attempt_id=? '
                                'WHERE r.run_id=?', (attempt_id, run_id)).fetchone()
                if row and row['state'] == 'DELETED':
                    raise make_error('Deleted run', 'RUN_DELETED', 410)
                if not row or not row['status']:
                    raise make_error('No failure evidence for this attempt', 'NOT_FOUND', 404)
                if row['status'] != 'PENDING' or time.monotonic() >= deadline:
                    data = json.loads(row['data_json'])
                    if data['logs'] is None:
                        data['logs'] = failure_evidence.log_tails(self._log_file_path(run_id, attempt_id, 'stdout').parent)
                    if row['status'] == 'INTERRUPTED':
                        for board in data['dmesg'].values():
                            if board['status'] == 'PENDING':
                                board['status'] = 'HOST_RESTARTED'
                        return {**data, 'status': 'PARTIAL'}
                    return {**data, 'status': row['status']}
            time.sleep(0.1)

    def _complete_cancelled(self, run_id: str, reason: str = 'OPERATOR_CANCELLED') -> None:
        ts = now()
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute(
                "UPDATE connector_runs SET state='COMPLETED', outcome='CANCELLED', pause_reason=NULL, "
                'analysis_latched=0, version=version+1, updated_at=?, ended_at=? WHERE run_id=?',
                (ts, ts, run_id),
            )
            c.execute(
                "UPDATE connector_run_steps SET state='CANCELLED' WHERE run_id=? AND state IN ('PENDING','RUNNING')",
                (run_id,),
            )
            c.execute(
                "UPDATE connector_analyses SET status='SUPERSEDED_BY_CANCEL', lease_token=NULL, updated_at=? "
                "WHERE run_id=? AND status IN ('PENDING','ANALYZING','HOLD')",
                (ts, run_id),
            )
            self._append_event(c, run_id, 'RUN_CANCELLED', {'reason': reason})
            c.commit()

    def _complete_paused(self, run_id: str, step_index: int) -> None:
        ts = now()
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute(
                "UPDATE connector_runs SET state='PAUSED', pause_reason='OPERATOR_PAUSE', pause_requested=0, "
                'current_step_index=?, version=version+1, updated_at=? WHERE run_id=?',
                (step_index, ts, run_id),
            )
            self._append_event(c, run_id, 'RUN_PAUSED', {'reason': 'OPERATOR_PAUSE', 'step_index': step_index})
            c.commit()

    def _mark_unknown(
        self,
        run_id: str,
        recovery_reason: str,
        *,
        attempt_id: str | None = None,
        console_evidence: dict | None = None,
    ) -> None:
        ts = now()
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if attempt_id:
                c.execute(
                    "UPDATE connector_run_attempts SET state='UNKNOWN', terminated=0, reason=?, "
                    'console_evidence_json=?, ended_at=COALESCE(ended_at, ?) WHERE attempt_id=?',
                    (recovery_reason, json.dumps(console_evidence) if console_evidence else None, ts, attempt_id),
                )
                c.execute("UPDATE connector_run_steps SET state='UNKNOWN', result_reason=? WHERE run_id=? AND latest_attempt_id=?",
                          (recovery_reason, run_id, attempt_id))
            c.execute(
                "UPDATE connector_runs SET state='UNKNOWN', recovery_reason=?, version=version+1, updated_at=? WHERE run_id=?",
                (recovery_reason, ts, run_id),
            )
            self._append_event(c, run_id, 'RUN_UNKNOWN', {'recovery_reason': recovery_reason})
            c.commit()

    def _close_run_observers(self, run_id: str) -> dict:
        observers = self._run_observers.pop(run_id, [])
        for obs in observers:
            try:
                obs.close()
            except Exception:
                pass
        return self._collect_observer_evidence(observers, fence=True)

    def _collect_observer_evidence(self, observers: list[Any], *, fence: bool = False) -> dict:
        if not observers:
            return {'observers': [], 'unsafe': False, 'panic': False, 'console_failure': False, 'fenced': fence}
        evidence = [obs.fence() if fence else obs.evidence() for obs in observers]
        unsafe = any(
            obs.gaps
            or obs.writer_error
            or obs.evidence_overflow
            or any(
                ev['kind'] == 'panic_signatures' or (ev['kind'] == 'boot_signatures' and not ev['expected'])
                for ev in obs.events
            )
            for obs in observers
        )
        return {
            'observers': evidence,
            'unsafe': unsafe,
            'panic': any(v.get('panic') for v in evidence),
            'console_failure': unsafe,
            'fenced': fence,
        }

    def _execute_flashing_phase(self, run_id: str, run_req: dict, run_dir: Path, attempt_ordinal: int) -> str:
        """Execute FLASHING safely; returns 'OK', 'PAUSED', 'CANCELLED', 'LATCHED', or 'UNKNOWN'."""
        attempt_id = uid()
        ts = now()
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            cur = c.execute(
                'SELECT state, cancel_requested, pause_requested, analysis_latched FROM connector_runs WHERE run_id=?',
                (run_id,),
            ).fetchone()
            if not cur or cur['state'] == 'DELETED':
                c.commit()
                return 'CANCELLED'
            if cur['cancel_requested'] or cur['state'] == 'CANCEL_REQUESTED':
                c.commit()
                if cur['state'] != 'COMPLETED':
                    self._complete_cancelled(run_id, 'OPERATOR_CANCELLED')
                return 'CANCELLED'
            if cur['state'] == 'COMPLETED':
                c.commit()
                return 'CANCELLED'
            if cur['pause_requested'] or cur['state'] in {'PAUSED', 'PAUSE_REQUESTED'}:
                c.commit()
                if cur['state'] != 'PAUSED':
                    self._complete_paused(run_id, 0)
                return 'PAUSED'
            if cur['state'] not in {'QUEUED', 'RUNNING'} or cur['analysis_latched']:
                c.commit()
                return 'LATCHED' if cur['analysis_latched'] else 'CANCELLED'
            res = c.execute(
                "UPDATE connector_runs SET state='FLASHING', version=version+1, updated_at=? "
                "WHERE run_id=? AND state IN ('QUEUED','RUNNING') AND cancel_requested=0 AND pause_requested=0",
                (ts, run_id),
            )
            if res.rowcount != 1:
                c.commit()
                return 'CANCELLED'
            c.execute(
                'INSERT INTO connector_run_attempts(attempt_id, run_id, step_index, phase, ordinal, state, started_at) '
                'VALUES(?,?,?,?,?,?,?)',
                (attempt_id, run_id, None, 'FLASHING', attempt_ordinal, 'RUNNING', ts),
            )
            self._append_event(c, run_id, 'FLASHING_STARTED', {'attempt_id': attempt_id})
            c.commit()

        installer = run_req['installer']
        connection = Connection.model_validate(run_req['connection'])
        snapshot_id = installer['installer_snapshot_id']
        source = self.host.runtime / 'installer-snapshots' / snapshot_id
        images = run_dir / 'images'
        if not images.exists():
            shutil.copytree(source, images)
        manifest = installer_snapshots.load_manifest(images, snapshot_id)
        legacy_manifest = {
            'schema_version': 1,
            'batch': manifest['batch'],
            'files': {n: r['sha256'] for n, r in manifest['files'].items()},
        }
        from types import SimpleNamespace
        profile = self.host.flashing.profile(
            SimpleNamespace(profile=installer['flash_profile'], manifest=legacy_manifest, connection=connection),
            streamed=True,
        )

        observers: list[Any] = []
        boards = [connection.a] + ([connection.b] if connection.b else [])
        if hasattr(self.host, 'console'):
            with self.host.lock:
                self.host.console.suspend([b.board_id for b in boards])
        prev_flash_item = getattr(self.host.flashing.context, 'item', None)
        self.host.flashing.context.item = {
            'id': attempt_id,
            'request': {'connection': run_req['connection']},
            'persist': False,
        }
        try:
            for board in boards:
                cfg = profile['boards'][board.board_id]
                obs_cfg = json.loads(json.dumps(cfg['observer']))
                obs_cfg['redact_values'] = [
                    os.environ[s['send_env']]
                    for s in cfg.get('login_steps', [])
                    if isinstance(s, dict) and s.get('send_env') in os.environ
                ]
                obs_dir = run_dir / ('console-' + board.board_id)
                obs_dir.mkdir(parents=True, exist_ok=True)
                obs = (
                    self.host.multiplexers.observer(obs_dir, board.board_id, obs_cfg)
                    if self.host.multiplexers
                    else ConsoleObserver(obs_dir, obs_cfg)
                )
                obs.board_id = board.board_id
                observers.append(obs)
                obs.start()
            self._run_observers[run_id] = observers

            def _check_safe_boundary(stage: str) -> str | None:
                ev = self._collect_observer_evidence(observers)
                if ev['unsafe']:
                    raise UnknownHardware('Console panic, reboot or evidence gap during flash', 'CONSOLE_UNSAFE')
                p_req, c_req = self._run_flags(run_id)
                if c_req:
                    self._append_log(run_id, attempt_id, 'events', f'Cancelled safely at {stage}\n')
                    return 'CANCELLED'
                if p_req:
                    self._append_log(run_id, attempt_id, 'events', f'Paused safely at {stage}\n')
                    return 'PAUSED'
                return None

            self.host.verify(connection.model_dump())
            for index, board in enumerate(boards):
                cfg = profile['boards'][board.board_id]
                obs = observers[index]

                decision = _check_safe_boundary(f'BEFORE_LKSHELL:{board.board_id}')
                if decision:
                    self._finish_flash_boundary(run_id, attempt_id, decision, observers)
                    return decision

                self.host.flashing.verify_profile_revision(installer['flash_profile'], installer['flash_profile_revision'])
                self._append_log(run_id, attempt_id, 'uart', f'[{board.board_id}] ENTERING_LKSHELL\n')
                obs.boundary('ENTERING_LKSHELL', boot=True, expected_boot=True)
                console = self.host.flashing.io.console(cfg)
                try:
                    for step in cfg.get('login_steps', []):
                        if not isinstance(step, dict) or set(step) - {'wait', 'send', 'send_env'}:
                            raise TestError('Invalid stored console login step', 'FLASH_NOT_CONFIGURED')
                        if step.get('wait'):
                            console.wait(step['wait'], profile.get('console_timeout', 120))
                        if step.get('send_env'):
                            val = os.environ.get(step['send_env'])
                            if val is None:
                                raise TestError('Console credential unavailable', 'FLASH_NOT_CONFIGURED')
                            console.command(val)
                        elif 'send' in step:
                            console.command(step['send'])
                    decision = _check_safe_boundary(f'BEFORE_REBOOT_LKSHELL:{board.board_id}')
                    if decision:
                        self._finish_flash_boundary(run_id, attempt_id, decision, observers)
                        return decision
                    console.command('reboot lkshell')
                    console.wait(cfg['lkshell_prompt'], profile.get('console_timeout', 120))
                    decision = _check_safe_boundary(f'ENTERING_FASTBOOT:{board.board_id}')
                    if decision:
                        self._finish_flash_boundary(run_id, attempt_id, decision, observers)
                        return decision
                    obs.boundary('ENTERING_FASTBOOT')
                    console.command('fast')
                finally:
                    console.close()

                deadline = time.monotonic() + profile.get('fastboot_timeout', 60)
                while True:
                    decision = _check_safe_boundary(f'WAIT_FASTBOOT:{board.board_id}')
                    if decision:
                        self._finish_flash_boundary(run_id, attempt_id, decision, observers)
                        return decision
                    devices = self.host.flashing.io.devices(profile)
                    if devices == [cfg['serial']]:
                        break
                    if devices:
                        raise TestError('Unexpected or multiple fastboot targets', 'BOARD_MISMATCH')
                    if time.monotonic() >= deadline:
                        raise TestError('Fastboot target readiness timed out', 'FASTBOOT_TIMEOUT')
                    time.sleep(0.1)

                decision = _check_safe_boundary(f'BEFORE_FLASH:{board.board_id}')
                if decision:
                    self._finish_flash_boundary(run_id, attempt_id, decision, observers)
                    return decision

                # Critical safety invariant (§4.3): NEVER taskkill/terminate BAT/fastboot during FLASHING!
                self._append_log(run_id, attempt_id, 'installer', f'[{board.board_id}] FLASHING {manifest["batch"]}\n')
                boot_start = obs.boundary('FLASHING', boot=True, expected_boot=True)
                console = self.host.flashing.io.console(cfg)
                try:
                    result = self.host.flashing.io.flash(profile, cfg, images, manifest['batch'])
                    self._append_log(run_id, attempt_id, 'installer', result.get('stdout', '') + '\n' + result.get('stderr', '') + '\n')
                    text = result.get('stdout', '') + '\n' + result.get('stderr', '')
                    markers = profile.get('failure_markers', ['FAILED', 'fastboot: error:'])
                    success = (
                        result.get('terminated') is True
                        and result.get('exit_code') == 0
                        and profile['success_marker'] in text
                        and not any(m.casefold() in text.casefold() for m in markers)
                    )
                    if not success:
                        raise TestError('BAT did not provide verified success', 'FLASH_FAILED')
                    self._append_log(run_id, attempt_id, 'uart', f'[{board.board_id}] WAITING_LOGIN\n')
                    console.wait(cfg['login_prompt'], profile.get('boot_timeout', 180))
                    boot_deadline = time.monotonic() + profile.get('boot_timeout', 180)
                    while True:
                        ev = obs.evidence(boot_start)
                        boots = [e['offset'] for e in ev['events'] if e['kind'] == 'boot_signatures' and e.get('expected')]
                        logins = [e['offset'] for e in ev['events'] if e['kind'] == 'login_markers']
                        if boots and any(login >= min(boots) for login in logins):
                            break
                        if self._collect_observer_evidence(observers)['unsafe']:
                            raise UnknownHardware('Console unsafe during post-flash boot', 'CONSOLE_UNSAFE')
                        if time.monotonic() >= boot_deadline:
                            raise TestError('Fresh observed boot then login prompt not established', 'CONSOLE_TIMEOUT')
                        time.sleep(0.05)
                finally:
                    console.close()
                obs.boundary('TC_READY')

            decision = _check_safe_boundary('AFTER_FLASH_ALL_BOARDS')
            if decision:
                self._finish_flash_boundary(run_id, attempt_id, decision, observers)
                return decision

            ev = self._collect_observer_evidence(observers, fence=False)
            with self.host.lock, self._connect() as c:
                c.execute(
                    "UPDATE connector_run_attempts SET state='PASSED', terminated=1, exit_code=0, console_evidence_json=?, ended_at=? "
                    'WHERE attempt_id=?',
                    (json.dumps(ev), now(), attempt_id),
                )
                self._append_event(c, run_id, 'FLASHING_PASSED', {'attempt_id': attempt_id})
                c.commit()
            return 'OK'
        except UnknownHardware as exc:
            ev = self._close_run_observers(run_id)
            if exc.code == 'HARDWARE_UNKNOWN' or bool(self.host.flashing.supervised):
                self._append_log(run_id, attempt_id, 'events', f'Flashing entered UNKNOWN: {exc.code}\n')
                self._mark_unknown(
                    run_id,
                    exc.code,
                    attempt_id=attempt_id,
                    console_evidence=ev,
                )
                return 'UNKNOWN'
            self._trigger_fail_stop_latch(
                run_id,
                attempt_id=attempt_id,
                phase='FLASHING',
                failed_step_index=None,
                reason=exc.code,
                console_evidence=ev,
            )
            return 'LATCHED'
        except Exception as exc:
            ev = self._close_run_observers(run_id)
            reason = exc.code if isinstance(exc, TestError) else f'FLASH_ERROR:{exc.__class__.__name__}'
            self._append_log(run_id, attempt_id, 'events', f'Flashing failed: {reason}\n')
            self._trigger_fail_stop_latch(
                run_id,
                attempt_id=attempt_id,
                phase='FLASHING',
                failed_step_index=None,
                reason=reason,
                console_evidence=ev,
            )
            return 'LATCHED'
        finally:
            self.host.flashing.context.item = prev_flash_item

    def _finish_flash_boundary(self, run_id: str, attempt_id: str, decision: str, observers: list[Any]) -> None:
        ev = self._close_run_observers(run_id)
        ts = now()
        with self.host.lock, self._connect() as c:
            c.execute(
                'UPDATE connector_run_attempts SET state=?, terminated=1, reason=?, console_evidence_json=?, ended_at=? WHERE attempt_id=?',
                (decision, f'BOUNDARY_{decision}', json.dumps(ev), ts, attempt_id),
            )
            c.commit()
        if decision == 'CANCELLED':
            self._complete_cancelled(run_id, 'CANCELLED_AT_FLASH_BOUNDARY')
        else:
            self._complete_paused(run_id, 0)

    def _reattach_flash_observers(self, run_id: str, run_req: dict, run_dir: Path) -> None:
        installer = run_req.get('installer')
        if not installer:
            return
        images = run_dir / 'images'
        if not images.is_dir():
            return
        connection = Connection.model_validate(run_req['connection'])
        manifest = installer_snapshots.load_manifest(images, installer['installer_snapshot_id'])
        legacy_manifest = {
            'schema_version': 1,
            'batch': manifest['batch'],
            'files': {n: r['sha256'] for n, r in manifest['files'].items()},
        }
        from types import SimpleNamespace
        profile = self.host.flashing.profile(
            SimpleNamespace(profile=installer['flash_profile'], manifest=legacy_manifest, connection=connection),
            streamed=True,
        )
        boards = [connection.a] + ([connection.b] if connection.b else [])
        if hasattr(self.host, 'console'):
            with self.host.lock:
                self.host.console.suspend([b.board_id for b in boards])
        observers: list[Any] = []
        try:
            for board in boards:
                cfg = profile['boards'][board.board_id]
                obs_cfg = json.loads(json.dumps(cfg['observer']))
                obs_cfg['redact_values'] = [
                    os.environ[s['send_env']]
                    for s in cfg.get('login_steps', [])
                    if isinstance(s, dict) and s.get('send_env') in os.environ
                ]
                obs_dir = run_dir / ('console-' + board.board_id)
                obs_dir.mkdir(parents=True, exist_ok=True)
                obs = (
                    self.host.multiplexers.observer(obs_dir, board.board_id, obs_cfg)
                    if self.host.multiplexers
                    else ConsoleObserver(obs_dir, obs_cfg)
                )
                obs.board_id = board.board_id
                observers.append(obs)
                obs.start()
                obs.boundary('TC_READY')
            self._run_observers[run_id] = observers
        except Exception:
            for obs in observers:
                try:
                    obs.close()
                except Exception:
                    pass
            raise

    def _execute_run(self, run_id: str) -> None:
        with self.host.lock, self._connect() as c:
            row = c.execute('SELECT * FROM connector_runs WHERE run_id=?', (run_id,)).fetchone()
            if not row or row['state'] != 'QUEUED' or row['analysis_latched']:
                return
            run_req = json.loads(row['request_json'])
            steps = [
                dict(r)
                for r in c.execute(
                    'SELECT * FROM connector_run_steps WHERE run_id=? ORDER BY step_index ASC',
                    (run_id,),
                ).fetchall()
            ]
            current_step = int(row['current_step_index'])
            max_ord_row = c.execute(
                'SELECT COALESCE(MAX(ordinal), 0) FROM connector_run_attempts WHERE run_id=?', (run_id,)
            ).fetchone()
            ordinal = int(max_ord_row[0])
            flash_passed = (
                c.execute(
                    "SELECT 1 FROM connector_run_attempts WHERE run_id=? AND phase='FLASHING' AND state='PASSED' LIMIT 1",
                    (run_id,),
                ).fetchone()
                is not None
            )

        run_dir = self.host.runtime / 'connector-snapshots' / run_id
        src_dir = run_dir / 'source'
        if not src_dir.is_dir():
            materialize_snapshot(
                self.host.runtime / 'source-snapshots' / run_req['source_snapshot_id'],
                src_dir,
                run_req['source_revision'],
            )

        if run_req['execution_mode'] == 'flash_and_test':
            if not flash_passed:
                ordinal += 1
                flash_outcome = self._execute_flashing_phase(run_id, run_req, run_dir, ordinal)
                if flash_outcome != 'OK':
                    return
            elif run_id not in self._run_observers:
                self._reattach_flash_observers(run_id, run_req, run_dir)

        template = validate_command_template(run_req['command_snapshot']['template'])
        validate_windows_command(template)
        connection = run_req['connection']

        for k in range(current_step, len(steps)):
            p_req, c_req = self._run_flags(run_id)
            if c_req:
                self._close_run_observers(run_id)
                self._complete_cancelled(run_id, 'OPERATOR_CANCELLED')
                return
            if p_req:
                self._close_run_observers(run_id)
                self._complete_paused(run_id, k)
                return

            step = steps[k]
            if step['state'] == 'PASSED':
                continue
            ordinal += 1
            attempt_id = uid()
            ts = now()
            with self.host.lock, self._connect() as c:
                c.execute('BEGIN IMMEDIATE')
                cur = c.execute(
                    'SELECT state, cancel_requested, pause_requested, analysis_latched FROM connector_runs WHERE run_id=?',
                    (run_id,),
                ).fetchone()
                if not cur or cur['state'] in {'COMPLETED', 'DELETED'}:
                    c.commit()
                    self._close_run_observers(run_id)
                    return
                if cur['cancel_requested'] or cur['state'] == 'CANCEL_REQUESTED':
                    c.commit()
                    self._close_run_observers(run_id)
                    self._complete_cancelled(run_id, 'OPERATOR_CANCELLED')
                    return
                if cur['state'] == 'PAUSED':
                    c.commit()
                    self._close_run_observers(run_id)
                    return
                if cur['pause_requested'] or cur['state'] == 'PAUSE_REQUESTED':
                    c.commit()
                    self._close_run_observers(run_id)
                    self._complete_paused(run_id, k)
                    return
                if cur['state'] not in {'QUEUED', 'RUNNING', 'FLASHING'} or cur['analysis_latched']:
                    c.commit()
                    self._close_run_observers(run_id)
                    return
                res = c.execute(
                    "UPDATE connector_runs SET state='RUNNING', current_step_index=?, version=version+1, updated_at=? "
                    "WHERE run_id=? AND state IN ('QUEUED','RUNNING','FLASHING') AND cancel_requested=0 AND pause_requested=0",
                    (k, ts, run_id),
                )
                if res.rowcount != 1:
                    c.commit()
                    self._close_run_observers(run_id)
                    return
                c.execute(
                    "UPDATE connector_run_steps SET state='RUNNING', latest_attempt_id=?, result_reason=NULL WHERE run_id=? AND step_index=?",
                    (attempt_id, run_id, k),
                )
                c.execute(
                    'INSERT INTO connector_run_attempts(attempt_id, run_id, step_index, phase, ordinal, state, started_at) '
                    'VALUES(?,?,?,?,?,?,?)',
                    (attempt_id, run_id, k, 'TC', ordinal, 'RUNNING', ts),
                )
                self._append_event(c, run_id, 'STEP_STARTED', {'step_index': k, 'tc_id': step['tc_id'], 'attempt_id': attempt_id})
                c.commit()

            step_req_meta = next((s for s in run_req['tests'] if s['step_index'] == k), {})
            parser_cfg = step_req_meta.get('parser', {})
            script = source_path(src_dir / step['path'])
            serial = step_req_meta.get('adb_serial')
            if serial:
                argv = []  # ADB transport resolves its own executable from the Host configuration.
            else:
                argv = resolve_argv(template[step['kind'].lower()], step, connection)
                argv[0], argv[1] = self.host.python, str(script)

            step_outcome = self._execute_single_tc(
                run_id=run_id,
                attempt_id=attempt_id,
                step_index=k,
                tc_id=step['tc_id'],
                argv=argv,
                working_dir=src_dir,
                connection=connection,
                timeout_s=step['effective_timeout_s'],
                parser_cfg={} if serial else parser_cfg,
                adb_script=script if serial else None, adb_serial=serial,
            )
            if step_outcome != 'PASS':
                return

        # All steps PASSED -> FINALIZING & fence observers
        with self.host.lock, self._connect() as c:
            c.execute(
                "UPDATE connector_runs SET state='FINALIZING', version=version+1, updated_at=? WHERE run_id=?",
                (now(), run_id),
            )
            c.commit()

        final_ev = self._close_run_observers(run_id)
        if final_ev['unsafe']:
            self._trigger_fail_stop_latch(
                run_id,
                attempt_id=None,
                phase='TC',
                failed_step_index=len(steps) - 1 if steps else None,
                reason='CONSOLE_UNSAFE',
                console_evidence=final_ev,
            )
            return

        ts = now()
        with self.host.lock, self._connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute(
                "UPDATE connector_runs SET state='COMPLETED', outcome='PASSED', pause_requested=0, current_step_index=?, "
                'version=version+1, updated_at=?, ended_at=? WHERE run_id=?',
                (len(steps), ts, ts, run_id),
            )
            self._append_event(c, run_id, 'RUN_PASSED', {'steps': len(steps)})
            c.commit()

    def _wait_for_adb(self, prefix: list[str], deadline: float, run_id: str) -> None:
        """Poll the selected transport and its shell until ready or cancellation."""
        reason = 'ADB_DEVICE_NOT_READY'

        def probe(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [*prefix, *args], capture_output=True, stdin=subprocess.DEVNULL,
                timeout=min(2, max(0.001, deadline - time.monotonic())),
            )

        while time.monotonic() < deadline:
            if self._worker_stop.is_set() or self._run_flags(run_id)[1]:
                return
            try:
                state = probe('get-state')
                # The error may quote the serial, which itself can contain "offline" or "unauthorized".
                status = state.stdout.strip()
                errors = state.stderr.lower().splitlines()
                def reported(label: bytes) -> bool:
                    pattern = rb'^(?:(?:adb|error):\s*)*(?:device\s+)?' + label + rb'(?:[.:\s]|$)'
                    return status == label or any(re.match(pattern, line.strip()) for line in errors)

                if reported(b'unauthorized'):
                    raise TestError('Board requires ADB authorization', 'ADB_UNAUTHORIZED')
                if state.returncode == 0 and state.stdout.strip() == b'device':
                    reason = 'ADB_SHELL_NOT_READY'
                    shell = probe('shell', 'echo', 'BSP_ADB_READY')
                    if shell.returncode == 0 and shell.stdout.strip() == b'BSP_ADB_READY':
                        return
                elif reported(b'offline'):
                    reason = 'ADB_OFFLINE'
                else:
                    reason = 'ADB_DEVICE_NOT_READY'
            except subprocess.TimeoutExpired:
                pass
            self._worker_stop.wait(min(0.5, max(0, deadline - time.monotonic())))
        raise TestError('Target board did not become ready for ADB', reason)

    def _execute_single_tc(
        self,
        *,
        run_id: str,
        attempt_id: str,
        step_index: int,
        tc_id: str,
        argv: list[str],
        working_dir: Path,
        connection: dict,
        timeout_s: int,
        parser_cfg: dict,
        adb_script: Path | None = None,
        adb_serial: str | None = None,
    ) -> str:
        tree = capture = None
        adb = remote = None
        remote_started = False
        remote_finished = False
        start = time.monotonic()
        proxy_owner = 'connector:' + attempt_id
        acquired_proxy = False
        written = {'stdout': 0, 'stderr': 0}

        def _flush_logs(texts: dict[str, str]) -> None:
            for stream in ('stdout', 'stderr'):
                txt = texts.get(stream, '')
                if len(txt) > written[stream]:
                    self._append_log(run_id, attempt_id, stream, txt[written[stream]:])
                    written[stream] = len(txt)

        def adb_boundary(timeout_reason: str) -> str | None:
            if self._worker_stop.is_set() or self._run_flags(run_id)[1]:
                if tree and not tree.stop():
                    self._mark_unknown(run_id, 'ADB_PUSH_STOP_UNCONFIRMED', attempt_id=attempt_id)
                    return 'UNKNOWN'
                self._close_run_observers(run_id)
                with self.host.lock, self._connect() as c:
                    c.execute("UPDATE connector_run_attempts SET state='CANCELLED', terminated=1, ended_at=? WHERE attempt_id=?",
                              (now(), attempt_id))
                    c.commit()
                self._complete_cancelled(run_id, 'CANCELLED_BEFORE_ADB_SHELL')
                return 'CANCELLED'
            if time.monotonic() - start >= timeout_s:
                raise TestError('ADB attempt timed out before TC execution', timeout_reason)
            observers = self._run_observers.get(run_id, [])
            if observers and self._collect_observer_evidence(observers)['unsafe']:
                raise TestError('Unsafe console before ADB execution', 'CONSOLE_UNSAFE')
            if self.host.multiplexers and self.host.multiplexers.failure(connection):
                raise TestError('Serial proxy unavailable before ADB execution', 'SERIAL_PROXY_FAILED')
            return None

        try:
            if adb_script is not None:
                adb, serial = adb_target(self.host, connection['a']['board_id'])
                if serial != adb_serial:
                    raise TestError('ADB serial changed', 'BOARD_MISMATCH')
                prefix = [adb, '-s', serial]
                # The shared ADB server must outlive the attempt's Windows Job Object.
                try:
                    subprocess.run([adb, 'start-server'], check=True, timeout=min(timeout_s, 10),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except (OSError, subprocess.SubprocessError) as exc:
                    raise TestError('Windows ADB server unavailable', 'ADB_SERVER_FAILED') from exc
                self._append_log(run_id, attempt_id, 'stderr', f'Checking ADB device and shell on {serial}\n')
                deadline = min(start + timeout_s, time.monotonic() + ADB_READY_TIMEOUT_S)
                try:
                    self._wait_for_adb(prefix, deadline, run_id)
                except TestError:
                    interrupted = adb_boundary('ADB_READY_TIMEOUT')
                    if interrupted:
                        return interrupted
                    raise
                before_transfer = adb_boundary('ADB_READY_TIMEOUT')
                if before_transfer:
                    return before_transfer
                remote = f'/data/local/tmp/bsp-tc-{attempt_id}{adb_script.suffix}'
                self._append_log(run_id, attempt_id, 'stderr', f'ADB push {tc_id} to {serial}\n')
                tree = ProcessTree([*prefix, 'push', str(adb_script), remote], working_dir,
                                   subprocess.PIPE, subprocess.PIPE)
                push_log = Capture(tree.process.stdout, tree.process.stderr, limit=64 * 1024)
                try:
                    while True:
                        interrupted = adb_boundary('ADB_PUSH_TIMEOUT')
                        if interrupted:
                            return interrupted
                        if tree.stopped():
                            break
                        time.sleep(0.05)
                    if tree.process.returncode != 0:
                        raise TestError(f'ADB push failed ({tree.process.returncode})', 'ADB_PUSH_FAILED')
                finally:
                    push_log.drain()
                    outputs, _ = push_log.snapshot()
                    for stream, text in outputs.items():
                        if text:
                            self._append_log(run_id, attempt_id, stream, text)
                tree.close()
                tree = None
                before_shell = adb_boundary('ADB_PUSH_TIMEOUT')
                if before_shell:
                    return before_shell
                interpreter = 'sh' if adb_script.suffix == '.sh' else 'python3'
                # Only generated paths and a random marker enter the remote shell.
                marker = 'BSP_TC_EXIT_' + secrets.token_hex(16) + '='
                command = f'{interpreter} {remote}; rc=$?; echo; echo {marker}$rc; exit "$rc"'
                tree = ProcessTree([*prefix, 'shell', command], working_dir, subprocess.PIPE, subprocess.PIPE)
                remote_started = True
            elif self.host.multiplexers:
                mapping = self.host.multiplexers.acquire(connection, proxy_owner)
                acquired_proxy = True
                tree = ProcessTree(
                    self.host.multiplexers.command(argv, self.host.runtime),
                    working_dir,
                    subprocess.PIPE,
                    subprocess.PIPE,
                    env=self.host.multiplexers.environment(mapping, self.host.runtime),
                )
            else:
                tree = ProcessTree(argv, working_dir, subprocess.PIPE, subprocess.PIPE)

            with self._active_lock:
                self._active_trees[run_id] = tree

            capture = Capture(tree.process.stdout, tree.process.stderr, limit=4 * 1024 * 1024)
            forced: str | None = None
            forced_reason = ''
            terminated = False

            while True:
                texts, overflow = capture.snapshot()
                _flush_logs(texts)
                _, c_req = self._run_flags(run_id)
                if c_req:
                    forced = 'CANCELLED'
                    forced_reason = 'OPERATOR_CANCELLED'
                elif self._worker_stop.is_set():
                    forced = 'CANCELLED'
                    forced_reason = 'HOST_SHUTTING_DOWN'
                elif overflow:
                    forced = 'ERROR'
                    forced_reason = 'OUTPUT_OVERFLOW'
                elif time.monotonic() - start > timeout_s:
                    forced = 'TIMEOUT'
                    forced_reason = f'TC_TIMEOUT_{timeout_s}S'
                elif self.host.multiplexers and self.host.multiplexers.failure(connection):
                    forced = 'ERROR'
                    forced_reason = 'SERIAL_PROXY_FAILED'
                else:
                    observers = self._run_observers.get(run_id, [])
                    if observers and self._collect_observer_evidence(observers)['unsafe']:
                        forced = 'ERROR'
                        forced_reason = 'CONSOLE_UNSAFE'

                if forced:
                    terminated = tree.stop()
                    break
                if tree.stopped():
                    terminated = True
                    break
                time.sleep(0.05)

            if not capture.drain():
                terminated = False
            texts, overflow = capture.snapshot()
            _flush_logs(texts)
            exit_code = tree.process.poll()

            if remote_started:
                matches = re.findall(r'^' + marker + r'([0-9]+)\r?$', texts['stdout'], re.MULTILINE)
                remote_finished = terminated and len(matches) == 1 and int(matches[0]) == exit_code
                if not remote_finished:
                    evidence = self._close_run_observers(run_id)
                    self._mark_unknown(run_id, forced_reason or 'ADB_REMOTE_EXIT_UNCONFIRMED',
                                       attempt_id=attempt_id, console_evidence=evidence)
                    return 'UNKNOWN'

            if forced == 'CANCELLED':
                self._close_run_observers(run_id)
                with self.host.lock, self._connect() as c:
                    c.execute(
                        "UPDATE connector_run_attempts SET state=?, exit_code=?, terminated=?, reason=?, ended_at=? WHERE attempt_id=?",
                        ('CANCELLED' if terminated else 'UNKNOWN', exit_code, int(terminated), forced_reason, now(), attempt_id),
                    )
                    c.commit()
                if terminated:
                    self._complete_cancelled(run_id, forced_reason)
                    return 'CANCELLED'
                self._mark_unknown(run_id, 'CANCEL_TERMINATION_UNCONFIRMED')
                return 'UNKNOWN'

            if forced in {'ERROR', 'TIMEOUT'} or overflow:
                reason = forced_reason or 'OUTPUT_OVERFLOW'
                ev = self._close_run_observers(run_id)
                with self.host.lock, self._connect() as c:
                    c.execute(
                        'UPDATE connector_run_attempts SET exit_code=?, terminated=? WHERE attempt_id=?',
                        (exit_code, int(terminated), attempt_id),
                    )
                    c.commit()
                self._trigger_fail_stop_latch(
                    run_id,
                    attempt_id=attempt_id,
                    phase='TC',
                    failed_step_index=step_index,
                    reason=reason,
                    console_evidence=ev,
                )
                return 'FAILED'

            verdict, parse_reason, _ = parse_result(
                texts.get('stdout', ''),
                texts.get('stderr', ''),
                exit_code,
                terminated=terminated,
                **parser_cfg,
            )
            if verdict == 'PASS':
                ts = now()
                with self.host.lock, self._connect() as c:
                    c.execute('BEGIN IMMEDIATE')
                    c.execute(
                        "UPDATE connector_run_attempts SET state='PASSED', exit_code=?, terminated=?, reason=?, ended_at=? WHERE attempt_id=?",
                        (exit_code, int(terminated), parse_reason, ts, attempt_id),
                    )
                    c.execute(
                        "UPDATE connector_run_steps SET state='PASSED', result_reason=? WHERE run_id=? AND step_index=?",
                        (parse_reason, run_id, step_index),
                    )
                    c.execute(
                        'UPDATE connector_runs SET current_step_index=?, version=version+1, updated_at=? WHERE run_id=?',
                        (step_index + 1, ts, run_id),
                    )
                    self._append_event(c, run_id, 'STEP_PASSED', {'step_index': step_index, 'tc_id': tc_id, 'attempt_id': attempt_id})
                    c.commit()
                return 'PASS'

            fail_reason = parse_reason or f'TC_{verdict}'
            ev = self._close_run_observers(run_id)
            with self.host.lock, self._connect() as c:
                c.execute(
                    'UPDATE connector_run_attempts SET exit_code=?, terminated=? WHERE attempt_id=?',
                    (exit_code, int(terminated), attempt_id),
                )
                c.commit()
            self._trigger_fail_stop_latch(
                run_id,
                attempt_id=attempt_id,
                phase='TC',
                failed_step_index=step_index,
                reason=fail_reason,
                console_evidence=ev,
            )
            return 'FAILED'
        except Exception as exc:
            stopped = tree.stop() if tree else True
            ev = self._close_run_observers(run_id)
            if not stopped or (remote_started and not remote_finished):
                self._mark_unknown(run_id, f'PROCESS_ERROR:{exc.__class__.__name__}')
                return 'UNKNOWN'
            self._trigger_fail_stop_latch(
                run_id,
                attempt_id=attempt_id,
                phase='TC',
                failed_step_index=step_index,
                reason=exc.code if isinstance(exc, TestError) else f'EXECUTION_ERROR:{exc.__class__.__name__}',
                console_evidence=ev,
            )
            return 'FAILED'
        finally:
            if adb and remote and (not remote_started or remote_finished):
                try:
                    subprocess.run([adb, '-s', adb_serial, 'shell', 'rm', '-f', remote], check=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                except (OSError, subprocess.SubprocessError):
                    self._append_log(run_id, attempt_id, 'stderr', 'ADB temporary script cleanup failed\n')

            with self._active_lock:
                if self._active_trees.get(run_id) is tree:
                    self._active_trees.pop(run_id, None)
            if tree:
                tree.close()
            if acquired_proxy and self.host.multiplexers:
                try:
                    self.host.multiplexers.release(proxy_owner)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Retention Integration
    # ------------------------------------------------------------------
    def protected_snapshot_refs(self, c: sqlite3.Connection) -> tuple[set[str], set[str]]:
        """Return (protected_run_dirs, protected_snapshot_ids) for active/failed/latched/UNKNOWN connector_runs."""
        protected_ids: set[str] = set()
        rows = c.execute(
            'SELECT run_id, state, outcome, analysis_latched, source_snapshot_id, installer_snapshot_id '
            "FROM connector_runs WHERE state!='DELETED'"
        ).fetchall()
        for r in rows:
            keep = (
                r['state'] in ACTIVE_RUN_STATES
                or r['state'] == 'PAUSED'
                or bool(r['analysis_latched'])
                or r['outcome'] not in {'PASSED', 'CANCELLED', 'ABORTED', 'SUPERSEDED_BY_REPREPARE'}
            )
            if keep:
                protected_ids.add(r['run_id'])
                if r['source_snapshot_id']:
                    protected_ids.add(r['source_snapshot_id'])
                if r['installer_snapshot_id']:
                    protected_ids.add(r['installer_snapshot_id'])
        return set(), protected_ids
