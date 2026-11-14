"""Review regressions: pre-TC UNKNOWN recovery must retain intent and ownership."""
import threading
import time

import pytest

from backend.gui_test.core.worker import Worker
from backend.gui_test.core.models import TestError
from backend.gui_test.tests.test_plugin_integration_http import client_for, PREFIX
from backend.gui_test.tests.test_plugin_integration_service import rig
from backend.gui_test.tests.test_core import legacy_policy


def tick_until(worker, predicate, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        worker.tick()
        if predicate(): return
        time.sleep(.005)
    assert predicate(), 'Worker did not reach the required durable state'


@pytest.mark.parametrize('intent,expected,tc_count', [('run', 'COMPLETED', 1), ('pause', 'PAUSED', 0), ('cancel', 'CANCELLED', 0)])
def test_api_worker_unknown_batch_then_ready_restores_only_permitted_intent(rig, tmp_path, intent, expected, tc_count):
    manager, _, _, request, _, _ = rig
    entered, return_unknown, ready = threading.Event(), threading.Event(), threading.Event()
    began, executed, cancelled = [], [], []
    batch = {'id': 'batch-one', 'batch_id': 'batch-one', 'token': 'private-owner', 'epoch': 1}
    def begin(receipt, context):
        began.append(context['run_id']); entered.set()
        assert return_unknown.wait(3)
        return batch | {'state': 'UNKNOWN', 'reason': 'Lost preparation acknowledgement'}
    def reconcile(*args):
        return batch | {'state': 'READY' if ready.is_set() else 'UNKNOWN', 'terminated': ready.is_set()}
    def execute(tc, connection, timeout, context, emit, cancelled):
        executed.append(tc['id']); emit('stdout', 'Test Result: PASS\n')
        return {'exit_code': 0, 'terminated': True}
    manager.runner.begin_integration = begin
    manager.runner.reconcile_integration = reconcile
    manager.runner.execute = execute
    manager.runner.cancel_batch = lambda receipt: cancelled.append(receipt)
    manager.runner.finish_integration = lambda receipt: receipt | {'state': 'RELEASED'}
    worker = Worker(manager)
    try:
        with client_for(rig, tmp_path) as client:
            run = client.post(PREFIX + '/integration/runs', json=request, headers={'Idempotency-Key': 'recover-one'}).json()
            legacy_policy(manager, run)
            worker.tick(); assert entered.wait(3)
            if intent != 'run':
                current = client.get(PREFIX + '/runs/' + run['id']).json()
                response = client.post(PREFIX + '/integration/runs/' + run['id'] + '/actions/' + intent,
                    json={'expected_version': current['version'], 'data': {}}, headers={'Idempotency-Key': intent + '-one'})
                assert response.status_code == 200, response.text
            return_unknown.set()
            tick_until(worker, lambda: manager.get(run['id'])['state'] == 'UNKNOWN')
            assert executed == []
            ready.set()
            tick_until(worker, lambda: manager.get(run['id'])['state'] == expected)
            result = client.get(PREFIX + '/runs/' + run['id']).json()
            assert result['state'] == expected and len(executed) == tc_count
            assert began == [run['id']]
            if intent == 'pause': assert result['environment_ready'] is True
            if intent == 'cancel': assert cancelled and result['attempts'] == []
    finally:
        return_unknown.set(); ready.set(); worker.close()


def test_ready_preparation_receipt_cannot_recover_unknown_tc_attempt(rig, tmp_path):
    manager, service, _, request, _, _ = rig
    manager.runner.begin_integration = lambda *args: {'state': 'READY', 'id': 'batch-one', 'terminated': True}
    manager.runner.execute = lambda *args: {'exit_code': None, 'terminated': False}
    # A READY parent receipt is independent of the still-unresolved child process.
    manager.runner.probe = lambda *args: 'UNKNOWN'
    worker = Worker(manager)
    try:
        with client_for(rig, tmp_path) as client:
            run = client.post(PREFIX + '/integration/runs', json=request, headers={'Idempotency-Key': 'unknown-tc'}).json()
            tick_until(worker, lambda: manager.get(run['id'])['state'] == 'UNKNOWN')
            before = manager.get(run['id'])
            assert len(before['attempts']) == 1 and before['attempts'][0]['state'] == 'UNKNOWN'
            service.record_batch(run['id'], {'state': 'READY', 'id': 'batch-one', 'terminated': True})
            after = manager.get(run['id'])
            assert after['state'] == 'UNKNOWN'
            assert after['attempts'] == before['attempts'] and manager.claim(run['id']) is None
    finally:
        worker.close()


@pytest.mark.parametrize('evidence,verdict', [('panic', 'ERROR'), ('observation_gap', 'UNKNOWN')])
def test_pass_stdout_cannot_leave_any_pass_verdict_when_console_evidence_is_unsafe(rig, evidence, verdict):
    manager, service, _, request, _, _ = rig
    manager.runner.begin_integration = lambda *args: {'state': 'READY', 'id': 'batch-one', 'terminated': True}
    run = service.start('unsafe-result', 'plugin-principal', request)
    service.prepare_run(run['id'])
    claim = manager.claim(run['id'])
    manager.emit(run['id'], claim['attempt']['id'], 'stdout', 'Test Result: PASS\n')
    manager.finish(claim, {'exit_code': 0, 'terminated': True, evidence: True})
    result = manager.get(run['id'])
    assert result['attempts'][0]['state'] == verdict
    assert result['results']['case'] == verdict
    assert result['slot_results']['0'] == verdict
    assert result['overall_result'] != 'PASS' and manager.claim(run['id']) is None
    assert result['integration'].get('logical_results', {}).get('case', {}).get('state') != 'PASS'


def test_cancel_source_preparation_failure_without_batch_is_terminal_without_runner_operation(rig):
    manager, service, _, request, _, _ = rig
    def fail(*args): raise TestError('Source modified during copy', 'SOURCE_CHANGED')
    service.preparer = fail
    run = service.start('source-failure', 'plugin-principal', request)
    service.prepare_run(run['id'])
    failed = manager.get(run['id'])
    assert failed['state'] == 'PAUSED' and failed['integration']['phase'] == 'FAILED'
    cancelled = service.act(run['id'], 'cancel-failed', 'plugin-principal', failed['version'], 'cancel')
    assert cancelled['state'] == 'CANCELLED' and cancelled['attempts'] == []


@pytest.mark.parametrize('proof,cancel_state', [(True, 'CANCELLED'), (False, 'UNKNOWN')])
def test_failed_batch_cancellation_requires_positive_termination_evidence(rig, proof, cancel_state):
    manager, service, _, request, _, _ = rig
    batch = {'id': 'batch-one', 'batch_id': 'batch-one', 'state': 'FAILED', 'terminated': proof}
    manager.runner.begin_integration = lambda *args: batch
    manager.runner.cancel_batch = lambda *args: None
    manager.runner.reconcile_integration = lambda *args: batch
    released = []
    manager.runner.finish_integration = lambda receipt: released.append(receipt) or receipt | {'state': 'RELEASED'}
    run = service.start('failed-batch', 'plugin-principal', request)
    service.prepare_run(run['id'])
    current = manager.get(run['id'])
    service.act(run['id'], 'cancel-failed', 'plugin-principal', current['version'], 'cancel')
    service.poll_batch(run['id'])
    if proof and hasattr(service, 'finalize_run'):
        service.finalize_run(run['id'])
    result = manager.get(run['id'])
    assert result['state'] == cancel_state
    service.release_batch(run['id'])
    assert bool(released) is proof


@pytest.mark.parametrize('ack_lost', [False, True])
def test_worker_waits_for_final_fence_before_public_pass_and_retries_lost_release_ack(rig, tmp_path, ack_lost):
    manager, _, _, request, _, _ = rig
    fence_entered, fence_release = threading.Event(), threading.Event()
    began, finish_calls = [], []
    batch = {'state': 'READY', 'id': 'batch-one', 'batch_id': 'batch-one', 'terminated': True}
    manager.runner.begin_integration = lambda *args: began.append('flash') or batch
    manager.runner.reconcile_integration = lambda *args: batch
    def execute(tc, connection, timeout, context, emit, cancelled):
        emit('stdout', 'Test Result: PASS\n')
        return {'exit_code': 0, 'terminated': True}
    def finish(receipt):
        finish_calls.append(receipt)
        fence_entered.set()
        assert fence_release.wait(3)
        if ack_lost and len(finish_calls) == 1:
            raise TestError('Parent was released but acknowledgement was lost', 'RUNNER_UNAVAILABLE')
        return receipt | {'state': 'RELEASED', 'terminated': True}
    manager.runner.execute = execute
    manager.runner.finish_integration = finish
    worker = Worker(manager)
    try:
        with client_for(rig, tmp_path) as client:
            run = client.post(PREFIX + '/integration/runs', json=request, headers={'Idempotency-Key': 'final-fence'}).json()
            tick_until(worker, fence_entered.is_set)
            pending = client.get(PREFIX + '/runs/' + run['id']).json()
            assert pending['state'] != 'COMPLETED' and pending['overall_result'] == 'INCOMPLETE'
            assert pending['integration']['phase'] == 'FINALIZING'
            report = client.get(PREFIX + '/runs/' + run['id'] + '/report/json').json()
            assert report['overall_result'] != 'PASS'
            fence_release.set()
            if ack_lost:
                tick_until(worker, lambda: manager.get(run['id'])['state'] == 'UNKNOWN')
                assert manager.get(run['id'])['overall_result'] == 'INCOMPLETE'
                rig[4][0] += 10  # Advance the injected clock past bounded finalization retry backoff.
            tick_until(worker, lambda: manager.get(run['id'])['state'] == 'COMPLETED')
            assert manager.get(run['id'])['overall_result'] == 'PASS'
            assert began == ['flash']
            assert len(finish_calls) == (2 if ack_lost else 1)
    finally:
        fence_release.set(); worker.close()


def test_final_console_fence_failure_blocks_public_pass_and_keeps_reservations(rig, tmp_path):
    manager, _, _, request, _, _ = rig
    manager.runner.begin_integration = lambda *args: {'state': 'READY', 'id': 'batch-one', 'terminated': True}
    manager.runner.reconcile_integration = lambda *args: {'state': 'UNKNOWN', 'id': 'batch-one', 'terminated': False}
    def execute(tc, connection, timeout, context, emit, cancelled):
        emit('stdout', 'Test Result: PASS\n')
        return {'exit_code': 0, 'terminated': True}
    manager.runner.execute = execute
    def unsafe(receipt): raise TestError('Final observation gap retained parent', 'HARDWARE_UNKNOWN')
    manager.runner.finish_integration = unsafe
    worker = Worker(manager)
    try:
        with client_for(rig, tmp_path) as client:
            run = client.post(PREFIX + '/integration/runs', json=request, headers={'Idempotency-Key': 'unsafe-final-fence'}).json()
            tick_until(worker, lambda: manager.get(run['id'])['state'] == 'UNKNOWN')
            result = client.get(PREFIX + '/runs/' + run['id']).json()
            assert result['overall_result'] == 'INCOMPLETE' and result['environment_ready'] is False
            assert result['attempts'][0]['state'] == 'PASS'
            with manager.store.connection() as connection:
                assert connection.execute('SELECT COUNT(*) FROM reservations WHERE run_id=?', (run['id'],)).fetchone()[0] > 0
            assert client.get(PREFIX + '/runs/' + run['id'] + '/report/json').json()['overall_result'] != 'PASS'
    finally:
        worker.close()


def test_preview_token_pins_runner_profile_and_rejects_later_profile_change(rig):
    manager, service, _, request, _, _ = rig
    manager.simulation = False
    revision = ['1' * 64]
    manager.runner.integration_profile = lambda name: {'profile': name, 'revision': revision[0]}
    preview = service.preview('plugin-principal', request)
    service.prepare_one()
    token = service.preparation(preview['preparation_id'], 'plugin-principal')['prepared_token']
    revision[0] = '2' * 64
    with pytest.raises(TestError) as error:
        service.start('stale-profile', 'plugin-principal', request | {'prepared_token': token})
    assert error.value.code == 'PREPARED_TOKEN_STALE'
    assert manager.store.all() == []


def test_accepted_request_profile_pin_survives_profile_change_and_replay_skips_probe(rig):
    manager, service, _, request, _, _ = rig
    manager.simulation = False
    probes = []
    def profile(name):
        probes.append(name)
        return {'profile': name, 'revision': '1' * 64}
    manager.runner.integration_profile = profile
    accepted = service.start('profile-intent', 'plugin-principal', request)
    def changed(name): raise AssertionError('Accepted-response replay must precede mutable Runner profile probe')
    manager.runner.integration_profile = changed
    assert service.start('profile-intent', 'plugin-principal', request) == accepted
    assert manager.store.snapshot(accepted['id'])['integration']['config']['flash_profile_revision'] == '1' * 64
    assert probes == ['reviewed-fixture']
