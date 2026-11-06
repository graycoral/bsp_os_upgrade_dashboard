from typing import Literal
from fastapi import APIRouter, Header, Response
from pydantic import BaseModel, Field
from ..core.models import StartRequest, Command, TestError, StrictModel, CommandTemplate, Connection
from ..core.reporting import export
from ..adapters.windows_ports import enumerate_ports


class SavedItem(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    data: dict


class CommandPreview(StrictModel):
    tc_id: str = Field(min_length=1, max_length=1024)
    source_revision: str = Field(min_length=1, max_length=256)
    connection: Connection
    template: CommandTemplate


class SourceInspect(StrictModel):
    kind: Literal['legacy', 'server-folder', 'git-url']
    location: str = Field(max_length=2048)


class SourceApply(StrictModel):
    inspection_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    ref: str | None = Field(default=None, max_length=1024)
    expected_version: int = Field(strict=True, ge=0)


def router(manager, live=False):
    api = APIRouter(prefix='/api/v1/gui-test' + ('/live' if live else ''))

    def connection():
        status = manager.runner.readiness()
        state = 'connected' if status['ready'] else 'unconfigured' if status['code'] == 'RUNNER_NOT_CONFIGURED' else 'disconnected'
        return {'state': state, 'ready': status['ready'], 'message': status['message']}

    def require_connection():
        if live:
            status = connection()
            if not status['ready']:
                raise TestError(status['message'], 'RUNNER_UNAVAILABLE', 503)

    @api.get('/capabilities')
    def capabilities():
        return {'mode': manager.mode, 'simulation': manager.simulation, 'hardware': not manager.simulation,
                'job_sync': manager.dashboard is not None,
                'message': 'Mock adapters only. Hardware commands and RBM API are not configured.' if manager.simulation else 'Windows Python execution through SSH tunnel. Physical board/image attestation and automatic Job synchronization are not configured.',
                'branches': manager.branches, 'sync_retries': manager.sync_retries,
                **({'connection': connection()} if live else {})}

    @api.get('/catalog')
    def catalog(branch: str = 'demo/main'):
        if live and manager.sources.state()['active']['kind'] == 'legacy' and not connection()['ready']:
            return {'branch': 'shared', 'revision': '', 'metadata_revision': '', 'tests': []}
        return manager.catalog(branch)

    @api.get('/source')
    def source():
        return manager.source_state()

    @api.post('/source/inspect')
    def inspect_source(body: SourceInspect):
        return manager.sources.inspect(body.kind, body.location)

    @api.put('/source')
    def apply_source(body: SourceApply):
        result = manager.sources.apply(body.inspection_id, body.ref, body.expected_version)
        if result['catalog'] is None:
            if live and not connection()['ready']:
                result['catalog'] = {'branch': 'shared', 'revision': '', 'metadata_revision': '', 'tests': []}
            else:
                try:
                    result['catalog'] = manager.catalog()
                except TestError:
                    result['catalog'] = {'branch': 'shared', 'revision': '', 'metadata_revision': '', 'tests': []}
        return result | {'execution': manager.source_execution()}

    @api.get('/module-selection')
    def module_selection(job_id: str, module_id: str, branch: str = 'demo/main', catalog_revision: str = ''):
        service = manager.module_selection_service
        if service is None or manager.mode != 'dashboard':
            raise TestError('이 화면에서는 BSP 모듈 TC 선택을 사용할 수 없습니다.', 'MODULE_CONTEXT_UNAVAILABLE', 422)
        return service.select(manager, job_id, module_id, branch, catalog_revision)

    @api.get('/boards')
    def boards():
        if live and not connection()['ready']:
            return {'source': 'WINDOWS_CONFIGURED', 'boards': []}
        return {'source': 'MOCK' if manager.simulation else 'WINDOWS_CONFIGURED', 'boards': manager.boards.boards()}

    @api.get('/ports')
    def ports():
        return enumerate_ports() if manager.mode == 'standalone' else {'status': 'USE_RBM_ADAPTER', 'ports': []}

    @api.post('/preflight')
    def preflight(body: StartRequest):
        require_connection()
        checked = manager.preflight(body.model_dump())
        return {'ok': checked['ok'], 'simulation': manager.simulation, 'checks': checked['checks']}

    @api.post('/commands/preview')
    def preview(body: CommandPreview):
        return manager.preview_command(body.tc_id, body.source_revision, body.connection.model_dump(), body.template.model_dump())

    @api.get('/runs')
    def runs():
        return [{k: manager.decorate(run)[k] for k in ('id', 'state', 'overall_result', 'created_at', 'progress', 'version')}
                for run in manager.store.all()]

    @api.post('/runs', status_code=202)
    def start(body: StartRequest, idempotency_key: str = Header(min_length=1, max_length=180),
              x_gui_session: str = Header(min_length=1, max_length=100)):
        require_connection()
        return manager.start(idempotency_key, x_gui_session, body.model_dump())

    @api.get('/runs/{run_id}')
    def run(run_id: str):
        return manager.get(run_id)

    @api.get('/runs/{run_id}/events')
    def events(run_id: str):
        return manager.store.events(run_id)

    @api.post('/runs/{run_id}/heartbeat')
    def heartbeat(run_id: str, x_gui_session: str = Header(min_length=1, max_length=100)):
        return manager.heartbeat(run_id, x_gui_session)

    @api.post('/runs/{run_id}/actions/{action}')
    def action(run_id: str, action: str, body: Command,
               idempotency_key: str = Header(min_length=1, max_length=180),
               x_gui_session: str = Header(min_length=1, max_length=100)):
        # Offline pause/cancel/control must still persist local intent. Resuming
        # or reconciling hardware requires the configured runner.
        if action in {'resume', 'recover', 'demo-recover'}:
            require_connection()
        return manager.act(run_id, idempotency_key, x_gui_session, body.expected_version, action, body.data)

    @api.get('/saved/{kind}')
    def saved(kind: Literal['suite', 'profile', 'command']):
        return manager.store.documents(kind)

    @api.put('/saved/{kind}')
    def save(kind: Literal['suite', 'profile', 'command'], body: SavedItem):
        return manager.save_document(kind, body.name, body.data)

    @api.get('/runs/{run_id}/report/{format}')
    def report(run_id: str, format: Literal['json', 'csv', 'html', 'pdf', 'logs']):
        content, mime = export(manager.get(run_id), format)
        return Response(content, media_type=mime, headers={'Content-Disposition': f'attachment; filename="{run_id}.{ "zip" if format == "logs" else format}"'})

    @api.get('/runs/{run_id}/logs/{attempt_id}/{stream}')
    def log(run_id: str, attempt_id: str, stream: Literal['stdout', 'stderr']):
        run = manager.get(run_id)
        a = next((a for a in run['attempts'] if a['id'] == attempt_id), None)
        if not a:
            raise TestError('Attempt not found in this run', status=404)
        return Response(a[stream], media_type='text/plain', headers={'Content-Disposition': f'attachment; filename="{attempt_id}-{stream}.log"'})

    return api
