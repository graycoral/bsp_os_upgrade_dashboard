"""Offline Windows force-stop entry; never imports Qt/httpx or opens hardware."""
import json
from pathlib import Path

from ..execution import launch
from ..execution.force_stop import stop_recorded
from ..execution.launch import LaunchLock, _lock_held, _plain_path


def _verify_legacy_ssh(active, stopped):
    """An old launcher starts OpenSSH directly, but may omit its process generation."""
    if active.get('phase') not in {'ssh_starting', 'ssh_running'} or active.get('transport'):
        return
    owner = active.get('owner')
    if owner in stopped:
        # The pinned launcher already passed the post-exit scan of all its children.
        return
    if owner is not None:
        launch._identity(owner)
    try:
        processes = launch._windows_process_snapshot()
        current_parent = launch.process_identity(owner['pid']) if owner else None
        for pid, (parent, image) in processes.items():
            if owner and parent != owner['pid']:
                continue
            if image and image.casefold() != 'ssh.exe':
                continue
            child = launch.process_identity(pid)
            if child is None:
                continue
            if owner and int(child['creation_time']) < int(owner['creation_time']):
                continue
            if current_parent and current_parent != owner and int(child['creation_time']) > int(current_parent['creation_time']):
                # Child belongs to a later generation that reused the parent's PID.
                continue
            raise RuntimeError(f'FORCE_STOP_PENDING: 구형 SSH 후보(PID {pid})의 소유권을 확인할 수 없습니다. '
                               '식별한 프로세스는 정리했습니다. 이 SSH가 종료되면 같은 명령으로 확인하세요.')
    except OSError as exc:
        raise RuntimeError('FORCE_STOP_PENDING: Windows SSH 프로세스 조회를 완료하지 못했습니다. '
                           '같은 계정에서 다시 실행하세요.') from exc


def force_stop(home):
    home = _plain_path(home)
    runtime = home / 'runtime'
    with LaunchLock(runtime / 'connector-start.lock'):
        def read(name):
            path = _plain_path(runtime / name)
            value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
            if not isinstance(value, dict):
                raise ValueError('Invalid connector process receipt')
            return value
        manager = read('connector-manager.json')
        active = read('active-endpoints.json')
        host_active = read('host-active.json')
        ssh_tunnel = read('ssh-tunnel.json')
        targets = [value for value in [
            manager.get('owner'),
            active.get('owner'), active.get('runner'), active.get('transport'),
            host_active.get('owner'), host_active.get('runner'),
            ssh_tunnel.get('transport'), ssh_tunnel.get('dashboard_transport'),
        ] if value is not None]
        if (manager or _lock_held(runtime / 'connector-manager.lock')) and not manager.get('owner'):
            raise RuntimeError('FORCE_STOP_BLOCKED: Manager 소유권 기록을 확인할 수 없습니다.')
        if _lock_held(runtime / 'runner.lock') and not (active.get('runner') or host_active.get('runner')):
            raise RuntimeError('FORCE_STOP_BLOCKED: Host 소유권 기록을 확인할 수 없습니다.')
        if _lock_held(runtime / 'ssh-tunnel.lock') and not (ssh_tunnel.get('transport') or ssh_tunnel.get('dashboard_transport') or active.get('transport')):
            from ..execution.launch import process_identity
            mgr_owner = manager.get('owner')
            idle_manager_tunnel = bool(
                ssh_tunnel
                and ssh_tunnel.get('ssh_state') in {'NOT_CONFIGURED', 'CONNECTING', 'RECONNECTING', 'AUTH_OR_CONFIG_ERROR', 'DISCONNECTED', 'STOPPED'}
                and isinstance(mgr_owner, dict)
                and mgr_owner.get('pid')
                and process_identity(mgr_owner['pid']) == mgr_owner
            )
            if not idle_manager_tunnel:
                raise RuntimeError('FORCE_STOP_BLOCKED: SSH 터널 소유권 기록을 확인할 수 없습니다.')
        def verify(stopped):
            _verify_legacy_ssh(active, stopped)
            if any(_lock_held(runtime / name) for name in ('connector-manager.lock', 'runner.lock', 'ssh-tunnel.lock')):
                raise RuntimeError('FORCE_STOP_PENDING: Manager/Host/SSH 잠금 종료를 확인할 수 없습니다.')

        return stop_recorded(runtime / 'force-stop.json', targets, verify_stopped=verify)
