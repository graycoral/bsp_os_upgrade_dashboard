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
        manager.runner.registry.save_console(value, links)
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

    return api
