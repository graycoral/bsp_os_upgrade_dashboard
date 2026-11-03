from pathlib import Path
import json
import os
from gui_test.core.manager import Manager
from gui_test.core.store import Store


def make_manager(runtime, mode):
    config_path = Path(runtime) / 'gui-test.json'
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        if config.get('runner') != 'windows-http':
            raise ValueError('Unsupported gui-test runner configuration')
        if mode != 'dashboard':
            raise ValueError('Windows remote execution is configured only for the integrated Dashboard')
        from gui_test.adapters.windows_remote import WindowsRemote
        adapter = WindowsRemote(config['url'], os.environ.get('GUI_TEST_RUNNER_TOKEN', ''))
        return Manager(Store(Path(runtime) / 'gui-test-dashboard-windows' / 'runs.db'), mode=mode, adapter=adapter)
    root = Path(runtime) / ('gui-test-' + mode + '-demo')
    dashboard = None
    if mode == 'dashboard':
        from gui_test.adapters.dashboard import DemoDashboard
        dashboard = DemoDashboard(root)
    return Manager(Store(root / 'runs.db'), mode=mode, dashboard=dashboard)
