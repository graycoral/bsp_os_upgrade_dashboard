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
        pending = read('force-stop.json')
        targets = [value for value in [manager.get('owner'), active.get('owner'),
                                       active.get('runner'), active.get('transport')] if value is not None]
        retry = pending and pending.get('state') != 'FORCE_STOPPED' and pending.get('targets')
        if active.get('phase') in {'ssh_starting', 'ssh_running'} and not active.get('transport') and not retry:
            from ..execution.launch import process_identity
            owner = active.get('owner')
            if not owner or process_identity(owner['pid']) != owner:
                raise RuntimeError('FORCE_STOP_BLOCKED: 이전 실행본의 orphan SSH 소유권 기록이 없습니다.')
        if (manager or _lock_held(runtime / 'connector-manager.lock')) and not manager.get('owner'):
            raise RuntimeError('FORCE_STOP_BLOCKED: Manager 소유권 기록을 확인할 수 없습니다.')
        if _lock_held(runtime / 'runner.lock') and not active.get('runner'):
            raise RuntimeError('FORCE_STOP_BLOCKED: Host 소유권 기록을 확인할 수 없습니다.')
        result = stop_recorded(runtime / 'force-stop.json', targets)
        if any(_lock_held(runtime / name) for name in ('connector-manager.lock', 'runner.lock')):
            from ..execution.force_stop import atomic_record
            result['state'] = 'FORCE_STOP_PENDING'
            atomic_record(runtime / 'force-stop.json', result)
            raise RuntimeError('FORCE_STOP_PENDING: Manager/Host 잠금 종료를 확인할 수 없습니다.')
        return result
