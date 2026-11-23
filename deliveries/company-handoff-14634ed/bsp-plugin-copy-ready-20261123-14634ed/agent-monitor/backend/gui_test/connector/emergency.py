"""Offline Windows force-stop entry; never imports Qt/httpx or opens hardware."""
import json
from pathlib import Path

from ..execution.force_stop import stop_recorded
from ..execution.launch import LaunchLock, _lock_held, _plain_path


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
        pending = read('force-stop.json')
        targets = [value for value in [
            manager.get('owner'),
            active.get('owner'), active.get('runner'), active.get('transport'),
            host_active.get('owner'), host_active.get('runner'),
            ssh_tunnel.get('transport'), ssh_tunnel.get('dashboard_transport'),
        ] if value is not None]
        retry = pending and pending.get('state') != 'FORCE_STOPPED' and pending.get('targets')
        if active.get('phase') in {'ssh_starting', 'ssh_running'} and not active.get('transport') and not retry:
            from ..execution.launch import process_identity
            owner = active.get('owner')
            if not owner or process_identity(owner['pid']) != owner:
                raise RuntimeError('FORCE_STOP_BLOCKED: 이전 실행본의 orphan SSH 소유권 기록이 없습니다.')
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
        result = stop_recorded(runtime / 'force-stop.json', targets)
        if any(_lock_held(runtime / name) for name in ('connector-manager.lock', 'runner.lock', 'ssh-tunnel.lock')):
            from ..execution.force_stop import atomic_record
            result['state'] = 'FORCE_STOP_PENDING'
            atomic_record(runtime / 'force-stop.json', result)
            raise RuntimeError('FORCE_STOP_PENDING: Manager/Host/SSH 잠금 종료를 확인할 수 없습니다.')
        return result
