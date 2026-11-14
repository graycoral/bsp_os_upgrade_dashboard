"""Provision shared TC/flash references without owning an execution process.

Public flash updates are named profile patches. Unrelated trusted legacy
profiles stay local and unchanged. Only Windows validates local file existence.
"""
import copy
from pathlib import Path, PureWindowsPath
import re
from types import SimpleNamespace
from typing import Annotated

from pydantic import Field, StrictBool, StrictInt, model_validator
from .models import StrictModel, CommandTemplate, Connection, TestError, digest
from ..adapters.runner import validate_command_template, validate_windows_command

SHA = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Name = Annotated[str, Field(pattern=r'^[A-Za-z0-9_.-]{1,80}$')]
Timeout = Annotated[float, Field(strict=True, ge=1, le=7200)]


def profile_revision(name, value):
    return digest({'profile': name, 'config': value})


class CommandSave(CommandTemplate):
    # None means create, never unconditional overwrite.
    expected_revision: SHA | None = None


class ProfileSelection(StrictModel):
    expected_settings_revision: SHA
    revision: SHA



class FlashObserver(StrictModel):
    port: str | None = Field(default=None, pattern=r'^COM[1-9][0-9]{0,3}$')
    rx_only_confirmed: StrictBool = False
    control_lines_isolated: StrictBool = False
    panic_signatures: list[str] = Field(min_length=1, max_length=32)
    boot_signatures: list[str] = Field(min_length=1, max_length=32)
    login_markers: list[str] = Field(min_length=1, max_length=32)

    @model_validator(mode='after')
    def valid_markers(self):
        for values in (self.panic_signatures, self.boot_signatures, self.login_markers):
            if any(not value.strip() or '\0' in value or not 1 <= len(value.encode('utf-8')) <= 1024 for value in values):
                raise ValueError('Explicit bounded observer signatures are required')
        return self

class FlashBoard(StrictModel):
    com: str = Field(pattern=r'^COM[1-9][0-9]{0,3}$')
    serial: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,160}$')
    baudrate: StrictInt = Field(default=115200, ge=1, le=4_000_000)
    line_ending: str = Field(default='cr', pattern=r'^(cr|lf|crlf)$')
    lkshell_prompt: str = Field(min_length=1, max_length=1024)
    boot_marker: str = Field(min_length=1, max_length=1024)
    login_prompt: str = Field(min_length=1, max_length=1024)
    observer: FlashObserver

    @model_validator(mode='after')
    def markers(self):
        for key in ('lkshell_prompt', 'boot_marker', 'login_prompt'):
            value = getattr(self, key)
            if not value.strip() or '\0' in value:
                raise ValueError('Explicit console readiness markers are required')
        if self.login_prompt not in self.observer.login_markers:
            raise ValueError('Fresh login marker must include this board login prompt')
        if self.lkshell_prompt.strip().casefold() in {'reboot lkshell', 'fast', 'fastboot init success'}:
            raise ValueError('lkshell readiness must identify actual output before fast')
        return self


class FlashProfile(StrictModel):
    enabled: StrictBool
    fastboot: str = Field(min_length=1, max_length=4096)
    batch_sha256: SHA
    success_marker: str = Field(min_length=1, max_length=1024)
    failure_markers: list[str] = Field(min_length=1, max_length=32)
    boards: dict[str, FlashBoard] = Field(min_length=1, max_length=32)
    image_root: str | None = Field(default=None, max_length=4096)
    console_timeout: Timeout = 120.0
    fastboot_timeout: Timeout = 60.0
    flash_timeout: Timeout = 1800.0
    boot_timeout: Timeout = 180.0
    max_bundle_bytes: StrictInt = Field(default=64 * 1024**3, ge=1, le=1024**4)

    @model_validator(mode='after')
    def safe(self):
        path = PureWindowsPath(self.fastboot)
        if (not path.is_absolute() and not Path(self.fastboot).is_absolute() or
                path.name.casefold() not in {'fastboot.exe', 'fastboot'} or
                any(c in self.fastboot for c in '\0\r\n') or '..' in path.parts):
            raise ValueError('Use an absolute fastboot executable path')
        if not self.success_marker.strip() or '\0' in self.success_marker:
            raise ValueError('Explicit BAT success output is required')
        if any(not v.strip() or len(v) > 1024 or '\0' in v for v in self.failure_markers):
            raise ValueError('Explicit nonempty BAT failure markers are required')
        if any(not re.fullmatch(r'[\w.-]{1,80}', name) for name in self.boards):
            raise ValueError('Invalid board identity')
        ports=[value.observer.port for value in self.boards.values() if value.observer.port is not None]
        if len(ports)!=len(set(ports)):
            raise ValueError('Each RX observer endpoint requires one owner')
        if len({value.serial for value in self.boards.values()}) != len(self.boards):
            raise ValueError('Fastboot serials must be distinct')
        if self.image_root is not None:
            root = PureWindowsPath(self.image_root)
            if (not root.is_absolute() and not Path(self.image_root).is_absolute() or
                    '..' in root.parts or any(c in self.image_root for c in '\0\r\n')):
                raise ValueError('Use a separate absolute image root')
        return self


def flash_value(value):
    return FlashProfile.model_validate(value).model_dump(exclude_none=True)


class FlashPatch(StrictModel):
    profiles: dict[Name, FlashProfile] = Field(min_length=1, max_length=100)
    expected_revisions: dict[Name, SHA | None] = Field(max_length=100)

    @model_validator(mode='after')
    def same_names(self):
        if set(self.profiles) != set(self.expected_revisions):
            raise ValueError('Every flash profile update requires its previous local revision or null for creation')
        return self


class FlashSave(StrictModel):
    expected_revision: SHA
    runner_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_profile_revision: SHA | None = None
    profile: FlashProfile


def merge_flash_patch(existing, patch, boards, runtime, *, serial_transport='native', console_observers=None):
    """Validate Windows's own files and mappings using the execution validator.

    No COM is opened and no process is started. Targeted CAS prevents a pending
    central patch from overwriting a newer local edit during reconnection.
    """
    from ..execution.flashing import FlashService
    patch = FlashPatch.model_validate(patch)
    result = copy.deepcopy(existing or {})
    profiles = result.setdefault('profiles', {})
    configured = [Connection.model_validate({'a': board}).a.model_dump() for board in boards]
    for name, model in patch.profiles.items():
        value = model.model_dump(exclude_none=True)
        old = profiles.get(name)
        if old is not None and advanced_flash_fields(old):
            error=TestError('This trusted profile has advanced fields; keep it unchanged and create a new named public profile',
                            'FLASH_PROFILE_ADVANCED',422)
            error.diagnostic={'unsupported_fields':advanced_flash_fields(old)}
            raise error
        previous = profile_revision(name, old) if old is not None else None
        if previous != profile_revision(name, value) and previous != patch.expected_revisions[name]:
            raise TestError('Local flash profile changed before application', 'FLASH_PROFILE_CHANGED', 409)
        profiles[name] = value
        if not value['enabled']:
            continue
        host = SimpleNamespace(runtime=Path(runtime).resolve(), configured_boards=configured,
                               multiplexers=object() if serial_transport=='proxy' else None,
                               console=SimpleNamespace(configs=console_observers or {}))
        checker = FlashService(host, {'profiles': {name: value}})
        for board_id in value['boards']:
            board = next((b for b in configured if b['board_id'] == board_id), None)
            if board is None:
                raise TestError('Flash profile refers to an unregistered board', 'BOARD_MISMATCH', 422)
            request = SimpleNamespace(profile=name, manifest={'batch': 'install.bat', 'files': {'install.bat': value['batch_sha256']}},
                                      connection=Connection.model_validate({'a': board}))
            checker.profile(request, streamed=not bool(value.get('image_root')))
            checker.validate_observers(value, request.connection)
    return result




def advanced_flash_fields(profile):
    """List every field the public editor cannot round-trip without losing data."""
    found=[key for key in profile if key not in FlashProfile.model_fields]
    for identity,board in profile.get('boards',{}).items():
        found.extend('boards.'+identity+'.'+key for key in board if key not in FlashBoard.model_fields)
        if isinstance(board.get('observer'),dict):
            found.extend('boards.'+identity+'.observer.'+key for key in board['observer'] if key not in FlashObserver.model_fields)
    return sorted(found)

def flash_setup_metadata(config):
    """Public editable keys only; never expose legacy credential/procedure values."""
    import os
    import shutil
    profiles=[]
    for name,profile in config.get('profiles',{}).items():
        safe={key:copy.deepcopy(value) for key,value in profile.items() if key in FlashProfile.model_fields}
        if isinstance(safe.get('boards'),dict):
            safe['boards']={identity:{key:copy.deepcopy(value) for key,value in board.items() if key in FlashBoard.model_fields}
                            for identity,board in safe['boards'].items()}
            for board in safe['boards'].values():
                if isinstance(board.get('observer'),dict):
                    board['observer']={key:value for key,value in board['observer'].items() if key in FlashObserver.model_fields}
        profiles.append({'name':name,'revision':profile_revision(name,profile),'profile':safe,
                         'advanced_fields':advanced_flash_fields(profile)})
    candidates=[(p.get('fastboot'),'configured-profile') for p in config.get('profiles',{}).values()]
    candidates.extend([(shutil.which('fastboot.exe'),'path'),(shutil.which('fastboot'),'path')])
    for key in ('ANDROID_SDK_ROOT','ANDROID_HOME'):
        if os.environ.get(key):candidates.append((str(Path(os.environ[key])/'platform-tools'/'fastboot.exe'),'android-sdk'))
    if os.environ.get('LOCALAPPDATA'):
        candidates.append((str(Path(os.environ['LOCALAPPDATA'])/'Android/Sdk/platform-tools/fastboot.exe'),'android-sdk'))
    executable=next(({'path':str(Path(path).resolve()),'source':source,'available':True} for path,source in candidates
                     if path and Path(path).is_file() and Path(path).suffix.lower()=='.exe'),
                    {'path':None,'source':None,'available':False})
    return {'profiles':profiles,'fastboot':executable}

class IntegrationProfiles:
    def __init__(self, manager):
        self.manager = manager
        from .shared_settings import attach_shared_settings
        self.settings = attach_shared_settings(manager)

    def commands(self):
        return {'commands': self.manager.store.documents('command')}

    def command(self, name):
        value = next((value for value in self.manager.store.documents('command') if value['name'] == name), None)
        if value is None:
            raise TestError('Command profile not found', 'NOT_FOUND', 404)
        return value

    def validate_command(self, value):
        template = validate_command_template(value)
        validate_windows_command(template)
        return template | {'revision': digest(template)}

    def save_command(self, name, body):
        value = CommandSave.model_validate(body)
        template = self.validate_command(value.model_dump(exclude={'expected_revision'}))
        return self.manager.save_document('command', name, {k: template[k] for k in ('single', 'dual')},
                                          expected_revision=value.expected_revision) | {'name': name}

    def select(self, kind, name, body):
        value = ProfileSelection.model_validate(body)
        if kind == 'command':
            snapshot = self.manager.command_snapshot(name, value.revision)
            validate_windows_command(snapshot['template'])
        else:
            actual = self.manager.runner.integration_profile(name)
            if actual.get('revision') != value.revision:
                raise TestError('Registered flash profile changed', 'FLASH_PROFILE_CHANGED', 409)
            registered = getattr(self.manager.runner, 'registry', None)
            registration = registered.read() if registered is not None else None
            if registration and actual.get('runner_id') != registration['runner_id']:
                raise TestError('Flash profile belongs to another runner', 'RUNNER_CHANGED', 409)
        current = self.settings.read()
        if current['revision'] != value.expected_settings_revision:
            raise TestError('Shared settings changed; reload before selection', 'SETTINGS_CHANGED', 409)
        integration = current['integration'] | {kind + '_profile': name, kind + ('_revision' if kind == 'command' else '_profile_revision'): value.revision}
        return self.settings.save({'expected_revision': value.expected_settings_revision, 'integration': integration,
                                   'timeouts': {k: v for k, v in current['timeouts'].items() if k != 'revision'}})

    def flashes(self):
        application = self.settings.connector_application()
        desired = (application.get('settings', {}).get('flashing') or {}).get('profiles', {})
        registry = getattr(self.manager.runner, 'registry', None)
        registered = registry.read() if registry is not None else None
        inventory = self.manager.runner.inventory() if registered is not None else {}
        applied = inventory.get('flash_profile_revisions', {})
        metadata={item['name']:item for item in inventory.get('flash_setup',{}).get('profiles',[])}
        names = sorted(set(desired) | set(applied))
        return {'runner_id': (registered or {}).get('runner_id'), 'fresh': inventory.get('fresh', False),
                'application_revision': application['revision'], 'application_state': application['state'],
                'profiles': [{'name': name, 'desired_revision': profile_revision(name, desired[name]) if name in desired else None,
                              'applied_revision': applied.get(name, {}).get('revision'),
                              'enabled': applied.get(name, {}).get('enabled'),
                              'desired_profile': desired.get(name), 'advanced_fields':metadata.get(name,{}).get('advanced_fields',[])} for name in names]}

    def flash_setup(self, discover_devices=False):
        registry=getattr(self.manager.runner,'registry',None)
        registration=registry.read() if registry is not None else None
        if registration is None:
            raise TestError('Register the Windows connector before discovery','RUNNER_NOT_CONFIGURED',409)
        value=self.manager.runner.flash_setup(discover_devices=discover_devices)
        if value.get('runner_id')!=registration['runner_id']:
            raise TestError('Flash discovery belongs to another runner','RUNNER_CHANGED',409)
        return value

    def save_flash(self, name, body):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', name):
            raise TestError('Invalid flash profile name', 'FLASH_PROFILE_INVALID', 422)
        value = FlashSave.model_validate(body)
        application = self.settings.connector_application()
        if application['revision'] != value.expected_revision:
            raise TestError('Connector settings changed; reload before saving', 'SETTINGS_CHANGED', 409)
        current_settings = copy.deepcopy(application.get('settings', {}))
        patch = current_settings.get('flashing') or {'profiles': {}, 'expected_revisions': {}}
        inventory = self.flashes()
        existing = next((item for item in inventory['profiles'] if item['name'] == name), None)
        if (existing or {}).get('advanced_fields'):
            error=TestError('Advanced local profile fields must be preserved; create a new named public profile', 'FLASH_PROFILE_ADVANCED',422)
            error.diagnostic={'unsupported_fields':existing['advanced_fields']}
            raise error
        current_revision = (existing or {}).get('desired_revision') or (existing or {}).get('applied_revision')
        if current_revision != value.expected_profile_revision:
            raise TestError('Flash profile changed; reload before saving', 'FLASH_PROFILE_CHANGED', 409)
        # Preserve the original local CAS base across edits to a still-pending patch.
        if name not in patch['expected_revisions'] or application['state'] == 'APPLIED':
            patch['expected_revisions'][name] = (existing or {}).get('applied_revision')
        patch['profiles'][name] = value.profile.model_dump(exclude_none=True)
        current_settings['flashing'] = patch
        result = self.settings.desired({'expected_revision': value.expected_revision, 'runner_id': value.runner_id,
                                        'settings': current_settings})
        return result | {'profile': name, 'profile_revision': profile_revision(name, patch['profiles'][name])}
