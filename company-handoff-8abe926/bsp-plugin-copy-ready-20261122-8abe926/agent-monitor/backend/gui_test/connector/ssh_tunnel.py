"""Independent Windows SSH -R (and optional -L) tunnel supervisor and stderr classifier.

Host lifetime is strictly decoupled from SSH lifetime: SSH drops, retries, or
fatal auth/config failures never kill or stop the local execution Host.
"""
from collections import deque
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time

from ..execution.bundle import external_environment, external_dll_search
from ..execution.launch import LaunchLock, process_identity, write_ssh_tunnel
from .logs import redact

FATAL_SSH_CODES = frozenset({
    'SSH_HOST_KEY_UNTRUSTED',
    'SSH_KEY_PERMISSIONS',
    'SSH_AUTH_FAILED',
    'SSH_FORWARDING_DISABLED',
    'SSH_CONFIG_INCOMPLETE',
    'SSH_BINARY_MISSING',
    'SSH_KEY_NOT_FOUND',
})

TRANSIENT_SSH_CODES = frozenset({
    'SSH_DISCONNECTED',
    'SSH_TIMEOUT',
    'SSH_CONNECTION_REFUSED',
    'SSH_REMOTE_PORT_BUSY',
    'SSH_DNS_FAILED',
    'SSH_CONNECTION_FAILED',
})

BACKOFF_SCHEDULE = (2.0, 4.0, 8.0, 15.0, 30.0)


def _check_windows_key_acl(key_path):
    """Best-effort read-only Windows icacls check for overly permissive private key ACLs."""
    if os.name != 'nt':
        return False
    icacls = shutil.which('icacls')
    if not icacls:
        return False
    try:
        res = subprocess.run(
            [icacls, str(key_path)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        out = res.stdout or ''
        for line in out.splitlines():
            low = line.lower()
            if any(bad in low for bad in ('everyone:', 'builtin\\users:', 'authenticated users:', '\\users:')):
                return True
    except Exception:
        pass
    return False


def _known_hosts_status(server, ssh_port, *, home_dir=None):
    kh = (Path(home_dir) if home_dir is not None else Path.home()) / '.ssh' / 'known_hosts'
    if not kh.is_file():
        return 'missing'
    try:
        text = kh.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return 'unknown'
    host_token = server if ssh_port == 22 else f'[{server}]:{ssh_port}'
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        first = line.split()[0]
        names = first.split(',')
        if host_token in names or server in names:
            return 'present'
    return 'missing'


def preflight_ssh(
    setup_cfg,
    *,
    remote_runner_port=8771,
    home_dir=None,
    env=None,
    which=None,
    connect=None,
    acl_checker=None,
):
    """Non-invasive Windows-side preflight checks before spawning ssh."""
    cfg = setup_cfg if isinstance(setup_cfg, dict) else {}
    server = str(cfg.get('server') or '').strip()
    account = str(cfg.get('account') or '').strip()
    ssh_port = cfg.get('ssh_port', 22)
    ssh_key = str(cfg.get('ssh_key') or '').strip()

    if (not server or not account or
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', server) or
            not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', account) or
            type(ssh_port) is not int or not 1 <= ssh_port <= 65535 or
            type(remote_runner_port) is not int or not 1 <= remote_runner_port <= 65535):
        return {
            'ok': False,
            'code': 'SSH_CONFIG_INCOMPLETE',
            'fatal': True,
            'summary': 'SSH 서버, 계정 또는 포트 설정이 누락되었거나 형식이 올바르지 않습니다.',
            'known_hosts_entry': 'unknown',
            'warnings': [],
            'ssh_path': None,
        }

    ssh_env = env if env is not None else external_environment()
    which_fn = which or (lambda name: shutil.which(name, path=ssh_env.get('PATH')))
    ssh_path = which_fn('ssh')
    if not ssh_path:
        return {
            'ok': False,
            'code': 'SSH_BINARY_MISSING',
            'fatal': True,
            'summary': 'Windows OpenSSH 클라이언트(ssh.exe)를 찾을 수 없습니다.',
            'known_hosts_entry': 'unknown',
            'warnings': [],
            'ssh_path': None,
        }

    warnings = []
    if ssh_key:
        kp = Path(ssh_key)
        if kp.is_symlink() or not kp.is_file():
            return {
                'ok': False,
                'code': 'SSH_KEY_NOT_FOUND',
                'fatal': True,
                'summary': '지정한 SSH 개인키 파일을 찾을 수 없습니다.',
                'known_hosts_entry': 'unknown',
                'warnings': [],
                'ssh_path': ssh_path,
            }
        acl_fn = acl_checker or _check_windows_key_acl
        if acl_fn(kp):
            warnings.append({
                'code': 'SSH_KEY_PERMISSIONS',
                'message': '개인키 파일 ACL에 다른 사용자/그룹 읽기 권한이 포함되어 OpenSSH가 거부할 수 있습니다. icacls로 현재 사용자만 허용하세요.',
            })

    kh_status = _known_hosts_status(server, ssh_port, home_dir=home_dir)
    if kh_status == 'missing':
        warnings.append({
            'code': 'KNOWN_HOSTS_MISSING',
            'message': f'~/.ssh/known_hosts에 {server}:{ssh_port} 호스트 키가 아직 없습니다.',
        })

    conn_fn = connect or socket.create_connection
    try:
        sock = conn_fn((server, ssh_port), timeout=2.5)
        sock.close()
    except socket.gaierror:
        return {
            'ok': False,
            'code': 'SSH_DNS_FAILED',
            'fatal': False,
            'summary': f'SSH 서버 호스트({server}) DNS 이름을 해석할 수 없습니다.',
            'known_hosts_entry': kh_status,
            'warnings': warnings,
            'ssh_path': ssh_path,
        }
    except ConnectionRefusedError:
        return {
            'ok': False,
            'code': 'SSH_CONNECTION_REFUSED',
            'fatal': False,
            'summary': f'{server}:{ssh_port} SSH 포트가 연결을 거부했습니다.',
            'known_hosts_entry': kh_status,
            'warnings': warnings,
            'ssh_path': ssh_path,
        }
    except (TimeoutError, socket.timeout):
        return {
            'ok': False,
            'code': 'SSH_TIMEOUT',
            'fatal': False,
            'summary': f'{server}:{ssh_port} SSH TCP 연결이 시간 초과되었습니다.',
            'known_hosts_entry': kh_status,
            'warnings': warnings,
            'ssh_path': ssh_path,
        }
    except OSError as exc:
        return {
            'ok': False,
            'code': 'SSH_CONNECTION_FAILED',
            'fatal': False,
            'summary': f'{server}:{ssh_port} SSH TCP 연결 실패 ({type(exc).__name__}).',
            'known_hosts_entry': kh_status,
            'warnings': warnings,
            'ssh_path': ssh_path,
        }

    return {
        'ok': True,
        'code': None,
        'fatal': False,
        'summary': 'SSH 사전 점검 통과',
        'known_hosts_entry': kh_status,
        'warnings': warnings,
        'ssh_path': ssh_path,
    }


def build_ssh_r_argv(ssh_bin, setup_cfg, *, actual_local_runner_port, remote_runner_port=8771, ssh_port=22):
    server = setup_cfg['server']
    account = setup_cfg['account']
    ssh_key = str(setup_cfg.get('ssh_key') or '').strip()
    argv = [
        str(ssh_bin), '-NT',
        '-o', 'BatchMode=yes',
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'LogLevel=VERBOSE',
        '-o', 'ServerAliveInterval=15',
        '-o', 'ServerAliveCountMax=3',
        '-o', 'ConnectTimeout=10',
        '-o', 'IdentitiesOnly=yes',
    ]
    if ssh_key:
        argv += ['-i', ssh_key]
    argv += [
        '-p', str(ssh_port),
        '-R', f'127.0.0.1:{remote_runner_port}:127.0.0.1:{actual_local_runner_port}',
        f'{account}@{server}',
    ]
    return argv


def build_ssh_l_argv(ssh_bin, setup_cfg, *, local_dashboard_port, remote_dashboard_port, ssh_port=22):
    server = setup_cfg['server']
    account = setup_cfg['account']
    ssh_key = str(setup_cfg.get('ssh_key') or '').strip()
    argv = [
        str(ssh_bin), '-NT',
        '-o', 'BatchMode=yes',
        '-o', 'ExitOnForwardFailure=yes',
        '-o', 'LogLevel=VERBOSE',
        '-o', 'ServerAliveInterval=15',
        '-o', 'ServerAliveCountMax=3',
        '-o', 'ConnectTimeout=10',
        '-o', 'IdentitiesOnly=yes',
    ]
    if ssh_key:
        argv += ['-i', ssh_key]
    argv += [
        '-p', str(ssh_port),
        '-L', f'127.0.0.1:{local_dashboard_port}:127.0.0.1:{remote_dashboard_port}',
        f'{account}@{server}',
    ]
    return argv


def is_forward_success_line(line, remote_runner_port=8771):
    if re.search(r'remote forward success', line, re.I):
        return True
    if re.search(rf'\bAllocated port\s+{int(remote_runner_port)}\b', line):
        return True
    if re.search(r'All remote forwarding requests succeeded', line, re.I):
        return True
    return False


def classify_ssh_stderr_line(line):
    """Return (code, is_fatal) for an OpenSSH stderr line, or (None, False)."""
    if re.search(r'Host key verification failed|REMOTE HOST IDENTIFICATION HAS CHANGED', line, re.I):
        return 'SSH_HOST_KEY_UNTRUSTED', True
    if re.search(r'UNPROTECTED PRIVATE KEY FILE|Bad permissions', line, re.I):
        return 'SSH_KEY_PERMISSIONS', True
    if re.search(r'Permission denied|Too many authentication failures', line, re.I):
        return 'SSH_AUTH_FAILED', True
    if re.search(r'remote port forwarding failed|listen port .* already in use', line, re.I):
        return 'SSH_REMOTE_PORT_BUSY', False
    if re.search(r'administratively prohibited|Forwarding disabled', line, re.I):
        return 'SSH_FORWARDING_DISABLED', True
    if re.search(r'Could not resolve hostname|Name or service not known|nodename nor servname provided', line, re.I):
        return 'SSH_DNS_FAILED', False
    if re.search(r'Connection refused', line, re.I):
        return 'SSH_CONNECTION_REFUSED', False
    if re.search(r'Connection timed out|Operation timed out', line, re.I):
        return 'SSH_TIMEOUT', False
    return None, False


_DIAG_SUMMARIES = {
    'CONNECTED': 'SSH 역방향 터널 연결 및 원격 포트 바인드 확인됨',
    'SSH_HOST_KEY_UNTRUSTED': 'Linux 서버 호스트 키를 신뢰할 수 없거나 변경되었습니다. OpenSSH known_hosts를 확인하세요.',
    'SSH_KEY_PERMISSIONS': 'SSH 개인키 파일 권한이 너무 개방되어 OpenSSH가 거부했습니다. 현재 사용자만 읽도록 제한하세요.',
    'SSH_AUTH_FAILED': 'SSH 인증에 실패했습니다. 개인키 경로, ssh-agent 또는 Linux authorized_keys를 확인하세요.',
    'SSH_REMOTE_PORT_BUSY': 'Linux 원격 포트(8771 등)가 이미 사용 중입니다. 점유 프로세스를 확인하고 포트를 분리하세요.',
    'SSH_FORWARDING_DISABLED': 'Linux sshd에서 포트 포워딩(AllowTcpForwarding/PermitListen)이 비활성화되어 있습니다.',
    'SSH_DNS_FAILED': 'SSH 서버 주소를 DNS에서 찾을 수 없습니다.',
    'SSH_CONNECTION_REFUSED': 'Linux SSH 포트 연결이 거부되었습니다.',
    'SSH_TIMEOUT': 'Linux SSH 연결 또는 바인드 대기 시간이 초과되었습니다.',
    'SSH_DISCONNECTED': 'SSH 터널이 끊어져 재연결을 시도 중입니다.',
}


class SshTunnelSupervisor:
    """Supervises the SSH -R process (and optional isolated -L process) independently of Host."""

    def __init__(
        self,
        runtime,
        setup_cfg,
        *,
        actual_local_runner_port,
        remote_runner_port=8771,
        remote_dashboard_port=None,
        local_dashboard_port=None,
        ssh_port=None,
        bind_timeout=15.0,
        stability_window=0.25,
        backoff_schedule=BACKOFF_SCHEDULE,
        popen=None,
        preflight_fn=None,
    ):
        self.runtime = Path(runtime)
        self.setup_cfg = dict(setup_cfg or {})
        self.actual_local_runner_port = int(actual_local_runner_port)
        self.remote_runner_port = int(remote_runner_port)
        self.remote_dashboard_port = int(remote_dashboard_port) if remote_dashboard_port else None
        self.local_dashboard_port = int(local_dashboard_port) if local_dashboard_port else None
        self.ssh_port = int(ssh_port if ssh_port is not None else self.setup_cfg.get('ssh_port', 22) or 22)
        self.bind_timeout = bind_timeout
        self.stability_window = stability_window
        self.backoff_schedule = tuple(backoff_schedule)
        self._popen = popen or subprocess.Popen
        self._preflight_fn = preflight_fn or preflight_ssh

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread = None
        self._lines = deque(maxlen=100)

        self.ssh_state = 'NOT_CONFIGURED' if not (self.setup_cfg.get('server') and self.setup_cfg.get('account')) else 'CONNECTING'
        self.last_error_code = None
        self.last_error_detail = ''
        self.last_preflight = None
        self.connected_since = None
        self.reconnect_attempts = 0
        self.optional_dashboard_forward = 'NOT_CONFIGURED' if self.remote_dashboard_port is None else 'CONNECTING'
        self._r_proc = None
        self._l_proc = None
        self._manual_reconnect_requested = False

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._wake_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name='ssh-tunnel-supervisor', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._wake_event.set()
        self._terminate_procs()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        with self._lock:
            self.ssh_state = 'STOPPED'
            self._write_receipt(None, None)

    def reconnect(self):
        with self._lock:
            self._manual_reconnect_requested = True
            if self.ssh_state == 'AUTH_OR_CONFIG_ERROR':
                self.ssh_state = 'CONNECTING'
            self.reconnect_attempts = 0
        self._terminate_procs()
        self._wake_event.set()

    def update_config(self, setup_cfg, *, actual_local_runner_port=None, remote_runner_port=None,
                      remote_dashboard_port=None, local_dashboard_port=None, ssh_port=None):
        with self._lock:
            self.setup_cfg = dict(setup_cfg or {})
            if actual_local_runner_port is not None:
                self.actual_local_runner_port = int(actual_local_runner_port)
            if remote_runner_port is not None:
                self.remote_runner_port = int(remote_runner_port)
            self.remote_dashboard_port = int(remote_dashboard_port) if remote_dashboard_port else None
            self.local_dashboard_port = int(local_dashboard_port) if local_dashboard_port else None
            self.ssh_port = int(ssh_port if ssh_port is not None else self.setup_cfg.get('ssh_port', 22) or 22)
            self.reconnect_attempts = 0
            self._manual_reconnect_requested = True
            if self.ssh_state in {'AUTH_OR_CONFIG_ERROR', 'NOT_CONFIGURED'}:
                self.ssh_state = 'CONNECTING'
        self._terminate_procs()
        self._wake_event.set()

    def _terminate_proc(self, proc):
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass

    def _terminate_procs(self):
        with self._lock:
            r_proc, l_proc = self._r_proc, self._l_proc
            self._r_proc = None
            self._l_proc = None
        self._terminate_proc(l_proc)
        self._terminate_proc(r_proc)

    def _write_receipt(self, r_id, l_id):
        try:
            write_ssh_tunnel(self.runtime, {
                'version': 2,
                'transport': r_id,
                'dashboard_transport': l_id,
                'remote_runner_port': self.remote_runner_port,
                'remote_dashboard_port': self.remote_dashboard_port,
                'local_dashboard_port': self.local_dashboard_port,
                'ssh_port': self.ssh_port,
                'ssh_state': self.ssh_state,
                'last_error_code': self.last_error_code,
                'connected_since': self.connected_since,
                'reconnect_attempts': self.reconnect_attempts,
            })
        except Exception:
            pass

    def _start_optional_dashboard_forward(self, ssh_bin, cfg, ssh_env):
        if self.remote_dashboard_port is None or self.local_dashboard_port is None:
            with self._lock:
                self.optional_dashboard_forward = 'NOT_CONFIGURED'
            return None
        argv = build_ssh_l_argv(
            ssh_bin, cfg,
            local_dashboard_port=self.local_dashboard_port,
            remote_dashboard_port=self.remote_dashboard_port,
            ssh_port=self.ssh_port,
        )
        try:
            kwargs = {
                'stdin': subprocess.DEVNULL,
                'stdout': subprocess.DEVNULL,
                'stderr': subprocess.DEVNULL,
                'env': ssh_env,
            }
            if os.name == 'nt':
                kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
            with external_dll_search():
                proc = self._popen(argv, **kwargs)
            time.sleep(0.15)
            if proc.poll() is not None:
                with self._lock:
                    self.optional_dashboard_forward = 'LOCAL_DASHBOARD_FORWARD_SKIPPED'
                return None
            with self._lock:
                if self._stop_event.is_set():
                    self._terminate_proc(proc)
                    return None
                self._l_proc = proc
                self.optional_dashboard_forward = 'CONNECTED'
            return proc
        except Exception:
            with self._lock:
                self.optional_dashboard_forward = 'LOCAL_DASHBOARD_FORWARD_SKIPPED'
            return None

    def _run_loop(self):
        lock_file = self.runtime / 'ssh-tunnel.lock'
        with LaunchLock(lock_file):
            backoff_idx = 0
            while not self._stop_event.is_set():
                with self._lock:
                    cfg = dict(self.setup_cfg)
                    self._manual_reconnect_requested = False
                    if not str(cfg.get('server') or '').strip() and not str(cfg.get('account') or '').strip():
                        self.ssh_state = 'NOT_CONFIGURED'
                        self.last_error_code = 'SSH_CONFIG_INCOMPLETE'
                        self.last_error_detail = 'SSH 서버와 계정이 아직 설정되지 않았습니다.'
                        self.connected_since = None
                        self._write_receipt(None, None)
                        unconfigured = True
                    else:
                        unconfigured = False
                        if self.reconnect_attempts == 0:
                            self.ssh_state = 'CONNECTING'
                        else:
                            self.ssh_state = 'RECONNECTING'
                        self._write_receipt(None, None)
                if unconfigured:
                    self._wait_until_manual_or_stop()
                    backoff_idx = 0
                    continue

                preflight = self._preflight_fn(
                    dict(cfg, ssh_port=self.ssh_port),
                    remote_runner_port=self.remote_runner_port,
                )
                with self._lock:
                    self.last_preflight = preflight

                if not preflight['ok']:
                    code = preflight['code']
                    fatal = preflight['fatal']
                    with self._lock:
                        self.last_error_code = code
                        self.last_error_detail = preflight['summary']
                        self.connected_since = None
                        self.ssh_state = 'AUTH_OR_CONFIG_ERROR' if fatal else 'RECONNECTING'
                        self._write_receipt(None, None)
                    if fatal:
                        self._wait_until_manual_or_stop()
                        backoff_idx = 0
                        continue
                    self._wait_backoff(backoff_idx)
                    backoff_idx = min(backoff_idx + 1, len(self.backoff_schedule) - 1)
                    continue

                ssh_bin = preflight['ssh_path']
                ssh_env = external_environment()
                argv = build_ssh_r_argv(
                    ssh_bin, cfg,
                    actual_local_runner_port=self.actual_local_runner_port,
                    remote_runner_port=self.remote_runner_port,
                    ssh_port=self.ssh_port,
                )
                try:
                    kwargs = {
                        'stdin': subprocess.DEVNULL,
                        'stdout': subprocess.PIPE,
                        'stderr': subprocess.PIPE,
                        'text': True,
                        'encoding': 'utf-8',
                        'errors': 'replace',
                        'env': ssh_env,
                    }
                    if os.name == 'nt':
                        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
                    with external_dll_search():
                        proc = self._popen(argv, **kwargs)
                except OSError as exc:
                    with self._lock:
                        self.last_error_code = 'SSH_CONNECTION_FAILED'
                        self.last_error_detail = redact(str(exc))
                        self.ssh_state = 'RECONNECTING'
                        self.reconnect_attempts += 1
                        self._write_receipt(None, None)
                    self._wait_backoff(backoff_idx)
                    backoff_idx = min(backoff_idx + 1, len(self.backoff_schedule) - 1)
                    continue

                r_id = process_identity(proc.pid)
                with self._lock:
                    self._r_proc = proc
                    self._write_receipt(r_id, None)

                bind_confirmed, code, is_fatal, detail = self._monitor_ssh_process(proc, r_id)
                self._terminate_proc(proc)
                with self._lock:
                    if self._l_proc is not None:
                        self._terminate_proc(self._l_proc)
                        self._l_proc = None
                    self._r_proc = None
                    self.connected_since = None
                    if self._stop_event.is_set():
                        self.ssh_state = 'STOPPED'
                        self._write_receipt(None, None)
                        break
                    if self._manual_reconnect_requested:
                        self._write_receipt(None, None)
                        backoff_idx = 0
                        continue
                    self.last_error_code = code or 'SSH_DISCONNECTED'
                    self.last_error_detail = detail or _DIAG_SUMMARIES.get(self.last_error_code, '')
                    if is_fatal or self.last_error_code in FATAL_SSH_CODES:
                        self.ssh_state = 'AUTH_OR_CONFIG_ERROR'
                        self._write_receipt(None, None)
                    else:
                        self.ssh_state = 'RECONNECTING'
                        self.reconnect_attempts += 1
                        self._write_receipt(None, None)
                        if bind_confirmed:
                            backoff_idx = 0

                if self.ssh_state == 'AUTH_OR_CONFIG_ERROR':
                    self._wait_until_manual_or_stop()
                    backoff_idx = 0
                else:
                    self._wait_backoff(backoff_idx)
                    backoff_idx = min(backoff_idx + 1, len(self.backoff_schedule) - 1)

    def _monitor_ssh_process(self, proc, r_id):
        """Read stderr/stdout, verify real bind + stability window, and stay alive until exit."""
        classified = {'code': None, 'fatal': False, 'detail': '', 'success_at': None}
        event_lock = threading.Lock()

        def read_stream(stream):
            if stream is None:
                return
            try:
                while True:
                    raw = stream.readline()
                    if not raw:
                        break
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8', errors='replace')
                    line = redact(raw.rstrip('\r\n'))
                    with self._lock:
                        self._lines.append(line)
                    with event_lock:
                        if is_forward_success_line(line, self.remote_runner_port) and classified['success_at'] is None:
                            classified['success_at'] = time.monotonic()
                        code, fatal = classify_ssh_stderr_line(line)
                        if code and (classified['code'] is None or fatal):
                            classified['code'] = code
                            classified['fatal'] = fatal
                            classified['detail'] = line
            except Exception:
                pass

        t_err = threading.Thread(target=read_stream, args=(proc.stderr,), daemon=True)
        t_out = threading.Thread(target=read_stream, args=(proc.stdout,), daemon=True)
        t_err.start()
        t_out.start()

        deadline = time.monotonic() + self.bind_timeout
        bind_confirmed = False
        while not self._stop_event.is_set() and not self._manual_reconnect_requested:
            with event_lock:
                code = classified['code']
                fatal = classified['fatal']
                detail = classified['detail']
                success_at = classified['success_at']

            if code is not None and not bind_confirmed:
                return False, code, fatal, detail

            if not bind_confirmed and success_at is not None:
                if time.monotonic() - success_at >= self.stability_window:
                    if proc.poll() is None:
                        bind_confirmed = True
                        # Start optional -L in isolated non-blocking subprocess before advertising CONNECTED
                        l_proc = self._start_optional_dashboard_forward(
                            self.last_preflight['ssh_path'],
                            self.setup_cfg,
                            external_environment(),
                        )
                        l_id = process_identity(l_proc.pid) if l_proc and l_proc.poll() is None else None
                        with self._lock:
                            self.ssh_state = 'CONNECTED'
                            self.last_error_code = None
                            self.last_error_detail = ''
                            self.connected_since = time.time()
                            self.reconnect_attempts = 0
                            self._write_receipt(r_id, l_id)

            if proc.poll() is not None:
                t_err.join(timeout=0.5)
                t_out.join(timeout=0.5)
                with event_lock:
                    code = classified['code']
                    fatal = classified['fatal']
                    detail = classified['detail']
                if not bind_confirmed:
                    return False, code or 'SSH_DISCONNECTED', fatal, detail or f'SSH exited with code {proc.returncode}'
                return True, code or 'SSH_DISCONNECTED', fatal, detail or f'SSH exited with code {proc.returncode}'

            if not bind_confirmed and time.monotonic() >= deadline:
                return False, 'SSH_TIMEOUT', False, f'{self.bind_timeout}초 내에 SSH -R 포트 바인드가 확인되지 않았습니다.'

            time.sleep(0.05)
        return bind_confirmed, None, False, ''

    def _wait_until_manual_or_stop(self):
        while not self._stop_event.is_set() and not self._manual_reconnect_requested:
            self._wake_event.wait(0.5)
            self._wake_event.clear()

    def _wait_backoff(self, idx):
        delay = self.backoff_schedule[min(idx, len(self.backoff_schedule) - 1)]
        deadline = time.monotonic() + delay
        while not self._stop_event.is_set() and not self._manual_reconnect_requested and time.monotonic() < deadline:
            self._wake_event.wait(min(0.2, max(0.01, deadline - time.monotonic())))
            self._wake_event.clear()

    def snapshot(self, *, local_state='READY'):
        with self._lock:
            ssh_state = self.ssh_state
            code = self.last_error_code
            if local_state == 'READY' and ssh_state == 'CONNECTED':
                overall = 'CONNECTED'
                diag_code = 'CONNECTED'
                severity = 'info'
            elif local_state == 'READY' and ssh_state in {'CONNECTING', 'RECONNECTING'}:
                overall = 'DEGRADED_SSH_RECONNECTING'
                diag_code = code or 'SSH_DISCONNECTED'
                severity = 'warning'
            elif ssh_state == 'AUTH_OR_CONFIG_ERROR' or local_state == 'FAILED':
                overall = 'ERROR'
                diag_code = code or 'SSH_AUTH_FAILED'
                severity = 'error'
            else:
                overall = 'DISCONNECTED'
                diag_code = code or 'SSH_DISCONNECTED'
                severity = 'warning' if ssh_state != 'STOPPED' else 'info'
            summary = self.last_error_detail or _DIAG_SUMMARIES.get(diag_code, diag_code)
            return {
                'overall_connection_state': overall,
                'local_state': local_state,
                'ssh_state': ssh_state,
                'tunnel': {
                    'server': self.setup_cfg.get('server', ''),
                    'account': self.setup_cfg.get('account', ''),
                    'ssh_port': self.ssh_port,
                    'remote_runner_port': self.remote_runner_port,
                    'actual_local_runner_port': self.actual_local_runner_port,
                    'remote_dashboard_port': self.remote_dashboard_port,
                    'local_dashboard_port': self.local_dashboard_port,
                    'optional_dashboard_forward': self.optional_dashboard_forward,
                    'connected_since': self.connected_since,
                    'reconnect_attempts': self.reconnect_attempts,
                },
                'ssh_diagnostic': {
                    'code': diag_code,
                    'severity': severity,
                    'summary': summary,
                    'detail': self.last_error_detail,
                    'recent_redacted_lines': list(self._lines),
                    'preflight': self.last_preflight,
                },
            }
