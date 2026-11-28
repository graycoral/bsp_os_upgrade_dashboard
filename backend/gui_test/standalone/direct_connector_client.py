"""Direct Board Connector client, TC projection, snapshot sync, and fail-stop analysis worker.

Communicates directly with Windows Host at http://127.0.0.1:<connector_port> and
reads/writes Linux <runtime>/shared-settings.db without requiring Agent Monitor (8766).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit
import uuid
import zipfile

import httpx

from ..adapters.runner import default_command_template
from ..core.connector_bootstrap import build_bootstrap_v2
from ..core.connector_diagnostics import diagnose_connector_endpoint
from ..core.discovery import discover_contents, script_paths
from ..core.failure_analysis import AnalysisResult, normalized_cause
from ..core.integration import _matches as _glob_matches, validate_patterns
from ..core.models import TestError, digest
from ..core.shared_settings_store import SharedSettingsStore, resolve_runtime_dir
from ..execution import installer_snapshots, source_snapshots
from ..execution.connector_runs import (
    CONNECTOR_DEFAULT_TC_TIMEOUT_SECONDS,
    ConnectorRunRequest,
    build_tc_projection,
    resolve_step_timeout,
)
from ..execution.source import read_source
from .analysis_runtime import bounded_evidence, diagnose as builtin_diagnose, invoke as runtime_invoke, sanitized, settings as load_analysis_settings
from .connector_observation import connection_status
from .plugin_sharing import (
    SHARING_CAPABILITY, SharingError, private_json, public_task, state_lock, valid_id, valid_secret,
    write_private_json,
)


SHARED_ERRORS = {
    'NOT_FOUND': 'No matching record in the selected task.',
    'TASK_NOT_FOUND': 'The selected task is not registered on the Windows Host.',
    'SHARING_TASK_CONFLICT': 'The task is already registered with different details.',
    'SHARING_AUTH_REQUIRED': 'The Windows Host did not accept the account or task credential.',
    'SHARING_FORBIDDEN': 'This account or task cannot use the requested shared Connector operation.',
    'SHARING_UNAVAILABLE': 'The Windows Host sharing configuration is unavailable.',
    'TASK_REQUIRED': 'The operation requires a registered task.',
    'RUNNER_CHANGED': 'The Windows Connector identity changed.',
    'OWNERSHIP_CHANGED': 'Run ownership changed. Read its current status before retrying.',
    'RUN_OWNERSHIP_CHANGED': 'Run ownership changed. Read its current status before retrying.',
    'RUN_DELETED': 'The selected Run has been permanently deleted.',
    'COMMAND_NOT_ALLOWED': 'The command profile must invoke Python with the TC path.',
    'RESERVATION_CONFLICT': 'The Windows Host has an active execution or reservation.',
    'PREVIEW_CHANGED': 'The recorded TC plan changed. Prepare the Run again.',
    'BOARD_MISMATCH': 'The Windows board mapping changed or is unavailable.',
    'RUN_EPOCH_CHANGED': 'Run ownership changed. Read its current status before retrying.',
    'ACTIVE_RUN_EXISTS': 'The Windows Host is busy.',
    'CONNECTOR_BUSY': 'The Windows Host is busy.',
    'MONITOR_UNAVAILABLE': 'The task Monitor destination is unavailable.',
    'MONITOR_NOT_APPROVED': 'The Windows operator must approve the task Monitor destination.',
    'MONITOR_NOT_CONFIGURED': 'The Windows operator must configure the task Monitor destination.',
    'MONITOR_CREDENTIAL_UNAVAILABLE': 'The approved Monitor key is unavailable.',
    'ANALYSIS_LATCH_ACTIVE': 'The Run is paused for failure analysis.',
    'IDEMPOTENCY_CONFLICT': 'The saved Run request conflicts with the Host receipt.',
}


def _local_loopback_url(port: int) -> str:
    if type(port) is not int or not 1 <= port <= 65535:
        raise TestError(f'Invalid connector port: {port}', 'INVALID_PORT', 422)
    return f'http://127.0.0.1:{port}'


def _make_peer_instance_id(state_dir: Path | None) -> str:
    if state_dir is None:
        return f'plugin-{uuid.uuid4().hex[:16]}'
    state_dir.mkdir(parents=True, exist_ok=True)
    id_file = state_dir / 'peer-instance-id.txt'
    if id_file.is_file():
        val = id_file.read_text(encoding='utf-8').strip()
        if val:
            return val
    val = f'plugin-{uuid.uuid4().hex[:16]}'
    id_file.write_text(val, encoding='utf-8')
    return val


class DirectConnectorClient:
    """Direct HTTP client for 127.0.0.1:<connector_port> + <runtime>/shared-settings.db."""

    def __init__(
        self,
        *,
        home: Path | None = None,
        runtime_dir: Path | None = None,
        connector_port: int | None = None,
        state_dir: Path | None = None,
        project: str | None = None,
        sharing_state=None,
        task_id: str | None = None,
        client: httpx.Client | None = None,
        peer_type: str = 'plugin',
        peer_version: str = 'direct-connector-v1',
        chunk_bytes: int = 16 * 1024 * 1024,
        sshd_config: Path | None = None,
        proc_root: Path | None = None,
        proc_tcp: Path | None = None,
        proc_tcp6: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.home = Path(home).expanduser().resolve() if home else None
        self.runtime_dir = resolve_runtime_dir(home=self.home, runtime=runtime_dir)
        self.task = None
        self.sharing_state = sharing_state
        self.credential, self.shared_transport = sharing_state.configuration() if sharing_state is not None else (None, None)
        self.shared = self.credential is not None
        self.state_dir = Path(state_dir) if state_dir else (self.runtime_dir / 'plugin-direct-state')
        self.project = project
        if not self.shared or task_id is not None:
            if self.shared:
                self._bind_task(sharing_state.task(task_id), project)
            else:
                self.store = SharedSettingsStore(self.runtime_dir)
        self.port = int(connector_port if connector_port is not None else (
            8771 if self.shared else self.store.read_preferences().get('preferred_connector_port', 8771)))
        self.url = _local_loopback_url(self.port)
        self.peer_type = peer_type
        self.peer_version = peer_version
        self.peer_instance_id = (self.task['task_id'] if self.task else None) if self.shared else _make_peer_instance_id(self.state_dir)
        self.chunk_bytes = max(4096, int(chunk_bytes))
        self.sshd_config = sshd_config
        self.proc_root = proc_root
        self.proc_tcp = proc_tcp
        self.proc_tcp6 = proc_tcp6
        self.clock = clock
        self.sleep = sleep
        self._owns_client = client is None
        self._client = client or self._new_transport_client()

    def _new_transport_client(self):
        options = {}
        if self.shared_transport and self.shared_transport['kind'] == 'unix':
            from ..core.shared_transport import shared_uds_transport

            try:
                options['transport'] = shared_uds_transport(self.shared_transport['socket'], self.shared_transport['owner_uid'])
            except (OSError, ValueError):
                raise SharingError('The approved shared Connector socket is unavailable or unsafe.', 'SHARED_TRANSPORT_REQUIRED') from None
        return httpx.Client(timeout=httpx.Timeout(30.0, connect=2.0), trust_env=False, follow_redirects=False, **options)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _bind_task(self, task, project=None):
        if project is not None and project != task['project']:
            raise SharingError('Use the project fixed when this task was created.', 'TASK_CONFLICT')
        self.task = task
        self.project = task['project']
        self.peer_instance_id = task['task_id']
        self.state_dir = self.sharing_state.task_directory(task['task_id'])
        self.store = SharedSettingsStore(self.state_dir)

    def require_task(self):
        if self.task is None:
            raise SharingError('Pass the current window task ID with --task or BSP_PLUGIN_TASK_ID.', 'TASK_REQUIRED')
        return self.task

    def register_task(self, task_id, *, project=None, monitor_id=None):
        if self.sharing_state is None:
            raise SharingError('Import the Windows Host credential before opening a task.', 'SHARING_CREDENTIAL_REQUIRED')
        task = self.sharing_state.task(task_id) if monitor_id is None else self.sharing_state.create_task(task_id, project, monitor_id)
        self._bind_task(task)
        receipt = self._request('PUT', f"/v1/sharing/tasks/{task['task_id']}", json_body={
            'project': task['project'], 'monitor_id': task['monitor_id'],
        })
        if any(receipt.get(key) != value for key, value in public_task(task).items()):
            raise TestError('Host returned another shared task.', 'TASK_MISMATCH', 409)
        return {'state': 'OPEN', **public_task(task)}

    def open_task_monitor(self, port, *, browser=None):
        task = self.require_task()
        if type(port) is not int or not 1 <= port <= 65535 or port == self.port:
            raise TestError('Set the approved Agent Monitor loopback port or run monitor ensure.', 'MONITOR_UNAVAILABLE', 503)
        base = _local_loopback_url(port)
        challenge = secrets.token_hex(32)
        try:
            request_headers = {'X-Bsp-Monitor-Challenge': challenge}
            if self.shared_transport['kind'] == 'unix':
                with httpx.Client(trust_env=False, timeout=2.0) as monitor:
                    response = monitor.get(base + '/api/v1/health', headers=request_headers)
            else:
                response = self._client.get(base + '/api/v1/health', follow_redirects=False, headers=request_headers)
            health = response.json() if response.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            health = {}
        if (not isinstance(health, dict) or health.get('mode') != 'shared-task-monitor'
                or health.get('monitor_id') != task['monitor_id']):
            raise TestError('The selected task Monitor is offline or its identity differs.', 'MONITOR_UNAVAILABLE', 503)
        proof = health.get('monitor_proof')
        if not isinstance(proof, str) or not re.fullmatch(r'[0-9a-f]{64}', proof):
            raise TestError('The selected task Monitor has no valid identity proof.', 'MONITOR_UNAVAILABLE', 503)
        route = f"/v1/sharing/tasks/{task['task_id']}"
        verified = self._request('POST', route + '/monitor-proof', json_body={
            'challenge': challenge, 'proof': proof,
        })
        if verified.get('verified') is not True:
            raise TestError('The Windows Host did not approve this task Monitor endpoint.', 'MONITOR_MISMATCH', 409)
        receipt = self._request('POST', route + '/view-tickets')
        secret = receipt.get('ticket')
        expires_at = receipt.get('expires_at')
        if (receipt.get('task_id') != task['task_id'] or receipt.get('monitor_id') != task['monitor_id']
                or receipt.get('monitor_port') != port or not valid_secret(secret)
                or type(expires_at) not in {float, int} or not 0 < expires_at - time.time() <= 180):
            raise TestError('The Windows Host did not approve this task Monitor endpoint.', 'MONITOR_MISMATCH', 409)
        url = base + '/plugin-task/?' + urlencode({'task': task['task_id']})
        self._launch_private_browser(url + '#ticket=' + secret, expires_at, browser or webbrowser.open_new_tab)
        return {'state': 'OPENED', **public_task(task), 'url': url}

    def _launch_private_browser(self, target, expires_at, browser):
        # Browser launchers may copy their command line to system logs. Pass a
        # private file URI, never the ticket itself, and remove the file at expiry.
        fd, name = tempfile.mkstemp(suffix='.html', prefix='.monitor-', dir=self.state_dir)
        launch_path = Path(name)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write('<!doctype html><meta name="referrer" content="no-referrer">'
                             '<script>location.replace(' + json.dumps(target) + ')</script>')
            owner = subprocess.Popen([sys.executable, '-I', '-B', '-c',
                                      'from pathlib import Path; import sys,time; '
                                      'time.sleep(max(0,float(sys.argv[2])-time.time())); Path(sys.argv[1]).unlink(missing_ok=True)',
                                      str(launch_path), str(expires_at)],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
            if not browser(launch_path.as_uri()):
                raise RuntimeError('No browser accepted the task destination')
            owner.poll()
        except (OSError, RuntimeError, webbrowser.Error):
            launch_path.unlink(missing_ok=True)
            raise TestError('A local browser could not open the selected task Monitor.', 'BROWSER_UNAVAILABLE', 503) from None

    def _shared_identity(self):
        if self.shared_transport['kind'] == 'unix':
            from ..core.shared_transport import validate_shared_socket

            try:
                validate_shared_socket(self.shared_transport['socket'], self.shared_transport['owner_uid'])
            except ValueError:
                raise TestError('The approved shared Connector socket is unavailable or unsafe.', 'SHARED_TRANSPORT_REQUIRED', 503) from None
        identity = self._request('GET', '/v1/identity')
        if (identity.get('service') != 'bsp-board-connector'
                or identity.get('runner_id') != self.credential['runner_id']):
            raise TestError('Connector identity differs from the imported Windows Host credential.', 'RUNNER_CHANGED', 409)
        if identity.get('sharing_mode') != 'shared' or SHARING_CAPABILITY not in identity.get('capabilities', []):
            raise TestError('The Windows Host must enable shared plugin ownership.', 'CAPABILITY_REQUIRED', 409)
        return identity

    def _request(self, method: str, path: str, *, json_body: Any = None, content: bytes | None = None, headers: dict[str, str] | None = None) -> dict:
        hdrs = dict(headers or {})
        if self.shared and path != '/v1/identity':
            self._shared_identity()  # Confirm the provisioned Host before sending credentials.
            hdrs['Authorization'] = 'Bearer ' + self.credential['token']
            if self.task:
                hdrs.update({'X-Bsp-Task-ID': self.task['task_id'], 'X-Bsp-Task-Key': self.task['task_key']})
        request_options = {'follow_redirects': False} if self.shared else {}
        try:
            resp = self._client.request(method, self.url + path, headers=hdrs, json=json_body, content=content, **request_options)
        except httpx.HTTPError as exc:
            raise TestError(
                f'보드 커넥터(127.0.0.1:{self.port})에 연결할 수 없습니다: {exc.__class__.__name__}',
                'CONNECTOR_UNREACHABLE',
                503,
            ) from exc
        if resp.status_code not in {200, 201, 202}:
            try:
                err = resp.json()
            except ValueError:
                err = {}
            if self.shared:
                reported_code = err.get('code') if isinstance(err, dict) else None
                code = reported_code if isinstance(reported_code, str) and reported_code in SHARED_ERRORS else 'CONNECTOR_ERROR'
                message = SHARED_ERRORS.get(code, f'Shared Connector HTTP {resp.status_code}.')
                raise TestError(message, code, resp.status_code)
            exc = TestError(err.get('message') or f'Connector HTTP {resp.status_code}', err.get('code') or 'CONNECTOR_ERROR', resp.status_code)
            if isinstance(err, dict):
                exc.extra = err
            raise exc
        if self.shared:
            try:
                value = resp.json()
            except ValueError:
                value = None
            if not isinstance(value, dict):
                raise TestError('Invalid shared Connector response.', 'CONNECTOR_ERROR', 502)
            return value
        return resp.json()

    # ------------------------------------------------------------------
    # Diagnostics, Peer Hello & Two-Way Settings Sync
    # ------------------------------------------------------------------
    def diagnose(self, *, reconcile_sync: bool = True, notify_peer: bool = True) -> dict:
        if self.shared:
            return self._diagnose_shared(notify_peer=notify_peer)
        prefs = self.store.read_preferences()
        expected_id = prefs.get('expected_runner_id')
        shared = self.store.read()
        probe_kwargs: dict[str, Any] = {
            'expected_runner_id': expected_id,
            'shared_revision': shared['revision'],
            'shared_settings': shared,
            'notify_peer': notify_peer,
            'peer_type': self.peer_type,
            'peer_instance_id': self.peer_instance_id,
            'peer_version': self.peer_version,
            'client': self._client,
        }
        if self.sshd_config is not None:
            probe_kwargs['sshd_config_path'] = self.sshd_config
        if self.proc_root is not None:
            probe_kwargs['proc_root'] = self.proc_root
        elif self.proc_tcp is not None:
            probe_kwargs['proc_root'] = self.proc_tcp.parent.parent

        report = diagnose_connector_endpoint(self.port, **probe_kwargs)
        ident = report.get('identity') or {}
        runner_id = ident.get('runner_id')
        connected = bool(report.get('connected'))
        sync_result = None
        if connected:
            if runner_id and not expected_id:
                self.store.pin_runner_if_unset(runner_id)
                expected_id = runner_id
            if reconcile_sync and report.get('windows'):
                sync_result = self.reconcile_offline_settings_sync(report['windows'].get('settings_sync_state'))

        linux_diag = dict(report.get('linux') or {})
        linux_diag['reachable'] = connected
        linux_diag['code'] = report.get('code')
        linux_diag['summary'] = report.get('summary')
        return {
            'port': self.port,
            'expected_runner_id': expected_id,
            'runner_id': runner_id,
            'reachable': connected,
            'code': report.get('code'),
            'report': report,
            'linux_diagnostics': linux_diag,
            'windows_diagnostics': report.get('windows'),
            'peer_hello': report.get('peer_hello'),
            'settings_sync': sync_result,
        }

    def _scoped_connection(self):
        value = self._request('GET', '/v1/diagnostics/connection')
        public_fields = ('runner_id', 'overall_connection_state', 'host_busy', 'occupied_project',
                         'pending_analyses', 'pending_analyses_count')
        return {key: value[key] for key in public_fields if key in value}

    def _diagnose_shared(self, *, notify_peer):
        runner_id = None
        try:
            runner_id = self._shared_identity()['runner_id']
            status = self._scoped_connection()
            if notify_peer:
                self._request('POST', '/v1/peer/hello', json_body={
                    'peer_type': self.peer_type, 'peer_instance_id': self.peer_instance_id or 'account-watch',
                    'peer_version': self.peer_version, 'target_port': self.port,
                    'expected_runner_id': runner_id, 'client_status': 'OK',
                })
            code, summary = 'CONNECTED', 'Shared Connector is connected.'
        except TestError as exc:
            code, summary, status = exc.code, exc.message, {}
        connected = code == 'CONNECTED'
        linux = {'reachable': connected, 'code': code, 'summary': summary}
        return {'port': self.port, 'expected_runner_id': self.credential['runner_id'],
                'runner_id': runner_id, 'reachable': connected, 'code': code,
                'report': {'connected': connected, 'code': code, 'summary': summary},
                'linux_diagnostics': linux, 'windows_diagnostics': status or None}

    def require_connected(self) -> dict:
        diag = self.diagnose()
        rep = diag['report']
        if not rep.get('connected'):
            code = rep.get('code') or 'CONNECTOR_UNREACHABLE'
            status = 409 if code == 'RUNNER_CHANGED' else 503
            raise TestError(rep.get('summary') or f'Connector 127.0.0.1:{self.port} is not connected', code, status)
        if (diag.get('settings_sync') or {}).get('status') == 'CONFLICT':
            raise TestError(
                '오프라인 중 Linux와 Windows 양쪽에서 공통 타임아웃/보관 설정이 수정되었습니다. 기준본을 선택하세요.',
                'SETTINGS_SYNC_CONFLICT',
                409,
            )
        return diag

    def watch_connection(
        self,
        *,
        interval: float = 3.0,
        on_change=None,
        stop_event=None,
        max_iterations: int | None = None,
        machine: bool = False,
        read_only: bool = False,
    ) -> dict:
        """Poll connector reachability and emit state transitions without cancelling runs on exit."""
        prev_key = None
        last_event: dict = {'event': 'DISCONNECTED', 'connected': False, 'runner_id': None}
        iteration = 0
        try:
            while max_iterations is None or iteration < max_iterations:
                iteration += 1
                if read_only:
                    diag = self.diagnose(reconcile_sync=False, notify_peer=False)
                else:
                    diag = self.diagnose()
                reachable = bool(diag.get('linux_diagnostics', {}).get('reachable'))
                runner_id = diag.get('runner_id')
                code = diag.get('code')
                inv = None
                if reachable and not self.shared:
                    try:
                        inv = self.inventory()
                        runner_id = inv.get('runner_id')
                        diag['inventory'] = inv
                    except (TestError, OSError) as exc:
                        reachable = False
                        inv = None
                        code = getattr(exc, 'code', 'CONNECTOR_UNREACHABLE')
                switched = bool(prev_key and prev_key[0] and reachable and prev_key[1] != runner_id)
                if switched:
                    code = 'RUNNER_CHANGED'
                cur_key = (reachable, runner_id, code if machine else None)
                if prev_key is None or cur_key != prev_key:
                    if reachable:
                        event_name = 'RUNNER_CHANGED' if switched else 'CONNECTED'
                    elif code == 'RUNNER_CHANGED':
                        event_name = 'RUNNER_CHANGED'
                    else:
                        event_name = 'DISCONNECTED'
                    last_event = {
                        'event': event_name,
                        'connected': reachable,
                        'runner_id': runner_id,
                        'diagnostics': diag,
                        'inventory': inv,
                    }
                    if machine:
                        last_event = connection_status({'reachable': reachable, 'runner_id': runner_id, 'code': code})
                    if on_change is not None:
                        on_change(last_event)
                    prev_key = cur_key
                if stop_event is not None and stop_event.is_set():
                    break
                if max_iterations is not None and iteration >= max_iterations:
                    break
                if stop_event is not None:
                    if stop_event.wait(max(0.05, float(interval))):
                        break
                else:
                    time.sleep(max(0.05, float(interval)))
        except KeyboardInterrupt:
            if machine:
                raise
        return last_event

    def reconcile_offline_settings_sync(self, sync_state: dict | None) -> dict:
        if not isinstance(sync_state, dict) or not sync_state.get('dirty_on_windows'):
            return {'status': 'IN_SYNC'}
        win_runner = sync_state.get('runner_id')
        prefs = self.store.read_preferences()
        expected = prefs.get('expected_runner_id')
        if expected and win_runner and win_runner != expected:
            return {'status': 'SKIPPED_RUNNER_MISMATCH', 'expected_runner_id': expected, 'actual_runner_id': win_runner}

        cur_timeouts = self.store.read_timeouts()
        cur_storage = self.store.read_storage_policy()
        cur_t_val = {k: v for k, v in cur_timeouts.items() if k != 'revision'}
        cur_s_val = {k: v for k, v in cur_storage.items() if k != 'revision'}
        cur_rev = digest({'timeouts': cur_t_val, 'storage_policy': cur_s_val})
        base_rev = sync_state.get('base_linux_revision')
        patch = sync_state.get('patch') or {}

        if base_rev is not None and base_rev != cur_rev:
            return {
                'status': 'CONFLICT',
                'code': 'SETTINGS_SYNC_CONFLICT',
                'base_linux_revision': base_rev,
                'current_linux_revision': cur_rev,
                'windows_patch': patch,
                'windows_revision': sync_state.get('windows_revision'),
            }

        if 'timeouts' in patch:
            t = patch['timeouts']
            self.store.save_timeouts({
                'expected_revision': cur_timeouts['revision'],
                'default_seconds': t.get('default_seconds', 600),
                'overrides': t.get('overrides', {}),
            })
        if 'storage_policy' in patch:
            self.store.save_storage_policy(dict(patch['storage_policy'], expected_revision=cur_storage['revision']))

        new_timeouts = self.store.read_timeouts()
        new_storage = self.store.read_storage_policy()
        new_linux_rev = digest({
            'timeouts': {k: v for k, v in new_timeouts.items() if k != 'revision'},
            'storage_policy': {k: v for k, v in new_storage.items() if k != 'revision'},
        })
        ack = self._request(
            'POST',
            '/v1/settings/ack-sync',
            json_body={
                'expected_runner_id': win_runner,
                'expected_windows_revision': sync_state.get('windows_revision'),
                'base_linux_revision': new_linux_rev,
                'resolved_by': self.peer_type,
            },
        )
        return {'status': 'PULLED_FROM_WINDOWS', 'new_linux_revision': new_linux_rev, 'ack': ack}

    def rebind_runner(self, runner_id: str | None = None, *, port: int | None = None) -> dict:
        if runner_id is None:
            ident = self._request('GET', '/v1/identity')
            runner_id = ident['runner_id']
        prefs = self.store.rebind_runner(runner_id)
        if port is not None:
            prefs = self.store.save_preferences({'preferred_connector_port': port}, expected_revision=prefs['revision'])
        return {'rebound': True, 'preferences': prefs}

    # ------------------------------------------------------------------
    # Basic Connector Queries & Controls
    # ------------------------------------------------------------------
    def identity(self) -> dict:
        return self._request('GET', '/v1/identity')

    def inventory(self) -> dict:
        if self.shared:
            self.require_task()
            return self._request('GET', '/v1/sharing/run-config')
        return self._request('GET', '/v1/inventory')

    def test_status(self) -> dict:
        return self._request('GET', '/v1/test-status')

    def connector_settings(self) -> dict:
        return self._request('GET', '/v1/control/settings')

    def update_connector_settings(self, patch: dict, *, expected_revision: str | None = None) -> dict:
        cur = self.connector_settings()
        exp = expected_revision if expected_revision is not None else cur['revision']
        t_doc = {k: v for k, v in self.store.read_timeouts().items() if k != 'revision'}
        s_doc = {k: v for k, v in self.store.read_storage_policy().items() if k != 'revision'}
        base_rev = digest({'timeouts': t_doc, 'storage_policy': s_doc})
        return self._request(
            'PUT',
            '/v1/control/settings',
            json_body={
                'expected_revision': exp,
                'expected_runner_id': self.store.read_preferences().get('expected_runner_id'),
                'source': 'linux',
                'base_linux_revision': base_rev,
                'patch': patch,
            },
        )

    def verify_connection(self, *, wait: bool = True) -> dict:
        return self._request('POST', '/v1/control/verify-connection', json_body={'wait': wait})

    def reconnect_ssh(self) -> dict:
        return self._request('POST', '/v1/control/reconnect-ssh')

    def open_putty(self, board_id: str | None = None) -> dict:
        return self._request('POST', '/v1/control/putty', json_body={'board_id': board_id} if board_id else {})

    def restart_connector(self) -> dict:
        return self._request('POST', '/v1/control/restart')

    # ------------------------------------------------------------------
    # TC Discovery & Catalog Projection Push
    # ------------------------------------------------------------------
    def _tc_root(self, override=None):
        configured = override if override is not None else self.store.read()['integration'].get('tc_root')
        if configured and str(configured).strip():
            root = Path(configured).expanduser().resolve()
            if root.is_dir():
                return root
        raise TestError('공통 TC 폴더(tc_root)를 먼저 설정하세요.', 'SOURCE_NOT_CONFIGURED', 422)

    def build_tc_projection(self, tc_root: Path | None = None) -> tuple[dict, dict]:
        root = self._tc_root(tc_root)
        t_doc = self.store.read_timeouts()
        return build_tc_projection(root, t_doc)

    def push_tc_projection(self, tc_root: Path | None = None, *, allow_offline=False) -> dict:
        payload, catalog = self.build_tc_projection(tc_root)
        if self.shared:
            return {'projection': payload, 'catalog': catalog}
        try:
            ack = self._request('PUT', '/v1/tc-catalog-projection', json_body=payload)
        except TestError as exc:
            if not allow_offline:
                raise
            return {'projection': payload, 'catalog': catalog, 'error': {'code': exc.code, 'message': exc.message}}
        return {'projection': payload, 'catalog': catalog, 'ack': ack}

    # ------------------------------------------------------------------
    # Snapshot Sync (Source & Resumable Chunked Installer)
    # ------------------------------------------------------------------
    def sync_source_snapshot(self, tc_root: Path) -> dict:
        root = Path(tc_root).expanduser().resolve()
        return self._sync_source_files(root, read_source(root))

    def _sync_source_files(self, root, files):
        manifest = source_snapshots.manifest(files, {'kind': 'local', 'path': str(root)}, {})
        snap_id = manifest['snapshot_id']
        rev = manifest['source_revision']
        status = self._request('GET', f'/v1/source-snapshots/{snap_id}')
        if status.get('state') == 'READY' and status.get('source_revision') == rev:
            return {'snapshot_id': snap_id, 'source_revision': rev, 'uploaded': False}

        with tempfile.TemporaryDirectory(prefix='dc-src-') as tmp:
            zpath = Path(tmp) / 'source.zip'
            with zipfile.ZipFile(zpath, 'w', compression=zipfile.ZIP_STORED) as zf:
                zf.writestr(source_snapshots.MANIFEST, json.dumps(manifest, sort_keys=True))
                for rel, raw in files.items():
                    zf.writestr(rel, raw)
            raw_zip = zpath.read_bytes()
        resp = self._request(
            'PUT',
            f'/v1/source-snapshots/{snap_id}',
            content=raw_zip,
            headers={'Content-Type': 'application/zip', 'Content-Length': str(len(raw_zip))},
        )
        return {'snapshot_id': snap_id, 'source_revision': resp.get('source_revision', rev), 'uploaded': True}

    def sync_installer_snapshot(self, installer_path: Path) -> dict:
        shared = self.store.read()['integration']
        allowed_roots = [Path(r).expanduser().resolve() for r in shared.get('installer_roots', []) if r]
        target = Path(installer_path).expanduser()
        if not allowed_roots:
            raise TestError('installer_roots가 설정되지 않아 이미지를 전송할 수 없습니다.', 'INSTALLER_ROOT_REQUIRED', 422)
        with tempfile.TemporaryDirectory(prefix='dc-inst-') as tmp:
            staged = Path(tmp) / 'staged'
            frozen = installer_snapshots.freeze_installer(target, allowed_roots, staged)
            snap_id = frozen['snapshot_id']
            status = self._request('GET', f'/v1/installer-snapshots/{snap_id}')
            if status.get('state') == 'READY':
                return {'installer_snapshot_id': snap_id, 'manifest': frozen, 'uploaded': False, 'total_bytes': int(status.get('archive_size') or 0)}

            staged_snap = staged / snap_id
            zpath = Path(tmp) / 'installer.zip'
            with zipfile.ZipFile(zpath, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
                zf.write(staged_snap / installer_snapshots.MANIFEST, installer_snapshots.MANIFEST)
                for rel in frozen['files']:
                    zf.write(staged_snap / rel, rel)
            shutil.rmtree(staged, ignore_errors=True)

            total = zpath.stat().st_size
            sha = installer_snapshots.file_hash(zpath)

            offset = int(status.get('offset') or 0)
            if status.get('archive_sha256') not in {None, sha} or status.get('archive_size') not in {None, total}:
                raise TestError('Windows에 다른 내용의 동일 스냅샷 전송 기록이 남아 있습니다.', 'IMAGE_CHANGED', 409)

            chunks = 0
            with zpath.open('rb') as zf_stream:
                while offset < total:
                    zf_stream.seek(offset)
                    chunk = zf_stream.read(min(self.chunk_bytes, total - offset))
                    if not chunk:
                        break
                    end = offset + len(chunk) - 1
                    res = self._request(
                        'PUT',
                        f'/v1/installer-snapshots/{snap_id}',
                        content=chunk,
                        headers={
                            'Content-Type': 'application/zip',
                            'Content-Range': f'bytes {offset}-{end}/{total}',
                            'Content-Length': str(len(chunk)),
                            'X-Archive-SHA256': sha,
                        },
                    )
                    chunks += 1
                    offset = int(res.get('offset', end + 1))
                    if res.get('state') == 'READY':
                        break
        return {'installer_snapshot_id': snap_id, 'manifest': frozen, 'uploaded': True, 'chunks': chunks, 'total_bytes': total}

    # ------------------------------------------------------------------
    # Autonomous Bundle Run Submit, Watch, Logs & Controls
    # ------------------------------------------------------------------
    def _resolve_connection_and_command(self, tests: list[dict], inventory: dict, command_override: dict | None = None) -> tuple[dict, dict]:
        boards = inventory.get('boards', [])
        needs_dual = any(t['kind'] == 'Dual' for t in tests)
        if not boards:
            raise TestError('Windows에 등록된 보드가 없습니다.', 'HARDWARE_NOT_READY', 422)

        by_id = {b.get('board_id'): b for b in boards if b.get('board_id')}
        active_boards = [b for b in boards if b.get('detected') or b.get('state') == 'CONNECTED']
        ordered_boards = active_boards + [b for b in boards if b not in active_boards]

        def _board_conn(entry: dict) -> dict:
            out = {'host': entry['host'], 'board_id': entry['board_id'], 'com': entry['com']}
            if entry.get('node'):
                out['node'] = entry['node']
            return out

        shared_conn = None if self.shared else (self.store.read()['integration'] or {}).get('connection')
        conn: dict[str, Any] = {}
        if isinstance(shared_conn, dict) and isinstance(shared_conn.get('a'), dict):
            a_spec = shared_conn['a']
            a_entry = by_id.get(a_spec.get('board_id')) or a_spec
            conn['a'] = _board_conn(a_entry)
            if needs_dual:
                b_spec = shared_conn.get('b')
                if isinstance(b_spec, dict):
                    b_entry = by_id.get(b_spec.get('board_id')) or b_spec
                else:
                    remaining = [b for b in ordered_boards if b.get('board_id') != conn['a']['board_id']]
                    if not remaining:
                        raise TestError('Dual TC 실행을 위해 2개 보드가 필요합니다.', 'HARDWARE_NOT_READY', 422)
                    b_entry = remaining[0]
                conn['b'] = _board_conn(b_entry)
        else:
            conn['a'] = _board_conn(ordered_boards[0])
            if needs_dual:
                if len(ordered_boards) < 2:
                    raise TestError('Dual TC 실행을 위해 2개 보드가 필요합니다.', 'HARDWARE_NOT_READY', 422)
                conn['b'] = _board_conn(ordered_boards[1])

        return conn, self._command_snapshot(command_override)

    def _command_snapshot(self, override=None, default=None):
        if override:
            return override
        profiles = self.store.read_command_profiles()
        if self.shared:
            # The store's baseline default is for simulation. Use the Windows
            # approved path template or Python fixtures when no task profile exists.
            profiles = [profile for profile in profiles
                        if profile['single'] != default_command_template()['single']]
        selected = next((p for p in profiles if p['name'] == 'default'), profiles[0] if profiles else None)
        if selected:
            tpl = {'single': selected['single'], 'dual': selected['dual']}
            return {'name': selected['name'], 'revision': selected['revision'], 'template': tpl}
        if default is not None:
            return default
        tpl = ({'single': ['python', '{tc_path}', '--com', '{com_a}'],
                'dual': ['python', '{tc_path}', '--a', '{com_a}', '--b', '{com_b}']}
               if self.shared else default_command_template())
        return {'name': 'default', 'revision': digest(tpl), 'template': tpl}

    def _run_patterns(self, patterns, module):
        if patterns is None:
            shared = self.store.read()['integration']
            patterns = (shared.get('module_defaults') or {}).get(module, shared.get('global_defaults'))
        if not patterns:
            raise TestError('실행할 TC를 지정하세요. 전체 실행은 --pattern "**/*.py"를 사용하세요.', 'TC_NOT_FOUND', 422)
        return validate_patterns(patterns)

    def _selected_catalog(self, root, patterns, files=None):
        # Exact paths keep caller order. Globs and legacy module keywords enumerate names only.
        names = None
        selected = {}
        for pattern in patterns:
            exact = pattern.endswith('.py') and not any(c in pattern for c in '*?[')
            if exact:
                path = root / pattern
                allowed = all(not p.startswith('.') and p != '__pycache__' for p in Path(pattern).parts)
                exists = pattern in files if files is not None else path.is_file() and path.resolve() == path
                if not allowed or not exists or path.name == '__init__.py':
                    raise TestError(f'지정한 TC를 찾을 수 없습니다: {pattern}', 'TC_NOT_FOUND', 422)
                selected[pattern] = None
                continue
            if names is None:
                names = sorted(files if files is not None else script_paths(root))
            keyword = not any(c in pattern for c in '*?[/')
            for name in names:
                if name.endswith('.py') and Path(name).name != '__init__.py' and (
                    _glob_matches(name, pattern) or (keyword and pattern.casefold() in name.casefold())
                ):
                    selected[name] = None
        if not selected:
            raise TestError('실행할 TC가 선택되지 않았습니다.', 'TC_NOT_FOUND', 422)
        texts = {name: (files[name].decode('utf-8') if files is not None else (root / name).read_text(encoding='utf-8'))
                 for name in selected}
        catalog = discover_contents(texts)
        by_path = {tc['path']: tc for tc in catalog['tests']}
        return catalog['revision'], [by_path[path] for path in selected]

    def _path_target(self, tc_root, tc_path, patterns, module):
        if patterns is not None or module is not None:
            if tc_path is not None:
                raise TestError('Use either a TC path or legacy selection patterns', 'TC_SELECTION', 422)
            return None
        if tc_path is not None:
            return tc_path
        if tc_root is None and self.store.read()['integration'].get('global_defaults'):
            return None
        return '.'

    def _host_path_request(self, root, target, origin):
        identity = self.identity()
        if not self.shared and 'connector-tc-path-v1' not in identity.get('capabilities', []):
            raise TestError('경로 실행을 지원하는 보드 커넥터로 갱신하세요.', 'CAPABILITY_REQUIRED', 409)
        if target != '.':
            source_snapshots.safe_name(target)
        receipt = self.sync_source_snapshot(root)
        request = {'tc_path': target, 'source_snapshot_id': receipt['snapshot_id'],
                   'source_revision': receipt['source_revision'], 'origin': origin}
        return request, identity['runner_id']

    def _host_path_plan(self, root, target, origin, *, summary=False):
        request, runner_id = self._host_path_request(root, target, origin)
        route = '/v1/connector-runs/plan-path' + ('?summary=true' if summary else '')
        plan = self._request('POST', route, json_body=request,
                             headers={'X-Expected-Runner-ID': runner_id})
        return request, plan

    def preview_run(
        self,
        *,
        tc_root: Path | None = None,
        tc_path: str | None = None,
        patterns: list[str] | None = None,
        module: str | None = None,
        installer: Path | None = None,
        flash_profile: str = 'default',
    ) -> dict:
        root = self._tc_root(tc_root)
        target = self._path_target(tc_root, tc_path, patterns, module)
        if target is not None:
            _, plan = self._host_path_plan(root, target, {'client': self.peer_type, 'project': self.project})
            if self.shared:
                plan = self._freeze_path_plan(plan)
            return plan | {'tc_root': str(root), 'tc_path': target,
                           'execution_mode': 'flash_and_test' if installer else 'tc_only',
                           'installer': str(installer) if installer else None, 'flash_profile': flash_profile if installer else None}
        return self._preview(root, self._run_patterns(patterns, module), installer, flash_profile)

    def _freeze_path_plan(self, plan, command_override=None):
        timeouts = dict(self.store.read_timeouts())
        timeouts.pop('revision', None)
        body = dict(plan)
        body['timeout_settings_snapshot'] = timeouts
        body['command_snapshot'] = self._command_snapshot(command_override, default=plan['command_snapshot'])
        return body

    def _preview(self, root, patterns, installer, flash_profile, files=None):
        if installer and (not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', flash_profile) or flash_profile in {'.', '..'}):
            raise TestError('유효한 플래싱 프로파일 이름을 지정하세요.', 'FLASH_NOT_CONFIGURED', 422)
        t_doc = {k: v for k, v in self.store.read_timeouts().items() if k != 'revision'}
        revision, ordered = self._selected_catalog(root, patterns, files)
        steps = []
        for idx, tc in enumerate(ordered):
            explicit_timeout = tc.get('timeout') if tc.get('timeout_explicit', True) else None
            eff = resolve_step_timeout(tc['id'], t_doc, explicit_timeout)
            steps.append({
                'step_index': idx,
                'tc_id': tc['id'],
                'path': tc['path'],
                'kind': tc['kind'],
                'effective_timeout_s': eff,
                'metadata_timeout_s': explicit_timeout,
                'after': list(tc.get('after', [])),
            })
        return {
            'execution_mode': 'flash_and_test' if installer else 'tc_only',
            'tc_root': str(root.resolve()),
            'source_revision': revision,
            'flash_profile': flash_profile if installer else None,
            'installer': str(installer) if installer else None,
            'timeout_settings_snapshot': t_doc,
            'tests': steps,
        }

    @staticmethod
    def _flash_confirmation(manifest, body):
        snapshot = body['installer']['installer_snapshot_id']
        installer_snapshots.validate_manifest(manifest, snapshot)
        batch = manifest['batch']
        files = manifest['files']
        return {
            'installer_snapshot_id': snapshot,
            'installer_bat': {'path': batch, **files[batch]},
            'images': {path: row for path, row in files.items() if path != batch},
            'target_boards': [board for board in body['connection'].values() if board],
        }

    def prepare_run(
        self,
        *,
        project: str,
        build: str,
        tc_root: Path | None = None,
        tc_path: str | None = None,
        patterns: list[str] | None = None,
        module: str | None = None,
        installer: Path | None = None,
        flash_profile: str = 'default',
        idempotency_key: str | None = None,
        command_snapshot: dict | None = None,
    ) -> dict:
        if installer and (not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', flash_profile) or flash_profile in {'.', '..'}):
            raise TestError('유효한 플래싱 프로파일 이름을 지정하세요.', 'FLASH_NOT_CONFIGURED', 422)
        if not all(isinstance(v, str) and v.strip() for v in (project, build)):
            raise TestError('A project and build identifier are required', 'INVALID_PREPARED_RUN', 422)
        diag = self.require_connected()
        root = self._tc_root(tc_root)
        origin = {'client': self.peer_type, 'session_id': self.peer_instance_id, 'project': project}
        if self.shared and project != self.require_task()['project']:
            raise TestError('Run project differs from the registered task.', 'TASK_MISMATCH', 409)
        target = self._path_target(tc_root, tc_path, patterns, module)
        if target is not None and self.shared:
            _, plan = self._host_path_plan(root, target, origin)
            body = self._freeze_path_plan(plan, command_snapshot)
        elif target is not None:
            body, receipt = self._host_path_plan(root, target, origin, summary=True)
            body['expected_plan_revision'] = receipt['plan_revision']
            if installer is not None:
                body['connection'] = receipt['connection']
        else:
            effective_patterns = self._run_patterns(patterns, module)
            files = read_source(root)
            preview = self._preview(root, effective_patterns, installer, flash_profile, files)
            conn, cmd = self._resolve_connection_and_command(preview['tests'], self.inventory(), command_snapshot)
            src_sync = self._sync_source_files(root, files)
            body = {'connection': conn, 'command_snapshot': cmd, 'source_snapshot_id': src_sync['snapshot_id'],
                    'source_revision': src_sync['source_revision'], 'tests': preview['tests'], 'origin': origin,
                    'timeout_settings_snapshot': preview['timeout_settings_snapshot'],
                    'failure_policy': {'mode': 'fail-stop-analysis-v1', 'max_retry_chain': 3,
                                       'stop_on_same_cause': True, 'verifier_required': True}}

        installer_spec = None
        if installer is not None:
            prof_info = self._request('GET', f'/v1/flash-profiles/{flash_profile}')
            if (prof_info.get('runner_id') != diag['runner_id'] or prof_info.get('profile') != flash_profile
                    or not re.fullmatch(r'[a-f0-9]{64}', str(prof_info.get('revision', '')))):
                raise TestError('Registered flash profile receipt does not match the Runner and profile',
                                'RUNNER_MISMATCH', 409)
            inst_sync = self.sync_installer_snapshot(Path(installer))
            installer_spec = {
                'installer_snapshot_id': inst_sync['installer_snapshot_id'],
                'flash_profile': flash_profile,
                'flash_profile_revision': prof_info['revision'],
            }

        body.update(execution_mode='flash_and_test' if installer else 'tc_only', installer=installer_spec)
        if 'tc_path' not in body:
            body['request_hash'] = digest(body)
            ConnectorRunRequest.model_validate(body)
        key = idempotency_key or f'dc-{uuid.uuid4().hex}'
        if not isinstance(key, str) or not 1 <= len(key) <= 180:
            raise TestError('Idempotency-Key must have 1..180 characters', 'INVALID_PREPARED_RUN', 422)
        record = {'schema_version': 1, 'project': project, 'build': build, 'runner_id': diag['runner_id'],
                  'idempotency_key': key, 'body': body}
        if self.shared:
            record['task_id'] = self.require_task()['task_id']
        if installer is not None:
            record['flash_confirmation'] = self._flash_confirmation(inst_sync['manifest'], body)
        return record | {'fingerprint': digest(record)}

    def send_prepared_run(self, prepared: dict) -> dict:
        """Submit the saved body to its original Host without preparing snapshots again."""
        return self._submit_prepared(prepared, require_replay=True)

    def _submit_prepared(self, prepared: dict, *, require_replay: bool) -> dict:
        if not isinstance(prepared, dict):
            raise TestError('Invalid prepared Run record', 'INVALID_PREPARED_RUN', 422)
        record = {k: v for k, v in prepared.items() if k not in {'fingerprint', 'run_id'}}
        required = {'schema_version', 'project', 'build', 'runner_id', 'idempotency_key', 'body'}
        if self.shared:
            required.add('task_id')
            if record.get('task_id') != self.require_task()['task_id']:
                raise TestError('Prepared Run belongs to another task.', 'TASK_MISMATCH', 409)
        if (set(record) - {'flash_confirmation'} != required or type(record['schema_version']) is not int or record['schema_version'] != 1
                or prepared.get('fingerprint') != digest(record) or not isinstance(record['body'], dict)):
            raise TestError('Invalid or modified prepared Run record', 'INVALID_PREPARED_RUN', 422)
        label = (record['body'].get('origin') or {}).get('project')
        if ((label is not None and label != record['project'])
                or (self.project is not None and self.project != record['project'])):
            raise TestError('Prepared Run belongs to another project', 'INVALID_PREPARED_RUN', 422)
        identity = self.identity()
        if identity.get('runner_id') != record['runner_id'] or identity.get('service') != 'bsp-board-connector':
            raise TestError('Prepared Run belongs to another Runner', 'RUNNER_CHANGED', 409)
        if require_replay and not {'connector-run-replay-v1', SHARING_CAPABILITY}.intersection(identity.get('capabilities', [])):
            raise TestError('Connector needs prepared Run replay support', 'CAPABILITY_REQUIRED', 409)
        body = record['body']
        confirmation = None
        if body.get('execution_mode') == 'flash_and_test':
            snapshot = body['installer']['installer_snapshot_id']
            if 'flash_confirmation' in record:
                saved = record['flash_confirmation']
                bat = saved['installer_bat']
                manifest = {'format': 'installer_snapshot_v1', 'batch': bat['path'], 'snapshot_id': snapshot,
                            'files': {**saved['images'], bat['path']: {'size': bat['size'], 'sha256': bat['sha256']}}}
                confirmation = self._flash_confirmation(manifest, body)
                if confirmation != saved:
                    raise TestError('Flash confirmation differs from the frozen request', 'IMAGE_CHANGED', 409)
            else:
                receipt = self._request('GET', f'/v1/installer-snapshots/{snapshot}?manifest=true')
                confirmation = self._flash_confirmation(receipt.get('manifest'), body)
        result = self._request(
            'POST', '/v1/connector-runs', json_body=record['body'],
            headers={'Idempotency-Key': record['idempotency_key'], 'X-Expected-Runner-ID': record['runner_id']},
        )
        if (result.get('runner_id') != record['runner_id'] or not result.get('run_id')
                or prepared.get('run_id', result['run_id']) != result['run_id']):
            raise TestError('Host response does not match the prepared Run', 'PREPARED_RUN_MISMATCH', 409)
        return result | {'flash_confirmation': confirmation} if confirmation else result

    def start_run(
        self,
        *,
        project: str | None = None,
        tc_root: Path | None = None,
        tc_path: str | None = None,
        patterns: list[str] | None = None,
        module: str | None = None,
        installer: Path | None = None,
        flash_profile: str = 'default',
        idempotency_key: str | None = None,
        command_snapshot: dict | None = None,
    ) -> dict:
        if self.shared:
            return self._start_shared_run(project=project or self.require_task()['project'], tc_root=tc_root,
                                          tc_path=tc_path, patterns=patterns, module=module, installer=installer,
                                          flash_profile=flash_profile, idempotency_key=idempotency_key,
                                          command_snapshot=command_snapshot)
        target = self._path_target(tc_root, tc_path, patterns, module)
        if installer is None and target is not None:
            connected = self.require_connected()
            origin = {'client': self.peer_type, 'session_id': self.peer_instance_id,
                      'project': project or self.project or 'direct'}
            request, runner_id = self._host_path_request(self._tc_root(tc_root), target, origin)
            if runner_id != connected['runner_id']:
                raise TestError('Connector identity changed before submission', 'RUNNER_CHANGED', 409)
            return self._request('POST', '/v1/connector-runs', json_body=request, headers={
                'Idempotency-Key': idempotency_key or f'dc-{uuid.uuid4().hex}', 'X-Expected-Runner-ID': runner_id})
        prepared = self.prepare_run(
            project=project or self.project or 'direct', build='direct', tc_root=tc_root, tc_path=tc_path, patterns=patterns, module=module,
            installer=installer, flash_profile=flash_profile, idempotency_key=idempotency_key,
            command_snapshot=command_snapshot,
        )
        return self._submit_prepared(prepared, require_replay=False)

    def _start_shared_run(self, **options):
        self.require_task()
        options_fingerprint = digest({key: str(value) if isinstance(value, Path) else value
                                      for key, value in options.items()})
        pending_file = self.state_dir / 'pending-run.json'
        with state_lock(self.state_dir, '.run-submit.lock'):
            try:
                pending = private_json(pending_file)
            except FileNotFoundError:
                prepared = self.prepare_run(build='direct', **options)
                pending = {'options': options_fingerprint, 'prepared': prepared}
                write_private_json(pending_file, pending)
            if pending.get('options') != options_fingerprint:
                raise TestError('Recover the pending Run with test recover before starting another.', 'PENDING_RUN_RECOVERY', 409)
            return self._recover_pending(pending_file, pending)

    def recover_run(self):
        self.require_task()
        pending_file = self.state_dir / 'pending-run.json'
        with state_lock(self.state_dir, '.run-submit.lock'):
            try:
                pending = private_json(pending_file)
            except FileNotFoundError:
                raise TestError('This task has no pending Run submission.', 'NOT_FOUND', 404) from None
            return self._recover_pending(pending_file, pending)

    def _recover_pending(self, path, pending):
        try:
            run = self.send_prepared_run(pending.get('prepared'))
        except TestError as exc:
            # Keep the key if acceptance cannot be ruled out, including auth
            # failures after rotation and a changed/misdirected tunnel.
            if exc.status in {400, 422} or exc.code in {
                    'ACTIVE_RUN_EXISTS', 'BOARD_MISMATCH', 'COMMAND_NOT_ALLOWED', 'CONNECTOR_BUSY',
                    'PREVIEW_CHANGED', 'RESERVATION_CONFLICT', 'RUN_DELETED'}:
                path.unlink()
            raise
        self.select_run(run['run_id'])
        path.unlink()
        return run

    def selected_run(self):
        self.require_task()
        try:
            selected = private_json(self.state_dir / 'selected-run.json').get('run_id')
        except FileNotFoundError:
            return None
        if not valid_id(selected):
            raise SharingError('The selected Run record is invalid.')
        return selected

    def select_run(self, run_id):
        self.require_task()
        if not valid_id(run_id):
            raise SharingError('The Connector returned an invalid Run identity.')
        write_private_json(self.state_dir / 'selected-run.json', {'run_id': run_id})

    def project_run(self, run_id):
        try:
            return self.get_run(run_id)
        except TestError as exc:
            if exc.code != 'NOT_FOUND':
                raise
            return None

    def get_run(self, run_id: str | None = None) -> dict:
        if run_id:
            if self.shared and not valid_id(run_id):
                raise TestError('Run not found in the selected task.', 'NOT_FOUND', 404)
            run = self._request('GET', f'/v1/connector-runs/{run_id}')
            if not self.shared and self.project is not None and (run.get('origin') or {}).get('project') != self.project:
                raise TestError('Run not found in this project', 'NOT_FOUND', 404)
            return run
        active = self._request('GET', '/v1/connector-runs/active')
        if active.get('run') and (self.shared or self.project is None or (active['run'].get('origin') or {}).get('project') == self.project):
            return active['run']
        runs = self.list_runs(limit=1)
        if not runs:
            raise TestError('실행 이력이 없습니다.', 'NOT_FOUND', 404)
        return runs[0]

    def list_runs(self, limit: int = 20) -> list[dict]:
        params = {'limit': int(limit)}
        if not self.shared and self.project is not None:
            params['project'] = self.project
        runs = self._request('GET', '/v1/connector-runs?' + urlencode(params)).get('runs', [])
        return [run for run in runs if self.shared or self.project is None or (run.get('origin') or {}).get('project') == self.project]

    def read_logs(self, run_id: str, attempt_id: str, *, stream: str = 'stdout', offset: int = 0, limit: int = 65536) -> dict:
        return self._request(
            'GET',
            f'/v1/connector-runs/{run_id}/attempts/{attempt_id}/logs?stream={stream}&offset={int(offset)}&limit={int(limit)}',
        )

    def failure_evidence(self, run_id: str, attempt_id: str, wait_ms: int = 0) -> dict:
        if not all(re.fullmatch(r'[a-f0-9]{32}', value) for value in (run_id, attempt_id)):
            raise TestError('Invalid run or attempt identity', 'INVALID_ID', 422)
        if self.project is not None:
            self.get_run(run_id)
        return self._request('GET', f'/v1/connector-runs/{run_id}/attempts/{attempt_id}/failure-evidence?wait_ms={wait_ms}')

    def watch_run(
        self,
        run_id: str,
        *,
        on_log: Callable[[str, str], None] | None = None,
        on_status: Callable[[dict], None] | None = None,
        poll_interval_s: float = 0.25,
        timeout_s: float | None = None,
    ) -> dict:
        """Follow run progress/logs; SIGINT/KeyboardInterrupt detaches cleanly WITHOUT cancelling."""
        offsets: dict[tuple[str, str], int] = {}
        done_streams: set[tuple[str, str]] = set()
        started = self.clock()
        try:
            while True:
                run = self.get_run(run_id)
                if on_status:
                    on_status(run)
                for att in run.get('attempts', []):
                    aid = att['attempt_id']
                    streams = ('uart', 'installer', 'events') if att['phase'] == 'FLASHING' else ('stdout', 'stderr', 'events')
                    for stream in streams:
                        key = (aid, stream)
                        if key in done_streams:
                            continue
                        off = offsets.get(key, 0)
                        while True:
                            lg = self.read_logs(run_id, aid, stream=stream, offset=off)
                            if lg.get('text') and on_log:
                                on_log(stream, lg['text'])
                            off = int(lg.get('next_offset', off))
                            offsets[key] = off
                            if lg.get('eof'):
                                done_streams.add(key)
                                break
                            if off >= int(lg.get('total_bytes', 0)):
                                break
                if run['state'] in {'COMPLETED', 'PAUSED', 'UNKNOWN'}:
                    return run
                if timeout_s is not None and (self.clock() - started) >= timeout_s:
                    return {'detached': True, 'reason': 'WATCH_TIMEOUT', 'run': run, 'hint': f'test status {run_id}'}
                self.sleep(poll_interval_s)
        except KeyboardInterrupt:
            return {
                'detached': True,
                'reason': 'OPERATOR_DETACH',
                'run_id': run_id,
                'cancelled': False,
                'hint': f'실행은 Windows 커넥터에서 계속 진행됩니다. 재확인: test status {run_id} / test logs {run_id} --follow',
            }

    @staticmethod
    def _epoch_header(epoch):
        if type(epoch) is not int or epoch < 1:
            raise TestError('Connector did not supply a valid Run owner epoch.', 'OWNERSHIP_CHANGED', 409)
        return {'X-Bsp-Run-Epoch': str(epoch)}

    def _run_control(self, run_id, action, *, expected_epoch=None, body=None):
        headers = None
        if self.shared:
            epoch = self.get_run(run_id).get('ownership_epoch') if expected_epoch is None else expected_epoch
            headers = self._epoch_header(epoch)
        return self._request('POST', f'/v1/connector-runs/{run_id}/{action}', json_body=body, headers=headers)

    def pause_run(self, run_id: str, *, expected_epoch=None) -> dict:
        return self._run_control(run_id, 'pause', expected_epoch=expected_epoch)

    def resume_run(self, run_id: str, *, expected_epoch=None) -> dict:
        return self._run_control(run_id, 'resume', expected_epoch=expected_epoch)

    def cancel_run(self, run_id: str, *, expected_epoch=None) -> dict:
        return self._run_control(run_id, 'cancel', expected_epoch=expected_epoch)

    def reconcile_run(self, run_id: str, action: str = 'MARK_ABORTED', reason: str = '', *, expected_epoch=None) -> dict:
        return self._run_control(run_id, 'reconcile', expected_epoch=expected_epoch, body={'action': action, 'reason': reason})

    # ------------------------------------------------------------------
    # Fail-Stop Analysis Claim + Verifier + Decision
    # ------------------------------------------------------------------
    def list_analyses(self, *, status: str | None = 'PENDING', run_id: str | None = None) -> list[dict]:
        params = {key: value for key, value in {'status': status, 'run_id': run_id}.items() if value}
        qs = ('?' + urlencode(params)) if params else ''
        analyses = self._request('GET', '/v1/analyses' + qs).get('analyses', [])
        if self.shared or self.project is None:
            return analyses
        owned = {identity for identity in {row.get('run_id') for row in analyses}
                 if identity and self.project_run(identity) is not None}
        return [row for row in analyses if row.get('run_id') in owned]

    def analyze_once(
        self,
        *,
        run_id: str | None = None,
        analysis_id: str | None = None,
        consumer: str | None = None,
        analyzer: Callable[[dict], dict] | None = None,
        verifier: Callable[[dict, dict], str] | None = None,
        lease_ttl_s: int = 120,
    ) -> dict | None:
        epoch = None
        if analysis_id is None or self.shared or self.project is not None:
            rows = self.list_analyses(status='PENDING' if analysis_id is None else None, run_id=run_id)
            if analysis_id is None and not rows:
                return None
            target = next((row for row in rows if analysis_id is None or row['analysis_id'] == analysis_id), None)
            if target is None:
                raise TestError('Analysis not found in the selected scope', 'NOT_FOUND', 404)
            analysis_id = target['analysis_id']
            if self.shared:
                epoch = target.get('ownership_epoch')
        headers = self._epoch_header(epoch) if self.shared else None
        claimed = self._request(
            'POST',
            f'/v1/analyses/{analysis_id}/claim',
            headers=headers,
            json_body={'lease_owner': consumer or self.peer_instance_id, 'lease_ttl_s': lease_ttl_s},
        )
        run = self.get_run(claimed['run_id'])
        if self.shared and (run.get('ownership_epoch') != epoch or claimed.get('ownership_epoch', epoch) != epoch):
            raise TestError('Run ownership changed during analysis claim.', 'OWNERSHIP_CHANGED', 409)
        att_id = claimed.get('attempt_id')
        logs: dict[str, str] = {}
        failure = None
        if att_id and claimed.get('failure_evidence_available'):
            failure = self.failure_evidence(run['run_id'], att_id, wait_ms=3500)
            logs = {name: item['text'] for name, item in failure['logs'].items() if item['text']}
        elif att_id:
            for stream in ('stdout', 'stderr', 'uart', 'installer', 'events'):
                try:
                    lg = self.read_logs(run['run_id'], att_id, stream=stream, offset=0, limit=65536)
                    if lg.get('text'):
                        logs[stream] = lg['text']
                except TestError:
                    pass
        diag = self._scoped_connection() if self.shared else self._request('GET', '/v1/diagnostics/connection')

        failed_step = next(
            (s for s in run.get('steps', []) if s['step_index'] == claimed.get('failed_step_index')),
            None,
        )
        evidence_item = {
            'id': claimed['analysis_id'],
            'run_id': run['run_id'],
            'phase': claimed['phase'],
            'failed_step_index': claimed.get('failed_step_index'),
            'tc_id': failed_step.get('tc_id') if failed_step else None,
            'evidence_revision': claimed['evidence_revision'],
            'attempts': run.get('attempts', []),
            'logs': logs,
            **({'failure_evidence': failure} if failure is not None else {}),
            'diagnostics': diag,
            'evidence_refs': [f"{run['run_id']}/{att_id}"] if att_id else [],
        }

        analysis_home = self.state_dir if self.shared else self.runtime_dir
        cfg_path = analysis_home / 'failure-analysis.json'
        cfg = load_analysis_settings(cfg_path)
        adapter_dir = analysis_home / 'analysis-adapters'
        if analyzer is not None:
            raw_res = analyzer(evidence_item)
        elif cfg.enabled and cfg.mode != 'builtin' and cfg.analyzer is not None:
            raw_res = runtime_invoke(cfg.analyzer, sanitized(evidence_item), adapter_dir)
        else:
            attempts = [dict(a, id=a['attempt_id'], tc_id=evidence_item['tc_id'])
                        for a in run['attempts'] if a['attempt_id'] == att_id]
            raw_res = builtin_diagnose({
                'attempt_id': att_id, 'phase': claimed['phase'],
                'evidence_revision': claimed['evidence_revision'],
                'run': {'attempts': attempts, 'reason': run.get('recovery_reason')},
                'evidence_refs': evidence_item['evidence_refs'],
            })

        verdict_raw = str(raw_res.get('verdict') or raw_res.get('action') or 'HOLD').upper()
        if verdict_raw not in {'HOLD', 'RETRY', 'REPREPARE'}:
            verdict_raw = 'HOLD'
        cause_key = normalized_cause(raw_res.get('cause_key') or raw_res.get('cause') or f"{claimed['phase'].lower()}:failure")
        summary = str(raw_res.get('summary') or raw_res.get('cause_summary') or 'Failure analyzed')[:2000]

        verifier_status = 'SKIPPED'
        if verdict_raw in {'RETRY', 'REPREPARE'}:
            if verifier is not None:
                verifier_status = verifier(evidence_item, raw_res)
            elif cfg.verifier is not None:
                v_out = runtime_invoke(
                    cfg.verifier,
                    sanitized({'contract': 'failure-remediation-v1', 'analysis': evidence_item, 'result': raw_res}),
                    adapter_dir,
                )
                verifier_status = 'PASSED' if v_out.get('passed') is True or v_out.get('status') == 'PASSED' else 'FAILED'
            else:
                verifier_status = 'FAILED'

        reprepare_payload = None
        if verdict_raw == 'REPREPARE' and verifier_status == 'PASSED' and raw_res.get('reprepare_tc_root'):
            src_sync = self.sync_source_snapshot(Path(raw_res['reprepare_tc_root']))
            reprepare_payload = {
                'source_snapshot_id': src_sync['snapshot_id'],
                'source_revision': src_sync['source_revision'],
            }
        elif isinstance(raw_res.get('reprepare'), dict):
            reprepare_payload = raw_res['reprepare']

        bounded_val, bounded_truncated = bounded_evidence(raw_res)
        return self._request(
            'POST',
            f'/v1/analyses/{analysis_id}/decision',
            headers=headers,
            json_body={
                'lease_token': claimed['lease_token'],
                'expected_evidence_revision': claimed['evidence_revision'],
                'verdict': verdict_raw,
                'cause_key': cause_key or 'unspecified',
                'summary': summary,
                'verifier_status': verifier_status,
                'reprepare': reprepare_payload,
                'analyzer_evidence': {'payload': bounded_val, 'truncated': bool(bounded_truncated)},
            },
        )


def export_windows_bootstrap_local(
    source_root: Path,
    output_dir: Path,
    *,
    server: str,
    account: str,
    ssh_port: int = 22,
    remote_runner_port: int = 8771,
    remote_dashboard_port: int | None = None,
    expected_runner_id: str | None = None,
) -> dict:
    """Create bootstrap-v2 + Windows connector directory locally without Agent Monitor."""
    import sys
    repo_root = Path(__file__).resolve().parents[3]
    app_dir = repo_root / 'apps' / 'agent-monitor'
    if app_dir.is_dir() and str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    from plugin_delivery import windows_directory
    profile = build_bootstrap_v2(
        server=server,
        account=account,
        ssh_port=ssh_port,
        remote_runner_port=remote_runner_port,
        remote_dashboard_port=remote_dashboard_port,
        expected_runner_id=expected_runner_id,
    )
    if (source_root / 'AGENT_MONITOR_SOURCE.json').is_file():
        return windows_directory(source_root, output_dir, profile=profile)
    from delivery import export as export_source
    with tempfile.TemporaryDirectory(prefix='plugin-board-source-') as temporary:
        snapshot = Path(temporary) / 'source'
        export_source(source_root, snapshot, include_ui=False)
        return windows_directory(snapshot, output_dir, profile=profile)
