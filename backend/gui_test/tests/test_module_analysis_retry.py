"""Host acceptance for changed-input analysis retries, using only local fixture DBs.

No BSP execution, real TC process, model call, board, or automatic result reporting.
"""
import copy
from contextlib import contextmanager

import pytest

from backend.gui_test.core.models import TestError, uid
from backend.gui_test.tests.test_failure_analysis import advisory, verifier
from backend.gui_test.tests.test_module_selection import module_rig, install_automatic_profile


def failed_parent(rig):
    run = rig.manager.start(uid(), 'owner', rig.request)
    claim = rig.manager.claim(run['id'])
    assert claim
    rig.manager.emit(run['id'], claim['attempt']['id'], 'stdout', 'Test Result: FAIL\n')
    rig.manager.finish(claim, {'exit_code': 0, 'terminated': True})
    return rig.manager.get(run['id'])


def changed_request(rig, *, source=True):
    if source:
        rig.source['revision'] = 'remediated-catalog'
        rig.source['tests'][0]['content_hash'] = 'remediated-bytes'
    selected = rig.service.select(rig.manager, rig.job_id, rig.module_id, 'shared', rig.source['revision'])
    command = rig.manager.save_document('command', 'Remediated module command', {
        'single': ['python', '{tc_path}', '--fixture-remediated', '-p', '{com_a}'],
        'dual': ['python', '{tc_path}', '--fixture-remediated', '-p', '{com_a}', '-p2', '{com_b}']})
    return rig.request | {'source_revision': rig.source['revision'], 'module_context': selected['context'],
                          'command_profile': 'Remediated module command', 'command_revision': command['revision']}


def submit_child(rig, request, *, callback=None):
    def verify(run, item, value):
        proof = verifier(run, item, value) | {'inputs_unchanged': False, 'retry_request': request}
        if callback:
            callback()
        return proof
    rig.manager.analysis.verifier = verify
    item = rig.manager.analysis.claim('owner', 'module-fixture')
    assert item
    return rig.manager.analysis.submit(item['id'], 'owner', item['lease_token'], advisory(item, action='REPREPARE'))


def test_changed_module_inputs_prepare_child_with_unchanged_bsp_baseline(module_rig):
    rig = module_rig
    parent = failed_parent(rig)
    bsp_before = copy.deepcopy(rig.engine.snapshot(rig.job_id))
    request = changed_request(rig)
    result = submit_child(rig, request)
    assert result['status'] == 'CHILD_CREATED'
    child = rig.manager.get(result['child_run_id'])
    assert child['module_context'] == request['module_context']
    assert child['module_context']['catalog_revision'] == 'remediated-catalog'
    assert {k: v for k, v in child['module_context'].items() if k != 'catalog_revision'} == {
        k: v for k, v in parent['module_context'].items() if k != 'catalog_revision'}
    assert child['source_revision'] == request['source_revision']
    assert child['command_snapshot']['revision'] == request['command_revision']
    assert child['timeout_settings_snapshot'] == parent['timeout_settings_snapshot']
    assert child['tests'][0]['content_hash'] == 'remediated-bytes'
    assert child['parent_run_id'] == parent['id'] and child['plan'] == parent['plan']
    assert child['retry_chain']['id'] == parent['retry_chain']['id']
    assert child['retry_chain']['automatic_retries'] == 1
    assert rig.manager.get(parent['id'])['attempts'] == parent['attempts']
    assert rig.manager.get(parent['id'])['tests'] == parent['tests']
    assert rig.engine.snapshot(rig.job_id) == bsp_before  # No manufactured module completion or final approval.
    assert rig.manager.claim(child['id'])['attempt']['slot_index'] == 0


def test_module_child_and_parent_analysis_receipts_commit_before_bsp_guard_release(module_rig, monkeypatch):
    rig = module_rig
    parent = failed_parent(rig)
    request = changed_request(rig)
    original = rig.service.retry_guard
    observed = []
    @contextmanager
    def inspect(*args):
        with original(*args):
            yield
            rows = rig.manager.store.all()
            old = next(run for run in rows if run['id'] == parent['id'])
            child = next(run for run in rows if run.get('parent_run_id') == parent['id'])
            analysis = rig.manager.analysis.get(old['failure_analysis']['request_id'], 'owner')
            with rig.manager.store.connection() as c:
                owners = [row['run_id'] for row in c.execute('SELECT run_id FROM reservations')]
            observed.append((old['child_run_id'], child['id'], analysis['status'], owners))
    monkeypatch.setattr(rig.service, 'retry_guard', inspect)
    result = submit_child(rig, request)
    assert observed == [(result['child_run_id'], result['child_run_id'], 'CHILD_CREATED', [result['child_run_id']] * 2)]


@pytest.mark.parametrize('field,value', [('job_id', 'other-job'), ('module_id', 'other-module'),
                                       ('attempt_id', 'other-attempt'), ('plan_version', 999),
                                       ('fingerprint', 'other-baseline')])
def test_module_retry_cannot_move_to_different_bsp_context(module_rig, field, value):
    rig = module_rig
    parent = failed_parent(rig)
    request = changed_request(rig)
    request['module_context'][field] = value
    result = submit_child(rig, request)
    assert result['status'] == 'HOLD'
    assert len(rig.manager.store.all()) == 1
    assert not rig.manager.get(parent['id']).get('child_run_id')


@pytest.mark.parametrize('change', ['pause', 'plan', 'attempt', 'prerequisite', 'boot-group', 'automatic'])
def test_module_child_final_acceptance_rechecks_bsp_gate_after_preparation(module_rig, monkeypatch, change):
    rig = module_rig
    parent = failed_parent(rig)
    request = changed_request(rig)
    original = rig.manager.analysis._prepare_child
    def prepare(*args):
        result = original(*args)
        if change == 'automatic':
            install_automatic_profile(rig)
        else:
            def mutate(job, module):
                if change == 'pause': job['paused'] = True
                if change == 'plan': job['plan_version'] += 1
                if change == 'attempt': module['stages']['device_test']['attempts'][-1]['id'] = 'replaced-attempt'
                if change == 'prerequisite': module['stages']['verification']['validity'] = 'INVALIDATED'
                if change == 'boot-group':
                    module['group'] = 'main'
                    boot = copy.deepcopy(module)
                    boot.update(id='required-boot-group', name='Bootloader', group='boot')
                    boot['stages']['device_test']['status'] = 'PENDING'
                    job['modules'].append(boot)
            rig.mutate(mutate)
        return result
    monkeypatch.setattr(rig.manager.analysis, '_prepare_child', prepare)
    with pytest.raises(TestError):
        submit_child(rig, request)
    assert len(rig.manager.store.all()) == 1
    current = rig.manager.get(parent['id'])
    assert current['failure_analysis']['latched'] and current['retry_chain']['automatic_retries'] == 0
    with rig.manager.store.connection() as c:
        assert all(row['run_id'] == parent['id'] for row in c.execute('SELECT run_id FROM reservations'))


@pytest.mark.parametrize('change', ['command', 'timeout', 'source-generation'])
def test_module_child_final_acceptance_rejects_changed_input_revisions(module_rig, monkeypatch, change):
    rig = module_rig
    parent = failed_parent(rig)
    request = changed_request(rig)
    original = rig.manager.analysis._prepare_child
    def prepare(*args):
        result = original(*args)
        if change == 'command':
            rig.manager.save_document('command', request['command_profile'], {
                'single': ['python', '{tc_path}', '--different-fixture', '{com_a}'],
                'dual': ['python', '{tc_path}', '--different-fixture', '{com_a}', '{com_b}']})
        elif change == 'timeout':
            settings = rig.manager.timeouts.read()
            rig.manager.timeouts.save({'expected_revision': settings['revision'], 'default_seconds': 777, 'overrides': {}})
        else:
            with rig.manager.store.transaction() as c:
                active = rig.manager.sources.state(c)
                active['version'] += 1
                active['active']['kind'] = 'server-folder'
                # A descriptor switch after preparation must never accept the old legacy source.
                c.execute("INSERT OR REPLACE INTO documents VALUES('source-state','active',?)", (__import__('json').dumps(active),))
        return result
    monkeypatch.setattr(rig.manager.analysis, '_prepare_child', prepare)
    with pytest.raises(TestError):
        submit_child(rig, request)
    assert len(rig.manager.store.all()) == 1
    assert not rig.manager.get(parent['id']).get('child_run_id')


@pytest.mark.parametrize('change', ['pause', 'automatic'])
def test_accepted_module_child_rechecks_current_host_gate_before_attempt(module_rig, change):
    rig = module_rig
    failed_parent(rig)
    result = submit_child(rig, changed_request(rig))
    assert result['status'] == 'CHILD_CREATED'
    if change == 'pause':
        rig.mutate(lambda job, module: job.update(paused=True))
    else:
        install_automatic_profile(rig)
    assert rig.manager.claim(result['child_run_id']) is None
    child = rig.manager.get(result['child_run_id'])
    assert not child['attempts'] and child['failure_analysis']['latched']


def test_module_retry_can_adopt_new_current_bsp_attempt_only_after_gates_are_ready(module_rig):
    rig = module_rig
    parent = failed_parent(rig)
    def rebuilt(job, module):
        # Synthetic state of a remediation that completed normal review/build/
        # verification and obtained its new confirmed plan and waiting device TC.
        job['plan_version'] += 1
        job['confirmed_plan'] = job['plan_version']
        job['fingerprint'] = 'current-remediated-bsp-baseline'
        stage = module['stages']['device_test']
        stage['attempts'].append({'id': 'current-remediated-attempt', 'status': 'WAITING_INPUT',
                                  'fingerprint': job['fingerprint']})
    rig.mutate(rebuilt)
    request = changed_request(rig)
    result = submit_child(rig, request)
    assert result['status'] == 'CHILD_CREATED'
    child = rig.manager.get(result['child_run_id'])
    assert child['module_context']['attempt_id'] == 'current-remediated-attempt'
    assert child['module_context']['fingerprint'] == 'current-remediated-bsp-baseline'
    assert child['module_context']['plan_version'] == parent['module_context']['plan_version'] + 1
    assert rig.manager.get(parent['id'])['module_context'] == parent['module_context']
    assert child['retry_chain']['id'] == parent['retry_chain']['id']
    assert rig.manager.claim(child['id'])


def test_module_child_attempt_commit_is_visible_before_bsp_guard_releases(module_rig, monkeypatch):
    rig = module_rig
    failed_parent(rig)
    result = submit_child(rig, changed_request(rig))
    child_id = result['child_run_id']
    original = rig.service.guard
    observed = []
    @contextmanager
    def inspect(*args):
        with original(*args):
            yield
            current = rig.manager.get(child_id)
            observed.append((current['state'], len(current['attempts'])))
    monkeypatch.setattr(rig.service, 'guard', inspect)
    assert rig.manager.claim(child_id)
    assert observed == [('RUNNING', 1)]


def test_cancellation_during_module_child_preparation_wins_atomic_acceptance(module_rig, monkeypatch):
    rig = module_rig
    parent = failed_parent(rig)
    request = changed_request(rig)
    original = rig.manager.analysis._prepare_child
    def prepare(*args):
        prepared = original(*args)
        current = rig.manager.get(parent['id'])
        rig.manager.act(parent['id'], uid(), 'owner', current['version'], 'cancel')
        return prepared
    monkeypatch.setattr(rig.manager.analysis, '_prepare_child', prepare)
    with pytest.raises(TestError) as error:
        submit_child(rig, request)
    assert error.value.code == 'ANALYSIS_STALE'
    current = rig.manager.get(parent['id'])
    assert current['state'] == 'CANCELLED' and not current.get('child_run_id')
    assert current['retry_chain']['automatic_retries'] == 0 and len(rig.manager.store.all()) == 1


def test_module_child_storage_failure_rolls_back_parent_chain_and_reservations(module_rig, monkeypatch):
    rig = module_rig
    parent = failed_parent(rig)
    request = changed_request(rig)
    original = rig.manager.store.save
    def crash(c, run, event, data=None):
        result = original(c, run, event, data)
        if event == 'FAILURE_ANALYSIS_CHILD_CREATED':
            raise RuntimeError('Fixture crash before acceptance receipt commit')
        return result
    monkeypatch.setattr(rig.manager.store, 'save', crash)
    with pytest.raises(RuntimeError):
        submit_child(rig, request)
    current = rig.manager.get(parent['id'])
    assert not current.get('child_run_id') and current['retry_chain']['automatic_retries'] == 0
    assert len(rig.manager.store.all()) == 1 and current['attempts'] == parent['attempts']
    with rig.manager.store.connection() as c:
        assert all(row['run_id'] == parent['id'] and row['token'] == parent['lease_token']
                   for row in c.execute('SELECT run_id,token FROM reservations'))


def test_same_input_module_retry_requires_current_bsp_gate_before_release(module_rig):
    rig = module_rig
    parent = failed_parent(rig)
    rig.mutate(lambda job, module: job.update(paused=True))
    rig.manager.analysis.verifier = verifier
    item = rig.manager.analysis.claim('owner', 'module-fixture')
    result = rig.manager.analysis.submit(item['id'], 'owner', item['lease_token'], advisory(item))
    assert result['status'] == 'HOLD'
    assert rig.manager.get(parent['id'])['retry_chain']['automatic_retries'] == 0
    assert rig.manager.claim(parent['id']) is None



def test_changed_module_timeout_is_pinned_in_child_and_parent_is_unchanged(module_rig, monkeypatch):
    rig = module_rig
    parent = failed_parent(rig)
    settings = rig.manager.timeouts.read()
    current = rig.manager.timeouts.save({'expected_revision': settings['revision'], 'default_seconds': 777, 'overrides': {}})
    monkeypatch.setattr(rig.manager.runner, 'require_timeout_support', lambda: None, raising=False)
    request = changed_request(rig) | {'timeout_revision': current['revision']}
    result = submit_child(rig, request)
    assert result['status'] == 'CHILD_CREATED'
    child = rig.manager.get(result['child_run_id'])
    assert child['timeout_settings_snapshot']['revision'] == current['revision']
    assert child['tests'][0]['timeout'] == 777
    assert rig.manager.get(parent['id'])['tests'][0]['timeout'] == parent['tests'][0]['timeout']
    assert rig.manager.get(parent['id'])['timeout_settings_snapshot'] == parent['timeout_settings_snapshot']


def test_retry_cannot_switch_to_another_independently_ready_module(module_rig):
    rig = module_rig
    parent = failed_parent(rig)
    def add_ready_module(job, module):
        other = copy.deepcopy(module)
        other['id'] = 'different-ready-module'
        job['modules'].append(other)
    rig.mutate(add_ready_module)
    request = changed_request(rig)
    other = rig.service.select(rig.manager, rig.job_id, 'different-ready-module', 'shared', rig.source['revision'])
    assert not other['blocked_reason'] and request['tc_ids'][0] in other['tc_ids']
    request['module_context'] = other['context']
    assert rig.manager.preflight(request)['ok']  # Independently valid, outside this retry's scope.
    result = submit_child(rig, request)
    assert result['status'] == 'HOLD'
    assert len(rig.manager.store.all()) == 1 and not rig.manager.get(parent['id']).get('child_run_id')
