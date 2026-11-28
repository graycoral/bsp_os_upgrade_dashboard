"""Windows operator selection and approved Monitor forwarding."""
import json
import re
import secrets
from urllib.parse import quote

import httpx

from ..core.models import TestError
from ..core.monitor_identity import CHALLENGE
from . import ssh_ownership

IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
TICKET = re.compile(r'[A-Za-z0-9_.~-]{16,512}')
ROUTE_KEYS = {'task_id', 'account', 'project', 'monitor_id', 'last_seen_at', 'active_run_id'}


def admin_headers(runtime):
    from ..execution.sharing import load_admin_token
    try:
        token = load_admin_token(runtime)
    except (OSError, ValueError, TestError):
        token = None
    return {'Authorization': 'Bearer ' + token} if token else {}


def approved_setup(runtime, default, profile):
    if not isinstance(profile, str) or not IDENTIFIER.fullmatch(profile):
        return None
    if profile == 'default':
        setup = default
    else:
        try:
            data = json.loads((runtime / 'shared-monitor-ssh.json').read_text(encoding='utf-8-sig'))
            setup = data['profiles'][profile]
        except (OSError, ValueError, KeyError, TypeError):
            return None
    if not isinstance(setup, dict):
        return None
    try:
        return ssh_ownership.endpoint(setup, setup.get('ssh_port', 22), 8771)
    except (TypeError, ValueError):
        return None


def destination(runtime, default, row):
    port, monitor_id = row.get('monitor_port'), row.get('monitor_id')
    if (type(port) is not int or not 1 <= port <= 65535
            or not isinstance(monitor_id, str) or not IDENTIFIER.fullmatch(monitor_id)):
        return None
    setup = approved_setup(runtime, default, row.get('ssh_profile'))
    return (setup, port) if setup else None


def default_task(tasks, active_task_id):
    if active_task_id:
        return active_task_id
    approved = [row['task_id'] for row in tasks if row['monitor_state'] == 'APPROVED']
    if len(approved) == 1:
        return approved[0]
    if len(tasks) == 1:
        return tasks[0]['task_id']
    return None


def task_list(client, host_url, runtime, default, generation_ready, *, blocked=False):
    try:
        response = client.get(host_url + '/v1/sharing/tasks')
        response.raise_for_status()
        value = response.json()
        rows = [row for row in value['tasks'] if isinstance(row, dict) and
                isinstance(row.get('task_id'), str) and IDENTIFIER.fullmatch(row['task_id'])]
        active = value.get('active_task_id')
    except httpx.HTTPStatusError as exc:
        state = 'ACCESS_DENIED' if blocked or exc.response.status_code in {401, 403} else 'OFFLINE'
        return {'state': state, 'tasks': [], 'active_task_id': None, 'default_task_id': None}, []
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return {'state': 'OFFLINE', 'tasks': [], 'active_task_id': None, 'default_task_id': None}, []
    projected = [
        {key: row.get(key) for key in ROUTE_KEYS} |
        {'monitor_state': ('UNREGISTERED' if destination(runtime, default, row) is None
                           else 'APPROVED' if generation_ready else 'OFFLINE')}
        for row in rows
    ]
    return {'state': 'READY' if generation_ready else 'OFFLINE', 'tasks': projected,
            'active_task_id': active, 'default_task_id': default_task(projected, active)}, rows


def monitor_url(client, row, setup, remote_port, supervisor, generation, host_url):
    monitor_id, task_id = row['monitor_id'], row['task_id']
    local_port = supervisor.forward_shared_monitor(setup, remote_port, generation)
    base = f'http://127.0.0.1:{local_port}'
    offline = TestError('승인된 작업 Monitor가 오프라인이거나 연결 세대가 변경됐습니다.', 'MONITOR_OFFLINE', 503)
    wrong_identity = TestError('승인된 Monitor 인스턴스와 연결된 서비스가 다릅니다.', 'MONITOR_IDENTITY_MISMATCH', 409)
    challenge = secrets.token_hex(32)
    # The HTTP probe carries no Host credential. Only the pinned Windows Host
    # connection below may receive the operator's Authorization header.
    try:
        with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as verifier:
            response = verifier.get(base + '/api/v1/health', headers={'X-Bsp-Monitor-Challenge': challenge})
            response.raise_for_status()
            health = response.json()
            page = verifier.head(base + '/plugin-task/')
            page.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        raise offline from exc
    if (not isinstance(health, dict) or health.get('status') != 'ok'
            or health.get('mode') != 'shared-task-monitor' or health.get('monitor_id') != monitor_id):
        raise wrong_identity
    proof = health.get('monitor_proof')
    if not isinstance(proof, str) or not CHALLENGE.fullmatch(proof):
        raise wrong_identity
    if page.headers.get('content-type', '').split(';')[0] != 'text/html':
        raise offline
    if not supervisor.shared_forward_live(generation, local_port):
        raise offline
    try:
        task_url = host_url + '/v1/sharing/tasks/' + task_id
        verification = client.post(task_url + '/monitor-proof', json={'challenge': challenge, 'proof': proof})
        if verification.status_code in {400, 401, 403, 404, 409, 422}:
            raise wrong_identity
        verification.raise_for_status()
        if verification.json() != {'verified': True}:
            raise wrong_identity
        if not supervisor.shared_forward_live(generation, local_port):
            raise offline
        response = client.post(task_url + '/view-tickets')
        response.raise_for_status()
        receipt = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in {401, 403, 404, 409}:
            raise TestError('이 작업의 Monitor를 열 권한이 없습니다.', 'MONITOR_ACCESS_DENIED', 403) from exc
        raise offline from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise offline from exc
    if (not isinstance(receipt, dict) or receipt.get('task_id') != task_id or receipt.get('monitor_id') != monitor_id
            or receipt.get('monitor_port') != remote_port or receipt.get('ssh_profile') != row.get('ssh_profile')):
        raise TestError('작업 Monitor 열기 권한을 확인할 수 없습니다.', 'MONITOR_ACCESS_DENIED', 403)
    ticket = receipt.get('ticket')
    if not isinstance(ticket, str) or not TICKET.fullmatch(ticket):
        raise TestError('작업 Monitor 열기 권한을 확인할 수 없습니다.', 'MONITOR_ACCESS_DENIED', 403)
    if not supervisor.shared_forward_live(generation, local_port):
        raise offline
    return base + '/plugin-task/?task=' + quote(task_id, safe='') + '#ticket=' + quote(ticket, safe='')
