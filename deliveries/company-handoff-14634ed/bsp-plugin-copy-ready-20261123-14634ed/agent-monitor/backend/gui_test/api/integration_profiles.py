"""Narrow common setup facade; none of these endpoints execute a command/TC."""
from fastapi import APIRouter, Request
from ..core.integration_profiles import IntegrationProfiles, CommandSave, ProfileSelection, FlashSave
from ..core.models import CommandTemplate, TestError

PREFIX = '/api/v1/gui-test/live/integration/profiles'


def create_router(manager):
    api = APIRouter(prefix=PREFIX)
    profiles = IntegrationProfiles(manager)

    def control(request):
        if not getattr(request.state, 'gui_principal', None):
            raise TestError('Authenticated common settings principal required', 'CONTROL_REQUIRED', 403)

    @api.get('/commands')
    def commands():
        return profiles.commands()

    @api.post('/commands/validate')
    def validate_command(body: CommandTemplate, request: Request):
        control(request)
        return profiles.validate_command(body.model_dump())

    @api.get('/commands/{name}')
    def command(name: str):
        return profiles.command(name)

    @api.put('/commands/{name}')
    def save_command(name: str, body: CommandSave, request: Request):
        control(request)
        return profiles.save_command(name, body.model_dump())

    @api.post('/commands/{name}/select')
    def select_command(name: str, body: ProfileSelection, request: Request):
        control(request)
        return profiles.select('command', name, body.model_dump())

    @api.get('/flash')
    def flash_profiles():
        return profiles.flashes()

    @api.get('/flash/discovery')
    def flash_setup():
        return profiles.flash_setup(False)

    @api.post('/flash/discover-devices')
    def discover_flash_devices(request: Request):
        control(request)
        return profiles.flash_setup(True)

    @api.put('/flash/{name}')
    def save_flash(name: str, body: FlashSave, request: Request):
        control(request)
        return profiles.save_flash(name, body.model_dump())

    @api.post('/flash/{name}/select')
    def select_flash(name: str, body: ProfileSelection, request: Request):
        control(request)
        return profiles.select('flash', name, body.model_dump())

    return api
