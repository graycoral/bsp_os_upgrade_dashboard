"""T-72/81/82: scheduling isolation and durable local process evidence only."""
from concurrent.futures import Future, wait
from threading import Event
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import UUID

import pytest

from backend.adapters import receipts
from backend.adapters.process import run_process
from backend.domain.engine import Engine
from backend.domain.policy import Conflict, uid
from backend.settings import Profile
from backend.storage.store import Store
from backend.worker.main import Worker, demo_v2_result

from test_orchestration_runtime import (runtime, action, analysis_claim, analysis_envelope,
    analyze_and_confirm, commit_report, coordinator_envelope, enqueue)
from test_orchestration_contracts import role_capability_profile


@pytest.mark.parametrize('author,reviewer', [('opencode', 'claude'), ('claude', 'codex')])
@pytest.mark.parametrize('review_eligible', [False, True])
def test_rr4_worker_review_preserves_author_policy_and_frozen_reviewer_capability(
        runtime, monkeypatch, author, reviewer, review_eligible):
    import backend.adapters.native as native
    from backend.adapters.bridge import Bridge
    from backend.adapters.capabilities import freeze_capabilities
    engine, job_id = runtime
    code = unknown_code_claim(engine, job_id)
    profile = code['job']['profile']
    declared = role_capability_profile()
    profile.update(execution='bridge', runner='bridge', agents=declared['agents'],
                   contract_capabilities=freeze_capabilities(declared))
    code['job']['execution'] = 'bridge'
    attempt = code['attempt']
    attempt.update(tool=author, review_tool=reviewer)
    attempt['request']['report_expectations']['selected_tool'] = author
    review_request = attempt['review_request']
    review_request['report_expectations'].update(author_tools=[author], selected_tool=reviewer)
    if not review_eligible:
        # The CLI is still configured and the original declaration still permits
        # review; only the immutable snapshot controls this invocation.
        profile['contract_capabilities']['tools'][reviewer]['roles'].remove('reviewer')
    envelope = demo_v2_result(code)
    independent = envelope['related_reports'][0]
    envelope['related_reports'] = []
    calls = []
    def invoke(_self, frozen, tool, request, timeout=None):
        calls.append((tool, request['stage']))
        if request['stage'] == 'code':
            return envelope
        assert review_eligible
        assert tool == reviewer and tool != author
        assert request['report_expectations']['author_tools'] == [author]
        assert request['session_id'] != attempt['session_id']
        return independent
    monkeypatch.setattr(Bridge, 'invoke', invoke)
    monkeypatch.setattr(native, 'workspace_revision', lambda _profile: envelope['observations']['source_revision'])
    worker = Worker(engine, delay=0)
    try:
        result = worker._execute(code)
        assert calls == [(author, 'code')] + ([(reviewer, 'review')] if review_eligible else [])
        if review_eligible:
            assert result['transport']['status'] == 'COMPLETED'
            assert result['related_reports'][0]['transport']['tool'] == reviewer
        else:
            assert result['transport']['status'] == 'FAILED'
            proof = engine.orchestration.transport_context(review_request['report_id'])
            assert engine.orchestration.valid_not_launched(proof)
    finally:
        worker.close()


def receipt_fixture():
    return {'receipt_version': 1, 'phase': 'LAUNCHED', 'host_id': receipts.host_identity(),
            'boot_id': receipts.boot_identity(), 'platform': os.name, 'launch_id': 'launch-1',
            'pid': 10000, 'start_id': '12345', 'group_id': 10000, 'session_id': 10000}


@pytest.mark.parametrize('raw', [None, {}, {'receipt_version': 2}, {'receipt_version': True}])
def test_t82_missing_or_unsupported_receipt_never_proves_termination(raw):
    assert receipts.verify_receipt(raw).state == 'UNKNOWN'


def test_t82_foreign_host_is_unknown_and_verified_boot_change_is_terminal():
    receipt = receipt_fixture()
    receipt['host_id'] = 'another-host'
    assert receipts.verify_receipt(receipt).state == 'UNKNOWN'
    receipt['host_id'] = receipts.host_identity()
    receipt['boot_id'] = 'another-boot'
    assert receipts.verify_receipt(receipt).state == 'TERMINATED'


def test_t82_unreadable_process_identity_stays_unknown(monkeypatch):
    def unavailable(*_):
        raise PermissionError('fixture inspection denied')
    monkeypatch.setattr(receipts, '_windows' if os.name == 'nt' else '_linux', unavailable)
    assert receipts.verify_receipt(receipt_fixture()).state == 'UNKNOWN'


@pytest.mark.skipif(os.name != 'nt', reason='Windows descendant verification policy')
def test_t82_windows_leader_pid_reuse_cannot_release_descendant_lease(monkeypatch):
    monkeypatch.setattr(receipts, '_windows', lambda pid: {'pid': pid, 'start_id': 'new-start', 'state': 'RUNNING'})
    assert receipts.verify_receipt(receipt_fixture()).state == 'UNKNOWN'


@pytest.mark.skipif(os.name != 'posix', reason='Linux exclusive process group identity')
def test_t82_linux_receipt_requires_exclusive_session_and_group():
    receipt = receipt_fixture()
    receipt['group_id'] = 99
    assert receipts.verify_receipt(receipt).state == 'UNKNOWN'


def test_t82_durable_receipt_atomic_replace_keeps_exact_hash(tmp_path):
    path = tmp_path / 'nested' / 'process.json'
    receipts.durable_receipt(path, {'phase': 'LAUNCHED', 'launch_id': 'one'})
    terminal = {'phase': 'TERMINATED', 'launch_id': 'one', 'exit_code': 0}
    digest = receipts.durable_receipt(path, terminal)
    assert json.loads(path.read_bytes()) == terminal
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert not path.with_name('process.json.tmp').exists()


def test_t82_receipted_process_publishes_launch_before_release_and_hashes_terminal_output(tmp_path, monkeypatch):
    # Release is a launch-callback barrier, so this does not depend on sleep timing.
    script = tmp_path / 'harmless.py'
    script.write_text("from pathlib import Path\nimport time\n"
                      "while not Path('release').exists(): time.sleep(.005)\n"
                      "print('fixture output')\n", encoding='utf-8')
    observed = []
    def record(value):
        durable = tmp_path / value['receipt_path']
        assert durable.is_file()
        assert hashlib.sha256(durable.read_bytes()).hexdigest() == value['receipt_sha256']
        observed.append(value)
        if value['phase'] == 'LAUNCHED':
            assert not (tmp_path / 'release').exists()
            (tmp_path / 'release').write_text('release fixture process')
    # Windows cannot establish descendant termination by inspecting only its leader;
    # inject the verification seam while still executing a real harmless local process.
    monkeypatch.setattr(receipts, 'verify_receipt', lambda _: receipts.ProcessVerification('TERMINATED', {'fixture': True}))
    result = run_process([sys.executable, str(script)], cwd=str(tmp_path), timeout=5,
                         launch_context={'launch_id': 'launch-1', 'intent_nonce': 'intent-1'}, receipt_sink=record)
    assert result.code == 0 and not result.unknown
    assert result.stdout.strip() == b'fixture output'
    assert [r['phase'] for r in observed] == ['LAUNCHED', 'TERMINATED']
    assert observed[0]['intent_nonce'] == 'intent-1'
    for name, raw in [('stdout', result.stdout), ('stderr', result.stderr)]:
        output = observed[-1]['outputs'][name]
        assert (tmp_path / output['path']).read_bytes() == raw
        assert output['sha256'] == hashlib.sha256(raw).hexdigest()


def test_t82_receipt_persistence_failure_is_unknown_even_if_process_is_killed(tmp_path):
    def fail_receipt(_):
        raise OSError('fixture disk unavailable')
    result = run_process([sys.executable, '-c', 'import sys; sys.stdin.read()'], cwd=str(tmp_path),
                         timeout=5, launch_context={'launch_id': 'failed-durability'}, receipt_sink=fail_receipt)
    assert result.unknown is True
    assert result.error


def settle(worker):
    futures = list(worker.pending) + list(worker.control_pending) + list(worker.jira_pending)
    if futures:
        _, unfinished = wait(futures, timeout=5)
        assert not unfinished, 'Bounded local fixture work did not finish.'


def advance_until(worker, condition, maximum=50):
    for _ in range(maximum):
        worker.tick()
        if condition():
            return
        settle(worker)
    pytest.fail('Worker did not reach the expected durable state within bounded fixture steps.')


def test_t71_t78_full_demo_v2_worker_preserves_confirmation_boot_manual_and_final_gates(tmp_path, monkeypatch):
    from backend.adapters.bridge import Bridge
    def forbidden(*_, **__):
        pytest.fail('Demo lifecycle attempted an external adapter call.')
    monkeypatch.setattr(Bridge, 'invoke', forbidden)
    monkeypatch.setattr(Bridge, 'execute', forbidden)
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    engine = Engine(Store(tmp_path / 'db.sqlite'), tmp_path / 'artifacts')
    profile = Profile(workspace=str(workspace), module_report_version=2, orchestration={'enabled': True},
                      modules=[{'name': 'Boot', 'group': 'boot'}, {'name': 'Main', 'group': 'main'}]).model_dump()
    job_id = engine.create(uid(), profile, 'Full simulated lifecycle', 'linux')['job_id']
    worker = Worker(engine, delay=0)
    try:
        snapshot = lambda: engine.store.snapshot(job_id)
        advance_until(worker, lambda: all(m['stages']['analysis']['status'] == 'SUCCEEDED' for m in snapshot()['modules']))
        assert snapshot()['confirmed_plan'] is None
        assert all(not m['stages']['design']['attempts'] for m in snapshot()['modules'])
        action(engine, job_id, 'confirm', {'plan_version': 1})
        advance_until(worker, lambda: snapshot()['modules'][0]['stages']['device_test']['status'] == 'WAITING_INPUT')
        boot, main = snapshot()['modules']
        assert main['stages']['analysis']['status'] == 'SUCCEEDED'
        assert main['stages']['design']['attempts'] == []
        assert snapshot()['integration']['status'] == 'PENDING'
        with pytest.raises(Conflict):
            action(engine, job_id, 'final-review', {'reviewer': 'fixture', 'evidence': 'Premature.'})
        for index in range(2):
            advance_until(worker, lambda: snapshot()['modules'][index]['stages']['device_test']['status'] == 'WAITING_INPUT')
            module = snapshot()['modules'][index]
            device = module['stages']['device_test']
            assert device['result'] is None  # Download/exit zero never manufactures a device result.
            action(engine, job_id, 'manual-test', {'module_id': module['id'], 'attempt_id': device['attempts'][-1]['id'],
                                                 'cases': {case: 'PASS' for case in device['required_cases']}})
        advance_until(worker, lambda: snapshot()['integration']['status'] == 'SUCCEEDED')
        assert snapshot()['final_review'] is None
        action(engine, job_id, 'final-review', {'reviewer': 'fixture human', 'evidence': 'Reviewed simulated result only.'})
        assert engine.snapshot(job_id)['state'] == 'COMPLETED'
        reports = engine.reports.list(job_id)
        assert len([r for r in reports if r['stage'] == 'review']) == 2
        for module in snapshot()['modules']:
            code = module['stages']['code']['result']
            assert code['review_report_id'] != code['report_id']
            assert len(module['stages']['design']['attempts']) == 1
            assert module['stages']['device_test']['result']['simulation'] is True
    finally:
        worker.close()


def test_t81_actual_worker_drains_modules_while_coordinator_and_jira_block(runtime, monkeypatch):
    from backend.adapters.bridge import Bridge
    from backend.adapters.capabilities import freeze_capabilities
    from backend.adapters.jira import Jira
    engine, job_id = runtime
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['execution'] = job['profile']['execution'] = 'bridge'
        job['profile']['runner'] = 'bridge'
        bridge_profile = role_capability_profile()
        job['profile'].update(agents=bridge_profile['agents'], build_argv=bridge_profile['build_argv'],
                              contract_capabilities=freeze_capabilities(bridge_profile))
        job['profile']['jira_url'] = 'https://fixture.invalid'
        job['session']['status'] = 'READY'
        engine.store.save(c, job, 'FIXTURE_CONNECTED')
    action(engine, job_id, 'decision', {'title': 'Deferred human choice', 'affected_modules': [engine.store.snapshot(job_id)['modules'][0]['id']]})
    control_entered, jira_entered, release = Event(), Event(), Event()
    def invoke(_self, profile, tool, request, timeout):
        assert request['message_type'] == 'orchestration_request'
        control_entered.set()
        assert release.wait(5), 'Coordinator fixture release was not signaled.'
        return Worker._failed_envelope('Fixture coordinator timeout.')
    def jira(_self, decision, prior):
        jira_entered.set()
        assert release.wait(5), 'Jira fixture release was not signaled.'
        return {'sync_status': 'UNKNOWN'}
    monkeypatch.setattr(Bridge, 'invoke', invoke)
    monkeypatch.setattr(Bridge, 'execute', lambda _self, claim: demo_v2_result(claim))
    monkeypatch.setattr(Jira, 'ensure_link', jira)
    worker = Worker(engine, delay=0)
    try:
        worker.tick()
        assert control_entered.wait(5) and jira_entered.wait(5)
        module_futures = list(worker.pending)
        assert module_futures
        _, unfinished = wait(module_futures, timeout=5)
        assert not unfinished
        worker.tick()
        snapshot = engine.store.snapshot(job_id)
        # The judgment targets module 0; module 1 is independently approved for analysis.
        assert snapshot['modules'][1]['stages']['analysis']['status'] == 'SUCCEEDED'
        assert not release.is_set()
        assert len(worker.control_pending) == len(worker.jira_pending) == 1
        # A DB writer can still commit while both external call barriers are held.
        action(engine, job_id, 'prompt', {'intent': 'note', 'prompt': 'fixture progress audit'})
    finally:
        release.set()
        worker.close()
    assert engine.store.snapshot(job_id)['modules'][1]['stages']['analysis']['status'] == 'SUCCEEDED'
    assert engine.orchestration.summary(job_id)['runs'][0]['status'] == 'FAILED'


@pytest.mark.parametrize('failure,expected_class', [
    ('malformed_json', 'CONTRACT'), ('tool_unavailable', 'CAPABILITY_UNSUPPORTED'),
    ('timeout', 'ENVIRONMENT'), ('tool_exit', 'ENVIRONMENT')])
def test_t81_real_control_adapter_failure_preserves_pass_and_independent_module_intake(
        runtime, monkeypatch, failure, expected_class):
    import backend.adapters.process as process
    from backend.adapters.capabilities import freeze_capabilities
    engine, job_id = runtime
    declared = role_capability_profile()
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['execution'] = job['profile']['execution'] = 'bridge'
        job['profile'].update(runner='bridge', agents=declared['agents'], build_argv=declared['build_argv'],
                              contract_capabilities=freeze_capabilities(declared))
        job['profile']['orchestration']['timeout_seconds'] = 17
        job['session']['status'] = 'READY'
        engine.store.save(c, job, 'FIXTURE_VALID_BRIDGE_CONTROL')
    passed = analysis_claim(engine, job_id, 0)
    commit_report(engine, passed, analysis_envelope(passed))
    independent = analysis_claim(engine, job_id, 1)
    run = engine.orchestration.claim(job_id, 'fixture-coordinator')
    assert run is not None
    preserved = engine.store.snapshot(job_id)['modules'][0]['stages']['analysis']
    if failure == 'tool_unavailable':
        # A frozen configuration can lose its executable between allocation and
        # dispatch; the adapter must reject it before launching any process.
        run['job']['profile']['agents']['claude'] = []
    calls = []
    def failed_process(argv, **kwargs):
        assert failure != 'tool_unavailable', 'An unavailable CLI was invoked.'
        calls.append(argv)
        assert kwargs['timeout'] == 17
        request = json.loads(kwargs['stdin'])
        assert request['orchestration_run_id'] == run['id']
        if failure == 'malformed_json':
            return process.ProcessResult(0, stdout=b'{invalid JSON')
        if failure == 'timeout':
            return process.ProcessResult(None, error='Fixture timeout, termination verified.')
        return process.ProcessResult(7, error='Fixture tool process exited unsuccessfully.')
    monkeypatch.setattr(process, 'run_process', failed_process)
    worker = Worker(engine, delay=0)
    try:
        envelope = worker.execute_orchestration(run)
        assert envelope['transport']['status'] == 'FAILED'
        assert envelope['transport']['error_class'] == expected_class
        assert bool(calls) == (failure != 'tool_unavailable')
        assert engine.orchestration.transport_context(run['id'])['result_envelope'] == envelope
        result = engine.orchestration.finish(run['id'], envelope)
        assert result['status'] == 'FAILED'
        assert engine.orchestration.summary(job_id)['proposals'] == []
        assert engine.store.snapshot(job_id)['modules'][0]['stages']['analysis'] == preserved
        commit_report(engine, independent, analysis_envelope(independent))
        snapshot = engine.store.snapshot(job_id)
        assert snapshot['modules'][0]['stages']['analysis'] == preserved
        assert snapshot['modules'][1]['stages']['analysis']['status'] == 'SUCCEEDED'
        assert len(engine.reports.list(job_id)) == 2
        with engine.store.connection() as c:
            assert c.execute('SELECT 1 FROM coordinator_lanes WHERE job_id=?', (job_id,)).fetchone() is None
    finally:
        worker.close()


def test_t72_worker_commits_completed_module_before_claiming_downstream(runtime, monkeypatch):
    engine, job_id = runtime
    analyze_and_confirm(engine, job_id)
    module_id = engine.store.snapshot(job_id)['modules'][0]['id']
    claim = engine.claim(job_id, module_id, 'design', 'fixture')
    completed = Future()
    completed.set_result(demo_v2_result(claim))
    worker = Worker(engine, delay=0)
    worker.pending[completed] = claim
    original_claim = engine.claim
    observed = []
    def checked_claim(jid, mid, stage, owner):
        if mid == module_id and stage == 'code':
            observed.append(engine.store.snapshot(jid)['modules'][0]['stages']['design']['status'])
        return original_claim(jid, mid, stage, owner)
    monkeypatch.setattr(engine, 'claim', checked_claim)
    try:
        worker.tick()
        assert observed and set(observed) == {'SUCCEEDED'}
        assert any(c['stage'] == 'code' for c in worker.pending.values())
    finally:
        worker.close()


def test_t72_ordinary_success_and_snapshot_polling_do_not_schedule_coordinator(runtime, monkeypatch):
    engine, job_id = runtime
    analyze_and_confirm(engine, job_id)
    # Consume the two documented initialization/analysis triggers first.
    run = engine.orchestration.claim(job_id, 'fixture')
    engine.orchestration.finish(run['id'], coordinator_envelope(run))
    module_id = engine.store.snapshot(job_id)['modules'][0]['id']
    claim = engine.claim(job_id, module_id, 'design', 'fixture')
    finished = Future()
    finished.set_result(demo_v2_result(claim))
    worker = Worker(engine, delay=0)
    worker.pending[finished] = claim
    calls = []
    monkeypatch.setattr(worker, 'execute_orchestration', lambda run: calls.append(run))
    try:
        worker.tick()
        for _ in range(3):
            engine.snapshot(job_id)
            engine.orchestration.summary(job_id)
        assert calls == []
        assert len(engine.orchestration.summary(job_id)['runs']) == 1
    finally:
        worker.close()


def test_t72_actual_worker_serializes_same_session_question_after_active_run(runtime, monkeypatch):
    from backend.adapters.bridge import Bridge
    engine, job_id = runtime
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['execution'] = job['profile']['execution'] = 'bridge'
        job['profile']['runner'] = 'bridge'
        job['session']['status'] = 'READY'
        engine.store.save(c, job, 'FIXTURE_CONNECTED')
    entered, release = Event(), Event()
    calls = []
    def invoke(_self, profile, tool, request, timeout):
        calls.append(request['stage'])
        if request['stage'] == 'orchestrate':
            entered.set()
            assert release.wait(5)
            return Worker._failed_envelope('Fixture control failure.')
        assert request['stage'] == 'question' and release.is_set()
        return {'outcome': 'SUCCEEDED', 'evidence': 'Read-only fixture answer.', 'external_session_id': 'question-session'}
    monkeypatch.setattr(Bridge, 'invoke', invoke)
    monkeypatch.setattr(Bridge, 'execute', lambda _self, claim: demo_v2_result(claim))
    worker = Worker(engine, delay=0)
    try:
        worker.tick()
        assert entered.wait(5)
        action(engine, job_id, 'prompt', {'intent': 'question', 'prompt': 'Explain stored status.'})
        worker.tick()
        assert calls == ['orchestrate']
        assert engine.store.snapshot(job_id)['prompts'][-1]['status'] == 'PENDING'
        release.set()
        settle(worker)
        worker.tick()
        settle(worker)
        worker.tick()
        assert calls[:2] == ['orchestrate', 'question']
        assert engine.store.snapshot(job_id)['prompts'][-1]['status'] == 'SUCCEEDED'
    finally:
        release.set()
        worker.close()


def test_t82_worker_terminal_result_survives_restart_before_future_intake(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    worker = Worker(engine, delay=0)
    try:
        envelope = worker.execute(claim)
        stored = engine.orchestration.transport_context(claim['attempt']['id'])
        assert stored['result_envelope'] == envelope
        assert engine.store.snapshot(job_id)['modules'][0]['stages']['analysis']['status'] == 'RUNNING'
        restarted = Engine(Store(engine.store.path), engine.artifacts)
        restarted.recover()
        stage = restarted.store.snapshot(job_id)['modules'][0]['stages']['analysis']
        assert stage['status'] == 'SUCCEEDED'
        assert len(stage['attempts']) == 1
        reports = restarted.reports.list(job_id)
        assert len(reports) == 1
        restarted.recover()
        assert restarted.reports.list(job_id) == reports
    finally:
        worker.close()


@pytest.mark.parametrize('state', ['ALIVE', 'UNKNOWN'])
def test_t82_unknown_writer_restart_retains_lease_and_cannot_be_retried(runtime, monkeypatch, state):
    import backend.adapters.process as process
    engine, job_id = runtime
    analyze_and_confirm(engine, job_id)
    module_id = engine.store.snapshot(job_id)['modules'][0]['id']
    design = engine.claim(job_id, module_id, 'design', 'fixture')
    engine.finish(job_id, module_id, 'design', design['attempt']['id'], design['attempt']['token'], demo_v2_result(design))
    code = engine.claim(job_id, module_id, 'code', 'fixture')
    intent = engine.orchestration.transport_context(code['attempt']['id'])
    engine.orchestration.record_transport(code['attempt']['id'], {
        'launch_id': intent['id'], 'intent_nonce': intent['nonce'], 'receipt_version': 1, 'pid': 1234})
    monkeypatch.setattr(process, 'verify_receipt', lambda _: receipts.ProcessVerification(state, {'fixture': True}))
    restarted = Engine(Store(engine.store.path), engine.artifacts)
    restarted.recover()
    stage = restarted.store.snapshot(job_id)['modules'][0]['stages']['code']
    assert stage['status'] == 'UNKNOWN'
    with restarted.store.connection() as c:
        assert c.execute('SELECT attempt,token FROM leases').fetchone()['attempt'] == code['attempt']['id']
    assert restarted.claim(job_id, module_id, 'code', 'other-worker') is None
    with pytest.raises(Conflict):
        action(restarted, job_id, 'retry', {'module_id': module_id, 'stage': 'code', 'previous_attempt_id': code['attempt']['id']})


def test_t82_verified_termination_without_authored_result_is_interrupted_failure(runtime, monkeypatch):
    import backend.adapters.process as process
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    intent = engine.orchestration.transport_context(claim['attempt']['id'])
    engine.orchestration.record_transport(claim['attempt']['id'], {
        'launch_id': intent['id'], 'intent_nonce': intent['nonce'], 'receipt_version': 1, 'pid': 1234})
    monkeypatch.setattr(process, 'verify_receipt', lambda _: receipts.ProcessVerification('TERMINATED', {'fixture': True}))
    restarted = Engine(Store(engine.store.path), engine.artifacts)
    restarted.recover()
    stage = restarted.store.snapshot(job_id)['modules'][0]['stages']['analysis']
    assert stage['status'] == 'FAILED'
    assert stage['result']['error_class'] == 'ENVIRONMENT'
    assert stage['attempts'][0]['id'] == claim['attempt']['id']


@pytest.mark.parametrize('runner', ['native', 'bridge'])
@pytest.mark.parametrize('stage', ['coordinate', 'question'])
def test_r4_legacy_controls_propagate_receipts_and_reconcile_durable_local_process_result(runtime, monkeypatch, runner, stage):
    import backend.adapters.native as native
    import backend.adapters.process as process
    engine, job_id = runtime
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['execution'] = job['profile']['execution'] = 'bridge'
        job['profile']['runner'] = runner
        job['profile']['agents']['claude'] = ['fixture-claude']
        job['profile']['instruction_snapshots'] = {'coordinate': '', 'question': ''}
        job['session']['status'] = 'NOT_CONNECTED' if stage == 'coordinate' else 'READY'
        engine.store.save(c, job, 'FIXTURE_LEGACY_RECEIPT')
    if stage == 'question':
        action(engine, job_id, 'prompt', {'intent': 'question', 'prompt': 'Explain stored status without execution.'})
    initial = engine.store.snapshot(job_id)
    session = str(UUID(initial['session']['id']))
    wire = {'outcome': 'SUCCEEDED', 'evidence': 'Harmless local control fixture.',
            'source_revision': initial['source_revision'], 'error_class': '', 'cause_key': ''}
    output = {'subtype': 'success', 'is_error': False, 'session_id': session, 'structured_output': wire} if runner == 'native' else wire | {'external_session_id': session}
    actual_process = process.run_process
    captured = []
    def local_process(argv, **kwargs):
        context, sink = kwargs.get('launch_context'), kwargs.get('receipt_sink')
        assert context and context.get('launch_id') and context.get('intent_nonce')
        assert callable(sink), 'Legacy control transport discarded its allocated receipt callback.'
        # Preserve the v1 request transport: no v2 envelope is injected into stdin.
        request_text = kwargs.get('stdin', b'').decode()
        assert 'module_request' not in request_text and 'orchestration_request' not in request_text
        assert stage in request_text
        release = Path(kwargs['cwd']) / ('release-' + stage)
        script = "from pathlib import Path\nimport time\nwhile not Path(" + repr(str(release)) + ").exists(): time.sleep(.005)\nprint(" + repr(json.dumps(output)) + ")\n"
        def durable(value):
            captured.append(value)
            sink(value)
            if value['phase'] == 'LAUNCHED':
                release.write_text('release harmless process')
        return actual_process([sys.executable, '-c', script], cwd=kwargs['cwd'], timeout=5,
                              launch_context=context, receipt_sink=durable)
    monkeypatch.setattr(native, 'run_process', local_process)
    monkeypatch.setattr(process, 'run_process', local_process)
    if os.name == 'nt':
        # Windows descendant inspection intentionally needs an injected verifier;
        # Linux execution checks the real exclusive process group to termination.
        monkeypatch.setattr(receipts, 'verify_receipt', lambda _: receipts.ProcessVerification('TERMINATED', {'fixture': True}))
        monkeypatch.setattr(process, 'verify_receipt', lambda _: receipts.ProcessVerification('TERMINATED', {'fixture': True}))
    worker = Worker(engine, delay=0)
    original_release = engine.orchestration.release_lane
    monkeypatch.setattr(engine.orchestration, 'release_lane', lambda *_args, **_kwargs: None)
    try:
        if stage == 'coordinate':
            worker.initialize_session(initial)
        else:
            worker.answer_question(initial)
        assert [r['phase'] for r in captured] == ['LAUNCHED', 'TERMINATED']
        with engine.store.connection() as c:
            lane = c.execute('SELECT owner_id FROM coordinator_lanes WHERE job_id=?', (job_id,)).fetchone()
        owner = lane['owner_id']
        persisted = engine.orchestration.transport_context(owner)
        assert persisted['process_receipt']['phase'] == 'TERMINATED'
        assert persisted['result_envelope']['legacy_control_result']['outcome'] == 'SUCCEEDED'
        monkeypatch.setattr(engine.orchestration, 'release_lane', original_release)
        restarted = Engine(Store(engine.store.path), engine.artifacts)
        restarted.recover()
        with restarted.store.connection() as c:
            remains = c.execute('SELECT 1 FROM coordinator_lanes WHERE owner_id=?', (owner,)).fetchone()
        if remains:
            result = restarted.orchestration.reconcile(job_id, owner, uid(), restarted.store.snapshot(job_id)['version'])
            assert result['status'] != 'UNKNOWN'
        with restarted.store.connection() as c:
            assert c.execute('SELECT 1 FROM coordinator_lanes WHERE job_id=?', (job_id,)).fetchone() is None
        snapshot = restarted.store.snapshot(job_id)
        assert snapshot['session']['status'] == 'READY' if stage == 'coordinate' else snapshot['prompts'][-1]['status'] == 'SUCCEEDED'
    finally:
        monkeypatch.setattr(engine.orchestration, 'release_lane', original_release)
        worker.close()


def unknown_code_claim(engine, job_id):
    analyze_and_confirm(engine, job_id)
    module_id = engine.store.snapshot(job_id)['modules'][0]['id']
    design = engine.claim(job_id, module_id, 'design', 'fixture')
    engine.finish(job_id, module_id, 'design', design['attempt']['id'], design['attempt']['token'], demo_v2_result(design))
    code = engine.claim(job_id, module_id, 'code', 'fixture')
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        stage = job['modules'][0]['stages']['code']
        stage['status'] = stage['attempts'][-1]['status'] = 'UNKNOWN'
        engine.store.save(c, job, 'FIXTURE_CRASH_DURING_REVIEW')
    return code


def store_process_state(engine, owner, state):
    intent = engine.orchestration.transport_context(owner)
    engine.orchestration.record_transport(owner, {'launch_id': intent['id'], 'intent_nonce': intent['nonce'],
        'receipt_version': 1, 'pid': 12345, 'start_id': 'old-start', 'fixture_state': state})


@pytest.mark.parametrize('review_state', ['ALIVE', 'UNKNOWN', 'INTENT', 'PID_REUSED', 'TERMINATED'])
def test_rr2_absent_parent_result_never_releases_writer_before_every_allocated_review_is_terminal(runtime, monkeypatch, review_state):
    import backend.adapters.process as process
    engine, job_id = runtime
    code = unknown_code_claim(engine, job_id)
    parent, review = code['attempt']['id'], code['attempt']['review_request']['report_id']
    store_process_state(engine, parent, 'TERMINATED')
    if review_state != 'INTENT':
        store_process_state(engine, review, review_state)
    def inspect(receipt):
        state = receipt.get('fixture_state', 'UNKNOWN')
        return receipts.ProcessVerification('UNKNOWN' if state == 'PID_REUSED' else state, {'fixture': True, 'pid_reused': state == 'PID_REUSED'})
    monkeypatch.setattr(process, 'verify_receipt', inspect)
    def forbidden_signal(*_args):
        pytest.fail('Reconciliation attempted to signal an old PID instead of checking stored identity.')
    monkeypatch.setattr(os, 'kill', forbidden_signal)
    if hasattr(os, 'killpg'):
        monkeypatch.setattr(os, 'killpg', forbidden_signal)
    assert engine.orchestration.transport_context(parent).get('result_envelope') is None
    key = uid()
    result = engine.reconcile_attempt(job_id, code['module']['id'], 'code', key, engine.store.snapshot(job_id)['version'])
    if review_state != 'TERMINATED':
        assert result['status'] == 'UNKNOWN'
        assert engine.store.snapshot(job_id)['modules'][0]['stages']['code']['status'] == 'UNKNOWN'
        with engine.store.connection() as c:
            assert c.execute('SELECT attempt FROM leases').fetchone()['attempt'] == parent
        assert engine.claim(job_id, code['module']['id'], 'code', 'second-writer') is None
        store_process_state(engine, review, 'TERMINATED')
        # An UNKNOWN inspection must not consume the idempotency key needed later.
        result = engine.reconcile_attempt(job_id, code['module']['id'], 'code', key, engine.store.snapshot(job_id)['version'])
    assert result['disposition'] == 'APPLIED'
    stage = engine.store.snapshot(job_id)['modules'][0]['stages']['code']
    assert stage['status'] == 'FAILED' and stage['result']['error_class'] == 'ENVIRONMENT'
    with engine.store.connection() as c:
        assert c.execute('SELECT count(*) FROM leases').fetchone()[0] == 0


def test_rr2_positive_never_invoked_review_branch_records_no_launch_proof_for_recovery(runtime, monkeypatch):
    import backend.adapters.process as process
    from backend.adapters.bridge import Bridge
    engine, job_id = runtime
    code = unknown_code_claim(engine, job_id)
    # Exercise the real adapter branch that knows code failed before review; a
    # missing review receipt by itself is tested as UNKNOWN in the matrix above.
    code['job']['execution'] = code['job']['profile']['execution'] = 'bridge'
    calls = []
    def failed_code(_self, profile, tool, request, timeout=None):
        calls.append(request['stage'])
        assert request['stage'] == 'code'
        return Worker._failed_envelope('Known code failure before review invocation.')
    monkeypatch.setattr(Bridge, 'invoke', failed_code)
    worker = Worker(engine, delay=0)
    try:
        worker._execute(code)
        assert calls == ['code']
        review_owner = code['attempt']['review_request']['report_id']
        proof = engine.orchestration.transport_context(review_owner)
        assert proof['status'] == 'NOT_LAUNCHED'
        assert engine.orchestration.valid_not_launched(proof)
        assert proof.get('process_receipt') is None
        store_process_state(engine, code['attempt']['id'], 'TERMINATED')
        monkeypatch.setattr(process, 'verify_receipt', lambda receipt: receipts.ProcessVerification(receipt.get('fixture_state', 'UNKNOWN'), {'fixture': True}))
        result = engine.reconcile_attempt(job_id, code['module']['id'], 'code', uid(), engine.store.snapshot(job_id)['version'])
        assert result['disposition'] == 'APPLIED'
        assert engine.store.snapshot(job_id)['modules'][0]['stages']['code']['status'] == 'FAILED'
        with engine.store.connection() as c:
            assert c.execute('SELECT count(*) FROM leases').fetchone()[0] == 0
    finally:
        worker.close()


def test_rr2_launched_review_cannot_be_relabelled_not_launched(runtime):
    engine, job_id = runtime
    code = unknown_code_claim(engine, job_id)
    owner = code['attempt']['review_request']['report_id']
    store_process_state(engine, owner, 'ALIVE')
    context = engine.orchestration.transport_context(owner)
    with pytest.raises(Conflict):
        engine.orchestration.record_not_launched(owner, {'launch_id': context['id'], 'intent_nonce': context['nonce'],
                                                       'reason': 'An existing receipt forbids this contradictory declaration.'})
    assert engine.orchestration.transport_context(owner)['process_receipt']['fixture_state'] == 'ALIVE'


def test_rr2_both_terminated_processes_replay_durable_code_and_review_once(runtime, monkeypatch):
    import backend.adapters.process as process
    engine, job_id = runtime
    code = unknown_code_claim(engine, job_id)
    envelope = demo_v2_result(code)
    # Exercise verified process recovery rather than the explicit demo-terminal shortcut.
    envelope['transport'].pop('simulation', None)
    parent = code['attempt']['id']
    review = code['attempt']['review_request']['report_id']
    engine.orchestration.record_result(parent, envelope)
    store_process_state(engine, parent, 'TERMINATED')
    store_process_state(engine, review, 'TERMINATED')
    monkeypatch.setattr(process, 'verify_receipt', lambda receipt: receipts.ProcessVerification(receipt.get('fixture_state', 'UNKNOWN'), {'fixture': True}))
    result = engine.reconcile_attempt(job_id, code['module']['id'], 'code', uid(), engine.store.snapshot(job_id)['version'])
    assert result['disposition'] == 'APPLIED'
    assert engine.store.snapshot(job_id)['modules'][0]['stages']['code']['status'] == 'SUCCEEDED'
    report_ids = {r['report_id'] for r in engine.reports.list(job_id)}
    assert code['attempt']['request']['report_id'] in report_ids and review in report_ids
    before = engine.reports.list(job_id)
    engine.recover()
    assert engine.reports.list(job_id) == before
    with engine.store.connection() as c:
        assert c.execute('SELECT count(*) FROM leases').fetchone()[0] == 0
