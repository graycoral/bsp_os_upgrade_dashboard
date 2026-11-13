from pathlib import Path
import json
import os
from .core.manager import Manager
from .core.store import Store
from .catalog_settings import CatalogSettings


class UnconfiguredWindows:
    """A real-mode workspace with no execution adapter. Never fabricates TC/boards."""
    simulation = False
    branches = ['shared']

    def readiness(self):
        return {'ready': False, 'code': 'RUNNER_NOT_CONFIGURED',
                'message': 'TEST BOARD CONNECTOR 연결이 설정되지 않았습니다. 커넥터에서 연결하면 공통 보드 목록에 반영됩니다.',
                'capabilities': {'source_snapshot_v1': False}}

    def catalog(self, branch='shared'):
        return {'branch': 'shared', 'revision': '', 'metadata_revision': '', 'tests': []}

    def boards(self):
        return []

    def verify(self, *args):
        from .core.models import TestError
        raise TestError('TEST BOARD CONNECTOR 커넥터에서 연결을 등록하세요.', 'RUNNER_NOT_CONFIGURED', 503)

    def execute(self, *args):
        self.verify()

    def prepare_source(self, *args):
        self.verify()

    def probe(self, process_ref):
        return 'UNKNOWN'


def live_manager(runtime, mode, current):
    # A configured manager is shared with its existing worker, never scheduled twice.
    if not current.simulation:
        return current
    return Manager(Store(Path(runtime) / ('gui-test-' + mode + '-windows') / 'runs.db'),
                   mode=mode, adapter=registered_adapter(runtime, current.catalog_settings), catalog_settings=current.catalog_settings)


def registered_adapter(runtime, settings, fallback=None):
    from .connector.registry import ConnectorRegistry, RegisteredWindows
    from .adapters.windows_remote import WindowsRemote
    return RegisteredWindows(ConnectorRegistry(runtime, factory=lambda url: WindowsRemote(url, catalog_timeout_provider=lambda: settings.read()['catalog_timeout_seconds'])), fallback)


def make_manager(runtime, mode, *, dashboard=None, module_selection_service=None):
    settings = CatalogSettings(Path(runtime) / 'gui-test-settings.json')
    config_path = Path(runtime) / 'gui-test.json'
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        if config.get('runner') not in {'windows-http', 'registered'}:
            raise ValueError('Unsupported gui-test runner configuration')
        if mode not in {'dashboard', 'integration'}:
            raise ValueError('Windows remote execution is configured only for the integrated Dashboard')
        from .adapters.windows_remote import WindowsRemote
        adapter = (WindowsRemote(config['url'],
                                 catalog_timeout_provider=lambda: settings.read()['catalog_timeout_seconds']) if config.get('url') else None)
        adapter = registered_adapter(runtime, settings, adapter)
        manager = Manager(Store(Path(runtime) / 'gui-test-dashboard-windows' / 'runs.db'), mode=mode,
                       adapter=adapter, dashboard=dashboard, module_selection_service=module_selection_service,
                       catalog_settings=settings)
        if config.get('integration'):
            from .core.integration import IntegrationService
            IntegrationService(manager, config['integration'])
        elif mode == 'integration':
            raise ValueError('Configure integration defaults in gui-test.json')
        return manager
    if mode == 'integration':
        raise ValueError('Headless integration requires a configured TEST BOARD CONNECTOR (Windows)')
    root = Path(runtime) / ('gui-test-' + mode + '-demo')
    return Manager(Store(root / 'runs.db'), mode=mode, dashboard=dashboard,
                   module_selection_service=module_selection_service, catalog_settings=settings)
