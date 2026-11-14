"""Public common configuration facade, with host authentication kept outside core."""
from typing import Literal
from fastapi import APIRouter, Request, Query
from ..core.models import TestError
from ..core.shared_settings import SharedUpdate, SettingsFile, ConnectorDesired, ConnectorReceipt, attach_shared_settings
from ..connector.api import require_local_connector
from ..core.connector_bootstrap import ConnectorEndpoint, ConnectorBootstrap, FORMAT

PREFIX = '/api/v1/gui-test/live/integration'


def service_mutation_allowed(path, method):
    """Exact extensions to the existing integration-only service control scope."""
    if method in {'GET', 'HEAD', 'OPTIONS'}:
        return True
    if path.startswith(PREFIX + '/'):
        return True
    return (method, path) in {
        ('POST', '/api/v1/gui-test/live/connector/register'),
        ('PUT', '/api/v1/gui-test/live/execution-timeouts'),
        ('PUT', '/api/v1/gui-test/live/source/request-settings'),
        ('POST', '/api/v1/gui-test/live/source/inspect'),
        ('PUT', '/api/v1/gui-test/live/source'),
    }


def create_router(manager):
    api = APIRouter(prefix=PREFIX)
    settings = attach_shared_settings(manager)

    def control(request):
        if not getattr(request.state, 'gui_principal', None):
            raise TestError('Authenticated common control principal required', 'CONTROL_REQUIRED', 403)

    @api.post('/connector-bootstrap')
    def connector_bootstrap(body: ConnectorEndpoint, request: Request):
        control(request)
        registry = getattr(request.app.state, 'registry', None) or getattr(request.app.state, 'gui_integration_registry', None)
        if registry is None:
            raise TestError('Integration service identity is unavailable', 'SERVICE_IDENTITY_MISMATCH', 409)
        identity = registry.snapshot(getattr(request.app.state, 'worker_running', False))
        return ConnectorBootstrap(format=FORMAT, endpoint=body, identity={key: identity[key] for key in ('runtime_id', 'package_version')}).model_dump()

    @api.get('/settings')
    def read_settings():
        return settings.read()

    @api.put('/settings')
    def save_settings(body: SharedUpdate, request: Request):
        control(request)
        return settings.save(body.model_dump())

    @api.get('/settings/file')
    def export_settings():
        return settings.export()

    @api.post('/settings/file/validate')
    def validate_settings_file(body: SettingsFile, request: Request):
        control(request)
        current = settings.read()
        return {'valid': True, 'current_revision': current['revision'],
                'revision_matches': body.expected_revision == current['revision']}

    @api.post('/settings/file')
    def import_settings(body: SettingsFile, request: Request):
        control(request)
        return settings.import_file(body.model_dump())

    @api.get('/paths')
    def browse_paths(kind: Literal['installer', 'source'], path: str | None = Query(None, max_length=4096)):
        return settings.browse(kind, path)

    @api.put('/connector-settings')
    def desired_connector_settings(body: ConnectorDesired, request: Request):
        control(request)
        return settings.desired(body.model_dump())

    @api.post('/connector-settings/receipt')
    def connector_settings_receipt(body: ConnectorReceipt, request: Request):
        require_local_connector(request)
        return settings.receipt(body.model_dump())

    return api
