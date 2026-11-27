"""Detached per-home manager; GUI close never owns Host/SSH lifetime."""
import argparse
import copy
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

from ..core.models import TestError
now = time.time
from ..execution.connector_runs import BridgeTokenStore
from ..execution.launch import (
    LaunchLock,
    _lock_held,
    bind_loopback,
    process_identity,
    read_host_active,
    read_ssh_tunnel,
    read_startup,
    remove_host_active,
    remove_ssh_tunnel,
    write_host_active,
)
from .settings import Settings
from .logs import logger, redact
from .ssh_tunnel import SshTunnelSupervisor, preflight_ssh


def storage_usage(root, protected=False):
    total=0; count=0; partial=False; started=time.monotonic()
    for base, dirs, files in os.walk(root,followlinks=False):
        dirs[:]=[name for name in dirs if not (Path(base)/name).is_symlink()]
        for name in files:
            file=Path(base)/name
            if file.is_symlink(): continue
            try: total+=file.stat().st_size; count+=1
            except OSError: partial=True
            if count>=10000 or time.monotonic()-started>.25: partial=True;break
        if count>=10000 or time.monotonic()-started>.25: break
    return {'runtime_bytes':total,'partial':partial,'protected':bool(protected),'automatic_cleanup':False}


def stale_display(cached,error):
    return dict(cached,state='ERROR',error=redact(error),console=dict(cached.get('console',{}),fresh=False,stale=True),fresh=False,
                boards=[dict(board,last_known_state=board.get('last_known_state',board['state']),state='UNKNOWN',stale=True) for board in cached.get('boards',[])])


class Manager:
    DEFAULT_LOCAL_HOST_PORT = 8772

    def __init__(self, home):
        self.home = Path(home)
        self.runtime = self.home / 'runtime'
        self.settings = Settings(home)
        self.log = logger(home)
        self.console_cursor = 0
        self.console_epoch = None
        self.storage_cache = None
        self.storage_checked = 0
        self.control_lock = threading.RLock()
        self.putty_cleanup = {}
        self.mirror_applying = False
        self.probe_lock = threading.RLock()
        self.thread = None
        self.wizard = None
        self.error = ''
        self.stop_event = threading.Event()
        self.shutdown = threading.Event()
        self.bridge_tokens = BridgeTokenStore(self.home / 'manager-bridge', windows=(os.name == 'nt'))
        self.bridge_token = self.bridge_tokens.ensure()
        self.host_process = None
        self.host_launch_id = None
        self.host_url = None
        self.host_runner_id = None
        self.local_runner_port = None
        self.remote_runner_port = 8771
        self.ssh_supervisor = None
        self._last_preflight = None
        self._last_verify_result = None
        self.cached = {
            'state': 'DISCONNECTED',
            'local_state': 'STOPPED',
            'ssh_state': 'DISCONNECTED',
            'overall_connection_state': 'DISCONNECTED',
            'boards': [],
            'error': '',
            'stages': {},
            'console': {'boards': [], 'errors': []},
            'executions': [],
        }
        from .mirror_client import MirrorClient
        self.mirror = MirrorClient(self)
        self._try_reattach_host()

        def monitor():
            last_probe = 0.0
            while not self.shutdown.is_set():
                if self.host_url:
                    try:
                        self._bridge_tick()
                    except Exception as exc:
                        self.log.error('BRIDGE_TICK_FAILED %s', redact(str(exc)))
                mono = time.monotonic()
                if mono - last_probe >= 3.0:
                    last_probe = mono
                    try:
                        self.cached = self.probe()
                    except Exception as exc:
                        if str(exc) != self.cached.get('error'):
                            self.log.error('STATUS_UNAVAILABLE %s', redact(str(exc)))
                        self.cached = stale_display(self.cached, str(exc))
                    try:
                        if self.cached.get('dashboard_url'):
                            self.mirror.tick(self.cached)
                    except Exception as exc:
                        self.cached['mirror_error'] = redact(str(exc))
                self.shutdown.wait(0.5)

        self.monitor = threading.Thread(target=monitor, name='connector-heartbeat', daemon=True)
        self.monitor.start()

    def close(self):
        self.shutdown.set()
        if self.ssh_supervisor:
            try:
                self.ssh_supervisor.stop()
            except Exception:
                pass
        if getattr(self, 'monitor', None) and self.monitor.is_alive():
            self.monitor.join(timeout=3.0)

    def _config_path(self):
        return self.home / 'windows-runner.json'

    def _resolve_ssh_settings(self):
        cfg = self.settings.read()
        setup = cfg.get('_setup', {}) if isinstance(cfg, dict) else {}
        remote_runner_port = setup.get('remote_runner_port', 8771)
        remote_dashboard_port = setup.get('remote_dashboard_port')
        local_dashboard_port = setup.get('dashboard_port', 8766)
        return cfg, setup, remote_runner_port, remote_dashboard_port, local_dashboard_port

    def _try_reattach_host(self):
        receipt = read_host_active(self.runtime)
        if not receipt:
            return False
        runner_url = f"http://127.0.0.1:{receipt['runner_port']}"
        import httpx
        try:
            with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
                r = client.get(runner_url + '/v1/identity')
                if r.status_code != 200:
                    return False
                ident = r.json()
                if receipt.get('runner_id') and ident.get('runner_id') != receipt.get('runner_id'):
                    return False
        except Exception:
            return False
        self.host_url = runner_url
        self.host_runner_id = ident.get('runner_id')
        self.local_runner_port = receipt.get('runner_port') or ident.get('local_port')
        self.host_launch_id = receipt.get('launch_id')
        _, setup, remote_runner_port, remote_dashboard_port, local_dashboard_port = self._resolve_ssh_settings()
        self.remote_runner_port = remote_runner_port
        self._send_bridge_heartbeat()
        if setup.get('server') and setup.get('account') and not self.ssh_supervisor:
            self._start_ssh_supervisor(setup, self.local_runner_port, remote_runner_port, local_dashboard_port, remote_dashboard_port)
        return True

    def _send_bridge_heartbeat(self):
        if not self.host_url:
            return None
        import httpx
        ssh_snap = self.ssh_supervisor.snapshot() if self.ssh_supervisor else None
        payload = {
            'manager_pid': os.getpid(),
            'local_port': self.local_runner_port,
            'remote_runner_port': self.remote_runner_port,
            'ssh_snapshot': ssh_snap,
            'preflight': self._last_preflight,
            'putty_active': bool(self.putty_cleanup),
        }
        try:
            with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
                r = client.post(
                    self.host_url + '/v1/internal/manager-heartbeat',
                    headers={'X-Manager-Token': self.bridge_token},
                    json=payload,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            return None
        return None

    def _bridge_tick(self):
        self._send_bridge_heartbeat()
        import httpx
        try:
            with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as client:
                r = client.get(
                    self.host_url + '/v1/internal/manager-tasks',
                    headers={'X-Manager-Token': self.bridge_token},
                )
                if r.status_code != 200:
                    return
                tasks = r.json().get('tasks', [])
        except Exception:
            return
        for task in tasks:
            self._execute_bridge_task(task)

    def _execute_bridge_task(self, task):
        import httpx
        task_id = task['task_id']
        action = task['action']
        payload = task.get('payload') or {}
        state = 'COMPLETED'
        result = {}
        error = None
        try:
            if action == 'OPEN_PUTTY':
                board_id = payload.get('board_id')
                if not board_id:
                    boards = self.settings.read().get('boards', [])
                    if not boards:
                        raise TestError('설정된 보드가 없습니다.', 'BOARD_MISMATCH', 422)
                    board_id = boards[0]['board_id']
                result = self.open_putty(board_id)
            elif action == 'APPLY_SETTINGS':
                result = self._apply_settings_to_tunnel(payload)
            elif action == 'RESTART_HOST':
                result = self.restart_host()
            elif action == 'RECONNECT_SSH':
                result = self.reconnect_ssh()
            elif action == 'VERIFY_CONNECTION':
                result = self.verify_connection(check_linux=bool(payload.get('check_linux', True)))
            else:
                raise TestError(f'Unknown manager task {action}', 'UNSUPPORTED_TASK', 422)
        except Exception as exc:
            state = 'FAILED'
            error = redact(str(exc))
            result = {'code': getattr(exc, 'code', 'TASK_FAILED'), 'message': error}
        try:
            with httpx.Client(timeout=3.0, trust_env=False, follow_redirects=False) as client:
                client.post(
                    self.host_url + f'/v1/internal/manager-tasks/{task_id}/result',
                    headers={'X-Manager-Token': self.bridge_token},
                    json={'state': state, 'result': result, 'error': error},
                )
        except Exception:
            pass

    def _apply_settings_to_tunnel(self, payload):
        _, setup, remote_runner_port, remote_dashboard_port, local_dashboard_port = self._resolve_ssh_settings()
        self.remote_runner_port = remote_runner_port
        ssh_keys = {'server', 'account', 'ssh_port', 'remote_runner_port', 'remote_dashboard_port', 'ssh_key'}
        patch = payload.get('patch') or {}
        if (set(patch) & ssh_keys) and self.local_runner_port:
            if self.ssh_supervisor:
                self.ssh_supervisor.stop()
                self.ssh_supervisor = None
            if setup.get('server') and setup.get('account'):
                self._start_ssh_supervisor(setup, self.local_runner_port, remote_runner_port, local_dashboard_port, remote_dashboard_port)
        return {'applied': True, 'tunnel_reconfigured': bool(set(patch) & ssh_keys)}

    def _build_ssh_supervisor(self, setup, local_runner_port, remote_runner_port, local_dashboard_port, remote_dashboard_port):
        return SshTunnelSupervisor(
            self.runtime,
            setup,
            actual_local_runner_port=local_runner_port,
            remote_runner_port=remote_runner_port,
            remote_dashboard_port=remote_dashboard_port,
            local_dashboard_port=local_dashboard_port,
        )

    def _start_ssh_supervisor(self, setup, local_runner_port, remote_runner_port, local_dashboard_port, remote_dashboard_port):
        if self.ssh_supervisor:
            self.ssh_supervisor.stop()
        self._last_preflight = preflight_ssh(setup, remote_runner_port=remote_runner_port)
        self.ssh_supervisor = self._build_ssh_supervisor(
            setup,
            local_runner_port,
            remote_runner_port,
            local_dashboard_port,
            remote_dashboard_port,
        )
        self.ssh_supervisor.start()

    def _spawn_host_process(self, port, *, allow_fallback=True):
        from scripts.setup_runtime import external_environment, is_frozen
        self.runtime.mkdir(parents=True, exist_ok=True)
        owner = process_identity(os.getpid())
        launch_id = secrets.token_hex(16)
        startup_path = self.runtime.resolve() / f'launch-{launch_id}.json'
        log_path = self.runtime / 'setup-runner.log'
        runner = [str(Path(sys.executable)), '--runner'] if is_frozen() else [str(Path(sys.executable)), '-B', '-m', 'backend.gui_test.execution.host']
        cmd = [
            *runner,
            '--config',
            str(self._config_path().resolve()),
            '--runtime',
            str(self.runtime.resolve()),
            '--port',
            str(port),
            '--launch-id',
            launch_id,
            '--startup-receipt',
            str(startup_path),
            '--owner-pid',
            str(owner['pid']),
            '--owner-created',
            owner['creation_time'],
        ]
        if allow_fallback:
            cmd.append('--allow-port-fallback')
        env = external_environment() if os.name == 'nt' else dict(os.environ)
        env['BSP_CONNECTOR_HOME'] = str(self.home.resolve())
        kwargs = {'stdin': subprocess.DEVNULL, 'env': env}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        with log_path.open('ab') as log:
            process = subprocess.Popen(cmd, stdout=log, stderr=log, **kwargs)
        child = process_identity(process.pid)
        import httpx
        receipt = None
        for _ in range(80):
            if process.poll() is not None:
                raise TestError(f'Host 프로세스가 시작 중 종료되었습니다 (코드 {process.returncode}).', 'HOST_START_FAILED', 500)
            try:
                receipt = read_startup(startup_path, launch_id=launch_id, owner=owner, runner=child)
            except (ValueError, OSError):
                receipt = None
            if receipt is not None:
                url = f"http://127.0.0.1:{receipt['runner_port']}"
                try:
                    with httpx.Client(timeout=1.5, trust_env=False, follow_redirects=False) as c:
                        r = c.get(url + '/v1/identity')
                        if r.status_code == 200 and r.json().get('runner_id') == receipt['runner_id']:
                            if _lock_held(self.runtime / 'runner.lock'):
                                break
                except Exception:
                    pass
            time.sleep(0.1)
        else:
            process.terminate()
            raise TestError('Host 준비 시간이 초과되었습니다.', 'HOST_START_TIMEOUT', 500)

        actual_port = int(receipt['runner_port'])
        host_receipt = {
            'version': 2,
            'launch_id': launch_id,
            'owner': owner,
            'runner': receipt['runner'],
            'runner_id': receipt['runner_id'],
            'runner_port': actual_port,
            'local_state': 'READY',
            'manager_attached': True,
            'started_at': now(),
        }
        write_host_active(self.runtime, host_receipt)
        self.host_process = process
        self.host_launch_id = launch_id
        self.local_runner_port = actual_port
        self.host_url = f'http://127.0.0.1:{actual_port}'
        self.host_runner_id = receipt['runner_id']
        return host_receipt | {'runner_url': self.host_url, 'remote_runner_port': self.remote_runner_port}

    def _stop_host_only(self):
        """Stop ONLY local Host process; NEVER touch SSH -R tunnel."""
        runtime = getattr(self, 'runtime', self.home / 'runtime')
        receipt = read_host_active(runtime)
        if getattr(self, 'host_url', None):
            import httpx
            try:
                with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as c:
                    r = c.post(self.host_url + '/v1/connection-stop')
                    if r.status_code == 409:
                        raise TestError('활성 작업 또는 미정리 작업이 있어 Host를 중지할 수 없습니다.', 'ACTIVE_RUN_BLOCKS_RESTART', 409)
            except TestError:
                raise
            except Exception:
                pass
        proc = getattr(self, 'host_process', None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3.0)
        elif receipt and receipt.get('runner'):
            pid = receipt['runner'].get('pid')
            if pid and process_identity(pid) == receipt['runner']:
                try:
                    import signal
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and _lock_held(runtime / 'runner.lock'):
                    time.sleep(0.1)
        launch_id = getattr(self, 'host_launch_id', None) or (receipt.get('launch_id') if receipt else None)
        if launch_id:
            remove_host_active(runtime, launch_id)
        self.host_process = None
        self.host_launch_id = None

    def restart_host(self):
        with self.control_lock:
            target_port = self.local_runner_port or self.DEFAULT_LOCAL_HOST_PORT
            self._stop_host_only()
            try:
                receipt = self._spawn_host_process(target_port, allow_fallback=False)
            except TestError:
                receipt = self._spawn_host_process(target_port, allow_fallback=True)
            new_port = int(receipt['runner_port'])
            if self.ssh_supervisor and (
                new_port != int(target_port)
                or (
                    hasattr(self.ssh_supervisor, 'actual_local_runner_port')
                    and new_port != int(self.ssh_supervisor.actual_local_runner_port)
                )
            ):
                _, setup, remote_runner_port, remote_dashboard_port, local_dashboard_port = self._resolve_ssh_settings()
                self.ssh_supervisor.update_config(
                    setup,
                    actual_local_runner_port=new_port,
                    remote_runner_port=remote_runner_port,
                    remote_dashboard_port=remote_dashboard_port,
                    local_dashboard_port=local_dashboard_port,
                )
            self._send_bridge_heartbeat()
            return {'restarted': True, 'runner_port': receipt['runner_port'], 'ssh_preserved': bool(self.ssh_supervisor)}

    def reconnect_ssh(self):
        with self.control_lock:
            _, setup, remote_runner_port, remote_dashboard_port, local_dashboard_port = self._resolve_ssh_settings()
            self.remote_runner_port = remote_runner_port
            if not setup.get('server') or not setup.get('account'):
                raise TestError('SSH server/account가 설정되지 않았습니다.', 'SSH_NOT_CONFIGURED', 422)
            local_port = self.local_runner_port or self.DEFAULT_LOCAL_HOST_PORT
            if self.ssh_supervisor:
                self._last_preflight = preflight_ssh(setup, remote_runner_port=remote_runner_port)
                self.ssh_supervisor.reconnect()
                self._send_bridge_heartbeat()
                return self.ssh_supervisor.snapshot()
            self._start_ssh_supervisor(setup, local_port, remote_runner_port, local_dashboard_port, remote_dashboard_port)
            self._send_bridge_heartbeat()
            return self.ssh_supervisor.snapshot()

    def verify_connection(self, *, check_linux=True):
        import httpx
        _, setup, remote_runner_port, remote_dashboard_port, local_dashboard_port = self._resolve_ssh_settings()
        preflight = preflight_ssh(setup, remote_runner_port=remote_runner_port)
        self._last_preflight = preflight
        ssh_snap = self.ssh_supervisor.snapshot() if self.ssh_supervisor else {'ssh_state': 'DISCONNECTED', 'ssh_diagnostic': None, 'tunnel': {}}
        host_ok = False
        host_ident = None
        if self.host_url:
            try:
                with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as c:
                    r = c.get(self.host_url + '/v1/identity')
                    if r.status_code == 200:
                        host_ident = r.json()
                        host_ok = True
            except Exception:
                host_ok = False
        linux_diag = None
        dash_fwd = (ssh_snap.get('tunnel') or {}).get('optional_dashboard_forward') or ssh_snap.get('optional_dashboard_forward')
        if check_linux and remote_dashboard_port and dash_fwd == 'CONNECTED':
            dash_port = (ssh_snap.get('tunnel') or {}).get('local_dashboard_port') or local_dashboard_port
            bootstrap = setup.get('connector_bootstrap')
            from ..core.connector_bootstrap import service_headers
            try:
                headers = service_headers(bootstrap) if bootstrap else {'X-Bsp-Service': 'plugin'}
            except Exception:
                headers = {'X-Bsp-Service': 'plugin'}
            try:
                with httpx.Client(timeout=2.0, trust_env=False, follow_redirects=False) as c:
                    r = c.get(
                        f'http://127.0.0.1:{dash_port}/api/v1/gui-test/live/connector/direct/linux-diagnostics',
                        headers=headers,
                    )
                    if r.status_code == 200:
                        linux_diag = r.json()
            except Exception:
                linux_diag = {'reachable': False}
        result = {
            'checked_at': now(),
            'local_state': 'READY' if host_ok else 'STOPPED',
            'ssh_state': ssh_snap.get('ssh_state', 'DISCONNECTED'),
            'overall_connection_state': 'CONNECTED' if (host_ok and ssh_snap.get('ssh_state') == 'CONNECTED') else (ssh_snap.get('ssh_state') or 'STOPPED'),
            'preflight': preflight,
            'tunnel': ssh_snap.get('tunnel'),
            'ssh_diagnostic': ssh_snap.get('ssh_diagnostic'),
            'host_identity': host_ident,
            'linux_diagnostics': linux_diag,
        }
        self._last_verify_result = result
        self._send_bridge_heartbeat()
        return result

    def connect(self):
        with self.control_lock:
            if getattr(self, 'mirror_applying', False):
                raise TestError('공통 설정을 적용 중입니다.', 'CONNECTOR_BUSY', 409)
            return self._connect()

    def _connect(self, *, desired_revision=None, apply_settings=True):
        from ..execution.force_stop import require_force_complete
        require_force_complete(self.home / 'runtime' / 'force-stop.json')
        from .shared_control import apply_pending
        if apply_settings:
            try:
                apply_pending(self.home, expected_revision=desired_revision)
            except TestError:
                raise
            except Exception:
                pass

        _, setup, remote_runner_port, remote_dashboard_port, local_dashboard_port = self._resolve_ssh_settings()
        self.remote_runner_port = remote_runner_port
        self.stop_event.clear()
        self.error = ''

        if not self._try_reattach_host():
            preferred_local = setup.get('local_runner_port') or self.DEFAULT_LOCAL_HOST_PORT
            self._spawn_host_process(preferred_local, allow_fallback=True)
            if setup.get('server') and setup.get('account'):
                self._start_ssh_supervisor(setup, self.local_runner_port, remote_runner_port, local_dashboard_port, remote_dashboard_port)
            self._send_bridge_heartbeat()

        ssh_state = self.ssh_supervisor.snapshot()['ssh_state'] if self.ssh_supervisor else 'CONFIG_MISSING'
        return {'state': 'CONNECTED' if ssh_state == 'CONNECTED' else 'CONNECTING', 'runner_port': self.local_runner_port}

    def status(self):
        with self.control_lock:
            return copy.deepcopy(self.cached) | {'putty_cleanup': copy.deepcopy(list(self.putty_cleanup.values()))}

    def probe(self):
        if not hasattr(self, 'probe_lock'):
            self.probe_lock = threading.RLock()
        with self.probe_lock:
            return Manager._probe(self)

    def _probe(self):
        from ..execution.launch import read_active
        runtime = getattr(self, 'runtime', self.home / 'runtime')
        host_receipt = read_host_active(runtime)
        if host_receipt is not None or getattr(self, 'host_url', None) or getattr(self, 'ssh_supervisor', None):
            return self._probe_direct(host_receipt)
        # Legacy v1 mock compatibility path (only when no host-active.json / direct supervisor exists).
        receipt = read_active(runtime)
        result = {'state': 'ERROR' if self.error else 'CONNECTING' if self.thread and self.thread.is_alive() else 'DISCONNECTED',
                  'error': self.error, 'boards': [], 'stages': {}, 'dashboard_url': '', 'console': {'boards': [], 'errors': []}, 'executions': []}
        if not receipt:
            return result
        import httpx
        with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
            response = client.get(receipt['runner_url'] + '/v1/inventory'); response.raise_for_status()
            inventory = response.json()
            if inventory['runner_id'] != receipt['runner_id']: raise TestError('Runner receipt identity mismatch', 'RUNNER_CHANGED')
            result.update(boards=inventory['boards'], dashboard_url=receipt['dashboard_url'], fresh=True, last_checked_at=inventory['checked_at'])
            setup = self.settings.read().get('_setup', {})
            result['connection_server'] = {key: setup.get(key) for key in ('server', 'account', 'ssh_port')}
            if self.storage_cache is None or time.monotonic() - self.storage_checked >= 60:
                self.storage_cache = storage_usage(self.home / 'runtime'); self.storage_checked = time.monotonic()
            result['storage'] = dict(self.storage_cache, protected=inventory['host_busy'] or inventory['reserved'])
            result['stages']['local'] = 'READY'; result['stages']['ssh'] = receipt['phase']
            for path, key in (('/console', 'console'), ('/recent-executions', 'recent')):
                if path == '/console': path += '?after=' + str(self.console_cursor) + ('&epoch=' + self.console_epoch if self.console_epoch else '')
                r = client.get(receipt['runner_url'] + '/v1' + path); r.raise_for_status()
                value = r.json()
                if key == 'recent':
                    result['executions'] = value['executions']
                    result['execution_paths'] = value.get('execution_paths', [])
                else:
                    result[key] = value; self.console_cursor = value.get('cursor', 0); self.console_epoch = value.get('epoch')
            bootstrap = self.settings.read().get('_setup', {}).get('connector_bootstrap')
            server_headers = {'X-Bsp-Service': 'plugin'}
            if bootstrap is not None:
                from ..core.connector_bootstrap import verify_service, service_headers
                server_headers = service_headers(bootstrap)
                health = client.get(receipt['dashboard_url'] + '/api/v1/health', headers=server_headers)
                health.raise_for_status()
                verify_service(bootstrap, health.json())
            r = client.post(receipt['dashboard_url'] + '/api/v1/gui-test/live/connector/register',
                            headers=server_headers, json={'url': 'http://127.0.0.1:' + str(receipt['remote_runner_port']), 'runner_id': receipt['runner_id']})
            if r.status_code != 200:
                result['stages']['roundtrip'] = 'REGISTRATION_FAILED'; result['state'] = 'ERROR'
                result['error'] = '역방향 등록 실패 HTTP ' + str(r.status_code)
            else:
                result['server_paths'] = r.json().get('server_paths')
                result['mirror_registration'] = {key: r.json().get(key) for key in ('runner_id', 'config_revision', 'transport_generation')}
                try:
                    status = client.get(receipt['dashboard_url'] + '/api/v1/gui-test/live/connector/test-status', headers=server_headers)
                    status.raise_for_status()
                    result['test_status'] = status.json()
                except Exception:
                    result['test_status'] = dict((getattr(self, 'cached', None) or {}).get('test_status') or {}, stale=True,
                        message='TC 상태 수신 실패 · 과거 수신 정보입니다. 서버·커넥터 버전을 확인하세요.')
                try:
                    from .shared_control import request, remember_desired, acknowledge
                    shared = request(self.home, 'settings')
                    result['shared_settings'] = shared
                    application = shared.get('connector_application', {})
                    remember_desired(self.home, application, receipt['runner_id'])
                    acknowledge(self.home, application, inventory)
                    result['analyses'] = request(self.home, 'analyses')
                except Exception as exc:
                    result['shared_error'] = redact(str(exc))
                result['stages'].update(dashboard='READY', roundtrip='READY'); result['state'] = 'CONNECTED'; result['source_ready'] = r.json().get('source_ready', False)
        return result

    def _probe_direct(self, host_receipt):
        runtime = getattr(self, 'runtime', self.home / 'runtime')
        runner_url = f"http://127.0.0.1:{host_receipt['runner_port']}" if host_receipt else getattr(self, 'host_url', None)
        ssh_sup = getattr(self, 'ssh_supervisor', None)
        ssh_snap = ssh_sup.snapshot() if ssh_sup else {}
        ssh_state = ssh_snap.get('ssh_state') or ('CONNECTED' if (read_ssh_tunnel(runtime) or {}).get('ssh_state') == 'CONNECTED' else 'DISCONNECTED')
        result = {
            'state': 'ERROR' if self.error else 'DISCONNECTED',
            'local_state': 'STOPPED',
            'ssh_state': ssh_state,
            'overall_connection_state': ssh_state,
            'error': self.error,
            'boards': [],
            'stages': {'local': 'STOPPED', 'ssh': ssh_state, 'agent_monitor': 'OPTIONAL_OFFLINE'},
            'dashboard_url': '',
            'console': {'boards': [], 'errors': []},
            'executions': [],
        }
        if not runner_url:
            return result
        import httpx
        with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
            inv_r = client.get(runner_url + '/v1/inventory')
            inv_r.raise_for_status()
            inventory = inv_r.json()
            expected_id = (host_receipt or {}).get('runner_id') or self.host_runner_id
            if expected_id and inventory['runner_id'] != expected_id:
                raise TestError('Runner receipt identity mismatch', 'RUNNER_CHANGED')
            diag_r = client.get(runner_url + '/v1/diagnostics/connection')
            diag = diag_r.json() if diag_r.status_code == 200 else {}
            ts_r = client.get(runner_url + '/v1/test-status')
            test_status = ts_r.json() if ts_r.status_code == 200 else {}
            an_r = client.get(runner_url + '/v1/analyses?status=PENDING')
            analyses = an_r.json().get('analyses', []) if an_r.status_code == 200 else []
            for path, key in (('/console', 'console'), ('/recent-executions', 'recent')):
                if path == '/console':
                    path += '?after=' + str(self.console_cursor) + ('&epoch=' + self.console_epoch if self.console_epoch else '')
                r = client.get(runner_url + '/v1' + path)
                if r.status_code == 200:
                    val = r.json()
                    if key == 'recent':
                        result['executions'] = val.get('executions', [])
                        result['execution_paths'] = val.get('execution_paths', [])
                    else:
                        result[key] = val
                        self.console_cursor = val.get('cursor', 0)
                        self.console_epoch = val.get('epoch')

        setup = self.settings.read().get('_setup', {})
        if self.storage_cache is None or time.monotonic() - self.storage_checked >= 60:
            self.storage_cache = storage_usage(self.home / 'runtime')
            self.storage_checked = time.monotonic()
        local_state = 'READY'
        effective_ssh_state = ssh_snap.get('ssh_state') or diag.get('ssh_state') or ssh_state
        overall = 'CONNECTED' if (local_state == 'READY' and effective_ssh_state == 'CONNECTED') else effective_ssh_state
        agent_peer = (diag.get('peers') or {}).get('agent_monitor') or {'client_status': 'OPTIONAL_OFFLINE'}
        result.update(
            state=overall,
            local_state=local_state,
            ssh_state=effective_ssh_state,
            overall_connection_state=overall,
            runner_id=inventory['runner_id'],
            runner_url=runner_url,
            boards=inventory['boards'],
            fresh=True,
            last_checked_at=inventory['checked_at'],
            connection_server={k: setup.get(k) for k in ('server', 'account', 'ssh_port')},
            storage=dict(self.storage_cache, protected=inventory['host_busy'] or inventory['reserved']),
            diagnostics=diag,
            test_status=test_status,
            active_run=diag.get('active_run') or inventory.get('active_connector_run'),
            pending_analyses=analyses,
            peers=diag.get('peers'),
            peer_warnings=diag.get('peer_warnings', []),
            readiness=diag.get('readiness'),
        )
        tunnel = ssh_snap.get('tunnel') or {}
        result['shared_source'] = [tunnel.get('server'), tunnel.get('account'), tunnel.get('ssh_port'),
                                   tunnel.get('remote_runner_port'), tunnel.get('remote_dashboard_port'), inventory['runner_id']]
        if overall == 'CONNECTED':
            result.update(self._direct_shared_settings(tunnel, diag, inventory['runner_id']))
            shared = result.get('shared_settings')
            if shared:
                root = shared['integration'].get('tc_root') or ''
                if root != (test_status.get('tc_root') or ''):
                    # A path update and a catalog delivery can arrive on different polls.
                    result['test_status'] = dict(test_status, items=[], tc_root=root, has_projection=False,
                                                 projection_stale=True, total_count=0,
                                                 message='현재 Linux TC 경로의 목록 수신 대기 중' if root else 'Linux TC 경로 미설정')
            elif test_status.get('tc_root'):
                result['test_status'] = dict(test_status, projection_stale=True, message='현재 서버 설정 확인 전 · 이전에 받은 TC 목록')
        result['stages'].update(
            local=local_state,
            ssh=effective_ssh_state,
            overall=overall,
            agent_monitor='CONNECTED' if agent_peer.get('client_status') == 'OK' and not agent_peer.get('stale') else 'OPTIONAL_OFFLINE',
        )
        return result

    def reload_connected_settings(self, supervisor):
        snapshot = supervisor.snapshot()
        if snapshot.get('ssh_state') != 'CONNECTED':
            return None
        tunnel = snapshot['tunnel']
        cached = self.cached
        runner_id = self.host_runner_id
        diag = {}
        if (runner_id and cached.get('runner_id') == runner_id and cached.get('fresh')
                and 0 <= time.time() - (cached.get('last_checked_at') or 0) <= 15):
            diag = cached.get('diagnostics') or {}
        result = self._direct_shared_settings(tunnel, diag, runner_id)
        latest = supervisor.snapshot()
        if (self.ssh_supervisor is not supervisor or latest.get('ssh_state') != 'CONNECTED'
                or latest.get('tunnel') != tunnel or self.host_runner_id != runner_id):
            raise TestError('조회 중 연결이 변경됐습니다. 현재 서버의 설정을 다시 불러오세요.', 'CONNECTION_CHANGED', 409)
        if 'shared_settings' in result:
            return result['shared_settings']
        raise TestError(result['shared_error'], result.get('shared_error_code', 'SHARED_SETTINGS_PENDING'),
                        result.get('shared_error_status', 503))

    def _direct_shared_settings(self, tunnel, diag, runner_id):
        from .shared_control import request
        from .ssh_tunnel import _same_linux_host
        from ..core.connector_diagnostics import settings_preview
        port = tunnel.get('remote_dashboard_port') or 8766
        error = (f'보드 연결됨 · Linux 공통 설정 수신 대기 중. Agent Monitor 포트 {port}의 설정 API '
                 '또는 같은 서버 플러그인의 연결 보고를 확인하세요.')
        if tunnel.get('optional_dashboard_forward') == 'CONNECTED':
            try:
                shared = request(self.home, 'settings', direct=True)
                if not (isinstance(shared, dict) and isinstance(shared.get('integration'), dict)
                        and isinstance(shared.get('timeouts'), dict) and shared.get('revision')):
                    raise ValueError('Invalid shared settings')
                return {'shared_settings': shared}
            except TestError as exc:
                if exc.status in (401, 403) or exc.code not in {
                        'CONNECTOR_DISCONNECTED', 'SHARED_UNAVAILABLE', 'SERVER_UNAVAILABLE'}:
                    return {'shared_error': exc.message, 'shared_error_code': exc.code, 'shared_error_status': exc.status}
            except (OSError, ValueError):
                pass
        since = tunnel.get('transport_started_at') or tunnel.get('connected_since')
        server = tunnel.get('server')
        bootstrap = self.settings.read().get('_setup', {}).get('connector_bootstrap') or {}
        # A runtime-pinned profile requires the Linux service identity proof.
        peers = [] if bootstrap.get('identity') else (diag.get('peers') or {}).get('recent', [])
        for peer in peers:
            if not isinstance(peer, dict) or not isinstance(peer.get('linux_diagnostics'), dict):
                continue
            reported = settings_preview(peer['linux_diagnostics'].get('shared_execution_settings'))
            if not reported or reported['revision'] != peer['linux_diagnostics'].get('active_shared_revision'):
                continue
            seen = peer.get('observed_at')
            if (peer.get('client_status') == 'OK' and peer.get('stale') is False
                    and peer.get('expected_runner_id') == runner_id
                    and peer.get('target_port') == tunnel.get('remote_runner_port')
                    and isinstance(since, (int, float)) and isinstance(seen, (int, float))
                    and since <= seen <= time.time() and server and _same_linux_host(peer.get('linux_host'), server)):
                return {'shared_settings': reported}
        probe = getattr(getattr(self, 'ssh_supervisor', None), 'read_linux_settings', None)
        shared = probe() if probe else None
        if shared and shared.get('settings_probe_error'):
            return {'shared_error': '보드 연결됨 · ' + shared['settings_probe_error']
                    + ' 같은 Linux 런타임에서 bsp gui_test settings show로 확인한 뒤 bsp gui_test connect를 실행하세요.'}
        if shared:
            return {'shared_settings': shared}
        return {'shared_error': error}


    def serial_control(self, board_id, manual, *, exclusive=False, lease=None):
        from ..execution.launch import read_active
        import httpx
        runtime = getattr(self, 'runtime', self.home / 'runtime')
        host_receipt = read_host_active(runtime)
        runner_url = (f"http://127.0.0.1:{host_receipt['runner_port']}" if host_receipt and host_receipt.get('runner_port') else None) or getattr(self, 'host_url', None)
        if not runner_url:
            receipt = read_active(runtime)
            runner_url = receipt['runner_url'] if receipt else None
        if not runner_url:
            raise TestError('보드를 먼저 연결하세요.', 'SERIAL_UNAVAILABLE', 409)
        with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
            payload = {'board_id': board_id, 'manual': manual}
            if exclusive:
                payload['exclusive'] = True
            if lease is not None:
                payload['lease'] = lease
            response = client.post(runner_url + '/v1/serial-control', json=payload)
            if response.status_code != 200:
                raise TestError(redact(response.text), 'SERIAL_BUSY', 409)
            return response.json()

    def open_putty(self, board_id):
        with self.control_lock: return self._open_putty(board_id)

    def _open_putty(self, board_id):
        import shutil
        value = self.probe()
        board = next((b for b in value['boards'] if b['board_id'] == board_id), None)
        proxy = board.get('serial_proxy', {}) if board else {}
        port = proxy.get('putty_port')
        if value.get('state') != 'CONNECTED' or value.get('fresh') is not True or value.get('stale') or not board or board.get('stale'):
            raise TestError('보드의 최근 연결 상태를 확인하세요.', 'CONNECTOR_STALE', 409)
        if any(b['state'] in {'RUNNING', 'UNKNOWN', 'RESERVED'} and b.get('serial_proxy', {}).get('owner') != 'manual' for b in value['boards']) or proxy.get('owner'):
            raise TestError('시험·예약·확인 필요 작업 또는 다른 콘솔 입력이 사용 중입니다.', 'SERIAL_BUSY', 409)
        if proxy.get('state') != 'READY' or type(port) is not int or not 1 <= port <= 65535:
            raise TestError('보드 프록시가 준비되지 않았습니다.', 'SERIAL_UNAVAILABLE', 409)
        if proxy.get('putty_connected'): raise TestError('이 보드의 PuTTY 연결이 이미 열려 있습니다.', 'SERIAL_BUSY', 409)
        configured = self.settings.read().get('putty_path')
        candidates = [configured, shutil.which('putty.exe')]
        for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            if os.environ.get(variable): candidates.append(str(Path(os.environ[variable])/'PuTTY'/'putty.exe'))
        executable = next((p for p in candidates if p and Path(p).is_file()), None)
        if not executable: raise TestError('PuTTY를 찾을 수 없습니다. 고급 연결 설정에서 putty.exe를 선택하세요.', 'PUTTY_NOT_FOUND')
        grant = self.serial_control(board_id, True, exclusive=True)
        lease = grant.get('manual_lease')
        if not isinstance(lease, str) or not lease:
            raise TestError('Windows 실행부를 같은 버전으로 갱신한 뒤 다시 연결하세요.', 'PUTTY_CONTROL_VERSION', 409)
        def release(): self._release_putty(board_id, lease)
        try:
            process = subprocess.Popen([executable, '-raw', '127.0.0.1', '-P', str(port)], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        except OSError as exc:
            release()
            raise TestError('PuTTY를 실행할 수 없습니다. 실행 파일 경로를 확인하세요.', 'PUTTY_START_FAILED', 409) from exc
        def finished():
            try: process.wait()
            finally: release()  # A stale window must never release a newer manual grant.
        threading.Thread(target=finished, name='putty-window', daemon=True).start()
        return {'opened':True}

    def _release_putty(self, board_id, lease):
        try:
            self.serial_control(board_id, False, lease=lease)
            return
        except Exception as exc:
            entry = {'board_id':board_id, 'state':'RETRYING', 'attempts':1, 'reason':redact(str(exc))}
            with self.control_lock: self.putty_cleanup[lease] = entry
            self.log.error('PUTTY_RELEASE_FAILED %s', entry['reason'])
        def retry():
            delay = 1
            while not self.shutdown.wait(delay):
                try: self.serial_control(board_id, False, lease=lease)
                except Exception as exc:
                    with self.control_lock:
                        entry['attempts'] += 1; entry['reason'] = redact(str(exc))
                    self.log.error('PUTTY_RELEASE_RETRY %s %s', board_id, entry['attempts'])
                    delay = min(30, delay * 2)
                else:
                    with self.control_lock:
                        if self.putty_cleanup.get(lease) is entry: del self.putty_cleanup[lease]
                    return
        threading.Thread(target=retry, name='putty-input-return', daemon=True).start()

    def disconnect(self):
        with self.control_lock:
            if getattr(self, 'mirror_applying', False):
                raise TestError('공통 설정을 적용 중입니다.', 'CONNECTOR_BUSY', 409)
            return self._disconnect()

    def _disconnect(self):
        import httpx
        from ..execution.launch import read_active
        runtime = getattr(self, 'runtime', self.home / 'runtime')
        try:
            value = self.probe()
        except httpx.HTTPStatusError as exc:
            raise TestError(f'종료 전 상태 조회가 HTTP {exc.response.status_code}로 실패했습니다. Host와 연결 상태를 확인하세요.',
                            'STOP_READINESS_UNAVAILABLE', 502) from exc
        except httpx.RequestError as exc:
            raise TestError('종료 전 상태를 조회할 수 없습니다. Host와 연결 상태를 확인하세요.',
                            'STOP_READINESS_UNAVAILABLE', 503) from exc
        if any(b['state'] in {'RUNNING', 'UNKNOWN', 'RESERVED'} for b in value['boards']):
            raise TestError('진행·예약·종료 불명 작업이 있어 연결을 종료할 수 없습니다.', 'CONNECTOR_BUSY', 409)
        active_run = value.get('active_run')
        if active_run and active_run.get('active'):
            raise TestError('자율 실행 묶음 또는 분석 래치가 남아 있어 연결을 종료할 수 없습니다.', 'CONNECTOR_BUSY', 409)
        if getattr(self, 'host_url', None) or read_host_active(runtime):
            if getattr(self, 'ssh_supervisor', None):
                self.ssh_supervisor.stop()
                self.ssh_supervisor = None
            remove_ssh_tunnel(runtime)
            self._stop_host_only()
            self.host_url = None
            self.host_runner_id = None
            self.stop_event.set()
            return {'state': 'DISCONNECTED'}
        if value.get('dashboard_url'):
            import httpx
            with httpx.Client(timeout=3, trust_env=False, follow_redirects=False) as client:
                bootstrap = self.settings.read().get('_setup', {}).get('connector_bootstrap')
                from ..core.connector_bootstrap import service_headers
                headers = service_headers(bootstrap) if bootstrap else {'X-Bsp-Service': 'plugin'}
                response = client.get(value['dashboard_url'] + '/api/v1/gui-test/live/connector/stop-readiness', headers=headers)
                response.raise_for_status()
                if response.json().get('safe') is not True: raise TestError('대시보드 예약·일시정지·삭제가 남아 있습니다.', 'CONNECTOR_BUSY', 409)
        elif self.thread and self.thread.is_alive():
            raise TestError('연결 준비 상태를 확인한 후 종료하세요.', 'CONNECTOR_BUSY', 409)
        if value.get('dashboard_url'):
            receipt = read_active(self.home/'runtime')
            import httpx
            with httpx.Client(timeout=3,trust_env=False,follow_redirects=False) as client:
                response=client.post(receipt['runner_url']+'/v1/connection-stop')
                response.raise_for_status()
        self.stop_event.set()
        return {'state': 'DISCONNECTING'}


def serve(home):
    if os.name != 'nt': raise SystemExit('Production connector requires Windows; use --preview on Mac')
    from ..execution.force_stop import require_force_complete
    require_force_complete(Path(home) / 'runtime' / 'force-stop.json')
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from scripts.setup_runtime import TokenStore, atomic_write
    home = Path(home)
    with LaunchLock(home / 'runtime' / 'connector-manager.lock'):
        credentials = TokenStore(home / 'manager-control', True)
        if not credentials.path.exists(): credentials.save(secrets.token_urlsafe(48))
        token = credentials.load()
        manager = Manager(home)
        listener = bind_loopback(8773, allow_fallback=True)
        app = create_manager_app(manager, token, browser_origin='http://127.0.0.1:' + str(listener.getsockname()[1]))
        atomic_write(home / 'runtime' / 'connector-manager.json', json.dumps({'owner': process_identity(os.getpid()), 'port': listener.getsockname()[1]}).encode())
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', access_log=False, log_level='warning'))
        server.run(sockets=[listener])


def create_manager_app(manager, token, *, browser_origin=None):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    if not hasattr(manager, 'control_lock'):
        manager.control_lock = threading.RLock()
    from .web import BrowserUI
    from .web_actions import ManagerActions, save_profile
    actions = ManagerActions(manager)
    browser = BrowserUI(actions, browser_origin) if browser_origin else None
    app.state.browser_ui = browser
    @app.middleware('http')
    async def auth(request: Request, call_next):
        if browser and request.url.path.startswith('/ui/'):
            return await browser.guard(request, call_next)
        if (request.client.host not in {'127.0.0.1', '::1'} or request.headers.get('origin') or request.headers.get('sec-fetch-site') or
                not hmac.compare_digest(request.headers.get('authorization', ''), 'Bearer ' + token)):
            return JSONResponse({'message': 'Manager authentication required'}, status_code=401)
        length=request.headers.get('content-length','0')
        if not length.isdigit() or int(length)>65536: return JSONResponse({},status_code=413)
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>65536: return JSONResponse({},status_code=413)
        request._body=bytes(data)
        return await call_next(request)
    @app.exception_handler(TestError)
    async def error(request, exc): return JSONResponse({'code': exc.code, 'message': exc.message}, status_code=exc.status)
    @app.get('/status')
    def status(): return manager.status()
    @app.get('/settings')
    def settings(): return manager.settings.read()
    @app.post('/settings')
    def save(body: dict):
        return save_profile(manager, body)
    @app.post('/server-port')
    def server_port(body: dict):
        if set(body) != {'server_port'}:
            raise TestError('Invalid server port request', 'CONNECTOR_CONFIG', 422)
        from .server_port import save_server_port
        return save_server_port(manager, body['server_port'])
    @app.post('/browser-ticket')
    def browser_ticket():
        if not browser:
            raise TestError('웹 화면을 지원하는 커넥터 Manager로 업데이트하세요. 기존 작업은 유지됩니다.', 'BROWSER_UNAVAILABLE', 409)
        return browser.ticket()
    @app.get('/shared-settings')
    def shared_settings():
        return actions.shared()
    @app.post('/shared-settings')
    def save_shared_settings(body: dict):
        return actions.shared(body)
    @app.get('/storage-policy')
    def storage_policy():
        return actions.storage()
    @app.post('/storage-policy')
    def save_storage_policy(body: dict):
        return actions.storage(body)
    @app.post('/storage-cleanup')
    def storage_cleanup(body: dict):
        return actions.storage(body, cleanup=True)
    @app.post('/server-paths')
    def server_paths(body: dict):
        from .shared_control import paths
        if set(body) - {'kind', 'path'}: raise TestError('Invalid server path request', status=422)
        return paths(manager.home, body.get('kind'), body.get('path', ''))
    @app.post('/connect')
    def connect(): return manager.connect()
    @app.post('/reconnect-ssh')
    def reconnect_ssh(): return manager.reconnect_ssh()
    @app.post('/verify-connection')
    def verify_connection(body: dict | None = None):
        return manager.verify_connection(check_linux=bool((body or {}).get('check_linux', True)))
    @app.post('/restart-host')
    def restart_host(): return manager.restart_host()
    @app.post('/serial-control')
    def serial_control(body: dict):
        if set(body) != {'board_id','manual'} or type(body['manual']) is not bool: raise TestError('Invalid control request', status=422)
        return manager.serial_control(body['board_id'], body['manual'])
    @app.post('/putty')
    def putty(body: dict):
        if set(body) != {'board_id'}: raise TestError('Invalid PuTTY request', status=422)
        return manager.open_putty(body['board_id'])
    @app.post('/disconnect')
    def disconnect(): return manager.disconnect()
    if browser:
        browser.routes(app)
    return app


class Client:
    preview = False
    def __init__(self, home): self.home = Path(home)
    def request(self, path, data=None):
        from scripts.setup_runtime import TokenStore
        import httpx
        from ..execution.launch import _lock_held
        if not _lock_held(self.home/'runtime'/'connector-manager.lock'): raise TestError('Manager receipt is stale','CONNECTOR_STALE')
        receipt = json.loads((self.home / 'runtime' / 'connector-manager.json').read_text())
        if process_identity(receipt['owner']['pid']) != receipt['owner']: raise TestError('Manager receipt is stale', 'CONNECTOR_STALE')
        token = TokenStore(self.home / 'manager-control', True).load(readonly=True)
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False) as client:
            try: response = client.request('GET' if data is None else 'POST', 'http://127.0.0.1:' + str(receipt['port']) + path,
                                      headers={'Authorization': 'Bearer ' + token}, **({'json': data} if data is not None else {}))
            except httpx.HTTPError as exc: raise TestError('Manager connection failed; check its log','CONNECTOR_UNAVAILABLE') from exc
            if response.status_code != 200:
                try: detail = response.json()
                except ValueError: detail = {}
                raise TestError(redact(detail.get('message', response.text)), detail.get('code', 'CONNECTOR_REQUEST'), response.status_code)
            return response.json()
    def status(self): return self.request('/status')
    def settings(self): return self.request('/settings')
    def save(self, value): return self.request('/settings', value)
    def server_port(self, port):
        try:
            return self.request('/server-port', {'server_port': port})
        except TestError as exc:
            if exc.status == 404:
                raise TestError('실행 중인 Manager가 포트 옵션을 지원하지 않습니다. 기존 작업을 마친 뒤 커넥터를 안전 종료하고 갱신한 버전으로 다시 실행하세요.', 'CONNECTOR_UPDATE_REQUIRED', 409) from exc
            raise
    def browser_ticket(self):
        try:
            value = self.request('/browser-ticket', {})
        except TestError as exc:
            if exc.status != 404 and exc.code != 'BROWSER_UNAVAILABLE':
                raise
            raise TestError('실행 중인 Manager의 웹 화면을 열지 못했습니다. 기존 작업을 완료한 뒤 커넥터를 안전 종료하고 같은 버전으로 다시 시작하세요. 작업을 강제 종료하거나 두 번째 Manager를 만들지 않습니다.', 'BROWSER_UNAVAILABLE', 409) from exc
        if value.get('capability') != 'connector_browser_v1':
            raise TestError('Manager의 웹 화면 버전이 일치하지 않습니다.', 'BROWSER_UNAVAILABLE', 409)
        return value
    def storage_policy(self): return self.request('/storage-policy')
    def save_storage_policy(self, value): return self.request('/storage-policy', value)
    def cleanup_snapshots(self, *, dry_run=True): return self.request('/storage-cleanup', {'dry_run': dry_run})
    def shared_settings(self): return self.request('/shared-settings')
    def save_shared_settings(self, value): return self.request('/shared-settings', value)
    def server_paths(self, kind, path=''): return self.request('/server-paths', {'kind': kind, 'path': path})
    def connect(self): return self.request('/connect', {})
    def reconnect_ssh(self): return self.request('/reconnect-ssh', {})
    def verify_connection(self, *, check_linux=True): return self.request('/verify-connection', {'check_linux': check_linux})
    def restart_host(self): return self.request('/restart-host', {})
    def disconnect(self): return self.request('/disconnect', {})
    def manual(self, board_id, enabled): return self.request('/serial-control', {'board_id':board_id, 'manual':enabled})
    def putty(self, board_id): return self.request('/putty', {'board_id':board_id})
    def ports(self):
        from ..adapters.windows_ports import enumerate_ports
        return enumerate_ports()['ports']


def ensure_manager(home):
    if os.name != 'nt': raise TestError('Windows production only. Mac: --preview', 'WINDOWS_REQUIRED')
    # Serialized against the explicit offline emergency command, including reuse.
    with LaunchLock(Path(home) / 'runtime' / 'connector-start.lock'):
        from ..execution.force_stop import require_force_complete
        require_force_complete(Path(home) / 'runtime' / 'force-stop.json')
        return _ensure_manager(home)


def _ensure_manager(home):
    client = Client(home)
    try: client.settings(); return client
    except (OSError, ValueError, TestError): pass
    subprocess.Popen([sys.executable, '-B', '-m', __package__ + '.supervisor', '--home', str(home)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)
    for _ in range(100):
        try: client.settings(); return client
        except (OSError, ValueError, TestError): time.sleep(.1)
    raise TestError('Manager did not start. Check dependencies and user profile.', 'CONNECTOR_START')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--home', required=True)
    serve(parser.parse_args().home)
