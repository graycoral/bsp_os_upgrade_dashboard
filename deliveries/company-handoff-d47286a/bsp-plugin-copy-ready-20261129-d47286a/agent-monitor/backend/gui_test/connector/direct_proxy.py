"""Direct Connector Proxy for Agent Monitor (8766): active HTTP probing, offline cache, and safe control."""
from __future__ import annotations

from contextlib import contextmanager
import json
import re
import threading
import time
from typing import Any
from urllib.parse import urlsplit
import uuid

import httpx

from ..core.connector_diagnostics import diagnose_connector_endpoint, linux_local_diagnostics
from ..core.models import TestError, digest
from ..core.shared_settings_store import SharedSettingsStore
from ..execution.connector_runs import VALID_LOG_STREAMS

_HEX_ID_RE = re.compile(r'^[a-f0-9]{32}$')


def validate_hex_id(value: str, label: str = 'id') -> str:
    if not isinstance(value, str) or not _HEX_ID_RE.fullmatch(value):
        raise TestError(f'Invalid {label}', 'INVALID_ID', 422)
    return value


def validate_log_stream(stream: str) -> str:
    if not isinstance(stream, str) or stream not in VALID_LOG_STREAMS:
        raise TestError(f'Invalid log stream: {stream}', 'INVALID_STREAM', 422)
    return stream


class DirectConnectorProxy:
    """Queries Windows Host (127.0.0.1:<preferred_connector_port>) directly and caches last snapshot."""

    def __init__(self, manager, *, registry=None, client_factory=None, clock=time.time, probe_ttl_s: float = 0.0):
        self.manager = manager
        self.registry = registry or getattr(getattr(manager, 'runner', None), 'registry', None)
        rt = getattr(manager, 'runtime', None) or (self.registry.path.parent if self.registry else None)
        self.shared_store = getattr(manager, 'shared_settings_store', None) or (SharedSettingsStore(rt) if rt else None)
        self._custom_client_factory = client_factory
        self.client_factory = client_factory or (
            lambda: httpx.Client(
                timeout=httpx.Timeout(3.0, connect=1.5, read=3.0),
                trust_env=False,
                follow_redirects=False,
            )
        )
        self._shared_client: httpx.Client | None = None
        self.clock = clock
        self.probe_ttl_s = max(0.0, float(probe_ttl_s))
        self._probe_cache: dict | None = None
        self._probe_cache_at: float = 0.0
        self.peer_instance_id = f'agent-monitor-{uuid.uuid4().hex[:12]}'
        self._lock = threading.RLock()
        self._bg_stop = threading.Event()
        self._bg_thread: threading.Thread | None = None

    @contextmanager
    def _client_ctx(self):
        if self._custom_client_factory is not None:
            with self._custom_client_factory() as client:
                yield client
            return
        with self._lock:
            if self._shared_client is None or self._shared_client.is_closed:
                self._shared_client = self.client_factory()
            client = self._shared_client
        yield client

    def _target_port(self) -> int:
        if self.shared_store:
            return int(self.shared_store.read_preferences().get('preferred_connector_port', 8771))
        return 8771

    def _expected_runner_id(self) -> str | None:
        if self.shared_store:
            return self.shared_store.read_preferences().get('expected_runner_id')
        return None

    def _base_url(self, port: int | None = None) -> str:
        p = int(port if port is not None else self._target_port())
        if not 1 <= p <= 65535:
            raise TestError('Invalid connector port', 'INVALID_PORT', 422)
        return f'http://127.0.0.1:{p}'

    def _request_windows(self, method: str, path: str, *, json_body: Any = None, headers: dict[str, str] | None = None) -> dict:
        if method != 'GET':
            self._probe_cache = None
        base = self._base_url()
        with self._client_ctx() as client:
            try:
                resp = client.request(method, base + path, json=json_body, headers=headers)
            except httpx.HTTPError as exc:
                raise TestError(
                    f'보드 커넥터({base})에 연결할 수 없습니다: {exc.__class__.__name__}',
                    'CONNECTOR_UNREACHABLE',
                    503,
                ) from exc
        if resp.status_code not in {200, 201, 202}:
            try:
                err = resp.json()
            except ValueError:
                err = {}
            exc = TestError(err.get('message') or f'Connector HTTP {resp.status_code}', err.get('code') or 'CONNECTOR_ERROR', resp.status_code)
            if isinstance(err, dict):
                exc.extra = err
            raise exc
        return resp.json()

    def linux_diagnostics(self) -> dict:
        port = self._target_port()
        return linux_local_diagnostics(port)

    def probe(self, *, port: int | None = None, max_age_s: float | None = None) -> dict:
        ttl = self.probe_ttl_s if max_age_s is None else max(0.0, float(max_age_s))
        if ttl > 0.0 and port is None and self._probe_cache is not None:
            if (self.clock() - self._probe_cache_at) <= ttl:
                return self._probe_cache
        target_port = int(port if port is not None else self._target_port())
        expected_id = self._expected_runner_id()
        shared = self.shared_store.read() if self.shared_store else None
        base_url = self._base_url(target_port)

        with self._client_ctx() as client:
            report = diagnose_connector_endpoint(
                target_port,
                expected_runner_id=expected_id,
                shared_revision=shared['revision'] if shared else None,
                shared_settings=shared,
                peer_type='agent_monitor',
                peer_instance_id=self.peer_instance_id,
                peer_version='direct-connector-v1',
                client=client,
            )

            if report.get('connected'):
                ident = report.get('identity') or {}
                runner_id = ident.get('runner_id')
                if self.shared_store and runner_id and not expected_id:
                    self.shared_store.pin_runner_if_unset(runner_id)
                    expected_id = runner_id

                def _get(suffix: str, default: Any = None):
                    try:
                        r = client.get(base_url + suffix)
                        return r.json() if r.status_code == 200 else default
                    except Exception:
                        return default

                inventory = _get('/v1/inventory', {'boards': []})
                diagnostics = report.get('windows') or _get('/v1/diagnostics/connection', {})
                test_status = _get('/v1/test-status', {})
                active_run_resp = _get('/v1/connector-runs/active', {'active': False, 'run': None})
                runs_resp = _get('/v1/connector-runs?limit=10', {'runs': []})
                analyses_resp = _get('/v1/analyses?status=PENDING', {'analyses': []})
                console = _get('/v1/console', {'boards': [], 'errors': [], 'cursor': 0})
                ctrl_settings = _get('/v1/control/settings', {})

                snapshot = {
                    'fresh': True,
                    'live_status': 'ONLINE',
                    'target_port': target_port,
                    'runner_id': runner_id,
                    'expected_runner_id': expected_id,
                    'identity': ident,
                    'overall_connection_state': diagnostics.get('overall_connection_state', report.get('overall_connection_state')),
                    'mutual_diagnostics': report,
                    'diagnostics': diagnostics,
                    'inventory': inventory,
                    'test_status': test_status,
                    'active_run': active_run_resp.get('run'),
                    'runs': runs_resp.get('runs', []),
                    'pending_analyses': analyses_resp.get('analyses', []),
                    'console': console,
                    'connector_settings': ctrl_settings,
                    'checked_at': self.clock(),
                }
                if self.registry and hasattr(self.registry, 'save_direct_cache'):
                    self.registry.save_direct_cache(snapshot)
                self._probe_cache = snapshot
                self._probe_cache_at = float(snapshot['checked_at'])
                return snapshot

        cached = self.registry.read_direct_cache() if (self.registry and hasattr(self.registry, 'read_direct_cache')) else None
        if cached:
            data = dict(cached.get('data') or {})
            data.update(
                fresh=False,
                live_status='OFFLINE_CACHED',
                target_port=target_port,
                expected_runner_id=expected_id,
                overall_connection_state=report.get('overall_connection_state', 'DISCONNECTED'),
                mutual_diagnostics=report,
                cached_at=cached.get('updated_at'),
                checked_at=self.clock(),
            )
            return data

        return {
            'fresh': False,
            'live_status': 'OFFLINE_EMPTY',
            'target_port': target_port,
            'runner_id': None,
            'expected_runner_id': expected_id,
            'overall_connection_state': report.get('overall_connection_state', 'DISCONNECTED'),
            'mutual_diagnostics': report,
            'diagnostics': report.get('windows'),
            'inventory': {'boards': []},
            'test_status': {},
            'active_run': None,
            'runs': [],
            'pending_analyses': [],
            'console': {'boards': [], 'errors': []},
            'connector_settings': {},
            'cached_at': None,
            'checked_at': self.clock(),
        }

    # ------------------------------------------------------------------
    # Safe Controls & Settings Proxy
    # ------------------------------------------------------------------
    def verify_connection(self, body: dict | None = None) -> dict:
        try:
            win = self._request_windows('POST', '/v1/control/verify-connection', json_body=body or {'wait': True})
            live = self.probe()
            return {'windows_verify': win, 'status': live}
        except TestError:
            live = self.probe()
            return {'windows_verify': None, 'status': live}

    def reconnect_ssh(self) -> dict:
        return self._request_windows('POST', '/v1/control/reconnect-ssh')

    def open_putty(self, board_id: str | None = None) -> dict:
        return self._request_windows('POST', '/v1/control/putty', json_body={'board_id': board_id} if board_id else {})

    def restart(self) -> dict:
        return self._request_windows('POST', '/v1/control/restart')

    def get_settings(self) -> dict:
        live = self.probe()
        shared = self.shared_store.read() if self.shared_store else {}
        prefs = self.shared_store.read_preferences() if self.shared_store else {}
        return {
            'fresh': live['fresh'],
            'live_status': live['live_status'],
            'connector_settings': live.get('connector_settings'),
            'shared_settings': shared,
            'preferences': prefs,
        }

    def update_settings(self, body: dict) -> dict:
        expected_rev = body.get('expected_revision')
        patch = body.get('patch')
        if not isinstance(patch, dict):
            raise TestError('patch dictionary required', 'INVALID_SETTINGS', 422)
        base_rev = None
        if self.shared_store:
            t_doc = {k: v for k, v in self.shared_store.read_timeouts().items() if k != 'revision'}
            s_doc = {k: v for k, v in self.shared_store.read_storage_policy().items() if k != 'revision'}
            base_rev = digest({'timeouts': t_doc, 'storage_policy': s_doc})
        return self._request_windows(
            'PUT',
            '/v1/control/settings',
            json_body={
                'expected_revision': expected_rev,
                'expected_runner_id': self._expected_runner_id(),
                'source': 'linux',
                'base_linux_revision': base_rev,
                'patch': patch,
            },
        )

    def update_preferences(self, body: dict) -> dict:
        if not self.shared_store:
            raise TestError('Shared settings store unavailable', 'STORE_UNAVAILABLE', 500)
        return self.shared_store.save_preferences(body, expected_revision=body.get('expected_revision'))

    def rebind(self, body: dict | None = None) -> dict:
        if not self.shared_store:
            raise TestError('Shared settings store unavailable', 'STORE_UNAVAILABLE', 500)
        data = dict(body or {})
        runner_id = data.get('runner_id')
        port = data.get('preferred_connector_port')
        if runner_id is None and port is not None:
            prefs = self.shared_store.save_preferences({'preferred_connector_port': port})
        elif runner_id is None:
            ident = self._request_windows('GET', '/v1/identity')
            runner_id = ident['runner_id']
            prefs = self.shared_store.rebind_runner(runner_id)
        else:
            prefs = self.shared_store.rebind_runner(runner_id)
            if port is not None:
                prefs = self.shared_store.save_preferences({'preferred_connector_port': port}, expected_revision=prefs['revision'])
        return {'rebound': True, 'preferences': prefs}

    def list_runs(self, limit: int = 20) -> dict:
        try:
            return self._request_windows('GET', f'/v1/connector-runs?limit={int(limit)}')
        except TestError:
            cached = self.registry.read_direct_cache() if (self.registry and hasattr(self.registry, 'read_direct_cache')) else None
            runs = (cached or {}).get('data', {}).get('runs', [])
            return {'runs': runs, 'fresh': False, 'live_status': 'OFFLINE_CACHED' if cached else 'OFFLINE_EMPTY'}

    def get_run(self, run_id: str) -> dict:
        run_id = validate_hex_id(run_id, 'run_id')
        return self._request_windows('GET', f'/v1/connector-runs/{run_id}')

    def pause_run(self, run_id: str) -> dict:
        run_id = validate_hex_id(run_id, 'run_id')
        return self._request_windows('POST', f'/v1/connector-runs/{run_id}/pause')

    def resume_run(self, run_id: str) -> dict:
        run_id = validate_hex_id(run_id, 'run_id')
        # Guard locally as well as relying on Host 409 ANALYSIS_LATCH_ACTIVE.
        run = self.get_run(run_id)
        if run.get('analysis_latched'):
            raise TestError(
                '실패 분석 래치가 활성화되어 있어 수동 재개할 수 없습니다. 분석 결과를 확인하거나 취소하세요.',
                'ANALYSIS_LATCH_ACTIVE',
                409,
            )
        return self._request_windows('POST', f'/v1/connector-runs/{run_id}/resume')

    def cancel_run(self, run_id: str) -> dict:
        run_id = validate_hex_id(run_id, 'run_id')
        return self._request_windows('POST', f'/v1/connector-runs/{run_id}/cancel')

    def reconcile_run(self, run_id: str, body: dict) -> dict:
        run_id = validate_hex_id(run_id, 'run_id')
        return self._request_windows('POST', f'/v1/connector-runs/{run_id}/reconcile', json_body=body)

    def rerun_run(self, run_id: str, idempotency_key: str | None = None) -> dict:
        run_id = validate_hex_id(run_id, 'run_id')
        headers = {'Idempotency-Key': idempotency_key} if idempotency_key else None
        return self._request_windows('POST', f'/v1/connector-runs/{run_id}/rerun', headers=headers)

    def read_logs(self, run_id: str, attempt_id: str, *, stream: str = 'stdout', offset: int = 0, limit: int = 65536) -> dict:
        run_id = validate_hex_id(run_id, 'run_id')
        attempt_id = validate_hex_id(attempt_id, 'attempt_id')
        stream = validate_log_stream(stream)
        return self._request_windows(
            'GET',
            f'/v1/connector-runs/{run_id}/attempts/{attempt_id}/logs?stream={stream}&offset={int(offset)}&limit={int(limit)}',
        )

    # ------------------------------------------------------------------
    # Background 10s Probe (keeps OFFLINE_CACHED fresh when Monitor is open)
    # ------------------------------------------------------------------
    def start_background_probe(self, interval: float = 10.0) -> None:
        with self._lock:
            if self._bg_thread and self._bg_thread.is_alive():
                return
            self._bg_stop.clear()

            def _loop():
                while not self._bg_stop.is_set():
                    try:
                        self.probe()
                    except Exception:
                        pass
                    self._bg_stop.wait(interval)

            self._bg_thread = threading.Thread(target=_loop, name='direct-connector-proxy-probe', daemon=True)
            self._bg_thread.start()

    def stop_background_probe(self) -> None:
        self._bg_stop.set()
        if self._bg_thread and self._bg_thread.is_alive():
            self._bg_thread.join(timeout=2.0)
