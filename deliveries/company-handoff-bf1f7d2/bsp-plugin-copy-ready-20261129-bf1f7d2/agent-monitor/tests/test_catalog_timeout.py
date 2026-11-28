"""T-192: stdlib setup transport deadlines and progress, without runner I/O."""
import builtins
import json

import pytest

from backend.gui_test.catalog_settings import CatalogSettings
from scripts import setup_runtime as setup


@pytest.mark.parametrize('override,expected', [(None, 100), (1, 1), (173, 173), (600, 600)])
def test_wizard_transport_extends_catalog_only(monkeypatch, override, expected):
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, _): return b'{}'
    class Opener:
        def open(self, request, timeout):
            calls.append((request.full_url, timeout))
            return Response()
    monkeypatch.setattr(setup, 'build_opener', lambda *_: Opener())
    for path in ('/identity', '/boards', '/catalog'):
        assert setup.runner_get(path, 'fixture-token', catalog_timeout=override) == {}
    assert [timeout for _, timeout in calls] == [5, 5, expected]
    assert calls[-1][0] == 'http://127.0.0.1:8771/v1/catalog'


@pytest.mark.parametrize('windows', [True, False])
def test_wizard_uses_own_platform_runtime_and_invocation_override(tmp_path, monkeypatch, windows):
    root, home = tmp_path / 'repo', tmp_path / 'private'
    root.mkdir()
    runtime = home / 'runtime' if windows else root / '.runtime'
    settings = CatalogSettings(runtime / 'gui-test-settings.json')
    settings.save(169)
    calls = []
    monkeypatch.setattr(setup, 'runner_get', lambda *args, **kwargs: calls.append((args, kwargs)) or {})
    wizard = setup.Wizard(root=root, home=home, windows=windows)
    wizard.get_runner('/catalog', 'fixture-token')
    settings.save(211)
    wizard.get_runner('/catalog', 'fixture-token')
    override = setup.Wizard(root=root, home=home, windows=windows, catalog_timeout=37)
    override.get_runner('/catalog', 'fixture-token')
    override.get_runner('/identity', 'fixture-token')
    assert [kwargs.get('catalog_timeout') for _, kwargs in calls] == [169, 211, 37, None]
    assert settings.read() == {'catalog_timeout_seconds': 211}
    assert not wizard.config.exists()


def test_menu_check_flushes_each_stage_before_request_and_reports_catalog_failure(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    root.mkdir()
    wizard = setup.Wizard(root=root, home=tmp_path / 'home', windows=False)
    wizard.config.parent.mkdir(parents=True)
    wizard.config.write_text(json.dumps({'runner': 'windows-http', 'url': wizard.runner_url}))
    monkeypatch.setattr(wizard.tokens, 'load', lambda: 'private-fixture-token')
    prints, requests = [], []
    def record_print(*args, **kwargs):
        prints.append((' '.join(map(str, args)), kwargs.get('flush', False)))
    monkeypatch.setattr(builtins, 'print', record_print)
    def get(path, token, **kwargs):
        requests.append(path)
        assert prints[-1][1] is True
        if path == '/catalog':
            assert 'TC 목록' in prints[-1][0]
            raise TimeoutError('fixture timeout')
        return {'boards': []} if path == '/boards' else {'runner_id': 'fixture'}
    monkeypatch.setattr(wizard, 'get_runner', get)
    with pytest.raises(RuntimeError, match='TC 목록 조회') as error:
        wizard.check()
    assert requests == ['/identity', '/boards', '/catalog']
    assert 'private-fixture-token' not in str(error.value)


def test_stdlib_catalog_timeout_redacts_transport_exception(monkeypatch):
    class Opener:
        def open(self, *_args, **_kwargs):
            raise TimeoutError('raw-secret-fixture-token')
    monkeypatch.setattr(setup, 'build_opener', lambda *_: Opener())
    with pytest.raises(TimeoutError) as error:
        setup.runner_get('/catalog', 'raw-secret-fixture-token', catalog_timeout=173)
    assert '173' in str(error.value)
    assert 'raw-secret-fixture-token' not in str(error.value)
