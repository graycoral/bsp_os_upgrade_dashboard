"""Connector requests to the shared server; local profile and execution ownership stay separate."""
import json
from pathlib import Path
from urllib.parse import urlencode

from ..core.models import TestError
from .logs import redact

PREFIX = '/api/v1/gui-test/live/integration/'


def request(home, suffix, method='GET', value=None, *, prefix=PREFIX, direct=False):
    import httpx
    from ..execution.launch import _lock_held, read_active, read_ssh_tunnel, process_identity
    runtime = Path(home) / 'runtime'
    url = None
    if direct or _lock_held(runtime / 'ssh-tunnel.lock'):
        tunnel = read_ssh_tunnel(runtime) or {}
        dashboard = tunnel.get('dashboard_transport')
        if (tunnel.get('ssh_state') == 'CONNECTED' and tunnel.get('transport') and dashboard
                and process_identity(dashboard['pid']) == dashboard and tunnel.get('local_dashboard_port')):
            url = f"http://127.0.0.1:{tunnel['local_dashboard_port']}"
    else:
        url = (read_active(runtime) or {}).get('dashboard_url')
    if not url:
        raise TestError('서버에 연결한 뒤 공통 설정을 불러오세요.', 'CONNECTOR_DISCONNECTED', 409)
    from .settings import Settings
    from ..core.connector_bootstrap import service_headers, verify_service
    bootstrap = Settings(home).read().get('_setup', {}).get('connector_bootstrap')
    headers = service_headers(bootstrap) if bootstrap else {'X-Bsp-Service': 'plugin'}
    with httpx.Client(timeout=2 if direct else 10, trust_env=False, follow_redirects=False) as client:
        try:
            if bootstrap and 'X-Bsp-Runtime-Id' in headers:
                health = client.get(url + '/api/v1/health', headers=headers)
                if health.status_code == 409:
                    raise TestError('Linux 서비스가 가져온 연결 프로필과 다릅니다.', 'SERVICE_IDENTITY_MISMATCH', 409)
                health.raise_for_status()
                identity = health.json()
                if not isinstance(identity, dict):
                    raise TestError('Linux 서비스 식별 응답을 확인하세요.', 'SERVICE_IDENTITY_MISMATCH', 409)
                verify_service(bootstrap, identity)
            response = client.request(method, url + prefix + suffix,
                                      headers=headers,
                                      **({'json': value} if value is not None else {}))
        except httpx.HTTPError as exc:
            raise TestError('공통 서버에 연결할 수 없습니다. 변경은 적용되지 않았습니다.', 'SHARED_UNAVAILABLE', 503) from exc
        if response.status_code != 200:
            try:
                error = response.json()
            except ValueError:
                error = {}
            if not isinstance(error, dict):
                error = {}
            raise TestError(redact(error.get('message', '공통 설정 요청 실패')),
                            error.get('code', 'SHARED_REQUEST'), response.status_code)
        return response.json()


def paths(home, kind, path=''):
    if kind not in {'installer', 'source'} or not isinstance(path, str) or len(path) > 4096:
        raise TestError('Invalid server path request', status=422)
    return request(home, 'paths?' + urlencode({'kind': kind, 'path': path}))


def pending_file(home):
    return Path(home) / 'runtime' / 'shared-connector-settings.json'


def remember_desired(home, application, runner_id, *, force=False):
    """Only the registered connector's desired revision may be staged for the next connection."""
    if not application or application.get('runner_id') != runner_id or not application.get('desired_revision'):
        return
    path = pending_file(home)
    old = json.loads(path.read_text()) if path.exists() else {}
    if not force and old.get('desired_revision') == application['desired_revision']:
        return
    from scripts.setup_runtime import atomic_write
    value = {k: application[k] for k in ('runner_id', 'desired_revision', 'settings')}
    if application.get('expected_profile_revision'):
        value['expected_profile_revision'] = application['expected_profile_revision']
    value['state'] = 'PENDING'
    atomic_write(path, json.dumps(value, ensure_ascii=False).encode())


def apply_pending(home, *, expected_revision=None):
    """Hold the normal startup locks and check durable jobs before changing a profile."""
    import sqlite3
    from ..execution.launch import LaunchLock
    path = pending_file(home)
    if not path.exists():
        if expected_revision:
            raise TestError('적용할 설정을 다시 확인하세요.', 'SETTINGS_CHANGED', 409)
        return
    value = json.loads(path.read_text())
    if expected_revision and value.get('desired_revision') != expected_revision:
        raise TestError('적용 요청 이후 설정이 변경됐습니다.', 'SETTINGS_CHANGED', 409)
    if value.get('state') != 'PENDING': return
    runtime = Path(home) / 'runtime'
    db = runtime / 'executions.db'
    if not db.is_file():
        raise TestError('등록된 장비 실행 기록이 없어 설정을 적용할 수 없습니다.', 'RUNNER_CHANGED', 409)
    with LaunchLock(runtime / 'setup-launch.lock'), LaunchLock(runtime / 'runner.lock'):
        with sqlite3.connect(db) as c:
            c.execute('BEGIN IMMEDIATE')
            identity = c.execute("SELECT value FROM runner_meta WHERE key='identity'").fetchone()
            if not identity or identity[0] != value.get('runner_id'):
                raise TestError('설정 대상 커넥터가 다릅니다.', 'RUNNER_CHANGED', 409)
            jobs = [json.loads(r[0]) for r in c.execute('SELECT data FROM jobs')]
            batches = [json.loads(r[0]) for r in c.execute('SELECT data FROM batches')]
            from .bootstrap import _active_connector_runs
            if any(j.get('state') in {'RUNNING','UNKNOWN'} for j in jobs) or any(b.get('state') != 'RELEASED' for b in batches) or _active_connector_runs(c):
                raise TestError('진행·예약·종료 불명 작업이 있어 장비 설정을 유지합니다.', 'CONNECTOR_BUSY', 409)
            from .settings import Settings
            if value.get('expected_profile_revision'):
                from .mirror import public_profile
                from ..core.models import digest
                if digest(public_profile(Settings(home).read())) != value['expected_profile_revision']:
                    raise TestError('Windows 설정이 변경됐습니다. 공통 설정을 다시 불러오세요.', 'SETTINGS_CHANGED', 409)
            before = Settings(home).read()
            saved = Settings(home).save(value['settings'], migration_checked=True)
            # Private nested settings stay in Windows; only hashes prove them
            # to the central service. Compare this exact saved snapshot later.
            fields = set(value['settings']) | {key for key in saved if saved.get(key) != before.get(key)}
            value['effective_settings'] = {key:saved[key] for key in fields if key != 'flashing'}
            value['state'] = 'SAVED'
            from scripts.setup_runtime import atomic_write
            atomic_write(path, json.dumps(value, ensure_ascii=False).encode())


def acknowledge(home, application, inventory):
    """APPLIED requires a fresh matching Host inventory, not merely a saved central value."""
    path = pending_file(home)
    if not path.exists() or not application or not application.get('desired_revision'):
        return
    value = json.loads(path.read_text())
    if (application.get('runner_id') != inventory.get('runner_id') or
            value.get('runner_id') != inventory.get('runner_id') or
            value.get('desired_revision') != application['desired_revision']):
        return
    from .settings import Settings
    from ..core.models import digest
    actual = Settings(home).read()
    patch = dict(value['settings'])
    if 'effective_settings' in value:
        patch.update(value['effective_settings'])
    elif 'console_observers' in patch:
        patch['console_observers'] = {
            board: dict(actual.get('console_observers', {}).get(board, {}), **cfg)
            for board, cfg in patch['console_observers'].items()}
    if 'boards' in patch:
        from ..core.models import Connection
        patch['boards'] = [Connection.model_validate({'a': b}).a.model_dump() for b in patch['boards']]
    flash = patch.pop('flashing', None)
    saved = value.get('state') == 'SAVED' and all(actual.get(k) == v for k, v in patch.items())
    if flash is not None:
        profiles = flash.get('profiles', {})
        actual_profiles = actual.get('flashing', {}).get('profiles', {})
        witnessed = inventory.get('configuration_fields', {}).get('flashing_profiles', {})
        saved = saved and all(actual_profiles.get(name) == profile and witnessed.get(name) == digest(profile)
                              for name, profile in profiles.items())
    expected_boards = patch.get('boards')
    actual_boards = [{k: b[k] for k in ('board_id', 'host', 'com', 'node') if k in b}
                     for b in inventory.get('boards', [])]
    if expected_boards is not None:
        saved = saved and expected_boards == actual_boards
    fields = inventory.get('configuration_fields', {})
    saved = saved and all(fields.get(k) == digest(v) for k,v in patch.items())
    busy = inventory.get('host_busy') or inventory.get('reserved')
    applied = saved and not busy
    if saved and application.get('state') == 'APPLIED':
        return
    request(home, 'connector-settings/receipt', 'POST', {
        'runner_id': value['runner_id'], 'desired_revision': value['desired_revision'],
        'state': 'APPLIED' if applied else 'BLOCKED',
        'reason': '' if applied else '작업 종료 후 커넥터를 다시 연결하면 적용됩니다.',
        'applied_revision': digest(value['settings']) if applied else ''})
