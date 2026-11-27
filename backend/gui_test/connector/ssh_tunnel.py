"""Independent Windows SSH -R (and optional -L) tunnel supervisor and stderr classifier.

Host lifetime is strictly decoupled from SSH lifetime: SSH drops, retries, or
fatal auth/config failures never kill or stop the local execution Host.
"""
from collections import deque
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time

from ..execution.bundle import external_environment, external_dll_search
from ..execution.launch import LaunchLock, process_identity, read_host_active, write_ssh_tunnel
from .logs import redact
from . import ssh_ownership

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


def _ssh_login_args(ssh_bin, setup_cfg, ssh_port):
    argv = [str(ssh_bin), '-T', '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
            '-o', 'ConnectTimeout=10', '-p', str(ssh_port)]
    ssh_key = str(setup_cfg.get('ssh_key') or '').strip()
    if ssh_key:
        argv += ['-i', ssh_key]
    return argv


def build_ssh_r_argv(ssh_bin, setup_cfg, *, actual_local_runner_port, remote_runner_port=8771, ssh_port=22):
    return _ssh_login_args(ssh_bin, setup_cfg, ssh_port) + [
        '-N', '-o', 'ExitOnForwardFailure=yes', '-o', 'LogLevel=DEBUG1',
        '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3',
        '-R', f'127.0.0.1:{remote_runner_port}:127.0.0.1:{actual_local_runner_port}',
        f"{setup_cfg['account']}@{setup_cfg['server']}",
    ]


_MAX_IDENTITY_BYTES = 65536


def _read_probe(proc, timeout, cancelled):
    """Limit bytes even when a forced command ignores curl's size limit."""
    limit = _MAX_IDENTITY_BYTES + 4  # newline and three-digit HTTP status
    output = bytearray()

    def read_stdout():
        output.extend(proc.stdout.read(limit + 1))
        if len(output) > limit:
            proc.kill()

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    try:
        while proc.poll() is None:
            if cancelled() or time.monotonic() >= deadline:
                proc.kill()
                proc.wait()
                raise subprocess.TimeoutExpired(proc.args, timeout)
            try:
                proc.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                continue
    finally:
        reader.join(timeout=1)
    if reader.is_alive() or len(output) > limit:
        raise ValueError('Incomplete or oversized probe response')
    return bytes(output)


def probe_remote_identity(ssh_bin, cfg, ssh_port, remote_port, runner_id, timeout, cancelled):
    """Return match, mismatch, or None when the finite SSH probe has no usable HTTP result."""
    if not runner_id:
        return False, '현재 Windows Host의 runner_id 확인 대기 중입니다.'
    url = f'http://127.0.0.1:{int(remote_port)}/v1/identity'
    command = (f"curl -q --noproxy '*' --silent --max-time 3 --max-filesize {_MAX_IDENTITY_BYTES} "
               f"--write-out '\\n%{{http_code}}' '{url}'")
    argv = _ssh_login_args(ssh_bin, cfg, ssh_port) + [
        '-o', 'ClearAllForwardings=yes', f"{cfg['account']}@{cfg['server']}", command,
    ]
    try:
        with external_dll_search():
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, env=external_environment(),
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with proc:
            output = _read_probe(proc, timeout, cancelled)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None, 'Linux identity 요청의 응답 크기, 실행 시간 또는 SSH 실행 상태를 확인하세요'
    if proc.returncode:
        return None, f'Linux identity 확인 명령 종료 코드 {proc.returncode} (SSH 원격 명령·curl·포트 확인)'
    body, _, status = output.rpartition(b'\n')
    if not status.isdigit() or len(status) != 3:
        return None, 'Linux 확인 명령에서 HTTP 상태를 수신하지 못했습니다'
    if status != b'200':
        return False, 'Linux /v1/identity의 HTTP 200 응답 확인 실패'
    try:
        ident = json.loads(body)
    except (ValueError, RecursionError):
        return False, 'Linux /v1/identity의 JSON 응답 확인 실패'
    if (not isinstance(ident, dict) or ident.get('service') != 'bsp-board-connector'
            or ident.get('schema_version') != 'direct-connector-v1'):
        return False, 'Linux 포트에서 다른 서비스 또는 호환되지 않는 identity 응답'
    if ident.get('runner_id') != runner_id:
        return False, 'Linux 포트의 runner_id와 현재 Windows Host가 다릅니다.'
    return True, ''


def probe_remote_listener(target):
    """Check Linux listener state after local shutdown without requesting a forward."""
    port = target['remote_runner_port']
    report = {key: target[key] for key in ('server', 'account', 'ssh_port', 'remote_runner_port')}
    report.update(state='UNKNOWN', listeners=[])
    marker = 'connector-ss-' + secrets.token_hex(12)
    # Give sshd a short grace period to release its listener before reporting BUSY.
    command = (f"for delay in 0 1 1; do sleep $delay; "
               f"rows=$(LC_ALL=C ss -H -ltnp 'sport = :{port}') || exit 1; "
               f'if [ -z "$rows" ]; then echo {marker}-FREE; exit 0; fi; done; '
               f"echo {marker}-BUSY; printf '%s\\n' \"$rows\"")
    try:
        env = external_environment()
        ssh = shutil.which('ssh', path=env.get('PATH'))
    except (OSError, ValueError):
        return report
    if not ssh:
        return report
    argv = _ssh_login_args(ssh, target, target['ssh_port']) + [
        '-o', 'ClearAllForwardings=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ControlPath=none',
        f"{target['account']}@{target['server']}", command,
    ]
    try:
        with external_dll_search():
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, env=env,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        with proc:
            data = _read_probe(proc, 10, lambda: False)
        if proc.returncode:
            return report
        lines = data.decode('utf-8', errors='replace').splitlines()
        if lines == [marker + '-FREE']:
            report['state'] = 'FREE'
        elif lines[:1] == [marker + '-BUSY']:
            for line in lines[1:]:
                fields = line.split(maxsplit=5)
                if len(fields) < 5 or fields[0] != 'LISTEN' or not fields[3].endswith(f':{port}'):
                    return dict(report, state='UNKNOWN', listeners=[])
                report['listeners'].append({'address': fields[3], 'process': fields[5][:256] if len(fields) > 5 else None})
            if report['listeners']:
                report['state'] = 'BUSY'
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return report


def _same_linux_host(reported, configured):
    if not isinstance(reported, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', reported):
        return False
    if reported.rstrip('.').casefold() == configured.rstrip('.').casefold():
        return True
    try:
        def addresses(host):
            return {addr[4][0] for addr in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        return not addresses(reported).isdisjoint(addresses(configured))
    except (OSError, UnicodeError):
        return False


def _recent_linux_probe(local_port, server, remote_port, runner_id, started_at):
    """Use the Linux client's own identity check when remote commands are restricted."""
    import httpx
    if not runner_id:
        return False
    try:
        with httpx.Client(timeout=1, trust_env=False) as client:
            response = client.get(f'http://127.0.0.1:{local_port}/v1/diagnostics/connection')
            response.raise_for_status()
            diag = response.json()
        if diag['runner_id'] != runner_id:
            return False
        return any(
            peer['client_status'] == 'OK' and peer['stale'] is False
            and started_at <= peer['observed_at'] <= time.time()
            and peer['target_port'] == remote_port
            and _same_linux_host(peer['linux_host'], server)
            and peer.get('expected_runner_id') in (None, runner_id)
            for peer in diag['peers']['recent']
        )
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError):
        return False


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


def classify_ssh_stderr_line(line):
    """Return (code, is_fatal) for an OpenSSH stderr line, or (None, False)."""
    # Forwarded channel errors concern the Host behind the tunnel.
    if re.search(r'\bchannel \d+:|\bconnect_to\b', line, re.I):
        return None, False
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
        bind_timeout=60.0,
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

    def _remember_ssh(self, proc, target, forward):
        try:
            identity = process_identity(proc.pid)
            if identity:
                ssh_ownership.update(self.runtime, target=target, processes=[identity], forward=forward)
            elif os.name == 'nt' and proc.poll() is None:
                raise OSError('실행 중인 SSH의 프로세스 생성 시각을 확인할 수 없습니다.')
            return identity
        except (OSError, ValueError, KeyError, TypeError):
            self._terminate_proc(proc)
            raise

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

    def _start_optional_dashboard_forward(self, ssh_bin, cfg, ssh_env, target):
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
            self._remember_ssh(proc, target, '-L')
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

    def _cancelled(self):
        return self._stop_event.is_set() or self._manual_reconnect_requested

    def _runner_id(self):
        try:
            host = read_host_active(self.runtime) or {}
        except (OSError, ValueError):
            return None
        if host.get('runner_port') == self.actual_local_runner_port and host.get('local_state') == 'READY':
            return host['runner_id']
        return None

    def _run_loop(self):
        lock_file = self.runtime / 'ssh-tunnel.lock'
        with LaunchLock(lock_file):
            backoff_idx = 0
            while True:
                with self._lock:
                    cfg = dict(self.setup_cfg)
                    self._manual_reconnect_requested = False
                try:
                    ssh_ownership.preserve_previous(self.runtime)
                except (OSError, ValueError) as exc:
                    self._wait_for_ownership_repair(exc)
                    if self._stop_event.is_set():
                        return
                    continue
                if self._stop_event.is_set():
                    break
                with self._lock:
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
                ssh_port, remote_port = self.ssh_port, self.remote_runner_port
                try:
                    target = ssh_ownership.endpoint(cfg, ssh_port, remote_port)
                    ownership = ssh_ownership.update(self.runtime, target=target)
                except (OSError, ValueError) as exc:
                    self._wait_for_ownership_repair(exc)
                    continue
                runner_id = self._runner_id()
                if runner_id:
                    already_serving, _ = probe_remote_identity(
                        ssh_bin, cfg, ssh_port, remote_port, runner_id, self.bind_timeout, self._cancelled,
                    )
                    if self._cancelled():
                        continue
                    if already_serving:
                        try:
                            pid = ssh_ownership.matching_reverse_pid(ownership, target)
                        except OSError:
                            pid = None
                        if pid:
                            guidance = (f'같은 접속 설정으로 실행한 이 프로필의 이전 주 SSH(PID {pid})가 남아 있습니다. '
                                        '진행 중인 작업을 확인한 뒤 같은 프로필에서 --force-stop을 실행하고 다시 시작하세요.')
                        else:
                            guidance = ('이 프로필의 기존 주 SSH를 확인할 수 없습니다. 수동 터널 또는 다른 프로필을 '
                                        '사용 중인지 확인하세요. 기존 연결을 계속 쓰거나 소유자가 포트를 비우면 자동 재시도합니다.')
                        with self._lock:
                            self.ssh_state = 'RECONNECTING'
                            self.last_error_code = 'SSH_REMOTE_PORT_BUSY'
                            self.last_error_detail = (f'주 SSH 시작 전에 Linux {remote_port}에서 현재 Host의 identity가 '
                                                      f'응답했습니다. {guidance}')
                            self._write_receipt(None, None)
                        self._wait_backoff(backoff_idx)
                        backoff_idx = min(backoff_idx + 1, len(self.backoff_schedule) - 1)
                        continue
                argv = build_ssh_r_argv(
                    ssh_bin, cfg,
                    actual_local_runner_port=self.actual_local_runner_port,
                    remote_runner_port=remote_port,
                    ssh_port=ssh_port,
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
                    r_id = self._remember_ssh(proc, target, '-R')
                except (OSError, ValueError) as exc:
                    with self._lock:
                        self.last_error_code = 'SSH_CONNECTION_FAILED'
                        self.last_error_detail = redact(str(exc))
                        self.ssh_state = 'RECONNECTING'
                        self.reconnect_attempts += 1
                        self._write_receipt(None, None)
                    self._wait_backoff(backoff_idx)
                    backoff_idx = min(backoff_idx + 1, len(self.backoff_schedule) - 1)
                    continue

                with self._lock:
                    self._r_proc = proc
                    self._write_receipt(r_id, None)

                bind_confirmed, code, is_fatal, detail = self._monitor_ssh_process(proc, r_id, ssh_bin, cfg, ssh_port, remote_port)
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

            if self.last_error_code != 'SSH_OWNERSHIP_UNAVAILABLE':
                with self._lock:
                    self.ssh_state = 'STOPPED'
                    self._write_receipt(None, None)

    def _monitor_ssh_process(self, proc, r_id, ssh_bin, cfg, ssh_port, remote_port):
        """Classify SSH errors and probe Linux until this tunnel exits or is stopped."""
        classified = {'code': None, 'fatal': False, 'detail': ''}
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

        started_at = time.time()
        proof = 'Linux /v1/identity HTTP 200'
        next_probe = time.monotonic() + self.stability_window
        probe_delay = 1.0
        bind_confirmed = False
        verified_at = None
        while not self._stop_event.is_set() and not self._manual_reconnect_requested:
            if proc.poll() is not None:
                t_err.join(timeout=0.5)
                t_out.join(timeout=0.5)
                with event_lock:
                    code = classified['code']
                    fatal = classified['fatal']
                    detail = classified['detail']
                return bind_confirmed, code or 'SSH_DISCONNECTED', fatal, detail or f'SSH exited with code {proc.returncode}'

            with event_lock:
                if classified['code'] and not bind_confirmed:
                    return False, classified['code'], classified['fatal'], classified['detail']

            if not bind_confirmed and verified_at is None and time.monotonic() >= next_probe:
                runner_id = self._runner_id()
                verified, detail = probe_remote_identity(
                    ssh_bin, cfg, ssh_port, remote_port, runner_id, self.bind_timeout,
                    lambda: self._cancelled() or proc.poll() is not None,
                )
                if verified is None:
                    verified = _recent_linux_probe(self.actual_local_runner_port, cfg['server'], remote_port,
                                                  runner_id, started_at)
                    if verified:
                        proof = 'Linux 클라이언트 /v1/identity 검증 (peer/hello)'
                if verified:
                    verified_at = time.monotonic()
                else:
                    with self._lock:
                        self.last_error_code = 'SSH_BIND_UNVERIFIED'
                        self.last_error_detail = f'Linux 127.0.0.1:{remote_port} — {detail}. 주 SSH 유지 중.'
                    next_probe = time.monotonic() + probe_delay
                    probe_delay = min(probe_delay * 2, self.bind_timeout, 15.0)
                continue

            if verified_at is not None and not bind_confirmed and time.monotonic() - verified_at >= self.stability_window:
                l_proc = self._start_optional_dashboard_forward(
                    ssh_bin, cfg, external_environment(), ssh_ownership.endpoint(cfg, ssh_port, remote_port),
                )
                l_id = process_identity(l_proc.pid) if l_proc and l_proc.poll() is None else None
                with self._lock:
                    if proc.poll() is not None or self._manual_reconnect_requested or self._stop_event.is_set():
                        continue
                    with event_lock:
                        if classified['code']:
                            continue
                    bind_confirmed = True
                    self.ssh_state = 'CONNECTED'
                    self.last_error_code = None
                    self.last_error_detail = ''
                    self.connected_since = time.time()
                    self.reconnect_attempts = 0
                    self._lines.append(f'{proof}, 포트 {remote_port}, Windows runner_id 일치')
                    self._write_receipt(r_id, l_id)

            time.sleep(0.05)
        return bind_confirmed, None, False, ''

    def _wait_for_ownership_repair(self, exc):
        with self._lock:
            self.ssh_state = 'AUTH_OR_CONFIG_ERROR'
            self.last_error_code = 'SSH_OWNERSHIP_UNAVAILABLE'
            self.last_error_detail = f'SSH 소유권 기록을 확인할 수 없습니다 ({type(exc).__name__}).'
        self._wait_until_manual_or_stop()

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
