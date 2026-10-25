from pathlib import Path
from gui_test.core.manager import Manager
from gui_test.core.store import Store


def make_manager(runtime, mode):
    root = Path(runtime) / ('gui-test-' + mode + '-demo')
    dashboard = None
    if mode == 'dashboard':
        from gui_test.adapters.dashboard import DemoDashboard
        dashboard = DemoDashboard(root)
    return Manager(Store(root / 'runs.db'), mode=mode, dashboard=dashboard)
