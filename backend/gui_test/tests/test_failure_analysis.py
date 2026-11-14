"""T-241: fail-stop, durable delivery, advisory remediation and retry chains.

All runners and remediation verifiers are local fixtures. No model/device calls.
"""
import copy
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError
from backend.gui_test.core.failure_analysis import AnalysisResult, POLICY, LEGACY_POLICY
from backend.gui_test.core.models import TestError, uid
from backend.gui_test.runtime import make_manager
from backend.gui_test.tests.test_core import request, start, action
from backend.gui_test.tests.test_plugin_integration_service import rig


def fail(manager, run, state='FAIL'):
    claim = manager.claim(run['id'])
    assert claim
    if state in {'FAIL', 'PASS'}:
        manager.emit(run['id'], claim['attempt']['id'], 'stdout', f'Test Result: {state}\n')
    manager.finish(claim, {'exit_code': 0, 'terminated': state != 'UNKNOWN',
                           **({'forced_state': state} if state in {'ERROR', 'TIMEOUT'} else {})})
    return manager.get(run['id'])


def advisory(item, cause='bad-port', **changes):
    return {'base_revision': item['evidence_revision'], 'cause_key': cause,
            'cause_summary': 'Fixture cause', 'remediation_summary': 'Fixture remediation',
            'evidence_refs': item['evidence_refs'], 'remediation_refs': ['fixture:trusted-remediation'],
            'action': 'RETRY', **changes}


def verifier(run, item, value):
    return {'run_id': run['id'], 'evidence_revision': item['evidence_revision'],
            'source_revision': run['source_revision'], 'command_revision': run['command_snapshot']['revision'],
            'runner_id': run.get('runner_id_snapshot', run.get('integration', {}).get('config', {}).get('runner_id')),
            'remediation_refs': value['remediation_refs'], 'remediation_verified': True,
            'process_stopped': True, 'board_ready': True, 'inputs_unchanged': True}


def submit(manager, cause='bad-port', **changes):
    item = manager.analysis.claim('owner', 'fixture')
    assert item
    return manager.analysis.submit(item['id'], 'owner', item['lease_token'], advisory(item, cause, **changes))


@pytest.mark.parametrize('state', ['FAIL', 'ERROR', 'TIMEOUT', 'UNKNOWN'])
def test_first_failure_latches_all_claim_paths_and_keeps_pending_and_raw(tmp_path, state):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager), state)
    assert run['execution_policy'] == POLICY and run['index'] == 0
    assert run['attempts'][0]['state'] == state
    assert run['overall_result'] == 'INCOMPLETE'
    assert run['progress']['counts']['PENDING'] == len(run['plan']) - 1
    assert len(manager.analysis.list('owner')) == 1
    assert manager.claim(run['id']) is None
    for name in (('resume',) if state == 'UNKNOWN' else ('resume', 'recover', 'demo-recover')):
        with pytest.raises(TestError) as error:
            action(manager, run, name)
        assert error.value.code == 'ANALYSIS_REQUIRED'
    with manager.store.transaction() as c:
        current = manager.store.get(c, run['id'])
        current.update(state='QUEUED', environment_ready=True)
        manager.store.save(c, current, 'BYPASS_FIXTURE')
    assert manager.claim(run['id']) is None


def test_atomic_failure_and_outbox_rollback_together(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, 'standalone')
    run = start(manager)
    claim = manager.claim(run['id'])
    manager.emit(run['id'], claim['attempt']['id'], 'stdout', 'Test Result: FAIL\n')
    original = manager.store.save
    def crash(c, current, event, data=None):
        if event == 'FAILURE_ANALYSIS_QUEUED':
            raise RuntimeError('Crash before durable commit')
        return original(c, current, event, data)
    monkeypatch.setattr(manager.store, 'save', crash)
    with pytest.raises(RuntimeError):
        manager.finish(claim, {'exit_code': 0, 'terminated': True})
    assert manager.store.documents('failure-analysis') == []
    assert manager.get(run['id'])['attempts'][0]['state'] == 'RUNNING'
    monkeypatch.setattr(manager.store, 'save', original)
    manager.finish(claim, {'exit_code': 0, 'terminated': True})
    assert len(manager.store.documents('failure-analysis')) == 1


def test_restart_and_expired_lease_redeliver_with_cas_and_idempotent_submit(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager))
    clock = [1000.0]
    manager.analysis.clock = lambda: clock[0]
    item = manager.analysis.claim('owner', 'first', 10)
    assert manager.analysis.claim('owner', 'other') is None
    reopened = make_manager(tmp_path, 'standalone')
    reopened.analysis.clock = lambda: clock[0]
    clock[0] += 11
    again = reopened.analysis.claim('owner', 'second')
    assert again['id'] == item['id'] and again['deliveries'] == 2
    with pytest.raises(TestError) as error:
        reopened.analysis.submit(item['id'], 'owner', item['lease_token'], advisory(item))
    assert error.value.code == 'ANALYSIS_LEASE_CONFLICT'
    value = advisory(again)
    receipt = reopened.analysis.submit(again['id'], 'owner', again['lease_token'], value)
    assert receipt['status'] == 'HOLD'
    assert reopened.analysis.submit(again['id'], 'owner', again['lease_token'], value) == receipt
    assert reopened.claim(run['id']) is None


def test_concurrent_analysis_claim_has_one_lease(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    fail(manager, start(manager))
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda n: manager.analysis.claim('owner', f'consumer-{n}'), range(8)))
    assert sum(item is not None for item in results) == 1


@pytest.mark.parametrize('change', ['pause', 'cancel', 'control'])
def test_delayed_analysis_cannot_win_user_control_change(tmp_path, change):
    manager = make_manager(tmp_path, 'standalone')
    manager.analysis.verifier = verifier
    run = fail(manager, start(manager))
    item = manager.analysis.claim('owner', 'fixture')
    if change == 'control':
        action(manager, run, 'request-control', session='other')
    else:
        action(manager, run, change)
    with pytest.raises(TestError) as error:
        manager.analysis.submit(item['id'], 'owner', item['lease_token'], advisory(item))
    assert error.value.code == 'ANALYSIS_STALE'
    assert manager.claim(run['id']) is None


@pytest.mark.parametrize('bad', ['none', 'boolean', 'remediation', 'source', 'runner', 'process', 'refs', 'unknown', 'reservation'])
def test_advisory_or_invalid_verification_never_dispatches(tmp_path, bad):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager), 'UNKNOWN' if bad == 'unknown' else 'FAIL')
    def invalid(run, item, value):
        proof = verifier(run, item, value)
        if bad == 'boolean': return True
        if bad == 'remediation': proof['remediation_verified'] = False
        if bad == 'source': proof['source_revision'] = 'another-source'
        if bad == 'runner': proof['runner_id'] = 'other-runner'
        if bad == 'process': proof['process_stopped'] = False
        if bad == 'refs': proof['remediation_refs'] = ['other-run']
        return proof
    manager.analysis.verifier = None if bad == 'none' else invalid
    if bad == 'reservation':
        with manager.store.transaction() as c:
            c.execute('DELETE FROM reservations WHERE run_id=?', (run['id'],))
    assert submit(manager)['status'] == 'HOLD'
    assert manager.claim(run['id']) is None
    assert manager.get(run['id'])['attempts'][0]['state'] == ('UNKNOWN' if bad == 'unknown' else 'FAIL')


def test_same_slot_retry_pass_precedes_followup_and_raw_failure_survives(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    manager.analysis.verifier = verifier
    run = fail(manager, start(manager))
    assert submit(manager)['status'] == 'RETRY_READY'
    run = fail(manager, run, 'PASS')
    assert [a['state'] for a in run['attempts']] == ['FAIL', 'PASS']
    assert [a['slot_index'] for a in run['attempts']] == [0, 0]
    assert run['index'] == 1 and manager.claim(run['id'])['attempt']['slot_index'] == 1


@pytest.mark.parametrize('causes', [['USB Port', 'usb-port'], ['a', 'b', 'c', 'd']])
def test_normalized_cause_recurrence_and_total_cap_survive_restart(tmp_path, causes):
    manager = make_manager(tmp_path, 'standalone')
    run = start(manager)
    for n, cause in enumerate(causes):
        run = fail(manager, run)
        manager = make_manager(tmp_path, 'standalone')
        manager.analysis.verifier = verifier
        result = submit(manager, cause)
        assert result['status'] == ('STOPPED' if n == len(causes) - 1 else 'RETRY_READY')
    run = manager.get(run['id'])
    assert run['retry_chain']['automatic_retries'] == len(causes) - 1
    assert manager.claim(run['id']) is None


def test_evidence_and_callback_schema_reject_foreign_refs_and_shell_fields(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    fail(manager, start(manager))
    item = manager.analysis.claim('owner', 'fixture')
    with pytest.raises(TestError) as error:
        manager.analysis.submit(item['id'], 'owner', item['lease_token'], advisory(item, evidence_refs=['run:other']))
    assert error.value.code == 'ANALYSIS_EVIDENCE_INVALID'
    with pytest.raises(ValidationError):
        AnalysisResult.model_validate(advisory(item, shell='reboot'))
    assert manager.analysis.get(item['id'], 'owner')['status'] == 'LEASED'


def test_hold_can_be_requeued_after_verifier_is_connected(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager))
    result = submit(manager)
    run = manager.get(run['id'])
    manager.analysis.requeue(result['id'], 'owner', run['version'])
    manager.analysis.verifier = verifier
    assert submit(manager)['status'] == 'RETRY_READY'


def test_changed_inputs_use_prepared_child_full_plan_and_chain(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager))
    before = copy.deepcopy(run)
    command = manager.save_document('command', 'remediated-profile', {'single': ['python', '-u', '{tc_path}', '{com_a}'], 'dual': ['python', '-u', '{tc_path}', '{com_a}', '{com_b}']})
    req = request(manager, command_profile='remediated-profile', command_revision=command['revision'])
    def changed(run, item, value):
        return verifier(run, item, value) | {'inputs_unchanged': False, 'retry_request': req}
    manager.analysis.verifier = changed
    result = submit(manager, action='REPREPARE')
    assert result['status'] == 'CHILD_CREATED'
    parent = manager.get(run['id'])
    child = manager.get(result['child_run_id'])
    assert child['parent_run_id'] == parent['id']
    assert parent['attempts'] == before['attempts'] and parent['source_revision'] == before['source_revision']
    assert child['index'] == 0 and child['plan'] == before['plan'] and not child['attempts']
    assert child['command_snapshot']['revision'] != before['command_snapshot']['revision']
    assert child['retry_chain']['id'] == parent['retry_chain']['id']
    assert child['retry_chain']['automatic_retries'] == 1
    assert manager.claim(parent['id']) is None
    claim = manager.claim(child['id'])
    assert claim['attempt']['slot_index'] == 0
    manager.emit(child['id'], claim['attempt']['id'], 'stdout', 'Test Result: FAIL\n')
    manager.finish(claim, {'exit_code': 0, 'terminated': True})
    manager.analysis.verifier = verifier
    assert submit(manager)['status'] == 'STOPPED'
    with pytest.raises(TestError):
        manager.analysis.requeue(result['id'], 'owner', parent['version'])


@pytest.mark.parametrize('batch_state', ['FAILED', 'UNKNOWN'])
def test_integration_preparation_and_boot_failures_latch_and_ready_cannot_bypass(rig, batch_state):
    manager, service, _, request, _, _ = rig
    manager.runner.begin_integration = lambda *args: {'state': batch_state, 'id': 'batch', 'terminated': batch_state != 'UNKNOWN'}
    accepted = service.start(uid(), 'plugin-principal', request)
    service.prepare_run(accepted['id'])
    failed = manager.get(accepted['id'])
    assert failed['failure_analysis']['latched'] is True
    service.record_batch(accepted['id'], {'state': 'READY', 'id': 'batch', 'terminated': True})
    assert manager.get(accepted['id'])['environment_ready'] is False
    assert manager.claim(accepted['id']) is None
    with pytest.raises(TestError):
        service.act(accepted['id'], uid(), 'plugin-principal', manager.get(accepted['id'])['version'], 'resume')


def test_legacy_policy_preserves_two_passes_after_initial_fail(rig):
    manager, service, _, request, _, _ = rig
    manager.runner.begin_integration = lambda *args: {'state': 'READY', 'id': 'batch', 'terminated': True}
    run = service.start(uid(), 'plugin-principal', request)
    with manager.store.transaction() as c:
        current = manager.store.get(c, run['id'])
        current.pop('execution_policy')
        current['integration']['retry_policy'] = LEGACY_POLICY
        manager.store.save(c, current, 'LEGACY_POLICY_FIXTURE')
    service.prepare_run(run['id'])
    for state in ['FAIL', 'PASS', 'PASS']:
        run = fail(manager, run, state)
    assert [a['state'] for a in run['attempts']] == ['FAIL', 'PASS', 'PASS']
    assert run['slot_results']['0'] == 'PASS' and not run.get('failure_analysis')


def test_analysis_callback_worker_uses_http_api_and_leaves_failed_callback_unacked(tmp_path):
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from backend.gui_test.api.failure_analysis import create_router
    from backend.gui_test.standalone.analysis_worker import AnalysisWorker
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager))
    app = FastAPI()
    @app.middleware('http')
    async def authenticated(request: Request, call_next):
        request.state.gui_principal = 'owner'
        return await call_next(request)
    @app.exception_handler(TestError)
    async def error(request, exc):
        return JSONResponse({'code': exc.code}, status_code=exc.status)
    app.include_router(create_router(manager))
    def broken(item):
        raise RuntimeError('Analyzer disconnected before result')
    with TestClient(app) as client:
        def transport(method, path, payload):
            response = client.request(method, path, json=payload)
            response.raise_for_status()
            return response.json()
        worker = AnalysisWorker(transport, broken, lease_seconds=1)
        with pytest.raises(RuntimeError):
            worker.tick()
        item = manager.analysis.list('owner')[0]
        assert item['status'] == 'LEASED' and item['deliveries'] == 1
        manager.analysis.clock = lambda: item['lease_until'] + 1
        manager.analysis.verifier = verifier
        worker.analyzer = lambda item: advisory(item)
        assert worker.tick()['status'] == 'RETRY_READY'
    assert manager.claim(run['id'])['attempt']['slot_index'] == 0


def test_pause_requested_before_failure_blocks_automatic_retry(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    manager.analysis.verifier = verifier
    run = start(manager)
    claim = manager.claim(run['id'])
    action(manager, run, 'pause')
    manager.emit(run['id'], claim['attempt']['id'], 'stdout', 'Test Result: FAIL\n')
    manager.finish(claim, {'exit_code': 0, 'terminated': True})
    assert submit(manager)['status'] == 'HOLD'
    assert manager.claim(run['id']) is None


def test_new_integration_policy_first_fail_does_not_retry(rig):
    manager, service, _, request, _, _ = rig
    manager.runner.begin_integration = lambda *args: {'state': 'READY', 'id': 'batch', 'terminated': True}
    run = service.start(uid(), 'plugin-principal', request)
    assert run['execution_policy'] == run['integration']['retry_policy'] == POLICY
    service.prepare_run(run['id'])
    run = fail(manager, run)
    assert run['attempts'][0]['state'] == 'FAIL'
    assert run['slot_results']['0'] == 'FAIL'
    assert manager.claim(run['id']) is None
    item = manager.analysis.claim('plugin-principal', 'fixture')
    assert item['phase'] == 'TC' and item['run']['integration']['phase'] == 'TESTING'


def test_unsupported_saved_policy_cannot_claim(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    run = start(manager)
    with manager.store.transaction() as c:
        current = manager.store.get(c, run['id'])
        current['execution_policy'] = 'future-policy-not-supported'
        manager.store.save(c, current, 'UNSUPPORTED_POLICY_FIXTURE')
    assert manager.claim(run['id']) is None


def test_preparation_failure_enqueues_durably_without_attempt(rig):
    manager, service, _, request, _, _ = rig
    def changed(*args):
        raise TestError('Published source changed', 'SOURCE_CHANGED')
    service.preparer = changed
    run = service.start(uid(), 'plugin-principal', request)
    service.prepare_run(run['id'])
    run = manager.get(run['id'])
    assert not run['attempts'] and run['failure_analysis']['latched']
    item = manager.analysis.claim('plugin-principal', 'fixture')
    assert item['phase'] == 'FAILED' and item['attempt_id'] is None


def test_integration_changed_installer_child_must_reprepare_flash_and_keep_chain(rig):
    manager, service, _, request, _, calls = rig
    batches = []
    def begin(receipt, context):
        batches.append(context['run_id'])
        return {'state': 'READY', 'batch_id': context['run_id'], 'epoch': 1, 'runner_id': 'a' * 32, 'terminated': True}
    manager.runner.begin_integration = begin
    parent = service.start(uid(), 'plugin-principal', request)
    service.prepare_run(parent['id'])
    parent = fail(manager, parent)
    def changed(run, item, value):
        return verifier(run, item, value) | {'inputs_unchanged': False,
            'retry_request': request | {'installer_path': '/srv/published/fixed/install.bat'},
            'batch_release_receipt': {'state': 'RELEASED', 'batch_id': run['id'], 'epoch': 1, 'runner_id': 'a' * 32}}
    manager.analysis.verifier = changed
    item = manager.analysis.claim('plugin-principal', 'fixture')
    result = manager.analysis.submit(item['id'], 'plugin-principal', item['lease_token'], advisory(item, action='REPREPARE'))
    assert result['status'] == 'CHILD_CREATED'
    child = manager.get(result['child_run_id'])
    assert child['integration']['phase'] == 'PREPARING' and not child['environment_ready']
    assert manager.claim(child['id']) is None
    assert len(calls) == 2 and len(batches) == 1
    assert child['retry_chain']['id'] == parent['retry_chain']['id']
    service.prepare_run(child['id'])
    assert len(batches) == 2 and batches == [parent['id'], child['id']]
    assert manager.claim(child['id'])['attempt']['slot_index'] == 0
    assert manager.get(parent['id'])['attempts'] == parent['attempts']


def test_changed_batch_evidence_redelivers_without_clearing_latch(rig):
    manager, service, _, request, _, _ = rig
    manager.runner.begin_integration = lambda *args: {'state': 'UNKNOWN', 'id': 'batch', 'terminated': False}
    run = service.start(uid(), 'plugin-principal', request)
    service.prepare_run(run['id'])
    item = manager.analysis.claim('plugin-principal', 'fixture')
    version = manager.get(run['id'])['version']
    service.record_batch(run['id'], {'state': 'UNKNOWN', 'id': 'batch', 'terminated': False})
    assert manager.get(run['id'])['version'] == version
    service.record_batch(run['id'], {'state': 'READY', 'id': 'batch', 'terminated': True})
    with pytest.raises(TestError) as error:
        manager.analysis.submit(item['id'], 'plugin-principal', item['lease_token'], advisory(item))
    assert error.value.code == 'ANALYSIS_LEASE_CONFLICT'
    assert manager.get(run['id'])['state'] == 'PAUSED'
    again = manager.analysis.claim('plugin-principal', 'fixture')
    assert again['id'] != item['id'] and again['evidence_revision'] > item['evidence_revision']
    assert manager.claim(run['id']) is None


def test_permanent_delete_cleans_failure_analysis_outbox(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager))
    run = action(manager, run, 'cancel')
    manager.sessions.delete(run['id'], 'owner', run['version'])
    assert manager.analysis.list('owner') == []
    assert manager.store.documents('failure-analysis') == []


@pytest.mark.parametrize('probe', ['UNKNOWN', 'RUNNING', 'STOPPED'])
def test_unknown_physical_reconciliation_preserves_latch_until_verified(tmp_path, monkeypatch, probe):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager), 'UNKNOWN')
    item = manager.analysis.claim('owner', 'fixture')
    monkeypatch.setattr(manager.runner, 'probe', lambda ref: probe)
    assert manager.reconcile_unknown(run['id']) is (probe == 'STOPPED')
    current = manager.get(run['id'])
    assert current['failure_analysis']['latched'] and not current['environment_ready']
    assert manager.claim(run['id']) is None
    if probe == 'STOPPED':
        assert current['state'] == 'PAUSED' and current['attempts'][0]['terminated']
        with pytest.raises(TestError):
            manager.analysis.submit(item['id'], 'owner', item['lease_token'], advisory(item))
        manager.analysis.verifier = verifier
        assert submit(manager)['status'] == 'RETRY_READY'
        assert manager.claim(run['id'])['attempt']['slot_index'] == 0
    else:
        assert current['state'] == 'UNKNOWN' and current['version'] == run['version']


def test_explicit_analysis_requeue_releases_manual_hold_but_not_latch(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    manager.analysis.verifier = verifier
    run = fail(manager, start(manager))
    run = action(manager, run, 'pause')
    item = manager.analysis.requeue(run['failure_analysis']['request_id'], 'owner', run['version'])
    current = manager.get(run['id'])
    assert current['failure_analysis']['latched'] and not current.get('analysis_manual_hold')
    assert manager.claim(run['id']) is None
    assert submit(manager)['status'] == 'RETRY_READY'


def test_service_analyzer_cannot_clear_another_owners_manual_hold(tmp_path):
    manager = make_manager(tmp_path, 'standalone')
    run = action(manager, fail(manager, start(manager)), 'pause')
    with pytest.raises(TestError) as error:
        manager.analysis.requeue(run['failure_analysis']['request_id'], 'other-principal', run['version'])
    assert error.value.code == 'CONTROL_REQUIRED'
    with pytest.raises(TestError):
        action(manager, run, 'reanalyze', session='other-principal')
    current = action(manager, run, 'reanalyze')
    assert current['failure_analysis']['latched'] and not current.get('analysis_manual_hold')
    assert manager.claim(run['id']) is None


def test_unknown_saved_policy_never_prepares_or_flashes(rig):
    manager, service, _, request, _, calls = rig
    run = service.start(uid(), 'plugin-principal', request)
    with manager.store.transaction() as c:
        value = manager.store.get(c, run['id'])
        value['execution_policy'] = 'future-unsupported-policy'
        manager.store.save(c, value, 'UNSUPPORTED_POLICY_FIXTURE')
    manager.runner.begin_integration = lambda *a, **k: pytest.fail('unsupported policy started hardware')
    assert service.prepare_run(run['id']) is False
    assert calls == [] and manager.claim(run['id']) is None


@pytest.mark.parametrize('completed_slots', [0, 1])
def test_ordinary_preflight_remediation_retries_original_pending_slot(tmp_path, monkeypatch, completed_slots):
    manager = make_manager(tmp_path, 'standalone')
    run = start(manager)
    for _ in range(completed_slots):
        run = fail(manager, run, 'PASS')
    history = copy.deepcopy(run['attempts'])
    original_verify = manager.boards.verify
    def disconnected(*args):
        raise TestError('Fixture board temporarily disconnected', 'RUNNER_UNAVAILABLE')
    monkeypatch.setattr(manager.boards, 'verify', disconnected)
    assert manager.claim(run['id']) is None
    blocked = manager.get(run['id'])
    assert blocked['index'] == completed_slots and blocked['attempts'] == history
    item = manager.analysis.claim('owner', 'fixture')
    assert item['phase'] == 'PREFLIGHT' and item['attempt_id'] is None
    monkeypatch.setattr(manager.boards, 'verify', original_verify)
    manager.analysis.verifier = verifier
    result = manager.analysis.submit(item['id'], 'owner', item['lease_token'], advisory(item))
    assert result['status'] == 'RETRY_READY'
    current = manager.get(run['id'])
    assert current['id'] == run['id'] and not current.get('child_run_id')
    assert current['index'] == completed_slots and current['attempts'] == history
    assert current['retry_chain']['automatic_retries'] == 1
    claim = manager.claim(run['id'])
    assert claim['attempt']['slot_index'] == completed_slots
    assert claim['tc']['id'] == current['plan'][completed_slots]['tc_id']
    assert [a['state'] for a in manager.get(run['id'])['attempts'][:completed_slots]] == ['PASS'] * completed_slots


@pytest.mark.parametrize('reservation', ['missing', 'wrong-token', 'foreign-owner'])
def test_ordinary_preflight_retry_requires_original_owned_reservation(tmp_path, monkeypatch, reservation):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager), 'PASS')
    original_verify = manager.boards.verify
    def disconnected(*args):
        raise TestError('Fixture board temporarily disconnected', 'RUNNER_UNAVAILABLE')
    monkeypatch.setattr(manager.boards, 'verify', disconnected)
    assert manager.claim(run['id']) is None
    monkeypatch.setattr(manager.boards, 'verify', original_verify)
    with manager.store.transaction() as c:
        resource = c.execute('SELECT resource FROM reservations WHERE run_id=? LIMIT 1', (run['id'],)).fetchone()[0]
        if reservation == 'missing':
            c.execute('DELETE FROM reservations WHERE resource=?', (resource,))
        elif reservation == 'wrong-token':
            c.execute('UPDATE reservations SET token=? WHERE resource=?', ('wrong-token', resource))
        else:
            c.execute('UPDATE reservations SET run_id=? WHERE resource=?', ('foreign-run', resource))
    manager.analysis.verifier = verifier
    assert submit(manager)['status'] == 'HOLD'
    assert manager.claim(run['id']) is None
    assert manager.get(run['id'])['index'] == 1


def test_ordinary_preflight_retry_rechecks_board_before_creating_attempt(tmp_path, monkeypatch):
    manager = make_manager(tmp_path, 'standalone')
    run = fail(manager, start(manager), 'PASS')
    original_verify = manager.boards.verify
    def disconnected(*args):
        raise TestError('Fixture board temporarily disconnected', 'RUNNER_UNAVAILABLE')
    monkeypatch.setattr(manager.boards, 'verify', disconnected)
    assert manager.claim(run['id']) is None
    monkeypatch.setattr(manager.boards, 'verify', original_verify)
    manager.analysis.verifier = verifier
    assert submit(manager)['status'] == 'RETRY_READY'
    monkeypatch.setattr(manager.boards, 'verify', disconnected)
    assert manager.claim(run['id']) is None
    current = manager.get(run['id'])
    assert current['failure_analysis']['latched'] and current['index'] == 1
    assert len(current['attempts']) == 1 and current['attempts'][0]['state'] == 'PASS'


def test_integration_preparation_cannot_use_same_input_preflight_retry(rig):
    manager, service, _, request, _, _ = rig
    def unavailable(*args):
        raise TestError('Fixture preparation failed', 'SOURCE_CHANGED')
    service.preparer = unavailable
    run = service.start(uid(), 'plugin-principal', request)
    service.prepare_run(run['id'])
    manager.analysis.verifier = verifier
    item = manager.analysis.claim('plugin-principal', 'fixture')
    assert item['attempt_id'] is None
    result = manager.analysis.submit(item['id'], 'plugin-principal', item['lease_token'], advisory(item))
    assert result['status'] == 'HOLD' and manager.claim(run['id']) is None
