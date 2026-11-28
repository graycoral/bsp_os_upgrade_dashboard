"""Portable composition and readiness work without Dashboard/private HTTP methods."""
import pytest
from fastapi.testclient import TestClient

from backend.gui_test.adapters.mock import MockRunner
from backend.gui_test.core.manager import Manager
from backend.gui_test.core.models import TestError
from backend.gui_test.core.store import Store
from backend.gui_test.runtime import make_manager
from backend.gui_test.standalone.server import create_app


@pytest.mark.parametrize('live', [False, True])
def test_standalone_initial_api_is_complete_without_host_integration(tmp_path, live):
    app = create_app(tmp_path, start_worker=False)
    prefix = '/api/v1/gui-test' + ('/live' if live else '')
    with TestClient(app, client=('127.0.0.1', 1000), headers={'X-BSP-Client': 'dashboard'}) as client:
        for path in ('/capabilities', '/source', '/catalog', '/boards', '/runs', '/saved/suite', '/saved/profile', '/saved/command'):
            response = client.get(prefix + path)
            assert response.status_code == 200, (path, response.text)
        assert client.get(prefix + '/demo/jobs').json() == []
        assert client.get(prefix + '/demo/jobs').status_code == 200
        assert app.state.manager.dashboard is None


class InProcessAdapter(MockRunner):
    """Complete non-HTTP adapter: no request/identity transport is available."""
    def __init__(self, ready=True, snapshot=False):
        self.ready, self.snapshot = ready, snapshot
    def readiness(self):
        return {'ready': self.ready, 'code': 'READY' if self.ready else 'DISCONNECTED',
                'message': 'Fixture connection', 'capabilities': {'source_snapshot_v1': self.snapshot}}


@pytest.mark.parametrize('ready,snapshot,code', [(True, True, 'READY'), (True, False, 'SOURCE_SNAPSHOT_UNSUPPORTED'),
                                               (False, True, 'RUNNER_UNAVAILABLE')])
def test_managed_source_requires_capability_and_connectivity(tmp_path, ready, snapshot, code):
    manager = Manager(Store(tmp_path / 'runs.db'), adapter=InProcessAdapter(ready, snapshot))
    assert manager.source_execution()['ready'] is ready
    root = tmp_path / 'source'; root.mkdir()
    (root / 'case.py').write_text('print("Test Result: PASS")')
    inspection = manager.sources.inspect('server-folder', str(root))
    manager.sources.apply(inspection['inspection_id'], None, 0)
    before = manager.sources.state()
    assert manager.source_execution()['code'] == code
    assert manager.source_execution()['ready'] is (code == 'READY')
    assert manager.sources.state() == before
    if code != 'READY':
        with pytest.raises(TestError) as error:
            manager.preflight({'tc_ids': ['case.py'], 'source_revision': manager.catalog()['revision'],
                               'connection': {'a': manager.boards.boards()[0]}, 'execution': 'mock'})
        assert error.value.code == code
        assert manager.store.all() == []


def test_portable_dashboard_mode_does_not_implicitly_create_host(tmp_path):
    manager = make_manager(tmp_path, 'dashboard')
    assert manager.dashboard is None
    assert manager.module_selection_service is None
    assert manager.catalog()['tests']
