"""Full-host plugin control keeps existing BSP policy and one Engine owner."""
import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.gui_test.standalone.bsp_plugin_client import BspPluginClient
from backend.gui_test.standalone.plugin_client import PluginClient
from backend.gui_test.core.models import TestError


def test_bsp_plugin_can_configure_create_observe_and_pause_same_job(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        health = http.get('/api/v1/health').json()
        assert 'bsp-control-v1' in health['capabilities']
        pins = {key: health[key] for key in ('runtime_id', 'package_version')}
        plugin = BspPluginClient('http://127.0.0.1', expected_identity=pins, client=http)
        config = plugin.bsp_settings()
        assert plugin.validate_bsp_settings(config['profile'])['execution'] == 'demo'
        config['profile']['host'] = 'fixture.example'
        plugin.save_bsp_settings(config)
        with pytest.raises(TestError) as stale: plugin.save_bsp_settings(config)
        assert stale.value.status == 409
        accepted = plugin.start_job('bsp-intent', title='plugin fixture')
        assert plugin.start_job('bsp-intent', title='plugin fixture') == accepted
        job = plugin.job(accepted['job_id'])
        # Initial plan gate is enforced by the same Engine even for plugin clients.
        with pytest.raises(TestError):
            plugin.job_action(job['id'], 'confirm', key='too-early', expected_version=job['version'])
        paused = plugin.job_action(job['id'], 'pause', key='pause', expected_version=job['version'])
        assert paused['job_id'] == job['id']
        assert plugin.job(job['id'])['paused'] is True
        assert len(plugin.jobs()) == 1 and plugin.job_events(job['id'])
        assert plugin.job_reports(job['id']) is not None
        assert plugin.job_orchestration(job['id']) is not None
        ordinary = PluginClient('http://127.0.0.1', expected_identity=pins, client=http)
        with pytest.raises(TestError): ordinary.request('GET', '/api/v1/config')
        with pytest.raises(TestError): plugin.request('POST', '/api/v1/jira/probe')
        with pytest.raises(TestError): plugin.request('POST', '/api/v1/config/probe')


def test_bsp_scope_does_not_bypass_identity_or_standalone_boundary(tmp_path):
    app = create_app(tmp_path / 'full')
    with TestClient(app, client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        wrong = BspPluginClient('http://127.0.0.1', expected_identity={'runtime_id': 'wrong', 'package_version': '0.1.0'}, client=http)
        with pytest.raises(TestError) as error: wrong.start_job('wrong')
        assert error.value.code == 'SERVICE_IDENTITY_MISMATCH'
        assert app.state.engine.store.all() == []
    from backend.gui_test.standalone.integration import create_app as standalone
    app = standalone(tmp_path / 'standalone', start_worker=False)
    with TestClient(app, client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        health = http.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin'}).json()
        assert 'bsp-control-v1' not in health['capabilities']
        plugin = BspPluginClient('http://127.0.0.1', expected_identity={k: health[k] for k in ('runtime_id', 'package_version')}, client=http)
        with pytest.raises(TestError) as error: plugin.start_job('unsupported')
        assert error.value.status == 403
