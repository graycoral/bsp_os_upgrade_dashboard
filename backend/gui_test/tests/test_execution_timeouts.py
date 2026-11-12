"""RQ-63: persisted bulk/individual limits and pinned Windows execution, no hardware."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.gui_test.runtime import make_manager
from backend.gui_test.core.models import TestError, digest, uid
from backend.gui_test.core.timeouts import TimeoutUpdate
from backend.gui_test.execution.host import Host, Execute
from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.standalone.server import create_app
from .test_core import request
from .test_windows_runner import BOARD, TEMPLATE, TOKEN


def save(manager, default=None, overrides=None, source=''):
    return manager.timeouts.save({'expected_revision': manager.timeouts.read()['revision'],
                                 'default_seconds': default, 'source_revision': source, 'overrides': overrides or {}})


@pytest.mark.parametrize('value', [0, -1, 86401, True, 10.5, '20'])
def test_timeout_values_are_bounded_strict_integers(value):
    for field in ('default_seconds', 'overrides'):
        data = {'expected_revision': 'a' * 64, 'source_revision': 'test-source', field: value if field == 'default_seconds' else {'case': value}}
        with pytest.raises(ValidationError): TimeoutUpdate.model_validate(data)
    with pytest.raises(ValidationError): Execute.model_validate({'id': uid(), 'tc_id': 'case', 'source_revision': 'x', 'connection': {'a': BOARD}, 'template': TEMPLATE, 'timeout_seconds': value})


def test_bulk_override_reset_persistence_and_source_scoping(tmp_path):
    m = make_manager(tmp_path, 'standalone')
    original = m.catalog(); identity = original['tests'][0]['id']
    save(m, 600)
    assert {t['timeout'] for t in m.catalog()['tests']} == {600}
    assert m.catalog()['revision'] == original['revision']
    save(m, 600, {identity: 75}, original['revision'])
    reloaded = make_manager(tmp_path, 'standalone')
    assert reloaded.catalog()['tests'][0]['timeout'] == 75
    assert all(t['timeout'] == 600 for t in reloaded.catalog()['tests'][1:])
    changed_source = original | {'revision': 'different-source'}
    assert {t['timeout'] for t in m.timeouts.apply(changed_source)['tests']} == {600}
    save(m, 30)  # Apply-all clears individual overrides.
    assert m.timeouts.read()['overrides'] == {} and {t['timeout'] for t in m.catalog()['tests']} == {30}
    save(m)
    assert [t['timeout'] for t in m.catalog()['tests']] == [t['timeout'] for t in original['tests']]


def test_compare_and_swap_prevents_lost_edits(tmp_path):
    a = make_manager(tmp_path, 'standalone'); b = make_manager(tmp_path, 'standalone')
    revision = a.timeouts.read()['revision']
    def edit(pair):
        manager, seconds = pair
        try: return manager.timeouts.save({'expected_revision': revision, 'default_seconds': seconds})['default_seconds']
        except TestError as exc: return exc.code
    with ThreadPoolExecutor(2) as pool: results = list(pool.map(edit, [(a, 100), (b, 200)]))
    assert results.count('TC_TIMEOUT_CHANGED') == 1
    assert a.timeouts.read()['default_seconds'] in (100, 200)


def test_start_pins_timeout_and_claim_survives_later_edits(tmp_path):
    m = make_manager(tmp_path, 'standalone'); profile = save(m, 600)
    with pytest.raises(TestError, match='Preflight'): m.preflight(request(m))
    req = request(m, timeout_revision=profile['revision'])
    run = m.start(uid(), 'owner', req)
    save(m, 120)
    frozen = m.get(run['id'])
    assert {t['timeout'] for t in frozen['tests']} == {600}
    assert frozen['timeout_settings_snapshot']['revision'] == profile['revision']
    claim = m.claim(run['id'])
    assert claim['tc']['timeout'] == 600 and claim['context']['timeout_override'] is True
    with pytest.raises(TestError) as exc: m.preflight(req)
    assert exc.value.code == 'TC_TIMEOUT_CHANGED'


def test_changed_setting_between_preflight_and_reservation_rejects_run(tmp_path, monkeypatch):
    m = make_manager(tmp_path, 'standalone'); req = request(m)
    preflight = m.preflight
    def race(value):
        checked = preflight(value); save(m, 300); return checked
    monkeypatch.setattr(m, 'preflight', race)
    with pytest.raises(TestError) as exc: m.start(uid(), 'owner', req)
    assert exc.value.code == 'TC_TIMEOUT_CHANGED' and m.store.all() == []


def test_host_uses_override_and_request_id_binds_limit(tmp_path, monkeypatch):
    root = tmp_path / 'tc'; root.mkdir(); (root / 'case.py').write_text("print('Test Result: PASS')")
    host = Host({'source_root': str(root), 'python': sys.executable, 'boards': [BOARD]}, tmp_path / 'runtime', ports=lambda: {BOARD['com']})
    observed = []
    def execute(item, directory, timeout): observed.append(timeout)
    monkeypatch.setattr(host, 'execute', execute)
    payload = {'id': uid(), 'tc_id': 'case.py', 'source_revision': host.catalog()['revision'], 'connection': {'a': BOARD}, 'template': TEMPLATE, 'timeout_seconds': 600}
    first = host.start(payload)
    host.threads[-1].join(2)
    assert observed == [600] and first['timeout_seconds'] == 600
    assert host.start(payload)['request_hash'] == first['request_hash']
    with pytest.raises(TestError) as exc: host.start(payload | {'timeout_seconds': 601})
    assert exc.value.code == 'IDEMPOTENCY_CONFLICT'


@pytest.mark.parametrize('supported', [False, True])
def test_adapter_capability_and_pinned_timeout_payload(supported):
    calls = []; payload = {}
    def respond(req):
        calls.append(req.url.path)
        if req.url.path == '/v1/identity': return httpx.Response(200, json={'tc_timeout_v1': supported})
        if req.url.path == '/v1/executions':
            payload.update(json.loads(req.content)); return httpx.Response(200, json={})
        return httpx.Response(200, json={'id': payload['id'], 'source_revision': 'fixed', 'request_hash': digest(payload),
                                       'state': 'DONE', 'terminated': True, 'exit_code': 0, 'stdout': 'Test Result: PASS', 'stderr': ''})
    remote = WindowsRemote('http://localhost', TOKEN, client=httpx.Client(transport=httpx.MockTransport(respond)))
    context = {'process_ref': 'windows:' + uid(), 'source_revision': 'fixed', 'command_template': TEMPLATE, 'timeout_override': True}
    if not supported:
        with pytest.raises(TestError) as exc: remote.execute({'id': 'case'}, {'a': BOARD}, 600, context, lambda *_: None, lambda: False)
        assert exc.value.code == 'TC_TIMEOUT_UNSUPPORTED' and calls == ['/v1/identity']
    else:
        result = remote.execute({'id': 'case'}, {'a': BOARD}, 600, context, lambda *_: None, lambda: False)
        assert payload['timeout_seconds'] == 600 and result['terminated']


def test_api_settings_are_separate_from_catalog_timeout_and_validated_offline(tmp_path):
    app = create_app(tmp_path, start_worker=False)
    with TestClient(app, client=('127.0.0.1', 1234), headers={'X-BSP-Client': 'dashboard'}) as client:
        base = '/api/v1/gui-test'
        old = client.get(base + '/execution-timeouts').json()
        value = client.put(base + '/execution-timeouts', json={'expected_revision': old['revision'], 'default_seconds': 600})
        assert value.status_code == 200
        assert client.get(base + '/source/request-settings').json() == {'catalog_timeout_seconds': 100}
        assert client.put(base + '/execution-timeouts', json={'expected_revision': old['revision'], 'default_seconds': 300}).status_code == 409
        assert client.put(base + '/execution-timeouts', json={'expected_revision': value.json()['revision'], 'default_seconds': True}).status_code == 422
