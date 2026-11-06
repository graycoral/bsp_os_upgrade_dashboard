from pathlib import Path
import json
import os
from .core.manager import Manager
from .core.store import Store


class UnconfiguredWindows:
    """A real-mode workspace with no execution adapter. Never fabricates TC/boards."""
    simulation = False
    branches = ['shared']

    def readiness(self):
        return {'ready': False, 'code': 'RUNNER_NOT_CONFIGURED',
                'message': 'Windows 실행기 연결이 설정되지 않았습니다. 연결 설정을 저장한 후 API와 worker를 다시 시작하세요.',
                'capabilities': {'source_snapshot_v1': False}}

    def catalog(self, branch='shared'):
        return {'branch': 'shared', 'revision': '', 'metadata_revision': '', 'tests': []}

    def boards(self):
        return []

    def verify(self, *args):
        from .core.models import TestError
        raise TestError('Windows 실행기 연결 설정 후 API와 worker를 다시 시작하세요.', 'RUNNER_NOT_CONFIGURED', 503)

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
                   mode=mode, adapter=UnconfiguredWindows())


def make_manager(runtime, mode, *, dashboard=None, module_selection_service=None):
    config_path = Path(runtime) / 'gui-test.json'
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        if config.get('runner') != 'windows-http':
            raise ValueError('Unsupported gui-test runner configuration')
        if mode != 'dashboard':
            raise ValueError('Windows remote execution is configured only for the integrated Dashboard')
        from .adapters.windows_remote import WindowsRemote
        adapter = WindowsRemote(config['url'], os.environ.get('GUI_TEST_RUNNER_TOKEN', ''))
        return Manager(Store(Path(runtime) / 'gui-test-dashboard-windows' / 'runs.db'), mode=mode,
                       adapter=adapter, dashboard=dashboard, module_selection_service=module_selection_service)
    root = Path(runtime) / ('gui-test-' + mode + '-demo')
    return Manager(Store(root / 'runs.db'), mode=mode, dashboard=dashboard,
                   module_selection_service=module_selection_service)
