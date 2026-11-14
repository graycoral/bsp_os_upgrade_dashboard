"""Storage policy and reviewable cache-only cleanup for plugin/monitor clients."""
from fastapi import APIRouter, Request
from ..core.models import TestError
from ..core.retention import StorageSettings, StorageUpdate, CleanupRequest, collect, connector_sync, connector_cleanup


def create_router(manager):
    api = APIRouter(prefix='/api/v1/gui-test/live/integration')
    settings = StorageSettings(manager.store)

    def control(request):
        if not getattr(request.state, 'gui_principal', None):
            raise TestError('Authenticated common control principal required', 'CONTROL_REQUIRED', 403)

    @api.get('/storage-policy')
    def read():
        return settings.read() | {'report': settings.report(), 'connector_sync': connector_sync(manager, retry=False)}

    @api.put('/storage-policy')
    def save(body: StorageUpdate, request: Request):
        control(request)
        value = settings.save(body.model_dump())
        return value | {'connector_sync': connector_sync(manager)}

    @api.post('/storage-cleanup')
    def cleanup(body: CleanupRequest, request: Request):
        control(request)
        return collect(manager, dry_run=body.dry_run) | {'connector_cleanup': connector_cleanup(manager, dry_run=body.dry_run)}

    return api
