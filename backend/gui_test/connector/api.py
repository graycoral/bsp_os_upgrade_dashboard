"""Narrow host adapter; no extra worker or scheduler is created here."""
import ipaddress
import json
from fastapi import APIRouter, Request, Query
from pydantic import Field
from ..core.models import StrictModel, TestError


class Registration(StrictModel):
    url: str = Field(max_length=256)
    runner_id: str = Field(pattern=r'^[a-f0-9]{32}$')


def require_local_connector(request):
    try:
        peer = ipaddress.ip_address(request.client.host)
        local = peer.is_loopback or bool(getattr(peer, 'ipv4_mapped', None) and peer.ipv4_mapped.is_loopback)
    except (ValueError, AttributeError):
        local = False
    if not local or request.headers.get('origin') or request.headers.get('sec-fetch-site'):
        raise TestError('Connector requests require a local non-browser client', 'CONTROL_REQUIRED', 403)


def router(manager):
    api = APIRouter(prefix='/api/v1/gui-test/live/connector')
    from .test_status import TestStatus
    tests = TestStatus(manager)

    @api.get('/test-status')
    def test_status(request: Request):
        require_local_connector(request)
        registry = getattr(manager.runner, 'registry', None)
        registration = registry.read() if registry is not None else None
        return tests.snapshot((registration or {}).get('runner_id'))

    @api.post('/register')
    def register(body: Registration, request: Request):
        require_local_connector(request)
        for run in manager.store.all():
            pinned = run.get('runner_id_snapshot') or (run.get('integration') or {}).get('config',{}).get('runner_id')
            if not run['simulation'] and ((pinned and pinned != body.runner_id) or (not pinned and run['attempts'])):
                raise TestError('Existing Run requires its original trusted connector', 'RUNNER_CHANGED', 409)
        result = manager.runner.registry.register(body.url, body.runner_id)
        previous_console=manager.runner.registry.console()
        cursor=previous_console.get('cursor',0); epoch=previous_console.get('epoch')
        value = manager.runner.target().request('/console?after='+str(cursor)+('&epoch='+epoch if epoch else '')+'&error_after='+str(previous_console.get('error_cursor',0)))
        manager.runner.registry.save_console(value, links, expected_registration=result)
        from .paths import server_paths
        return result | {'server_paths': server_paths(manager, body.runner_id), 'source_ready': manager.sources.descriptor() is not None or manager.runner.target().request('/identity').get('source_configured_v1') is True}

    @api.get('/inventory')
    def inventory():
        return manager.runner.inventory() if hasattr(manager.runner, 'registry') else {'boards': [], 'fresh': False}

    @api.get('/stop-readiness')
    def stop_readiness(request: Request):
        require_local_connector(request)
        active = any(run['state'] not in {'COMPLETED', 'CANCELLED'} for run in manager.store.all())
        with manager.store.connection() as c:
            deletion = any(json.loads(row[0]).get('state') not in {'DONE', 'DELETED'} for row in c.execute("SELECT data FROM documents WHERE kind='session-deletion'"))
        return {'safe': not active and not deletion}

    def links(refs):
        found = []
        for run in manager.store.all():
            for attempt in run['attempts']:
                if (attempt.get('process_ref') or '').removeprefix('windows:') in refs:
                    found.append({'run_id': run['id'], 'attempt_id': attempt['id'], 'batch_id': ((run.get('integration') or {}).get('batch') or {}).get('batch_id')})
        return found

    @api.get('/console')
    def console():
        registry = getattr(manager.runner, 'registry', None)
        if registry is None: return {'boards': [], 'errors': [], 'cursor': 0}
        return registry.console()

    @api.get('/errors')
    def errors(after: int = Query(0, ge=0)):
        return manager.runner.registry.errors(after)

    @api.get('/recent-executions')
    def recent_executions():
        return manager.runner.target().request('/recent-executions')

    def mirror():
        from .mirror import ConnectorMirror
        registry = getattr(manager.runner, 'registry', None)
        if registry is None:
            raise TestError('보드 커넥터를 먼저 연결하세요.', 'CONNECTOR_DISCONNECTED', 409)
        return ConnectorMirror(registry)

    @api.get('/mirror')
    def mirror_snapshot():
        from ..core.shared_settings import attach_shared_settings
        value = mirror().snapshot()
        registry = manager.runner.registry
        registration = registry.read()
        # Read persisted observations; opening the tab must not contact hardware.
        value['inventory'] = dict((registration or {}).get('inventory', {'boards': []}),
                                  fresh=value['fresh'], runner_id=(registration or {}).get('runner_id'))
        value['console'] = registry.console()
        value['errors'] = registry.recent_errors()
        value['settings'] = attach_shared_settings(manager).read()
        value['test_status'] = tests.snapshot((registration or {}).get('runner_id'))
        return value

    @api.post('/mirror/state')
    def mirror_state(body: dict, request: Request):
        require_local_connector(request)
        if set(body) != {'projection', 'registration'} or not isinstance(body['registration'], dict):
            raise TestError('Invalid mirror projection', status=422)
        return mirror().publish(body['projection'], expected_registration=body['registration'])

    @api.post('/mirror/commands')
    def mirror_command(body: dict, request: Request):
        if not getattr(request.state, 'gui_principal', None):
            raise TestError('Common control principal required', 'CONTROL_REQUIRED', 403)
        viewer = getattr(request.state, 'gui_browser', None)
        required = 'settings' if body.get('action') == 'apply-settings' else 'control'
        if viewer is not None and required not in viewer.get('scopes', []):
            raise TestError('This command requires the ' + required + ' scope', 'CONTROL_REQUIRED', 403)
        def validate(value):
            if value['action'] == 'restart':
                if any(run['state'] not in {'COMPLETED', 'CANCELLED'} for run in manager.store.all()):
                    raise TestError('진행·예약·종료 불명 Run이 있습니다.', 'CONNECTOR_BUSY', 409)
                with manager.store.connection() as c:
                    if any(json.loads(row[0]).get('state') not in {'DONE', 'DELETED'} for row in c.execute("SELECT data FROM documents WHERE kind='session-deletion'")):
                        raise TestError('시험 기록 삭제를 확인 중입니다.', 'CONNECTOR_BUSY', 409)
                return
            if value['action'] != 'apply-settings':
                return
            from ..core.shared_settings import attach_shared_settings
            application = attach_shared_settings(manager).connector_application()
            if (application.get('runner_id') != value['runner_id'] or
                    application.get('desired_revision') != value['body']['desired_revision']):
                raise TestError('공통 설정이 변경됐습니다. 다시 불러오세요.', 'SETTINGS_CHANGED', 409)
        return mirror().create(body, validate=validate)

    @api.get('/mirror/commands/{command_id}')
    def mirror_command_receipt(command_id: str):
        return mirror().get(command_id)

    @api.post('/mirror/commands/{command_id}/abandon')
    def mirror_abandon(command_id: str, body: dict, request: Request):
        viewer = getattr(request.state, 'gui_browser', None)
        if (not getattr(request.state, 'gui_principal', None) or
                viewer is not None and 'control' not in viewer.get('scopes', [])):
            raise TestError('Common control scope required', 'CONTROL_REQUIRED', 403)
        return mirror().abandon(command_id, body)

    @api.post('/mirror/claim')
    def mirror_claim(body: dict, request: Request):
        require_local_connector(request)
        return mirror().claim(body)

    @api.post('/mirror/commands/{command_id}/receipt')
    def mirror_receipt(command_id: str, body: dict, request: Request):
        require_local_connector(request)
        return mirror().finish(command_id, body)

    return api
