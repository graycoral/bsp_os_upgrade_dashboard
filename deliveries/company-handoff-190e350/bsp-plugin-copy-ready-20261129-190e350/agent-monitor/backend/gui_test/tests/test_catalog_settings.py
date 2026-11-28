"""T-191/192: request preferences never depend on hardware or alter TC deadlines."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.gui_test.catalog_settings import CatalogSettings
from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.core.models import TestError
from backend.gui_test.runtime import make_manager
from backend.gui_test.standalone.server import create_app


def test_absent_default_boundaries_and_independent_readers(tmp_path):
    path = tmp_path / 'runtime' / 'gui-test-settings.json'
    writer, reader = CatalogSettings(path), CatalogSettings(path)
    assert reader.read() == {'catalog_timeout_seconds': 100}
    assert not path.exists()
    for seconds in (1, 600, 137):
        assert writer.save(seconds) == {'catalog_timeout_seconds': seconds}
        assert reader.read() == {'catalog_timeout_seconds': seconds}
        assert json.loads(path.read_text(encoding='utf-8')) == reader.read()


@pytest.mark.parametrize('invalid', [0, -1, 601, True, False, 1.5, 100.0, '100', None, {}, []])
def test_invalid_save_preserves_previous_bytes(tmp_path, invalid):
    path = tmp_path / 'gui-test-settings.json'
    settings = CatalogSettings(path)
    settings.save(171)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        settings.save(invalid)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_failed_replace_preserves_settings_and_cleans_temporary_file(tmp_path, monkeypatch):
    settings = CatalogSettings(tmp_path / 'gui-test-settings.json')
    settings.save(137)
    before = settings.path.read_bytes()
    def fail(*_):
        raise OSError('fixture disk failure')
    monkeypatch.setattr('backend.gui_test.catalog_settings.os.replace', fail)
    with pytest.raises(OSError, match='fixture disk failure'):
        settings.save(222)
    assert settings.path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [settings.path]


@pytest.mark.parametrize('prefix', ['/api/v1/gui-test', '/api/v1/gui-test/live'])
def test_settings_api_persists_without_runner_readiness(tmp_path, prefix, monkeypatch):
    app = create_app(tmp_path, start_worker=False)
    def forbidden(*_, **__):
        pytest.fail('Request preferences must not contact the Windows runner')
    monkeypatch.setattr(app.state.manager.runner, 'readiness', forbidden)
    headers = {'X-BSP-Client': 'dashboard'}
    with TestClient(app, client=('127.0.0.1', 1000), headers=headers) as client:
        assert client.get(prefix + '/source/request-settings').json() == {'catalog_timeout_seconds': 100}
        saved = client.put(prefix + '/source/request-settings', json={'catalog_timeout_seconds': 139})
        assert saved.status_code == 200
        assert saved.json() == {'catalog_timeout_seconds': 139}
        for body in ({}, {'catalog_timeout_seconds': 139, 'timeout': 9},
                     *({'catalog_timeout_seconds': value} for value in (True, '100', 1.5, 0, 601, None))):
            assert client.put(prefix + '/source/request-settings', json=body).status_code == 422
        assert client.get(prefix + '/source/request-settings').json() == saved.json()
    assert CatalogSettings(tmp_path / 'gui-test-settings.json').read() == saved.json()
    assert not (tmp_path / 'gui-test.json').exists()
    # A newly created API process reads the durable preference, not a cached draft.
    with TestClient(create_app(tmp_path, start_worker=False), client=('127.0.0.1', 1000)) as client:
        assert client.get(prefix + '/source/request-settings').json() == saved.json()


def test_runtime_api_and_worker_adapters_reread_same_settings_file(tmp_path, monkeypatch):
    (tmp_path / 'gui-test.json').write_text(json.dumps({'runner': 'windows-http', 'url': 'http://localhost:8771'}))
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', 'fixture-token-' + 'a' * 48)
    api, worker = make_manager(tmp_path, 'dashboard'), make_manager(tmp_path, 'dashboard')
    settings = CatalogSettings(tmp_path / 'gui-test-settings.json')
    observed = []
    def respond(request):
        observed.append(request.extensions['timeout']['read'])
        return httpx.Response(200, json={'tests': []})
    with httpx.Client(transport=httpx.MockTransport(respond)) as transport:
        api.runner.client = worker.runner.client = transport
        api.runner.catalog()
        settings.save(177)
        worker.runner.catalog()
        settings.save(201)
        api.runner.catalog()
    assert observed == [100, 177, 201]


def test_catalog_captures_timeout_once_while_control_requests_keep_five_seconds(tmp_path):
    settings = CatalogSettings(tmp_path / 'gui-test-settings.json')
    calls, reads = [], []
    def provider():
        reads.append(True)
        return settings.read()['catalog_timeout_seconds']
    def respond(request):
        calls.append((request.url.path, request.extensions['timeout']['read']))
        if request.url.path.endswith('/catalog'):
            settings.save(222)  # An edit during this request affects only the next catalog.
            return httpx.Response(200, json={'tests': []})
        return httpx.Response(200, json={'boards': [], 'runner_id': 'fixture', 'terminated': True})
    with httpx.Client(timeout=5, transport=httpx.MockTransport(respond)) as client:
        remote = WindowsRemote('http://localhost', 'x' * 48, client=client, catalog_timeout_provider=provider)
        remote.catalog()
        remote.readiness()
        remote.boards()
        remote.request('/executions/fixture/poll', 'POST')
        remote.catalog()
    assert calls == [('/v1/catalog', 100), ('/v1/identity', 5), ('/v1/boards', 5),
                     ('/v1/executions/fixture/poll', 5), ('/v1/catalog', 222)]
    assert len(reads) == 2


def test_catalog_timeout_has_stage_specific_safe_error():
    token = 'secret-token-' + 'x' * 48
    def respond(request):
        raise httpx.ReadTimeout('raw transport details ' + token, request=request)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        remote = WindowsRemote('http://localhost', token, client=client)
        with pytest.raises(TestError) as error:
            remote.catalog()
        assert error.value.code == 'TC_CATALOG_TIMEOUT'
        assert token not in str(error.value)
