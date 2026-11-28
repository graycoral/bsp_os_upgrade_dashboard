"""T-201/202/207: durable acceptance and prepared inputs, without device I/O."""
import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend.gui_test.core.integration import IntegrationService
from backend.gui_test.core.models import TestError
from backend.gui_test.runtime import make_manager
from backend.gui_test.tests.test_core import legacy_policy


@pytest.fixture
def rig(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    template = {'single': ['python', '{tc_path}', '{com_a}'],
                'dual': ['python', '{tc_path}', '{com_a}', '{com_b}']}
    saved = manager.save_document('command', 'plugin-fixture', template)
    config = {'installer_roots': ['/srv/published'], 'tc_root': '/srv/tests',
              'connection': {'a': manager.boards.boards()[0]},
              'command_profile': 'plugin-fixture', 'command_revision': saved['revision'],
              'runner_id': 'a' * 32, 'flash_profile': 'reviewed-fixture',
              'runner_token': 'secret-must-never-enter-run'}
    request = {'installer_path': '/srv/published/release/install.bat', 'tc_patterns': ['*.py']}
    clock = [1000.0]
    calls = []
    tests = [{'id': 'case', 'path': 'case.py', 'name': 'case', 'kind': 'Single',
              'timeout': 10, 'after': [], 'disabled_reason': '', 'content_hash': 'fixed'}]
    receipt = {'catalog': {'revision': 'fixed-source', 'metadata_revision': 'fixed-metadata', 'tests': tests},
               'tests': tests, 'source_snapshot': {'snapshot_id': 'b' * 64, 'source_revision': 'fixed-source'},
               'installer_snapshot': {'snapshot_id': 'c' * 64}}
    def prepare(req, cfg):
        calls.append((copy.deepcopy(req), copy.deepcopy(cfg)))
        return copy.deepcopy(receipt)
    service = IntegrationService(manager, config, clock=lambda: clock[0], preparer=prepare)
    return manager, service, config, request, clock, calls


def ready_token(service, request):
    started = service.preview('plugin-principal', request)
    assert started['state'] == 'PREPARING'
    assert service.prepare_one() is True
    ready = service.preparation(started['preparation_id'], 'plugin-principal')
    assert ready['state'] == 'READY' and ready['tc_ids'] == ['case']
    return ready['prepared_token']


def test_acceptance_freezes_config_without_source_io_and_forbids_early_claim(rig):
    manager, service, config, request, _, calls = rig
    accepted = service.start('intent-one', 'plugin-principal', request)
    assert accepted['state'] == 'QUEUED' and accepted['environment_ready'] is False
    assert calls == []
    assert manager.claim(accepted['id']) is None
    config['connection']['a']['com'] = 'COM99'
    config['tc_root'] = '/srv/replaced'
    request['tc_patterns'].append('changed/*.py')
    persisted = manager.get(accepted['id'])
    assert persisted['integration']['config']['tc_root'] == '/srv/tests'
    assert persisted['connection_snapshot']['a']['com'] != 'COM99'
    assert persisted['integration']['request']['tc_patterns'] == ['*.py']
    assert 'secret-must-never-enter-run' not in str(persisted)


def test_same_key_replay_precedes_config_validation_and_returns_original_receipt(rig):
    manager, service, config, request, _, calls = rig
    accepted = service.start('intent-one', 'plugin-principal', request)
    config.clear()
    replay = service.start('intent-one', 'plugin-principal', request)
    assert replay == accepted
    assert len(manager.store.all()) == 1 and calls == []
    with pytest.raises(TestError) as error:
        service.start('intent-one', 'plugin-principal', request | {'tc_patterns': ['other.py']})
    assert error.value.code == 'IDEMPOTENCY_CONFLICT'


def test_concurrent_delivery_commits_one_run_and_one_acceptance_response(rig):
    manager, service, _, request, _, calls = rig
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: service.start('same-intent', 'plugin-principal', request), range(8)))
    assert all(value == responses[0] for value in responses)
    assert len(manager.store.all()) == 1 and calls == []


def test_token_one_use_and_expired_replay_still_returns_original_acceptance(rig):
    manager, service, _, request, clock, calls = rig
    token = ready_token(service, request)
    token_request = request | {'prepared_token': token}
    accepted = service.start('intent-one', 'plugin-principal', token_request)
    with pytest.raises(TestError) as error:
        service.start('new-intent', 'plugin-principal', token_request)
    assert error.value.code == 'PREPARED_TOKEN_USED'
    clock[0] += 1801
    assert service.start('intent-one', 'plugin-principal', token_request) == accepted
    assert len(manager.store.all()) == 1 and len(calls) == 1


@pytest.mark.parametrize('mismatch', ['principal', 'patterns', 'config', 'expiry', 'forged'])
def test_prepared_token_binding_fails_before_creating_a_run(rig, mismatch):
    manager, service, config, request, clock, _ = rig
    token = ready_token(service, request)
    req = request | {'prepared_token': token}
    principal = 'plugin-principal'
    if mismatch == 'principal': principal = 'different-principal'
    if mismatch == 'patterns': req['tc_patterns'] = ['other.py']
    if mismatch == 'config': config['runner_id'] = 'd' * 32
    if mismatch == 'expiry': clock[0] += 1800
    if mismatch == 'forged': req['prepared_token'] = 'forged-token-that-is-at-least-32-characters'
    with pytest.raises(TestError) as error:
        service.start('new-intent', principal, req)
    assert error.value.code == 'PREPARED_TOKEN_STALE'
    assert manager.store.all() == []


def test_preview_failure_is_durable_and_does_not_create_hardware_run(rig):
    manager, service, _, request, _, _ = rig
    def changed_source(*args):
        raise TestError('Producer modified published input', 'SOURCE_CHANGED')
    service.preparer = changed_source
    preview = service.preview('plugin-principal', request)
    assert service.prepare_one() is True
    outcome = service.preparation(preview['preparation_id'], 'plugin-principal')
    assert outcome['state'] == 'FAILED' and outcome['reason'] == 'SOURCE_CHANGED'
    assert 'prepared_token' not in outcome and manager.store.all() == []
    with pytest.raises(TestError) as error:
        service.preparation(preview['preparation_id'], 'different-principal')
    assert error.value.status == 403


def test_prepared_token_is_not_stored_as_plaintext_and_is_retrievable_after_service_restart(rig):
    manager, service, config, request, clock, _ = rig
    preview = service.preview('plugin-principal', request)
    service.prepare_one()
    token = service.preparation(preview['preparation_id'], 'plugin-principal')['prepared_token']
    assert token not in str(manager.store.documents('integration-preparation'))
    reopened = IntegrationService(manager, config, clock=lambda: clock[0], preparer=service.preparer)
    assert reopened.preparation(preview['preparation_id'], 'plugin-principal')['prepared_token'] == token


def test_internal_batch_owner_credentials_never_appear_in_public_run_or_reports(rig):
    from backend.gui_test.core.reporting import export
    manager, service, _, request, _, _ = rig
    owner_token = 'private-batch-owner-token-should-not-be-exposed'
    manager.runner.begin_integration = lambda *args: {'state': 'READY', 'id': 'batch-one', 'token': owner_token,
                                                     'epoch': 1, 'terminated': True}
    run = service.start('intent-one', 'plugin-principal', request)
    service.prepare_run(run['id'])
    public = manager.get(run['id'])
    assert owner_token not in str(public)
    for format in ('json', 'csv', 'html', 'logs'):
        content, _ = export(public, format)
        assert owner_token.encode() not in content


def test_unknown_pre_tc_batch_recovery_never_starts_another_flash(rig):
    manager, service, _, request, _, _ = rig
    started = []
    manager.runner.begin_integration = lambda *args: started.append(args) or {'state': 'UNKNOWN', 'id': 'batch-one', 'terminated': False}
    manager.runner.reconcile_integration = lambda *args: {'state': 'UNKNOWN', 'id': 'batch-one', 'terminated': False}
    accepted = service.start('intent-one', 'plugin-principal', request)
    service.prepare_run(accepted['id'])
    assert manager.get(accepted['id'])['state'] == 'UNKNOWN'
    reopened = IntegrationService(manager, service.config, preparer=service.preparer)
    reopened.recover()
    assert reopened.prepare_run(accepted['id']) is False
    assert len(started) == 1
    assert manager.claim(accepted['id']) is None


@pytest.mark.parametrize('trials,verdict,remaining', [
    (['PASS'], 'PASS', True), (['FAIL', 'PASS', 'PASS'], 'PASS', True),
    (['FAIL', 'PASS', 'FAIL'], 'FAIL', False), (['FAIL', 'FAIL'], 'FAIL', False),
])
def test_trial_results_keep_raw_failures_and_one_logical_slot_before_next_tc(rig, trials, verdict, remaining):
    manager, service, _, request, _, _ = rig
    original = service.preparer
    def two_cases(*args):
        receipt = original(*args)
        second = {**receipt['catalog']['tests'][0], 'id': 'next-case', 'path': 'next.py'}
        receipt['catalog']['tests'].append(second)
        return receipt
    service.preparer = two_cases
    manager.runner.begin_integration = lambda *args: {'state': 'READY', 'id': 'batch-one', 'terminated': True}
    accepted = legacy_policy(manager, service.start('trial-intent', 'plugin-principal', request))
    service.prepare_run(accepted['id'])
    for expected in trials:
        claim = manager.claim(accepted['id'])
        assert claim and claim['tc']['id'] == 'case'
        manager.emit(accepted['id'], claim['attempt']['id'], 'stdout', 'Test Result: ' + expected + '\n')
        manager.finish(claim, {'exit_code': 0, 'terminated': True})
    run = manager.get(accepted['id'])
    assert [attempt['state'] for attempt in run['attempts']] == trials
    assert {attempt['slot_index'] for attempt in run['attempts']} == {0}
    assert run['slot_results']['0'] == verdict and run['results']['case'] == verdict
    assert run['integration']['logical_results']['case']['attempts'] == len(trials)
    assert run['results'].get('next-case', 'PENDING') == 'PENDING'
    if remaining:
        assert manager.claim(accepted['id'])['tc']['id'] == 'next-case'
    else:
        assert run['overall_result'] == 'INCOMPLETE'
        assert manager.claim(accepted['id']) is None
