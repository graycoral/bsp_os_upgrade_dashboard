"""Plugin module inventory never implicitly replaces selected/frozen modules."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.gui_test.core.models import TestError
from backend.gui_test.standalone.bsp_plugin_client import BspPluginClient
from backend.gui_test.standalone.plugin_client import PluginClient


MODULE = {'stable_key': 'bsp/kernel', 'name': 'Kernel', 'group': 'boot', 'target_paths': ['kernel']}


def plugin(http):
    health = http.get('/api/v1/health').json()
    assert 'plugin-module-catalog-v1' in health['capabilities']
    return BspPluginClient('http://127.0.0.1', expected_identity={
        key: health[key] for key in ('runtime_id', 'package_version')}, client=http)


def test_catalog_persists_and_does_not_replace_saved_or_frozen_modules(tmp_path):
    app = create_app(tmp_path)
    with TestClient(app, client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        client = plugin(http)
        before = client.bsp_settings()
        job_id = client.start_job('catalog-job')['job_id']
        frozen = app.state.engine.store.snapshot(job_id)
        assert client.module_catalog() == {'version': 0, 'modules': []}
        first = client.publish_modules([MODULE], expected_version=0)
        assert first == {'version': 1, 'modules': [MODULE]}
        assert client.publish_modules([MODULE], expected_version=1) == first
        assert client.bsp_settings() == before
        assert app.state.engine.store.snapshot(job_id) == frozen
        selected = deepcopy(before)
        selected['profile']['modules'] = [MODULE]
        client.save_bsp_settings(selected)
        client.publish_modules([], expected_version=1)
        assert client.bsp_settings()['profile']['modules'] == [MODULE]
        assert app.state.engine.store.snapshot(job_id) == frozen
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        client = plugin(http)
        assert client.module_catalog() == {'version': 2, 'modules': []}
        assert client.bsp_settings()['profile']['modules'] == [MODULE]


def test_stale_catalog_writer_is_rejected_without_mutation(tmp_path):
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        client = plugin(http)
        current = client.publish_modules([MODULE], expected_version=0)
        with pytest.raises(TestError) as error:
            client.publish_modules([], expected_version=0)
        assert error.value.status == 409
        assert client.module_catalog() == current


@pytest.mark.parametrize('change', [
    {'stable_key': ''}, {'name': ' '}, {'group': 'unknown'}, {'target_paths': ['../private']},
    {'target_paths': ['/private']}, {'unexpected': True},
])
def test_invalid_catalog_does_not_replace_last_inventory(tmp_path, change):
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        client = plugin(http)
        current = client.publish_modules([MODULE], expected_version=0)
        with pytest.raises(TestError) as error:
            client.publish_modules([{**MODULE, **change}], expected_version=1)
        assert error.value.status == 422
        assert client.module_catalog() == current


def test_catalog_write_requires_pinned_full_host_plugin_scope(tmp_path):
    with TestClient(create_app(tmp_path), client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        body = {'expected_version': 0, 'modules': [MODULE]}
        assert http.get('/api/v1/config/modules').json() == {'version': 0, 'modules': []}
        assert http.put('/api/v1/config/modules', json=body, headers={'X-Bsp-Client': 'dashboard'}).status_code == 403
        headers = {'X-Bsp-Service': 'plugin', 'X-Bsp-Scope': 'bsp-control-v1', 'Origin': 'http://127.0.0.1'}
        assert http.put('/api/v1/config/modules', json=body, headers=headers).status_code == 403
        wrong = BspPluginClient('http://127.0.0.1', expected_identity={'runtime_id': 'wrong', 'package_version':'0.1.0'}, client=http)
        with pytest.raises(TestError) as error:
            wrong.publish_modules([MODULE], expected_version=0)
        assert error.value.status == 409
        ordinary = PluginClient('http://127.0.0.1', expected_identity=plugin(http).expected, client=http)
        with pytest.raises(TestError):
            ordinary.request('PUT', '/api/v1/config/modules', body)
        client = plugin(http)
        for modules in ([MODULE, MODULE], [MODULE, {**MODULE, 'stable_key': 'other'}]):
            with pytest.raises(TestError) as error:
                client.publish_modules(modules, expected_version=0)
            assert error.value.status == 422
        assert client.module_catalog() == {'version': 0, 'modules': []}
