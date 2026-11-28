"""Stop recorded local processes, then inspect their server-side listener."""
import json

from ..execution import launch
from ..execution.force_stop import StopResidue, atomic_record, recorded_process_alive, stop_recorded
from . import ssh_ownership
from .windows_processes import discover_windows_processes
from ..execution.launch import LaunchLock, _lock_held, _plain_path


def _verify_legacy_ssh(active, stopped):
    """An old launcher starts OpenSSH directly, but may omit its process generation."""
    if active.get('phase') not in {'ssh_starting', 'ssh_running'} or active.get('transport'):
        return
    owner = active.get('owner')
    if owner is None or owner in stopped:
        # Without a recorded parent, only profile-specific discovery can identify SSH.
        return
    launch._identity(owner)
    try:
        processes = launch._windows_process_snapshot()
        candidates = []
        for pid, (parent, image) in processes.items():
            if parent != owner['pid']:
                continue
            if image and image.casefold() != 'ssh.exe':
                continue
            child = launch.process_identity(pid)
            if child is None:
                continue
            if int(child['creation_time']) < int(owner['creation_time']):
                continue
            current_parent = launch.process_identity(owner['pid'])
            if current_parent and current_parent != owner and int(child['creation_time']) > int(current_parent['creation_time']):
                # Child belongs to a later generation that reused the parent's PID.
                continue
            candidates.append(dict(child, role='구형 SSH 후보', parent_pid=parent))
        if candidates:
            raise StopResidue(candidates)
    except OSError as exc:
        raise RuntimeError('FORCE_STOP_PENDING: Windows SSH 프로세스 조회를 완료하지 못했습니다. '
                           '같은 계정에서 다시 실행하세요.') from exc


def force_stop(home):
    home = _plain_path(home)
    runtime = home / 'runtime'
    with LaunchLock(runtime / 'connector-start.lock'):
        endpoints = []
        try:
            result = _check_profile(home, inspect_only=False, endpoints=endpoints)
        except RuntimeError as initial:
            if not str(initial).startswith(('FORCE_STOP_PENDING:', 'FORCE_STOP_BLOCKED:')):
                raise
            # Handles have closed. Verify the same profile once without signalling
            # anything. Preserve checkpoints if a current blocker still exists.
            try:
                result = _check_profile(home, inspect_only=True, endpoints=endpoints)
            except StopResidue as current:
                if isinstance(initial, StopResidue):
                    raise
                path = runtime / 'force-stop.json'
                record = json.loads(path.read_bytes())
                detail = f'{initial} / {current}'
                atomic_record(path, dict(record, detail=detail))
                raise RuntimeError(detail) from current
        from .ssh_tunnel import probe_remote_listener
        result['remote_ports'] = [probe_remote_listener(item) for item in endpoints]
        if not endpoints:
            result['remote_ports'] = [{'state': 'UNKNOWN', 'reason': 'NO_RECORDED_ENDPOINT'}]
        atomic_record(runtime / 'force-stop.json', result)
        return result


def check_before_start(home):
    """Caller holds connector-start.lock. Never kills processes or contacts Linux."""
    home = _plain_path(home)
    path = home / 'runtime/force-stop.json'
    if not path.exists():
        return
    record = json.loads(path.read_bytes())
    if not isinstance(record, dict):
        raise ValueError('Invalid force-stop retry record')
    if record.get('state') == 'FORCE_STOPPED':
        return
    if record.get('version') != 1 or record.get('state') not in ('FORCE_STOP_PENDING', 'FORCE_STOPPING'):
        raise ValueError('Invalid force-stop retry record')
    _check_profile(home, inspect_only=True, endpoints=[])


def _check_profile(home, *, inspect_only, endpoints):
    runtime = home / 'runtime'
    def read(name):
        path = _plain_path(runtime / name)
        value = json.loads(path.read_bytes()) if path.exists() else {}
        if not isinstance(value, dict):
            raise ValueError('Invalid connector process receipt')
        return value
    manager = read('connector-manager.json')
    active = read('active-endpoints.json')
    host_active = read('host-active.json')
    ssh_tunnel = read('ssh-tunnel.json')
    ownership = ssh_ownership.read(runtime)

    def remember_endpoints(data):
        for item in [data['last_endpoint'], *(r['endpoint'] for r in data['owners'])]:
            if item and item not in endpoints:
                endpoints.append(item)

    remember_endpoints(ownership)
    try:
        discovered = {} if inspect_only else discover_windows_processes(home)
    except (OSError, ValueError, RuntimeError):
        # Clean proven targets even if discovery is temporarily unavailable.
        # The second scan below is mandatory before confirming completion.
        discovered = {}
    targets = [value for value in [
        *(proc for group in discovered.values() for proc in group),
        *(r['process'] for r in ownership['owners']),
        manager.get('owner'),
        active.get('owner'), active.get('runner'), active.get('transport'),
        host_active.get('owner'), host_active.get('runner'),
        ssh_tunnel.get('transport'), ssh_tunnel.get('dashboard_transport'),
    ] if value is not None]
    if not inspect_only and _lock_held(runtime / 'connector-manager.lock') and not (manager.get('owner') or discovered.get('manager')):
        raise RuntimeError('FORCE_STOP_BLOCKED: Manager 소유권 기록을 확인할 수 없습니다.')
    if not inspect_only and _lock_held(runtime / 'runner.lock') and not (active.get('runner') or host_active.get('runner') or discovered.get('host')):
        raise RuntimeError('FORCE_STOP_BLOCKED: Host 소유권 기록을 확인할 수 없습니다.')
    if not inspect_only and _lock_held(runtime / 'ssh-tunnel.lock') and not (ssh_tunnel.get('transport') or ssh_tunnel.get('dashboard_transport') or active.get('transport') or discovered.get('ssh') or discovered.get('manager')):
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
        found = discover_windows_processes(home)
        remaining = [dict(p, role=role) for role, group in found.items() for p in group]
        locks = [name for name in ('connector-manager.lock', 'runner.lock', 'ssh-tunnel.lock')
                 if _lock_held(runtime / name)]
        try:
            _verify_legacy_ssh(active, stopped)
        except StopResidue as exc:
            remaining.extend(exc.processes)
        ownership = ssh_ownership.read(runtime)
        remember_endpoints(ownership)
        if inspect_only or locks:
            owners = [r for r in ownership['owners'] if recorded_process_alive(r['process'])]
        else:
            owners = ssh_ownership.update(runtime, is_alive=recorded_process_alive)['owners']
        remaining.extend(dict(r['process'], role='ssh') for r in owners)
        if remaining or locks:
            raise StopResidue(remaining, locks)

    path = runtime / 'force-stop.json'
    result = stop_recorded(path, targets, verify_stopped=verify, inspect_only=inspect_only)
    if not inspect_only:
        result['discovered_processes'] = discovered
    return result
