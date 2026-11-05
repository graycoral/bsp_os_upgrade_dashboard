"""Module-scoped TC membership and request boundaries; every source is synthetic."""
import copy
from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.gui_test.core.models import ModuleContext, StartRequest
from backend.gui_test.core.module_selection import belongs_to_module, resolve_module_tests


def tc(identity, path=None, **changes):
    return {'id': identity, 'path': path or identity, 'name': identity,
            'kind': 'Single', 'timeout': 10, 'content_hash': 'fixture-' + identity,
            'disabled_reason': '', 'after': [], **changes}


def catalog(*tests):
    return {'revision': 'shared-fixture', 'metadata_revision': 'metadata-fixture',
            'branch': 'shared', 'tests': list(tests)}


@pytest.mark.parametrize('path,expected', [
    ('ethernet/link.py', True), ('ETHERNET/link.py', True),
    ('drivers/Ethernet_link.py', True), ('drivers\\ethernet\\link.py', True),
    ('drivers/Ｅｔｈｅｒｎｅｔ/link.py', True),
    ('notethernet/link.py', False), ('Ethernet2/link.py', False),
    ('network/link.py', False), ('net/link.py', False), ('display/link.py', False),
])
def test_path_membership_uses_normalized_complete_tokens_not_substrings_or_synonyms(path, expected):
    assert belongs_to_module(tc(path), 'Ethernet') is expected


def test_explicit_membership_overrides_path_hints_and_supports_shared_tc():
    source = catalog(tc('ethernet/path.py', modules=['Display']),
                     tc('shared/link.py', modules=['ethernet', 'Display']),
                     tc('network/fallback.py'))
    before = copy.deepcopy(source)
    result = resolve_module_tests(source, 'Ethernet')
    assert result['blocked_reason'] is None and result['tc_ids'] == ['shared/link.py']
    assert source == before
    assert resolve_module_tests(source, 'Display')['tc_ids'] == ['ethernet/path.py', 'shared/link.py']


@pytest.mark.parametrize('memberships', [[], 'Ethernet', ['Ethernet', 'ethernet'], ['Ethernet', 1], ['Ethernet\n'], ['']])
def test_invalid_relevant_membership_fails_closed_instead_of_using_path_fallback(memberships):
    result = resolve_module_tests(catalog(tc('Ethernet/link.py', modules=memberships), tc('Display/video.py')), 'Ethernet')
    assert result['blocked_reason']
    assert result['tc_ids'] == [] and result['tests'] == []


def test_unrelated_invalid_metadata_does_not_block_a_valid_module():
    source = catalog(tc('Display/video.py', modules=[]), tc('ethernet/link.py'))
    assert resolve_module_tests(source, 'Ethernet')['tc_ids'] == ['ethernet/link.py']


def test_dependency_order_is_stable_without_expanding_into_other_modules():
    source = catalog(tc('ethernet/dependent.py', after=['ethernet/base.py']),
                     tc('ethernet/independent.py'), tc('ethernet/base.py'), tc('Display/video.py'))
    result = resolve_module_tests(source, 'Ethernet')
    assert result['blocked_reason'] is None
    assert result['tc_ids'] == ['ethernet/independent.py', 'ethernet/base.py', 'ethernet/dependent.py']
    assert [test['id'] for test in result['tests']] == result['tc_ids']


@pytest.mark.parametrize('tests', [
    [tc('Display/video.py')],
    [tc('ethernet/link.py', disabled_reason='Unavailable fixture')],
    [tc('ethernet/link.py'), tc('ethernet/link.py')],
    [tc('ethernet/link.py', after=['missing.py'])],
    [tc('ethernet/link.py', after=['Display/video.py']), tc('Display/video.py')],
    [tc('ethernet/a.py', after=['ethernet/b.py']), tc('ethernet/b.py', after=['ethernet/a.py'])],
    [tc('ethernet/link.py', after=['ethernet/link.py'])],
    [tc('ethernet/link.py', after='bad-format')],
    [tc('ethernet/link.py', after=['ethernet/base.py', 'ethernet/base.py']), tc('ethernet/base.py')],
])
def test_unavailable_or_invalid_module_never_falls_back_to_selecting_the_whole_catalog(tests):
    result = resolve_module_tests(catalog(*tests), 'Ethernet')
    assert result['blocked_reason']
    assert result['tests'] == [] and result['tc_ids'] == []


def test_approved_explicit_mapping_can_include_a_shared_predecessor_but_never_omits_it():
    source = catalog(tc('ethernet/link.py', after=['shared/setup.py']), tc('shared/setup.py'), tc('Display/video.py'))
    blocked = resolve_module_tests(source, 'Ethernet', ['ethernet/link.py'])
    assert blocked['blocked_reason'] and blocked['tc_ids'] == []
    result = resolve_module_tests(source, 'Ethernet', ['ethernet/link.py', 'shared/setup.py'])
    assert result['blocked_reason'] is None
    assert result['tc_ids'] == ['shared/setup.py', 'ethernet/link.py']


@pytest.mark.parametrize('mapping', [[], ['not-found.py'], 'ethernet/link.py', [1]])
def test_invalid_automatic_mapping_blocks_instead_of_falling_back_to_path_matching(mapping):
    result = resolve_module_tests(catalog(tc('ethernet/link.py')), 'Ethernet', mapping)
    assert result['blocked_reason'] and result['tc_ids'] == []


def module_context(**changes):
    return {'job_id': 'bsp-job', 'module_id': 'ethernet-module', 'attempt_id': 'attempt-1',
            'plan_version': 1, 'fingerprint': 'bsp-fingerprint', 'catalog_revision': 'shared-fixture', **changes}


def start_request(**changes):
    return {'tc_ids': ['ethernet/link.py'], 'source_revision': 'shared-fixture',
            'connection': {'a': {'host': 'fixture-windows', 'board_id': 'fixture-a', 'com': 'COM31'}}, **changes}


@pytest.mark.parametrize('field', ['job_id', 'module_id', 'attempt_id', 'plan_version', 'fingerprint', 'catalog_revision'])
def test_partial_module_context_cannot_cross_the_request_boundary(field):
    value = module_context()
    del value[field]
    with pytest.raises(ValidationError):
        StartRequest.model_validate(start_request(module_context=value))


@pytest.mark.parametrize('changes', [{'plan_version': True}, {'plan_version': '1'}, {'attempt_id': None},
                                    {'catalog_revision': ''}, {'fingerprint': 1}, {'unexpected': 'field'}])
def test_module_context_is_strict_and_rejects_unbound_or_forged_field_types(changes):
    with pytest.raises(ValidationError):
        ModuleContext.model_validate(module_context(**changes))


def test_operational_context_cannot_be_mixed_with_a_demo_job_result_link():
    with pytest.raises(ValidationError, match='Operational module context'):
        StartRequest.model_validate(start_request(module_context=module_context(), job_id='demo-dashboard-job'))


def test_optional_module_context_preserves_legacy_request_serialization_and_hash_input():
    legacy = StartRequest.model_validate(start_request()).model_dump()
    explicit_null = StartRequest.model_validate(start_request(module_context=None)).model_dump()
    assert 'module_context' not in legacy
    assert legacy == explicit_null
    bound = StartRequest.model_validate(start_request(module_context=module_context())).model_dump()
    assert bound['module_context'] == module_context()


@pytest.fixture
def module_rig(tmp_path):
    from backend.domain.engine import Engine
    from backend.settings import Profile
    from backend.services.module_test_selection import ModuleTestSelection
    from backend.storage.store import Store as BspStore
    from backend.gui_test.core.manager import Manager
    from backend.gui_test.core.models import uid
    from backend.gui_test.core.store import Store as GuiStore

    source = catalog(tc('ethernet/link.py'), tc('ethernet/extra.py'), tc('Display/video.py'))
    board = {'host': 'fixture-windows', 'board_id': 'fixture-a', 'com': 'COM31'}

    class Source:
        simulation = False
        branches = ['shared']
        def catalog(self, branch='shared'):
            return copy.deepcopy(source)
        def boards(self):
            return [board.copy()]
        def verify(self, *args):
            return None

    engine = Engine(BspStore(tmp_path / 'bsp.db'), tmp_path / 'artifacts')
    profile = Profile().model_dump()
    identity = engine.create(uid(), profile, 'Module selection fixture', 'linux',
                             modules=[{'name': 'Ethernet', 'group': 'boot'}])['job_id']
    with engine.store.transaction() as connection:
        job = engine.store.get(connection, identity)
        job['confirmed_plan'] = job['plan_version']
        module = job['modules'][0]
        for name, value in module['stages'].items():
            if name != 'device_test':
                value.update(status='SUCCEEDED', validity='CURRENT')
        module['stages']['device_test'].update(status='WAITING_INPUT', attempts=[{
            'id': 'attempt-1', 'status': 'WAITING_INPUT', 'fingerprint': job['fingerprint']}])
        engine.store.save(connection, job, 'SYNTHETIC_MODULE_READY')
    service = ModuleTestSelection(engine, tmp_path)
    manager = Manager(GuiStore(tmp_path / 'gui.db'), mode='dashboard', adapter=Source(), module_selection_service=service)
    command = manager.save_document('command', 'Module fixture command', {
        'single': ['python', '{tc_path}', '-p', '{com_a}'],
        'dual': ['python', '{tc_path}', '-p', '{com_a}', '-p2', '{com_b}']})
    module_id = module['id']
    selected = service.select(manager, identity, module_id, 'shared', source['revision'])
    request = start_request(module_context=selected['context'], execution='hardware',
                            command_profile='Module fixture command', command_revision=command['revision'])

    def mutate(operation):
        with engine.store.transaction() as connection:
            current = engine.store.get(connection, identity)
            operation(current, current['modules'][0])
            engine.store.save(connection, current, 'SYNTHETIC_MODULE_CHANGED')

    return SimpleNamespace(engine=engine,manager=manager,service=service,source=source,
                           job_id=identity,module_id=module_id,selected=selected,request=request,
                           mutate=mutate,runtime=tmp_path)


def expect_error(code, operation):
    from backend.gui_test.core.models import TestError
    with pytest.raises(TestError) as raised:
        operation()
    assert raised.value.code == code
    return raised.value


def test_service_and_manager_prepare_only_current_module_candidates_without_starting_a_run(module_rig):
    rig = module_rig
    assert rig.selected['tc_ids'] == ['ethernet/link.py', 'ethernet/extra.py']
    assert rig.selected['blocked_reason'] is None and rig.selected['mode'] == 'manual'
    assert rig.selected['context']['attempt_id'] == 'attempt-1'
    checked = rig.manager.preflight(rig.request)
    assert checked['ok'] and [item['id'] for item in checked['tests']] == ['ethernet/link.py']
    assert rig.manager.store.all() == []


@pytest.mark.parametrize('change', [
    {'attempt_id': 'old-attempt'}, {'plan_version': 2},
    {'fingerprint': 'old-fingerprint'}, {'catalog_revision': 'old-catalog'},
])
def test_forged_or_stale_context_is_rejected_before_reserving_gui_resources(module_rig, change):
    rig = module_rig
    request = rig.request | {'module_context': rig.request['module_context'] | change}
    expect_error('MODULE_CONTEXT_CHANGED', lambda: rig.manager.start('stale-start', 'owner', request))
    assert rig.manager.store.all() == []
    with rig.manager.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM reservations').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM commands').fetchone()[0] == 0


def test_cross_module_tc_is_rejected_even_when_it_exists_in_the_catalog(module_rig):
    rig = module_rig
    request = rig.request | {'tc_ids': ['Display/video.py']}
    error = expect_error('MODULE_TC_MISMATCH', lambda: rig.manager.preflight(request))
    assert error.status == 422
    assert rig.manager.store.all() == []


@pytest.mark.parametrize('gate_change', ['paused', 'plan', 'prior-stage', 'attempt-fingerprint'])
def test_current_server_gates_and_attempt_baseline_are_checked_again(module_rig, gate_change):
    rig = module_rig
    def change(job, module):
        if gate_change == 'paused':
            job['paused'] = True
        elif gate_change == 'plan':
            job['confirmed_plan'] = None
        elif gate_change == 'prior-stage':
            module['stages']['verification'].update(status='FAILED', validity='UNVERIFIED')
        else:
            module['stages']['device_test']['attempts'][-1]['fingerprint'] = 'stale-attempt-baseline'
    rig.mutate(change)
    expect_error('MODULE_TEST_BLOCKED', lambda: rig.manager.preflight(rig.request))
    assert rig.manager.store.all() == []


def test_catalog_change_during_bsp_query_is_not_accepted_as_a_new_context(module_rig, monkeypatch):
    rig = module_rig
    original = rig.manager.catalog
    def changing_catalog(branch='shared'):
        rig.mutate(lambda job, module: job.update(paused=True))
        return original(branch)
    monkeypatch.setattr(rig.manager, 'catalog', changing_catalog)
    expect_error('MODULE_CONTEXT_CHANGED', lambda: rig.service.select(
        rig.manager, rig.job_id, rig.module_id, 'shared', rig.source['revision']))


def test_caller_catalog_revision_cannot_be_silently_rebound(module_rig):
    rig = module_rig
    expect_error('SOURCE_CHANGED', lambda: rig.service.select(rig.manager, rig.job_id, rig.module_id, 'shared', 'old-catalog'))


def make_bridge(rig):
    def change(job, module):
        job['execution'] = 'bridge'
        job['session']['status'] = 'READY'
    rig.mutate(change)


def install_automatic_profile(rig):
    from backend.services.module_test_selection import ModuleTestSelection
    make_bridge(rig)
    (rig.runtime / 'device-test.json').write_text(json.dumps({'enabled': True, 'modules': {
        'Ethernet': {'enabled': True, 'cases': {'boot': ['ethernet/link.py'], 'functional': ['ethernet/extra.py']}}}}), encoding='utf-8')
    rig.service = ModuleTestSelection(rig.engine, rig.runtime)
    rig.manager.module_selection_service = rig.service


def test_approved_automatic_profile_owns_waiting_attempt_before_pipeline_dispatch(module_rig):
    rig = module_rig
    install_automatic_profile(rig)
    selected = rig.service.select(rig.manager, rig.job_id, rig.module_id, 'shared', rig.source['revision'])
    assert selected['mode'] == 'automatic' and not selected['frozen']
    assert selected['tc_ids'] == ['ethernet/link.py', 'ethernet/extra.py'] and selected['blocked_reason']
    error = expect_error('AUTOMATIC_TEST_OWNED', lambda: rig.manager.start('automatic-duplicate', 'owner', rig.request))
    assert error.status == 403 and rig.manager.store.all() == []


def test_changed_automatic_configuration_requires_restart_and_never_uses_the_cached_manual_mode(module_rig):
    from backend.gui_test.core.models import TestError
    rig = module_rig
    make_bridge(rig)
    (rig.runtime / 'device-test.json').write_text(json.dumps({'enabled': False}), encoding='utf-8')
    selected = rig.service.select(rig.manager, rig.job_id, rig.module_id, 'shared', rig.source['revision'])
    assert selected['blocked_reason'] and selected['tc_ids'] == []
    with pytest.raises(TestError) as raised:
        rig.manager.preflight(rig.request)
    assert raised.value.message == selected['blocked_reason']
    assert rig.manager.store.all() == []


def freeze_automatic(rig):
    def change(job, module):
        stage = module['stages']['device_test']
        stage['status'] = 'RUNNING'
        stage['automation'] = {'payload': {'source_revision': 'frozen-source',
            'tests': [rig.source['tests'][0]],
            'cases': {'boot': ['ethernet/link.py'], 'functional': ['ethernet/link.py']}}}
    rig.mutate(change)


def test_frozen_automatic_scope_comes_from_its_saved_payload_without_reading_live_catalog(module_rig, monkeypatch):
    rig = module_rig
    freeze_automatic(rig)
    def forbidden(*args, **kwargs):
        pytest.fail('Frozen automatic selection must not query mutable live TC content')
    monkeypatch.setattr(rig.manager, 'catalog', forbidden)
    selected = rig.service.select(rig.manager, rig.job_id, rig.module_id, 'shared', 'new-live-source')
    assert selected['mode'] == 'automatic' and selected['frozen'] is True
    assert selected['context']['catalog_revision'] == 'frozen-source'
    assert selected['tc_ids'] == ['ethernet/link.py'] and selected['blocked_reason']


def test_start_rechecks_automatic_ownership_after_preflight_before_gui_commit(module_rig, monkeypatch):
    rig = module_rig
    monkeypatch.setattr(rig.manager.boards, 'verify', lambda *args: freeze_automatic(rig))
    expect_error('AUTOMATIC_TEST_OWNED', lambda: rig.manager.start('ownership-race', 'owner', rig.request))
    assert rig.manager.store.all() == []
    with rig.manager.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM commands').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM reservations').fetchone()[0] == 0


def test_gui_run_and_idempotency_receipt_are_committed_before_the_bsp_guard_is_released(module_rig, monkeypatch):
    rig = module_rig
    original = rig.service.guard
    observed = []
    @contextmanager
    def inspecting_guard(*args):
        with original(*args):
            yield
            with rig.manager.store.connection() as connection:
                observed.append((connection.execute('SELECT count(*) FROM runs').fetchone()[0],
                                 connection.execute('SELECT count(*) FROM commands').fetchone()[0],
                                 connection.execute('SELECT count(*) FROM reservations').fetchone()[0]))
    monkeypatch.setattr(rig.service, 'guard', inspecting_guard)
    first = rig.manager.start('guarded-start', 'owner', rig.request)
    assert first['module_context'] == rig.selected['context']
    assert observed == [(1, 1, 2)]
    # Retransmission returns the committed receipt even after this BSP context changes.
    rig.mutate(lambda job, module: job.update(paused=True))
    repeated = rig.manager.start('guarded-start', 'owner', rig.request)
    assert repeated == first and len(rig.manager.store.all()) == 1


@pytest.mark.parametrize('kind', ['no-service', 'standalone'])
def test_unbound_workspaces_reject_operational_context(module_rig, kind):
    rig = module_rig
    if kind == 'no-service':
        rig.manager.module_selection_service = None
    else:
        rig.manager.mode = 'standalone'
    error = expect_error('MODULE_CONTEXT_UNAVAILABLE', lambda: rig.manager.preflight(rig.request))
    assert error.status == 422 and rig.manager.store.all() == []


def test_module_api_preserves_scope_errors_and_rejects_mixed_demo_links(module_rig):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from backend.gui_test.api.router import router
    from backend.gui_test.core.models import TestError
    rig = module_rig
    app = FastAPI()
    @app.exception_handler(TestError)
    async def test_error(request: Request, error: TestError):
        return JSONResponse({'code': error.code, 'message': error.message}, status_code=error.status)
    app.include_router(router(rig.manager))
    with TestClient(app) as client:
        response = client.get('/api/v1/gui-test/module-selection', params={
            'job_id': rig.job_id, 'module_id': rig.module_id, 'branch': 'shared', 'catalog_revision': rig.source['revision']})
        assert response.status_code == 200 and response.json()['tc_ids'] == rig.selected['tc_ids']
        forged = client.post('/api/v1/gui-test/preflight', json=rig.request | {'tc_ids': ['Display/video.py']})
        assert forged.status_code == 422 and forged.json()['code'] == 'MODULE_TC_MISMATCH'
        mixed = client.post('/api/v1/gui-test/runs', headers={'Idempotency-Key': 'mixed-demo', 'X-GUI-Session': 'owner'},
                            json=rig.request | {'job_id': 'demo-link'})
        assert mixed.status_code == 422
        assert rig.manager.store.all() == []
