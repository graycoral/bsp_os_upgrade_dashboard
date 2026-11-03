from typing import Literal
from fastapi import APIRouter, Header, Response
from pydantic import BaseModel, Field
from gui_test.core.models import StartRequest, Command, TestError, StrictModel, CommandTemplate, Connection, uid
from gui_test.core.reporting import export
from gui_test.adapters.windows_ports import enumerate_ports


class SavedItem(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    data: dict


class CommandPreview(StrictModel):
    tc_id: str = Field(min_length=1, max_length=1024)
    source_revision: str = Field(min_length=1, max_length=256)
    connection: Connection
    template: CommandTemplate


def router(manager):
    api = APIRouter(prefix='/api/v1/gui-test')

    @api.get('/capabilities')
    def capabilities():
        return {'mode': manager.mode, 'simulation': True, 'hardware': False,
                'message': 'Mock adapters only. Hardware commands and RBM API are not configured.',
                'branches': ['demo/main', 'demo/next'], 'sync_retries': manager.sync_retries}

    @api.get('/catalog')
    def catalog(branch: str = 'demo/main'):
        return manager.catalog(branch)

    @api.get('/boards')
    def boards():
        return {'source': 'MOCK', 'boards': manager.boards.boards()}

    @api.get('/ports')
    def ports():
        return enumerate_ports() if manager.mode == 'standalone' else {'status': 'USE_RBM_ADAPTER', 'ports': []}

    @api.post('/preflight')
    def preflight(body: StartRequest):
        checked = manager.preflight(body.model_dump())
        return {'ok': checked['ok'], 'simulation': True, 'checks': checked['checks']}

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

    @api.get('/demo/jobs')
    def jobs():
        return manager.dashboard.jobs() if manager.dashboard else []

    @api.post('/demo/jobs')
    def create_job(idempotency_key: str = Header(min_length=1, max_length=180)):
        if not manager.dashboard:
            raise TestError('Standalone cannot link to a Dashboard')
        return manager.dashboard.create(idempotency_key)

    @api.get('/demo/jobs/{job_id}')
    def job(job_id: str):
        if not manager.dashboard:
            raise TestError('No Dashboard in standalone', status=404)
        return manager.dashboard.engine.snapshot(job_id)

    @api.post('/demo/jobs/{job_id}/change-baseline')
    def change_baseline(job_id: str):
        if not manager.dashboard:
            raise TestError('No Dashboard in standalone')
        e = manager.dashboard.engine
        j = e.snapshot(job_id)
        return e.act(job_id, uid(), j['version'], 'invalidate', {'source_revision': 'demo-changed-' + uid(), 'reason': 'User-injected demo baseline change'})

    @api.post('/demo/jobs/{job_id}/approve-revalidation')
    def approve(job_id: str, body: Command, idempotency_key: str = Header(min_length=1, max_length=180)):
        if not manager.dashboard:
            raise TestError('No Dashboard in standalone')
        return manager.dashboard.engine.act(job_id, idempotency_key, body.expected_version,
                                            'approve-gui-revalidation', body.data)

    return api
