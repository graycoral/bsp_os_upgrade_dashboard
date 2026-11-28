"""Browser host adapter. Execution stays with the existing connector Manager."""
import copy
import json
import os
import subprocess
import sys
import threading
import time

from ..core.models import TestError, digest
from .paths import path_text

PROFILE_KEYS = {'_setup', 'python', 'boards', 'console_observers', 'board_names',
                'connector_inactive_boards', 'serial_transport', 'serial_settings', 'putty_path'}
SETUP_KEYS = {'server', 'account', 'ssh_port', 'remote_dashboard_port', 'ssh_key'}


def save_profile(manager, patch, revision=None):
    """The legacy IPC and browser both use the same check/save lock."""
    from ..execution.launch import read_active, read_host_active
    from pydantic import ValidationError
    if not isinstance(patch, dict) or ('_setup' in patch and not isinstance(patch['_setup'], dict)):
        raise TestError('Invalid connector profile', status=422)
    if 'serial_settings' in patch and (not isinstance(patch['serial_settings'], dict) or
                                      any(not isinstance(value, dict) for value in patch['serial_settings'].values())):
        raise TestError('Invalid serial settings', status=422)
    with manager.control_lock:
        if getattr(manager, 'mirror_applying', False):
            raise TestError('공통 설정을 적용 중입니다.', 'CONNECTOR_BUSY', 409)
        current = manager.settings.read()
        if revision is not None and revision != digest(current):
            raise TestError('다른 화면에서 설정이 변경됐습니다. 초안을 보존하고 최신 설정을 다시 불러오세요.', 'SETTINGS_CONFLICT', 409)
        runtime = getattr(manager, 'runtime', manager.home / 'runtime')
        if (read_active(runtime) is not None or read_host_active(runtime) is not None or
                getattr(manager, 'host_url', None) or (manager.thread and manager.thread.is_alive())):
            raise TestError('연결 종료 후 매핑을 변경하세요.', 'CONNECTOR_BUSY', 409)
        patch = copy.deepcopy(patch)
        if isinstance(patch.get('_setup'), dict):
            patch['_setup'] = dict(current.get('_setup', {}), **patch['_setup'])
        if isinstance(patch.get('serial_settings'), dict):
            serial = copy.deepcopy(current.get('serial_settings', {}))
            for key, value in patch['serial_settings'].items():
                serial[key] = dict(serial.get(key, {}), **value)
            patch['serial_settings'] = serial
        try:
            return manager.settings.save(patch)
        except (ValidationError, TypeError, ValueError, AttributeError) as exc:
            raise TestError('설정 형식과 보드 COM 매핑을 확인하세요.', 'CONNECTOR_CONFIG', 422) from exc


class ManagerActions:
    preview = False

    def __init__(self, manager):
        self.manager, self.home = manager, manager.home
        self.picker_lock = threading.Lock()

    def status(self):
        value = copy.deepcopy(self.manager.status())
        checked = value.get('last_checked_at')
        fresh = (value.get('fresh') is True and isinstance(checked, (float, int))
                 and 0 <= time.time() - checked <= 15)
        value['fresh'] = fresh
        value['stale'] = value.get('state') == 'CONNECTED' and not fresh
        if not fresh:
            for board in value.get('boards', []):
                board['stale'] = True
        value['path_text'] = path_text(value)
        # Never send an execution argv or unknown profile fields to the browser.
        return value

    def settings(self):
        with self.manager.control_lock:
            value = self.manager.settings.read()
            profile = {k: copy.deepcopy(v) for k, v in value.items() if k in PROFILE_KEYS}
            profile['_setup'] = {k: v for k, v in profile.get('_setup', {}).items() if k in SETUP_KEYS}
            return {'profile': profile, 'revision': digest(value)}

    def save(self, body):
        if set(body) != {'profile', 'revision'} or not isinstance(body['profile'], dict) or not isinstance(body['revision'], str):
            raise TestError('Invalid profile update', status=422)
        setup = body['profile'].get('_setup', {})
        if not isinstance(setup, dict) or set(body['profile']) - PROFILE_KEYS or set(setup) - SETUP_KEYS:
            raise TestError('Unsupported profile fields', status=422)
        save_profile(self.manager, body['profile'], body['revision'])
        return self.settings()

    def ports(self):
        from ..adapters.windows_ports import enumerate_ports
        return enumerate_ports()['ports']

    def action(self, name, body):
        with self.manager.control_lock:
            if name == 'connect' and not body:
                return self.manager.connect()
            if name == 'disconnect' and not body:
                return self.manager.disconnect()
            if name == 'verify-connection' and not body:
                return self.manager.verify_connection()
            if name == 'reconnect-ssh' and not body:
                return self.manager.reconnect_ssh()
            if name == 'restart-host' and not body:
                return self.manager.restart_host()
            if name == 'open-logs' and not body:
                if os.name != 'nt':
                    raise TestError('Windows에서 로그 폴더를 열 수 있습니다.', 'WINDOWS_REQUIRED', 409)
                os.startfile(str(self.home / 'logs'))
                return {'opened': True}
            if name in {'manual', 'putty'}:
                expected = {'board_id', 'manual'} if name == 'manual' else {'board_id'}
                if set(body) != expected or not isinstance(body.get('board_id'), str) or (name == 'manual' and type(body['manual']) is not bool):
                    raise TestError('Invalid board control request', status=422)
                status = self.status()
                if not status['fresh'] or status.get('state') != 'CONNECTED':
                    raise TestError('보드의 최근 상태를 확인한 뒤 제어하세요.', 'CONNECTOR_STALE', 409)
                if not any(b['board_id'] == body['board_id'] for b in status.get('boards', [])):
                    raise TestError('선택한 보드를 찾을 수 없습니다.', 'BOARD_NOT_FOUND', 409)
                return (self.manager.serial_control(body['board_id'], body['manual']) if name == 'manual'
                        else self.manager.open_putty(body['board_id']))
        raise TestError('Unsupported browser action', status=422)

    def _host_url(self):
        from ..execution.launch import read_host_active
        runtime = getattr(self.manager, 'runtime', self.home / 'runtime')
        receipt = read_host_active(runtime)
        if receipt and receipt.get('runner_port'):
            return f"http://127.0.0.1:{receipt['runner_port']}"
        return getattr(self.manager, 'host_url', None)

    def _host_settings_request(self, method='GET', payload=None):
        import httpx
        url = self._host_url()
        if not url:
            raise TestError('보드 커넥터 Host가 실행 중이 아닙니다.', 'SERVER_UNAVAILABLE', 503)
        with httpx.Client(timeout=3.0, trust_env=False, follow_redirects=False) as client:
            resp = client.request(method, url + '/v1/control/settings', json=payload)
        if resp.status_code >= 400:
            try:
                err = resp.json()
            except ValueError:
                err = {}
            raise TestError(err.get('message') or f'Host settings HTTP {resp.status_code}', err.get('code') or 'CONNECTOR_ERROR', resp.status_code)
        return resp.json()

    def shared(self, body=None):
        from .shared_control import request
        supervisor = getattr(self.manager, 'ssh_supervisor', None)
        if body is None and supervisor is not None:
            current = self.manager.reload_connected_settings(supervisor)
            if current is not None:
                return current
        try:
            saved = request(self.home, 'settings', 'GET' if body is None else 'PUT', body)
        except TestError as exc:
            if exc.code not in {'CONNECTOR_DISCONNECTED', 'SERVER_UNAVAILABLE'} or not self._host_url():
                raise
        else:
            host_url = self._host_url() if body is not None else None
            if host_url:
                from .shared_control import refresh_tc_catalog
                import httpx
                try:
                    refresh_tc_catalog(self.home, host_url, saved)
                except (TestError, httpx.HTTPError, ValueError, KeyError):
                    saved['catalog_pending'] = True
            return saved
        current = getattr(self.manager, 'cached', {})
        preview = current.get('shared_settings') or {}
        fields = (preview.get('integration') or {}) if (preview.get('read_only') and current.get('state') == 'CONNECTED'
                  and 0 <= time.time() - (current.get('last_checked_at') or 0) <= 15) else {}
        if body is None:
            data = self._host_settings_request('GET')
            s = data.get('settings', {})
            return {
                'revision': data.get('revision'),
                'integration': fields,
                'timeouts': s.get('timeouts', {'default_seconds': 600, 'overrides': {}}),
                'connector_application': {'state': 'SAVED', 'reason': '오프라인 로컬 편집(재연결 시 동기화)'},
                'offline_direct': True,
            }
        integration = body.get('integration') or {}
        if any(integration.get(key) for key in ('tc_root', 'installer_path', 'flash_profile', 'installer_roots')):
            raise TestError('Linux 공통 서버에 다시 연결한 뒤 TC 경로와 퓨징 설정을 저장하세요.', 'SHARED_UNAVAILABLE', 503)
        patch = {}
        if isinstance(body, dict) and 'timeouts' in body:
            patch['timeouts'] = body['timeouts']
        saved = self._host_settings_request('PUT', {
            'expected_revision': body.get('expected_revision') if isinstance(body, dict) else None,
            'source': 'windows',
            'patch': patch,
        })
        return {
            'revision': saved.get('revision'),
            'integration': fields,
            'timeouts': saved.get('settings', {}).get('timeouts', {}),
            'connector_application': {'state': 'SAVED', 'reason': '오프라인 로컬 저장(재연결 시 동기화)'},
            'sync_state': saved.get('sync_state'),
            'offline_direct': True,
        }

    def storage(self, body=None, cleanup=False):
        from .shared_control import request
        try:
            return request(self.home, 'storage-cleanup' if cleanup else 'storage-policy',
                           'POST' if cleanup else 'GET' if body is None else 'PUT', body)
        except TestError as exc:
            if exc.code not in {'CONNECTOR_DISCONNECTED', 'SERVER_UNAVAILABLE'} or not self._host_url():
                raise
        if cleanup:
            import httpx
            url = self._host_url()
            if not url:
                raise TestError('보드 커넥터 Host가 실행 중이 아닙니다.', 'SERVER_UNAVAILABLE', 503)
            with httpx.Client(timeout=5.0, trust_env=False, follow_redirects=False) as client:
                r = client.post(url + '/v1/storage-cleanup', json=body or {'dry_run': True})
                r.raise_for_status()
                return r.json()
        if body is None:
            data = self._host_settings_request('GET')
            sp = data.get('settings', {}).get('storage_policy', {})
            return dict(sp, revision=data.get('revision'), connector_sync={'state': 'SYNC_PENDING' if (data.get('sync_state') or {}).get('dirty_on_windows') else 'SAVED'})
        saved = self._host_settings_request('PUT', {
            'expected_revision': body.get('expected_revision') if isinstance(body, dict) else None,
            'source': 'windows',
            'patch': {'storage_policy': {k: v for k, v in body.items() if k != 'expected_revision'}},
        })
        sp = saved.get('settings', {}).get('storage_policy', {})
        return dict(sp, revision=saved.get('revision'), connector_sync={'state': 'SYNC_PENDING'}, sync_state=saved.get('sync_state'))

    def server_paths(self, body):
        from .shared_control import paths
        if set(body) - {'kind', 'path'}:
            raise TestError('Invalid server path request', status=422)
        return paths(self.home, body.get('kind'), body.get('path', ''))

    def pick(self, body):
        if set(body) != {'kind'} or body['kind'] not in {'python', 'ssh_key', 'putty'}:
            raise TestError('Invalid picker request', status=422)
        if os.name != 'nt':
            raise TestError('파일 선택을 지원하지 않습니다. 전체 경로를 직접 입력하세요.', 'PICKER_UNAVAILABLE', 409)
        if not self.picker_lock.acquire(blocking=False):
            raise TestError('이미 열린 파일 선택창을 확인하세요.', 'PICKER_BUSY', 409)
        try:
            result = subprocess.run([sys.executable, '-B', '-m', __package__ + '.native_picker', body['kind']],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding='utf-8', timeout=180,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                                    env=dict(os.environ, PYTHONUTF8='1'))
            if result.returncode:
                raise ValueError('picker failed')
            value = json.loads(result.stdout)
            if set(value) != {'path'} or not isinstance(value['path'], str):
                raise ValueError('invalid picker output')
            return value
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise TestError('파일 선택창을 열 수 없습니다. 전체 경로를 직접 입력하세요.', 'PICKER_UNAVAILABLE', 409) from exc
        finally:
            self.picker_lock.release()


class PreviewActions:
    """Mock-only host: no production settings, processes, COM, SSH, or file pickers."""
    preview = True

    def __init__(self, adapter):
        self.adapter = adapter
        self.lock = threading.RLock()

    def status(self):
        value = self.adapter.status()
        value['preview'] = True
        value['stale'] = value.get('state') == 'CONNECTED' and value.get('fresh') is not True
        value.setdefault('console', {})['stale'] = value.get('fresh') is not True
        value['path_text'] = path_text(value)
        return value

    def settings(self):
        value = self.adapter.settings()
        return {'profile': value, 'revision': digest(value)}

    def save(self, body):
        with self.lock:
            if set(body) != {'profile', 'revision'} or body['revision'] != self.settings()['revision']:
                raise TestError('모의 설정이 변경됐습니다.', 'SETTINGS_CONFLICT', 409)
            self.adapter.save(body['profile'])
            return self.settings()

    def ports(self):
        return self.adapter.ports()

    def action(self, name, body):
        if name == 'connect': return self.adapter.connect()
        if name == 'disconnect': return self.adapter.disconnect()
        if name == 'verify-connection': return self.adapter.verify_connection()
        if name == 'reconnect-ssh': return self.adapter.reconnect_ssh()
        if name == 'restart-host': return self.adapter.restart_host()
        if name == 'manual': return self.adapter.manual(body['board_id'], body['manual'])
        if name == 'putty': return self.adapter.putty(body['board_id'])
        if name == 'scenario' and body.get('value') in {'연결', '시험 중', '오류', '미연결', '확인 필요'}:
            self.adapter.scenario = body['value']
            return self.status()
        if name == 'open-logs': return {'opened': False, 'preview': True}
        raise TestError('미리보기에서 지원하지 않는 동작입니다.', status=422)

    def pick(self, body):
        raise TestError('미리보기에서는 파일 선택창을 열 수 없습니다. 전체 경로를 직접 입력하세요.',
                        'PICKER_UNAVAILABLE', 409)

    def shared(self, body=None):
        raise TestError('미리보기는 공통 서버를 호출하지 않습니다.', 'PREVIEW_ONLY', 409)

    def storage(self, body=None, cleanup=False):
        raise TestError('모의 화면에서는 서버 저장 공간을 변경하지 않습니다.', 'PREVIEW_ONLY', 409)

    def server_paths(self, body):
        raise TestError('미리보기는 서버 파일을 탐색하지 않습니다.', 'PREVIEW_ONLY', 409)
