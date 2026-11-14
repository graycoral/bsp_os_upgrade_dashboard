"""The full host mounts the same fresh-profile workflow without test-added routes."""
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.gui_test.tests import test_integration_profiles as workflow


def test_full_host_fresh_profiles_use_actual_mounted_routes(tmp_path, monkeypatch):
    def full_host(path):
        app = create_app(path)
        # The shared workflow uses this local alias for its execution adapter;
        # the production full host continues owning the same live manager.
        app.state.manager = app.state.gui_live_manager
        with TestClient(app, client=('127.0.0.1', 1234), headers=workflow.SERVICE) as client:
            response = client.get(workflow.PROFILES + '/commands')
            assert response.status_code == 200, response.text
            assert response.json() == {'commands': []}
            assert client.get(workflow.PROFILES + '/flash').status_code == 200
        return app

    monkeypatch.setattr(workflow, 'app_for', full_host)
    workflow.test_full_fresh_profile_setup_pins_flash_command_and_runs_mocked_tc(tmp_path, monkeypatch)
