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
import shutil
import socket
import tempfile
import time
from typing import Any, Callable
from urllib.parse import urlsplit
import uuid
import zipfile

import httpx

from ..adapters.runner import default_command_template
from ..core.connector_bootstrap import build_bootstrap_v2
from ..core.connector_diagnostics import diagnose_connector_endpoint
from ..core.discovery import discover
from ..core.failure_analysis import AnalysisResult, normalized_cause
from ..core.integration import _matches as _glob_matches
from ..core.models import TestError, digest
from ..core.shared_settings_store import SharedSettingsStore, resolve_runtime_dir
from ..execution import installer_snapshots, source_snapshots
from ..execution.connector_runs import (
    CONNECTOR_DEFAULT_TC_TIMEOUT_SECONDS,
    ConnectorRunRequest,
    MAX_TC_PROJECTION_BYTES,
    MAX_TC_PROJECTION_ITEMS,
    resolve_step_timeout,
)
from ..execution.source import read_source
from .analysis_runtime import bounded_evidence, diagnose as builtin_diagnose, invoke as runtime_invoke, sanitized, settings as load_analysis_settings
from .connector_observation import connection_status


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
        self.store = SharedSettingsStore(self.runtime_dir)
        prefs = self.store.read_preferences()
        self.port = int(connector_port if connector_port is not None else prefs.get('preferred_connector_port', 8771))
        self.url = _local_loopback_url(self.port)
        parsed = urlsplit(self.url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1':
            raise ValueError('DirectConnectorClient requires http://127.0.0.1:<port>')
        self.state_dir = Path(state_dir) if state_dir else (self.runtime_dir / 'plugin-direct-state')
        self.peer_type = peer_type
        self.peer_version = peer_version
        self.peer_instance_id = _make_peer_instance_id(self.state_dir)
        self.chunk_bytes = max(4096, int(chunk_bytes))
        self.sshd_config = sshd_config
        self.proc_root = proc_root
        self.proc_tcp = proc_tcp
        self.proc_tcp6 = proc_tcp6
        self.clock = clock
        self.sleep = sleep
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=httpx.Timeout(30.0, connect=2.0), trust_env=False, follow_redirects=False)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request(self, method: str, path: str, *, json_body: Any = None, content: bytes | None = None, headers: dict[str, str] | None = None) -> dict:
        hdrs = dict(headers or {})
        try:
            resp = self._client.request(method, self.url + path, headers=hdrs, json=json_body, content=content)
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
            exc = TestError(err.get('message') or f'Connector HTTP {resp.status_code}', err.get('code') or 'CONNECTOR_ERROR', resp.status_code)
            if isinstance(err, dict):
                exc.extra = err
            raise exc
        return resp.json()

    # ------------------------------------------------------------------
    # Diagnostics, Peer Hello & Two-Way Settings Sync
    # ------------------------------------------------------------------
    def diagnose(self, *, reconcile_sync: bool = True) -> dict:
        prefs = self.store.read_preferences()
        expected_id = prefs.get('expected_runner_id')
        shared_rev = self.store.read()['revision']
        probe_kwargs: dict[str, Any] = {
            'expected_runner_id': expected_id,
            'shared_revision': shared_rev,
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
    ) -> dict:
        """Poll connector reachability and emit state transitions without cancelling runs on exit."""
        prev_key = None
        last_event: dict = {'event': 'DISCONNECTED', 'connected': False, 'runner_id': None}
        iteration = 0
        try:
            while max_iterations is None or iteration < max_iterations:
                iteration += 1
                diag = self.diagnose()
                reachable = bool(diag.get('linux_diagnostics', {}).get('reachable'))
                runner_id = diag.get('runner_id')
                code = diag.get('code')
                inv = None
                if reachable:
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
                        if not prev_key or not prev_key[0] or switched:
                            try:
                                shared = self.store.read()['integration']
                                if shared.get('tc_root') and Path(shared['tc_root']).is_dir():
                                    self.push_tc_projection(Path(shared['tc_root']))
                            except Exception:
                                pass
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
    def build_tc_projection(self, tc_root: Path | None = None) -> tuple[dict, dict]:
        shared = self.store.read()['integration']
        t_doc = self.store.read_timeouts()
        root = Path(tc_root or shared.get('tc_root') or '').expanduser()
        if not str(root) or not root.is_dir():
            raise TestError('유효한 공통 TC 폴더(tc_root)가 설정되지 않았습니다.', 'SOURCE_NOT_CONFIGURED', 422)
        catalog = discover(root)
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
            'items': items,
        }
        # Trim if encoded JSON approaches 512 KiB limit
        while items and len(json.dumps(payload).encode('utf-8')) > MAX_TC_PROJECTION_BYTES:
            items.pop()
            payload['items'] = items
            payload['truncated'] = True
        return payload, catalog

    def push_tc_projection(self, tc_root: Path | None = None) -> dict:
        payload, catalog = self.build_tc_projection(tc_root)
        ack = self._request('PUT', '/v1/tc-catalog-projection', json_body=payload)
        return {'projection': payload, 'catalog': catalog, 'ack': ack}

    # ------------------------------------------------------------------
    # Snapshot Sync (Source & Resumable Chunked Installer)
    # ------------------------------------------------------------------
    def sync_source_snapshot(self, tc_root: Path) -> dict:
        root = Path(tc_root).expanduser().resolve()
        files = read_source(root)
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
                return {'installer_snapshot_id': snap_id, 'uploaded': False, 'total_bytes': int(status.get('archive_size') or 0)}

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
        return {'installer_snapshot_id': snap_id, 'uploaded': True, 'chunks': chunks, 'total_bytes': total}

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

        shared_conn = (self.store.read()['integration'] or {}).get('connection')
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

        if command_override:
            cmd = command_override
        else:
            profiles = self.store.read_command_profiles()
            selected = next((p for p in profiles if p['name'] == 'default'), profiles[0] if profiles else None)
            if selected:
                tpl = {'single': selected['single'], 'dual': selected['dual']}
                cmd = {'name': selected['name'], 'revision': selected['revision'], 'template': tpl}
            else:
                tpl = default_command_template()
                cmd = {'name': 'default', 'revision': digest(tpl), 'template': tpl}
        return conn, cmd

    def _select_tests(self, catalog: dict, patterns: list[str] | None = None) -> list[dict]:
        all_tests = [t for t in catalog.get('tests', []) if not t.get('disabled_reason')]
        if patterns:
            pats = [p for p in patterns if p]

            def _matches_pattern(tc: dict, pat: str) -> bool:
                if _glob_matches(tc['path'], pat):
                    return True
                if not any(ch in pat for ch in ('*', '?', '/')):
                    low = pat.casefold()
                    return low in tc['id'].casefold() or low in tc['path'].casefold()
                return False

            picked = [t for t in all_tests if any(_matches_pattern(t, p) for p in pats)]
        else:
            picked = list(all_tests)
        if not picked:
            raise TestError('실행할 TC가 선택되지 않았습니다.', 'TC_NOT_FOUND', 422)

        by_id = {t['id']: t for t in all_tests}
        ordered: list[dict] = []
        added: set[str] = set()

        def add_with_deps(tc_id: str):
            if tc_id in added:
                return
            tc = by_id.get(tc_id)
            if not tc:
                raise TestError(f'Missing dependency TC: {tc_id}', 'TC_NOT_FOUND', 422)
            for dep in tc.get('after', []):
                add_with_deps(dep)
            added.add(tc_id)
            ordered.append(tc)

        for tc in picked:
            add_with_deps(tc['id'])
        return ordered

    def preview_run(
        self,
        *,
        tc_root: Path | None = None,
        patterns: list[str] | None = None,
        module: str | None = None,
        installer: Path | None = None,
        flash_profile: str = 'default',
    ) -> dict:
        if installer and (not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', flash_profile) or flash_profile in {'.', '..'}):
            raise TestError('유효한 플래싱 프로파일 이름을 지정하세요.', 'FLASH_NOT_CONFIGURED', 422)
        shared = self.store.read()['integration']
        t_doc = {k: v for k, v in self.store.read_timeouts().items() if k != 'revision'}
        root = Path(tc_root or shared.get('tc_root') or '').expanduser()
        if not str(root) or not root.is_dir():
            raise TestError('공통 TC 폴더(tc_root)를 먼저 설정하세요.', 'SOURCE_NOT_CONFIGURED', 422)
        catalog = discover(root)
        effective_patterns = patterns
        if effective_patterns is None:
            mod_defaults = shared.get('module_defaults') or {}
            if module and module in mod_defaults:
                effective_patterns = mod_defaults[module] or None
            elif shared.get('global_defaults'):
                effective_patterns = shared['global_defaults'] or None
        ordered = self._select_tests(catalog, effective_patterns)
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
            'source_revision': catalog['revision'],
            'flash_profile': flash_profile if installer else None,
            'installer': str(installer) if installer else None,
            'timeout_settings_snapshot': t_doc,
            'tests': steps,
        }

    def prepare_run(
        self,
        *,
        project: str,
        build: str,
        tc_root: Path | None = None,
        patterns: list[str] | None = None,
        module: str | None = None,
        installer: Path | None = None,
        flash_profile: str = 'default',
        idempotency_key: str | None = None,
        command_snapshot: dict | None = None,
    ) -> dict:
        if not all(isinstance(v, str) and v.strip() for v in (project, build)):
            raise TestError('A project and build identifier are required', 'INVALID_PREPARED_RUN', 422)
        diag = self.require_connected()
        preview = self.preview_run(tc_root=tc_root, patterns=patterns, module=module, installer=installer, flash_profile=flash_profile)
        root = Path(preview['tc_root'])
        inv = self.inventory()
        conn, cmd = self._resolve_connection_and_command(preview['tests'], inv, command_snapshot)
        src_sync = self.sync_source_snapshot(root)
        self.push_tc_projection(root)

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

        body = {
            'execution_mode': preview['execution_mode'],
            'connection': conn,
            'source_snapshot_id': src_sync['snapshot_id'],
            'source_revision': src_sync['source_revision'],
            'command_snapshot': cmd,
            'installer': installer_spec,
            'tests': preview['tests'],
            'timeout_settings_snapshot': preview['timeout_settings_snapshot'],
            'failure_policy': {
                'mode': 'fail-stop-analysis-v1',
                'max_retry_chain': 3,
                'stop_on_same_cause': True,
                'verifier_required': True,
            },
            'origin': {'client': self.peer_type, 'session_id': self.peer_instance_id},
        }
        body['request_hash'] = digest(body)
        key = idempotency_key or f'dc-{uuid.uuid4().hex}'
        if not isinstance(key, str) or not 1 <= len(key) <= 180:
            raise TestError('Idempotency-Key must have 1..180 characters', 'INVALID_PREPARED_RUN', 422)
        ConnectorRunRequest.model_validate(body)
        record = {'schema_version': 1, 'project': project, 'build': build, 'runner_id': diag['runner_id'],
                  'idempotency_key': key, 'body': body}
        return record | {'fingerprint': digest(record)}

    def send_prepared_run(self, prepared: dict) -> dict:
        """Submit the saved body to its original Host without preparing snapshots again."""
        return self._submit_prepared(prepared, require_replay=True)

    def _submit_prepared(self, prepared: dict, *, require_replay: bool) -> dict:
        if not isinstance(prepared, dict):
            raise TestError('Invalid prepared Run record', 'INVALID_PREPARED_RUN', 422)
        record = {k: v for k, v in prepared.items() if k not in {'fingerprint', 'run_id'}}
        required = {'schema_version', 'project', 'build', 'runner_id', 'idempotency_key', 'body'}
        if (set(record) != required or type(record['schema_version']) is not int or record['schema_version'] != 1
                or prepared.get('fingerprint') != digest(record) or not isinstance(record['body'], dict)):
            raise TestError('Invalid or modified prepared Run record', 'INVALID_PREPARED_RUN', 422)
        identity = self.identity()
        if identity.get('runner_id') != record['runner_id'] or identity.get('service') != 'bsp-board-connector':
            raise TestError('Prepared Run belongs to another Runner', 'RUNNER_CHANGED', 409)
        if require_replay and 'connector-run-replay-v1' not in identity.get('capabilities', []):
            raise TestError('Connector needs prepared Run replay support', 'CAPABILITY_REQUIRED', 409)
        result = self._request(
            'POST', '/v1/connector-runs', json_body=record['body'],
            headers={'Idempotency-Key': record['idempotency_key'], 'X-Expected-Runner-ID': record['runner_id']},
        )
        if (result.get('runner_id') != record['runner_id'] or not result.get('run_id')
                or prepared.get('run_id', result['run_id']) != result['run_id']):
            raise TestError('Host response does not match the prepared Run', 'PREPARED_RUN_MISMATCH', 409)
        return result

    def start_run(
        self,
        *,
        tc_root: Path | None = None,
        patterns: list[str] | None = None,
        module: str | None = None,
        installer: Path | None = None,
        flash_profile: str = 'default',
        idempotency_key: str | None = None,
        command_snapshot: dict | None = None,
    ) -> dict:
        prepared = self.prepare_run(
            project='direct', build='direct', tc_root=tc_root, patterns=patterns, module=module,
            installer=installer, flash_profile=flash_profile, idempotency_key=idempotency_key,
            command_snapshot=command_snapshot,
        )
        return self._submit_prepared(prepared, require_replay=False)

    def get_run(self, run_id: str | None = None) -> dict:
        if run_id:
            return self._request('GET', f'/v1/connector-runs/{run_id}')
        active = self._request('GET', '/v1/connector-runs/active')
        if active.get('run'):
            return active['run']
        runs = self._request('GET', '/v1/connector-runs?limit=1').get('runs', [])
        if not runs:
            raise TestError('실행 이력이 없습니다.', 'NOT_FOUND', 404)
        return runs[0]

    def list_runs(self, limit: int = 20) -> list[dict]:
        return self._request('GET', f'/v1/connector-runs?limit={int(limit)}').get('runs', [])

    def read_logs(self, run_id: str, attempt_id: str, *, stream: str = 'stdout', offset: int = 0, limit: int = 65536) -> dict:
        return self._request(
            'GET',
            f'/v1/connector-runs/{run_id}/attempts/{attempt_id}/logs?stream={stream}&offset={int(offset)}&limit={int(limit)}',
        )

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

    def pause_run(self, run_id: str) -> dict:
        return self._request('POST', f'/v1/connector-runs/{run_id}/pause')

    def resume_run(self, run_id: str) -> dict:
        return self._request('POST', f'/v1/connector-runs/{run_id}/resume')

    def cancel_run(self, run_id: str) -> dict:
        return self._request('POST', f'/v1/connector-runs/{run_id}/cancel')

    def reconcile_run(self, run_id: str, action: str = 'MARK_ABORTED', reason: str = '') -> dict:
        return self._request('POST', f'/v1/connector-runs/{run_id}/reconcile', json_body={'action': action, 'reason': reason})

    # ------------------------------------------------------------------
    # Fail-Stop Analysis Claim + Verifier + Decision
    # ------------------------------------------------------------------
    def list_analyses(self, *, status: str | None = 'PENDING', run_id: str | None = None) -> list[dict]:
        params = []
        if status:
            params.append(f'status={status}')
        if run_id:
            params.append(f'run_id={run_id}')
        qs = ('?' + '&'.join(params)) if params else ''
        return self._request('GET', '/v1/analyses' + qs).get('analyses', [])

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
        if analysis_id is None:
            pending = self.list_analyses(status='PENDING', run_id=run_id)
            if not pending:
                return None
            analysis_id = pending[0]['analysis_id']

        claimed = self._request(
            'POST',
            f'/v1/analyses/{analysis_id}/claim',
            json_body={'lease_owner': consumer or self.peer_instance_id, 'lease_ttl_s': lease_ttl_s},
        )
        run = self.get_run(claimed['run_id'])
        att_id = claimed.get('attempt_id')
        logs: dict[str, str] = {}
        if att_id:
            for stream in ('stdout', 'stderr', 'uart', 'installer', 'events'):
                try:
                    lg = self.read_logs(run['run_id'], att_id, stream=stream, offset=0, limit=65536)
                    if lg.get('text'):
                        logs[stream] = lg['text']
                except TestError:
                    pass
        diag = self._request('GET', '/v1/diagnostics/connection')

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
            'diagnostics': diag,
            'evidence_refs': [f"{run['run_id']}/{att_id}"] if att_id else [],
        }

        cfg_path = self.runtime_dir / 'failure-analysis.json'
        cfg = load_analysis_settings(cfg_path)
        adapter_dir = self.runtime_dir / 'analysis-adapters'
        if analyzer is not None:
            raw_res = analyzer(evidence_item)
        elif cfg.enabled and cfg.mode != 'builtin' and cfg.analyzer is not None:
            raw_res = runtime_invoke(cfg.analyzer, sanitized(evidence_item), adapter_dir)
        else:
            raw_res = builtin_diagnose({
                'id': claimed['analysis_id'],
                'summary': f"{claimed['phase']} failed",
                'evidence_refs': evidence_item['evidence_refs'],
            })

        verdict_raw = str(raw_res.get('verdict') or raw_res.get('action') or 'HOLD').upper()
        if verdict_raw not in {'HOLD', 'RETRY', 'REPREPARE'}:
            verdict_raw = 'HOLD'
        cause_key = normalized_cause(raw_res.get('cause_key') or raw_res.get('cause') or f"{claimed['phase'].lower()}:failure")
        summary = str(raw_res.get('summary') or 'Failure analyzed')[:2000]

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
