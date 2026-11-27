"""Linux-side and mutual direct-connector connection diagnostics.

Read-only /proc and .ssh inspection plus loopback HTTP probing so both Linux
(Plugin / Agent Monitor) and Windows (Board Connector) can diagnose why a
direct connection is not working without killing unrelated processes.
"""
import os
from pathlib import Path
import re
import socket
import stat
from urllib.parse import urlsplit

import httpx


LOOPBACK_V4_HEX = {'0100007F', '00000000'}
# Linux /proc/net/tcp6 encodes 4 little-endian 32-bit words on x86_64/arm64,
# and big-endian on big-endian hosts. Accept both representations of ::1, ::, and ::ffff:127.0.0.1.
LOOPBACK_V6_HEX = {
    '00000000000000000000000001000000',
    '00000000000000000000000000000001',
    '0000000000000000FFFF00000100007F',
    '00000000000000000000FFFF7F000001',
    '00000000000000000000000000000000',
}


def _parse_proc_tcp(path, *, v6=False):
    entries = []
    try:
        lines = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return entries
    allowed_ips = LOOPBACK_V6_HEX if v6 else LOOPBACK_V4_HEX
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 10:
            continue
        local_addr, state, uid_str, inode_str = parts[1], parts[3], parts[7], parts[9]
        if state != '0A':  # TCP_LISTEN
            continue
        if ':' not in local_addr:
            continue
        ip_hex, port_hex = local_addr.rsplit(':', 1)
        if ip_hex.upper() not in allowed_ips:
            continue
        try:
            port = int(port_hex, 16)
            sock_uid = int(uid_str)
            inode = int(inode_str)
        except ValueError:
            continue
        entries.append({
            'family': 'ipv6' if v6 else 'ipv4',
            'ip_hex': ip_hex.upper(),
            'port': port,
            'uid': sock_uid,
            'inode': inode,
        })
    return entries


def _cmdline_hint(proc_pid_dir):
    try:
        comm = (proc_pid_dir / 'comm').read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        comm = None
    hint = comm
    try:
        raw = (proc_pid_dir / 'cmdline').read_bytes()
        args = [part.decode('utf-8', errors='replace') for part in raw.split(b'\x00') if part]
        joined = ' '.join(args)
        if 'serve_monitor.py' in joined or 'apps/agent-monitor' in joined:
            hint = 'agent-monitor'
        elif 'board_connector' in joined or 'execution.host' in joined:
            hint = 'board-connector'
        elif comm:
            hint = comm
        elif args:
            hint = Path(args[0]).name
    except OSError:
        pass
    return comm, hint


def _map_inodes_to_pids(proc_root, target_inodes):
    inode_map = {}
    permission_denied = False
    proc = Path(proc_root)
    if not proc.is_dir():
        return inode_map, permission_denied
    try:
        pid_dirs = [p for p in proc.iterdir() if p.name.isdigit() and p.is_dir()]
    except OSError:
        return inode_map, permission_denied
    for pid_dir in pid_dirs:
        pid = int(pid_dir.name)
        fd_dir = pid_dir / 'fd'
        try:
            fds = list(fd_dir.iterdir())
        except PermissionError:
            permission_denied = True
            continue
        except OSError:
            continue
        matched = []
        for fd in fds:
            try:
                target = os.readlink(fd)
            except PermissionError:
                permission_denied = True
                continue
            except OSError:
                continue
            if target.startswith('socket:[') and target.endswith(']'):
                try:
                    inode = int(target[8:-1])
                except ValueError:
                    continue
                if inode in target_inodes:
                    matched.append(inode)
        if matched:
            comm, hint = _cmdline_hint(pid_dir)
            for inode in matched:
                inode_map[inode] = {'pid': pid, 'comm': comm, 'cmdline_hint': hint}
    return inode_map, permission_denied


def scan_loopback_listeners(target_port, *, proc_root=Path('/proc'), current_uid=None):
    """Inspect /proc/net/tcp{,6} for loopback listeners and sshd port mismatches."""
    proc = Path(proc_root)
    all_entries = _parse_proc_tcp(proc / 'net' / 'tcp', v6=False) + _parse_proc_tcp(proc / 'net' / 'tcp6', v6=True)
    inodes = {e['inode'] for e in all_entries if e['inode'] > 0}
    inode_map, perm_denied = _map_inodes_to_pids(proc, inodes)

    target_listeners = []
    other_sshd_ports = set()
    uid_filter = os.getuid() if current_uid is None and hasattr(os, 'getuid') else current_uid

    for entry in all_entries:
        owner = inode_map.get(entry['inode'])
        if owner is None and entry['uid'] == 0:
            info = {
                'port': entry['port'],
                'family': entry['family'],
                'listener_owner_uid': 0,
                'pid': None,
                'comm': 'privileged_or_root_listener',
                'cmdline_hint': 'privileged_or_root_listener',
                'permission_limited': True,
            }
        elif owner is None:
            info = {
                'port': entry['port'],
                'family': entry['family'],
                'listener_owner_uid': entry['uid'],
                'pid': None,
                'comm': 'unknown',
                'cmdline_hint': None,
                'permission_limited': perm_denied,
            }
        else:
            info = {
                'port': entry['port'],
                'family': entry['family'],
                'listener_owner_uid': entry['uid'],
                'pid': owner['pid'],
                'comm': owner['comm'],
                'cmdline_hint': owner['cmdline_hint'],
                'permission_limited': False,
            }

        if entry['port'] == target_port:
            target_listeners.append(info)
        elif info['comm'] in {'sshd', 'sshd-session'} and (uid_filter is None or entry['uid'] == uid_filter):
            other_sshd_ports.add(entry['port'])

    return {
        'target_port': target_port,
        'listening': bool(target_listeners),
        'listener': target_listeners[0] if target_listeners else None,
        'listeners': target_listeners,
        'suspected_port_mismatch_ports': sorted(other_sshd_ports),
    }


def audit_linux_ssh_prereqs(*, home_dir=None, sshd_config_path=Path('/etc/ssh/sshd_config')):
    """Read-only audit of ~/.ssh permissions, authorized_keys, and sshd_config."""
    warnings = []
    home = Path(home_dir) if home_dir is not None else Path.home()
    ssh_dir = home / '.ssh'
    try:
        ssh_dir_exists = ssh_dir.exists()
    except OSError:
        ssh_dir_exists = False
    if not ssh_dir_exists:
        warnings.append({'code': 'SSH_DIR_MISSING', 'message': '~/.ssh 디렉터리가 없습니다.'})
    else:
        try:
            mode = stat.S_IMODE(ssh_dir.stat().st_mode)
            if mode & 0o077:
                warnings.append({
                    'code': 'SSH_DIR_PERMISSIONS_TOO_OPEN',
                    'message': f'~/.ssh 권한({oct(mode)})이 너무 개방되어 있습니다. chmod 700 ~/.ssh 권장.',
                })
        except OSError:
            pass
        auth_keys = ssh_dir / 'authorized_keys'
        try:
            auth_keys_exists = auth_keys.exists()
        except OSError:
            auth_keys_exists = False
        if not auth_keys_exists:
            warnings.append({'code': 'AUTHORIZED_KEYS_MISSING', 'message': '~/.ssh/authorized_keys 파일이 없습니다.'})
        else:
            try:
                mode = stat.S_IMODE(auth_keys.stat().st_mode)
                if mode & 0o022:
                    warnings.append({
                        'code': 'AUTHORIZED_KEYS_PERMISSIONS_TOO_OPEN',
                        'message': f'~/.ssh/authorized_keys 권한({oct(mode)})이 너무 개방되어 있습니다. chmod 600 권장.',
                    })
            except OSError:
                pass

    cfg = Path(sshd_config_path)
    try:
        cfg_is_file = cfg.is_file()
    except OSError:
        cfg_is_file = False
    if cfg_is_file:
        try:
            text = cfg.read_text(encoding='utf-8', errors='replace')
            for raw_line in text.splitlines():
                line = raw_line.split('#', 1)[0].strip()
                if not line:
                    continue
                low = line.lower()
                if re.match(r'^allowtcpforwarding\s+no\b', low):
                    warnings.append({'code': 'SSHD_ALLOW_TCP_FORWARDING_NO', 'message': 'sshd_config에 AllowTcpForwarding no가 설정되어 있습니다.'})
                elif re.match(r'^disableforwarding\s+yes\b', low):
                    warnings.append({'code': 'SSHD_DISABLE_FORWARDING_YES', 'message': 'sshd_config에 DisableForwarding yes가 설정되어 있습니다.'})
                elif re.match(r'^permitlisten\s+', low):
                    warnings.append({'code': 'SSHD_PERMIT_LISTEN_RESTRICTED', 'message': f'sshd_config에 PermitListen 제한이 있습니다: {line}'})
        except OSError:
            pass
    return warnings


def linux_local_diagnostics(port, *, proc_root=Path('/proc'), home_dir=None,
                            sshd_config_path=Path('/etc/ssh/sshd_config'), current_uid=None):
    scan = scan_loopback_listeners(port, proc_root=proc_root, current_uid=current_uid)
    warnings = audit_linux_ssh_prereqs(home_dir=home_dir, sshd_config_path=sshd_config_path)
    return {
        'target_port': port,
        'port_listener': scan['listener'],
        'listeners': scan['listeners'],
        'listening': scan['listening'],
        'suspected_port_mismatch_ports': scan['suspected_port_mismatch_ports'],
        'ssh_prereq_warnings': warnings,
    }


def settings_preview(document):
    """Return the displayable Linux fields. Local automation metadata stays on Linux."""
    if not isinstance(document, dict) or not isinstance(document.get('revision'), str) or not document['revision']:
        return None
    cfg, limits = document.get('integration'), document.get('timeouts')
    if not isinstance(cfg, dict) or not isinstance(limits, dict):
        return None
    paths = {k: cfg.get(k, '') for k in ('tc_root', 'installer_path', 'flash_profile')}
    if any(not isinstance(v, str) for v in paths.values()):
        return None
    for key in ('installer_roots', 'global_defaults'):
        values = cfg.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            return None
        paths[key] = values
    seconds = limits.get('default_seconds')
    if seconds is not None and (type(seconds) is not int or not 1 <= seconds <= 86400):
        return None
    return {'revision': document['revision'], 'integration': paths, 'timeouts': {'default_seconds': seconds},
            'read_only': True}


def _send_peer_hello(client, base_url, *, peer_type, peer_instance_id, peer_version, target_port,
                     expected_runner_id, linux_host, client_status, client_issue, linux_diag,
                     shared_revision=None, shared_settings=None):
    payload = {
        'peer_type': peer_type,
        'peer_instance_id': peer_instance_id,
        'peer_version': peer_version,
        'target_port': target_port,
        'expected_runner_id': expected_runner_id,
        'linux_host': linux_host,
        'client_status': client_status,
        'client_issue': client_issue,
        'linux_diagnostics': {
            'port_listener': linux_diag.get('port_listener'),
            'ssh_prereq_warnings': linux_diag.get('ssh_prereq_warnings', []),
            'suspected_port_mismatch_ports': linux_diag.get('suspected_port_mismatch_ports', []),
            'active_shared_revision': shared_revision,
        },
    }
    if client_status == 'OK' and shared_settings:
        preview = settings_preview(shared_settings)
        if preview:
            payload['linux_diagnostics']['shared_execution_settings'] = preview
    try:
        r = client.post(base_url + '/v1/peer/hello', json=payload)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _probe_other_service(client, base_url):
    try:
        r = client.get(base_url + '/api/v1/health')
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict) and ('status' in data or 'managed_runtime' in data):
                return 'agent-monitor'
    except Exception:
        pass
    return 'unknown'


def diagnose_connector_endpoint(
    port,
    *,
    expected_runner_id=None,
    shared_revision=None,
    shared_settings=None,
    peer_type='plugin',
    peer_instance_id='plugin-cli',
    peer_version='2026.11.19',
    linux_host=None,
    proc_root=Path('/proc'),
    home_dir=None,
    sshd_config_path=Path('/etc/ssh/sshd_config'),
    current_uid=None,
    client=None,
    notify_peer=True,
    timeout=1.5,
):
    """Run Linux-side local audit + live connector HTTP mutual diagnostics."""
    linux_diag = linux_local_diagnostics(
        port, proc_root=proc_root, home_dir=home_dir,
        sshd_config_path=sshd_config_path, current_uid=current_uid,
    )
    base_url = f'http://127.0.0.1:{port}'
    host_name = linux_host or socket.gethostname()
    own_client = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=timeout, read=max(timeout, 3.0)),
                                  trust_env=False, follow_redirects=False)
    def peer_hello(status, issue, verified_runner=None):
        if not notify_peer:
            return None
        return _send_peer_hello(
            http, base_url, peer_type=peer_type, peer_instance_id=peer_instance_id,
            peer_version=peer_version, target_port=port, expected_runner_id=verified_runner or expected_runner_id,
            linux_host=host_name, client_status=status, client_issue=issue,
            linux_diag=linux_diag, shared_revision=shared_revision, shared_settings=shared_settings,
        )

    windows_checklist = [
        'Windows에서 board-connector.cmd 실행 및 연결 시작 상태 확인',
        f'SSH 역방향 터널(-R 127.0.0.1:{port}:127.0.0.1:8772) 바인드 상태 및 포트 일치 확인',
        'Windows SSH 호스트 키(known_hosts) 및 개인키 ACL(icacls) 권한 확인',
    ]
    try:
        try:
            resp = http.get(base_url + '/v1/identity')
        except (httpx.ConnectError, OSError) as exc:
            # Connection refused vs socket listening but refused
            return {
                'schema_version': 'mutual-connection-report-v1',
                'connected': False,
                'overall_connection_state': 'DISCONNECTED',
                'code': 'CONNECTOR_TUNNEL_NOT_LISTENING',
                'summary': f'Linux 127.0.0.1:{port}에서 보드 커넥터 터널이 수신 대기 중이 아닙니다.',
                'detail': str(exc),
                'target_port': port,
                'linux': linux_diag,
                'windows': None,
                'windows_checklist': windows_checklist,
                'peer_notified': False,
            }
        except (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError, httpx.ProtocolError) as exc:
            return {
                'schema_version': 'mutual-connection-report-v1',
                'connected': False,
                'overall_connection_state': 'ERROR',
                'code': 'STALE_SSH_TUNNEL',
                'summary': f'127.0.0.1:{port} TCP 연결은 열려 있으나 HTTP 응답이 없습니다(좀비 터널 또는 Windows Host 미기동).',
                'detail': type(exc).__name__,
                'target_port': port,
                'linux': linux_diag,
                'windows': None,
                'windows_checklist': windows_checklist,
                'peer_notified': False,
            }

        if resp.status_code != 200:
            service_sig = _probe_other_service(http, base_url)
            return {
                'schema_version': 'mutual-connection-report-v1',
                'connected': False,
                'overall_connection_state': 'ERROR',
                'code': 'PORT_OCCUPIED_BY_OTHER_SERVICE',
                'service_signature': service_sig,
                'summary': f'127.0.0.1:{port} 포트를 보드 커넥터가 아닌 다른 서비스({service_sig})가 점유 중입니다.',
                'detail': f'HTTP {resp.status_code} on /v1/identity',
                'target_port': port,
                'linux': linux_diag,
                'windows': None,
                'windows_checklist': [],
                'peer_notified': False,
            }

        try:
            identity = resp.json()
        except ValueError:
            identity = None

        if not isinstance(identity, dict) or not isinstance(identity.get('runner_id'), str):
            service_sig = _probe_other_service(http, base_url)
            return {
                'schema_version': 'mutual-connection-report-v1',
                'connected': False,
                'overall_connection_state': 'ERROR',
                'code': 'PORT_OCCUPIED_BY_OTHER_SERVICE',
                'service_signature': service_sig,
                'summary': f'127.0.0.1:{port} 포트가 보드 커넥터 identity JSON을 반환하지 않았습니다({service_sig}).',
                'detail': 'Invalid /v1/identity payload',
                'target_port': port,
                'linux': linux_diag,
                'windows': None,
                'windows_checklist': [],
                'peer_notified': False,
            }

        caps = identity.get('capabilities') or []
        if 'direct-connector-v1' not in caps:
            issue = {
                'code': 'CONNECTOR_PROTOCOL_UNSUPPORTED',
                'message': 'Windows 보드 커넥터가 direct-connector-v1 프로토콜을 지원하지 않습니다.',
                'expected': 'direct-connector-v1',
                'actual': caps,
            }
            hello = peer_hello('INCOMPATIBLE', issue)
            return {
                'schema_version': 'mutual-connection-report-v1',
                'connected': False,
                'overall_connection_state': 'ERROR',
                'code': 'CONNECTOR_PROTOCOL_UNSUPPORTED',
                'summary': issue['message'],
                'target_port': port,
                'identity': identity,
                'linux': linux_diag,
                'windows': None,
                'peer_hello': hello,
                'peer_notified': hello is not None,
            }

        actual_runner_id = identity['runner_id']
        if expected_runner_id and actual_runner_id != expected_runner_id:
            issue = {
                'code': 'RUNNER_CHANGED',
                'message': f'연결된 보드 커넥터 runner_id({actual_runner_id})가 기대값({expected_runner_id})과 다릅니다.',
                'expected': expected_runner_id,
                'actual': actual_runner_id,
            }
            hello = peer_hello('MISMATCH', issue)
            win_diag = None
            try:
                dr = http.get(base_url + '/v1/diagnostics/connection')
                if dr.status_code == 200:
                    win_diag = dr.json()
            except Exception:
                pass
            return {
                'schema_version': 'mutual-connection-report-v1',
                'connected': False,
                'overall_connection_state': 'ERROR',
                'code': 'RUNNER_CHANGED',
                'summary': issue['message'],
                'expected_runner_id': expected_runner_id,
                'actual_runner_id': actual_runner_id,
                'target_port': port,
                'identity': identity,
                'linux': linux_diag,
                'windows': win_diag,
                'peer_hello': hello,
                'peer_notified': hello is not None,
            }

        hello = peer_hello('OK', None, actual_runner_id)
        win_diag = None
        try:
            dr = http.get(base_url + '/v1/diagnostics/connection')
            if dr.status_code == 200:
                win_diag = dr.json()
        except Exception:
            pass
        readiness = (win_diag or {}).get('readiness') or {}
        exec_ready = readiness.get('execution_ready', True)
        code = 'CONNECTED' if exec_ready else 'READY_WITH_HW_WARNINGS'
        return {
            'schema_version': 'mutual-connection-report-v1',
            'connected': True,
            'overall_connection_state': (win_diag or {}).get('overall_connection_state', 'CONNECTED'),
            'code': code,
            'summary': '보드 커넥터 직결 연결됨' + ('' if exec_ready else ' (하드웨어/TC 실행 준비 확인 필요)'),
            'target_port': port,
            'identity': identity,
            'linux': linux_diag,
            'windows': win_diag,
            'peer_hello': hello,
            'peer_notified': hello is not None,
        }
    finally:
        if own_client:
            http.close()
