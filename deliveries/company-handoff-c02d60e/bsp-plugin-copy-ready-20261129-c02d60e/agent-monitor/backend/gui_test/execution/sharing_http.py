"""Shared Host HTTP policy and task-only Monitor views."""

import re
import sqlite3
from contextlib import nullcontext

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from ..core.models import TestError
from . import retention, sharing
from .connector_runs import ACTIVE_RUN_STATES, ACTIVE_RUN_STATES_SQL


_TASK_ROUTE = re.compile(r'/v1/(?:connector-runs|analyses)(?:/.*)?|/v1/sharing/run-config')
_SNAPSHOT_ROUTE = re.compile(r'/v1/(source|installer)-snapshots/[a-f0-9]{64}')
_BATCH_ROUTE = re.compile(r'/v1/batches/[a-f0-9]{32}(?:/(?:prepare|poll|cancel|release|reconcile))?')
_SERVICE_EXECUTIONS = re.compile(r'/v1/executions(?:/[a-f0-9]{32}(?:/(?:poll|cancel|reconcile))?)?')
_TASK_PATH = re.compile(r'/v1/sharing/tasks/([a-f0-9]{32})(?:/(view-tickets|view|monitor-proof)(?:/.*)?)?')
_SERVICE_INFO = frozenset({'/v1/boards', '/v1/verify', '/v1/flash-setup'})
_INFO_SHARED = frozenset({'/v1/diagnostics/connection', '/v1/test-status'})


def bearer_token(request):
    scheme, _, value = request.headers.get('authorization', '').partition(' ')
    return value if scheme.lower() == 'bearer' else ''


def authorize(host, request):
    path, method = request.url.path, request.method
    path = path.rstrip('/')
    bearer = bearer_token(request)
    request.state.access = None
    request.state.mode = 'blocked'
    try:
        mode, access = host.sharing.mode_and_access(bearer)
    except sqlite3.Error:
        if (method, path) == ('GET', '/v1/identity'):
            return
        raise sharing.unavailable() from None
    except TestError as exc:
        if (method, path) == ('GET', '/v1/identity') and exc.code == 'SHARING_UNAVAILABLE':
            return
        raise
    request.state.mode = mode
    if mode == 'individual':
        if path.startswith('/v1/sharing/'):
            raise TestError('Shared Host mode is disabled', 'SHARING_DISABLED', 409)
        return
    if (method, path) == ('GET', '/v1/identity'):
        request.state.access = access
        return

    match = _TASK_PATH.fullmatch(path)
    if (path == '/v1/sharing/view-tickets/redeem' and method == 'POST'
            or match and match[2] == 'view' and method == 'GET'):
        return
    if not access:
        raise sharing.auth_required()

    register = match and match[2] is None and method == 'PUT'
    task_route = _TASK_ROUTE.fullmatch(path)
    if access.role == 'admin':
        if task_route:
            raise sharing.denied()
    elif access.role == 'service':
        if not (_SNAPSHOT_ROUTE.fullmatch(path) or _BATCH_ROUTE.fullmatch(path)
                or _SERVICE_EXECUTIONS.fullmatch(path) or path in _SERVICE_INFO
                or path == '/v1/batches' or path.startswith('/v1/flash-profiles/')):
            raise sharing.denied()
    else:
        if not (task_route or register or match and match[2] in {'view-tickets', 'monitor-proof'} or _SNAPSHOT_ROUTE.fullmatch(path)
                or path.startswith('/v1/flash-profiles/') or path in _INFO_SHARED
                or path in {'/v1/sharing/tasks', '/v1/peer/hello'}):
            raise sharing.denied()
        task_id = request.headers.get('x-bsp-task-id')
        key = request.headers.get('x-bsp-task-key')
        if register and task_id not in {None, match[1]}:
            raise sharing.denied()
        task_optional = path in {'/v1/peer/hello', '/v1/diagnostics/connection'}
        if not task_optional or task_id or key:
            access = host.sharing.task_access(access, match[1] if register else task_id, key)
            if not register:
                with host.sharing.connect() as db:
                    host.sharing.require_task(db, access)
    request.state.access = access


def task_access(request):
    access = request.state.access
    return access if access and access.role == 'account' and access.task_id else None


def data_access(request):
    access = request.state.access
    return access if access and access.role in {'account', 'service'} else None


def service_access(request):
    access = request.state.access
    return access if access and access.role == 'service' else None


def require_active(sh, db, access):
    if access.role == 'account':
        sh.require_task(db, access)
    else:
        sh.require_principal(db, access)


def owner_action(host, request, identity, fn, *args, analysis=False, mutate=False, snapshots=False, **kwargs):
    access = task_access(request)
    if not access:
        return fn(identity, *args, **kwargs)
    with retention.cache_lock(host) if snapshots else nullcontext(), host.lock:
        with host.sharing.connect() as db:
            host.sharing.require_task(db, access)
            if analysis:
                row = db.execute('SELECT run_id FROM connector_analyses WHERE analysis_id=?', (identity,)).fetchone()
                if not row:
                    raise sharing.not_found()
                run_id = row['run_id']
            else:
                run_id = identity
            epoch = request.headers.get('x-bsp-run-epoch')
            owner = host.sharing.owner(db, run_id, access.task_id, epoch if mutate else None)
            if mutate and epoch is None:
                raise TestError('X-Bsp-Run-Epoch is required for this action', 'RUN_EPOCH_REQUIRED', 422)
        result = fn(identity, *args, **kwargs)
        if analysis and 'status' in result:
            result['ownership_epoch'] = owner['epoch']
        return result


def service_action(host, request, identity, fn, *args, batch=False, snapshot_id=None, snapshot_kind='installer'):
    access = service_access(request)
    if not access:
        return fn(identity, *args)
    with retention.cache_lock(host) if snapshot_id else nullcontext(), host.lock:
        with host.sharing.connect() as db:
            check = host.sharing.require_batch if batch else host.sharing.require_job
            check(db, access, identity)
            if snapshot_id:
                host.sharing.require_snapshot(db, access, snapshot_kind, snapshot_id)
        return fn(identity, *args)


def task_list(host, db, access):
    tasks = host.sharing.task_rows(db, access)
    row = db.execute(
        'SELECT r.run_id,o.task_id FROM connector_runs r LEFT JOIN sharing_run_owners o USING(run_id) '
        f'WHERE r.state IN ({ACTIVE_RUN_STATES_SQL}) OR r.analysis_latched=1 ORDER BY r.updated_at DESC LIMIT 1',
        ACTIVE_RUN_STATES,
    ).fetchone()
    active_task = row['task_id'] if row and access.role == 'admin' else None
    for task in tasks:
        matches = row and row['task_id'] == task['task_id']
        task['active_run_id'] = row['run_id'] if matches else None
        if matches:
            active_task = task['task_id']
    return {'tasks': tasks, 'active_task_id': active_task}


def occupancy(db, access):
    run = db.execute(
        'SELECT t.account,t.project FROM connector_runs r LEFT JOIN sharing_run_owners o USING(run_id) '
        'LEFT JOIN sharing_tasks t USING(task_id) '
        f'WHERE r.state IN ({ACTIVE_RUN_STATES_SQL}) OR r.analysis_latched=1 LIMIT 1', ACTIVE_RUN_STATES,
    ).fetchone()
    busy = (run is not None or db.execute(
        "SELECT EXISTS(SELECT 1 FROM jobs WHERE json_extract(data,'$.state') IN ('RUNNING','UNKNOWN')) "
        "OR EXISTS(SELECT 1 FROM batches WHERE json_extract(data,'$.state')!='RELEASED')"
    ).fetchone()[0] == 1)
    result = {'host_busy': busy}
    if run and run['account'] == access.name:
        result['occupied_project'] = run['project']
    return result


def run_config(host):
    inventory = host.inventory()
    busy = inventory['host_busy'] or inventory['reserved']
    fields = ('board_id', 'host', 'com', 'node', 'detected')
    boards = [{key: board[key] for key in fields if key in board} | {
        'state': 'RESERVED' if busy else ('CONNECTED' if board['detected'] else 'DISCONNECTED'),
    } for board in inventory['boards']]
    return {'runner_id': host.identity, 'boards': boards, 'host_busy': busy,
            'flash_profile_revisions': host.flash_profile_revisions}


def scoped_diagnostics(host, access):
    with host.lock, host.sharing.connect() as db:
        if access.task_id:
            host.sharing.require_task(db, access)
            active = host.connector.get_active_run(task_id=access.task_id)
            analyses = host.connector.list_analyses(status='PENDING', task_id=access.task_id)
        else:
            host.sharing.require_principal(db, access)
            active, analyses = None, []
        return {
            'runner_id': host.identity,
            'overall_connection_state': 'CONNECTED',
            **occupancy(db, access),
            'active_run': active,
            'active_run_summary': active,
            'pending_analyses': len(analyses),
            'pending_analyses_count': len(analyses),
        }


def attach_sharing(app, host):
    sh = host.sharing

    @app.put('/v1/sharing/tasks/{task_id}')
    def bind_task(request: Request, task_id: str, body: dict):
        if set(body) != {'project', 'monitor_id'}:
            raise sharing.invalid_value('Task registration requires project and Monitor ID')
        access = task_access(request)
        if not access or access.task_id != task_id:
            raise sharing.denied()
        with host.lock, sh.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            sh.bind_task(db, access, **body)
            return task_list(host, db, access)['tasks'][0]

    @app.get('/v1/sharing/tasks')
    def list_tasks(request: Request):
        with host.lock, sh.connect() as db:
            return task_list(host, db, request.state.access)

    @app.get('/v1/sharing/run-config')
    def get_run_config(request: Request):
        access = task_access(request)
        with host.lock, sh.connect() as db:
            sh.require_task(db, access)
            return run_config(host)

    @app.post('/v1/sharing/tasks/{task_id}/view-tickets')
    def ticket(request: Request, task_id: str):
        with host.lock, sh.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return JSONResponse(sh.mint_view(db, task_id, access=request.state.access),
                                headers={'Cache-Control': 'no-store'})

    @app.post('/v1/sharing/tasks/{task_id}/monitor-proof')
    def monitor_proof(request: Request, task_id: str, body: dict):
        if set(body) != {'challenge', 'proof'}:
            raise sharing.invalid_value('Monitor proof requires challenge and proof')
        with host.lock, sh.connect() as db:
            sh.verify_task_monitor(db, request.state.access, task_id, **body)
        return {'verified': True}

    @app.post('/v1/sharing/view-tickets/redeem')
    def redeem(body: dict):
        if (set(body) - {'ticket', 'monitor_id', 'task_id', 'monitor_proof'} or
                not all(isinstance(body.get(key), str) for key in ('ticket', 'monitor_id', 'monitor_proof')) or
                'task_id' in body and not isinstance(body['task_id'], str)):
            raise sharing.auth_required()
        with host.lock, sh.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            grant = sh.mint_view(db, body.get('task_id'), monitor_id=body['monitor_id'],
                                 ticket=body['ticket'], monitor_proof=body['monitor_proof'])
            return JSONResponse(grant, headers={'Cache-Control': 'no-store'})

    @app.get('/v1/sharing/tasks/{task_id}/view')
    def view(request: Request, task_id: str, run_id: str | None = None):
        with host.lock, sh.connect() as db:
            task = sh.require_view(db, bearer_token(request), 'view', task_id=task_id)
            runs = host.connector.list_runs(task_id=task_id)
            active = host.connector.get_active_run(task_id=task_id)
            if run_id:
                sh.owner(db, run_id, task_id)
                run = host.connector.get_run(run_id)
            else:
                run = active or (runs[0] if runs else None)
            summary = dict(task) | {'active_run_id': active['run_id'] if active else None}
            return JSONResponse({'task': summary, 'run': run, 'runs': runs}, headers={'Cache-Control': 'no-store'})

    @app.get('/v1/sharing/tasks/{task_id}/view/runs/{run_id}/attempts/{attempt_id}/logs')
    def view_logs(request: Request, task_id: str, run_id: str, attempt_id: str,
                  stream: str = 'stdout', offset: int = Query(0, ge=0), limit: int = Query(65536, ge=1, le=524288)):
        with host.lock, sh.connect() as db:
            task = sh.require_view(db, bearer_token(request), 'view', task_id=task_id)
            sh.owner(db, run_id, task_id)
            result = host.connector.read_attempt_logs(run_id, attempt_id, stream=stream, offset=offset, limit=limit)
        return JSONResponse(result | {'monitor_id': task['monitor_id']}, headers={'Cache-Control': 'no-store'})

    @app.post('/v1/sharing/runs/{run_id}/handoff')
    def handoff(request: Request, run_id: str, body: dict):
        if request.state.access.role != 'admin':
            raise sharing.denied()
        if set(body) != {'expected_epoch', 'task_id'}:
            raise sharing.invalid_value('Run handoff requires expected_epoch and task_id')
        with host.lock, sh.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return sh.handoff(db, run_id, **body)

    @app.post('/v1/sharing/principals/revoke')
    def revoke(request: Request, body: dict):
        if request.state.access.role != 'admin':
            raise sharing.denied()
        if set(body) != {'role', 'name'}:
            raise sharing.invalid_value('Revocation requires role and name')
        with host.lock, sh.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            sh.revoke(db, **body)
        return {'revoked': True}
