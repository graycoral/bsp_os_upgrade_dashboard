"""Connector requests to the shared server; local profile and execution ownership stay separate."""
import json
from pathlib import Path
from urllib.parse import urlencode

from ..core.models import TestError
from .logs import redact

PREFIX = '/api/v1/gui-test/live/integration/'


def request(home, suffix, method='GET', value=None):
    import httpx
    from ..execution.launch import read_active
    receipt = read_active(Path(home) / 'runtime')
    if not receipt or not receipt.get('dashboard_url'):
        raise TestError('서버에 연결한 뒤 공통 설정을 불러오세요.', 'CONNECTOR_DISCONNECTED', 409)
    from .settings import Settings
    from ..core.connector_bootstrap import service_headers
    bootstrap = Settings(home).read().get('_setup', {}).get('connector_bootstrap')
    headers = service_headers(bootstrap) if bootstrap else {'X-Bsp-Service': 'plugin'}
    with httpx.Client(timeout=10, trust_env=False, follow_redirects=False) as client:
        try:
            response = client.request(method, receipt['dashboard_url'] + PREFIX + suffix,
                                      headers=headers,
                                      **({'json': value} if value is not None else {}))
        except httpx.HTTPError as exc:
            raise TestError('공통 서버에 연결할 수 없습니다. 변경은 적용되지 않았습니다.', 'SHARED_UNAVAILABLE', 503) from exc
        if response.status_code != 200:
            try:
                error = response.json()
            except ValueError:
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


def remember_desired(home, application, runner_id):
    """Only the registered connector's desired revision may be staged for the next connection."""
    if not application or application.get('runner_id') != runner_id or not application.get('desired_revision'):
        return
    path = pending_file(home)
    old = json.loads(path.read_text()) if path.exists() else {}
    if old.get('desired_revision') == application['desired_revision']:
        return
    from scripts.setup_runtime import atomic_write
    value = {k: application[k] for k in ('runner_id', 'desired_revision', 'settings')}
    value['state'] = 'PENDING'
    atomic_write(path, json.dumps(value, ensure_ascii=False).encode())


def apply_pending(home):
    """Hold the normal startup locks and check durable jobs before changing a profile."""
    import sqlite3
    from ..execution.launch import LaunchLock
    path = pending_file(home)
    if not path.exists(): return
    value = json.loads(path.read_text())
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
            if any(j.get('state') in {'RUNNING','UNKNOWN'} for j in jobs) or any(b.get('state') != 'RELEASED' for b in batches):
                raise TestError('진행·예약·종료 불명 작업이 있어 장비 설정을 유지합니다.', 'CONNECTOR_BUSY', 409)
            from .settings import Settings
            Settings(home).save(value['settings'])
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
    if application.get('state') == 'APPLIED':
        return
    from .settings import Settings
    from ..core.models import digest
    actual = Settings(home).read()
    patch = dict(value['settings'])
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
    request(home, 'connector-settings/receipt', 'POST', {
        'runner_id': value['runner_id'], 'desired_revision': value['desired_revision'],
        'state': 'APPLIED' if applied else 'BLOCKED',
        'reason': '' if applied else '작업 종료 후 커넥터를 다시 연결하면 적용됩니다.',
        'applied_revision': digest(value['settings']) if applied else ''})
