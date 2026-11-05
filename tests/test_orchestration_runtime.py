"""T-72..82: durable state transitions through public orchestration/intake APIs."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from threading import Barrier

import pytest

from backend.domain.engine import Engine
from backend.domain.policy import Conflict, uid
from backend.settings import Profile
from backend.storage.store import Store
from test_orchestration_contracts import role_capability_profile


@pytest.fixture
def runtime(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    (workspace / 'evidence.log').write_bytes(b'fixture evidence\n')
    engine = Engine(Store(tmp_path / 'db.sqlite'), tmp_path / 'artifacts')
    profile = Profile(workspace=str(workspace), module_report_version=2,
                      orchestration={'enabled': True}, modules=[{'name': 'BSP', 'group': 'boot'},
                      {'name': 'Independent', 'group': 'boot'}]).model_dump()
    job_id = engine.create(uid(), profile, 'v2 fixture', 'linux')['job_id']
    return engine, job_id


def analysis_claim(engine, job_id, index=0):
    module = engine.store.snapshot(job_id)['modules'][index]
    claim = engine.claim(job_id, module['id'], 'analysis', 'fixture-owner')
    assert claim is not None
    return claim


@pytest.mark.parametrize('mutation,expected', [
    ('default', ('opencode', 'claude')), ('opencode_reviewer_only', ('claude', 'codex')),
    ('claude_not_implementer', ('opencode', 'claude')), ('codex_not_reviewer', ('opencode', 'claude')),
    ('no_pair', None), ('claude_reviewer_ineligible', ('claude', 'codex')),
    ('opencode_v1_only', ('claude', 'codex')), ('codex_v1_only_fallback', None)])
def test_rr4_selection_uses_frozen_roles_versions_and_independent_review(mutation, expected):
    from backend.adapters.capabilities import freeze_capabilities
    from backend.domain.policy import implementation_tool, reviewer
    profile = role_capability_profile()
    profile['contract_capabilities'] = freeze_capabilities(profile)
    caps = profile['contract_capabilities']['tools']
    if mutation in {'opencode_reviewer_only', 'no_pair', 'codex_v1_only_fallback'}:
        caps['opencode']['roles'] = ['reviewer']
    if mutation == 'claude_not_implementer':
        caps['claude']['roles'].remove('implementer')
    if mutation in {'codex_not_reviewer', 'no_pair'}:
        caps['codex']['roles'] = ['implementer']
    if mutation == 'claude_reviewer_ineligible':
        caps['claude']['roles'].remove('reviewer')
    if mutation == 'opencode_v1_only':
        caps['opencode']['module_report_versions'] = [1]
    if mutation == 'codex_v1_only_fallback':
        caps['codex']['module_report_versions'] = [1]
    # Live declarations cannot override the frozen job snapshot.
    available = {tool: True for tool in profile['agents']}
    if expected is None:
        with pytest.raises(Conflict) as error:
            implementation_tool([], available, profile=profile)
        assert error.value.code == 'CAPABILITY_UNSUPPORTED'
    else:
        author, _ = implementation_tool([], available, profile=profile)
        selected_review = reviewer([author], available, profile=profile)
        assert (author, selected_review) == expected
        assert author != selected_review


@pytest.mark.parametrize('escalation', ['hard', 'repeated_fix'])
@pytest.mark.parametrize('codex_eligible', [False, True])
def test_rr4_escalation_requires_eligible_claude_and_codex_pair(escalation, codex_eligible):
    from backend.adapters.capabilities import freeze_capabilities
    from backend.domain.policy import implementation_tool
    profile = role_capability_profile()
    profile['contract_capabilities'] = freeze_capabilities(profile)
    if not codex_eligible:
        profile['contract_capabilities']['tools']['codex']['roles'] = ['implementer']
    attempts = [{'status': 'FAILED', 'error_class': 'FIX', 'cause_key': 'same-root'}] * 2 if escalation == 'repeated_fix' else []
    available = {tool: True for tool in profile['agents']}
    if codex_eligible:
        assert implementation_tool(attempts, available, hard=escalation == 'hard', profile=profile) == ('claude', 'opus')
    else:
        with pytest.raises(Conflict) as error:
            implementation_tool(attempts, available, hard=escalation == 'hard', profile=profile)
        assert error.value.code == 'CAPABILITY_UNSUPPORTED'


@pytest.mark.parametrize('fallback_allowed', [False, True])
def test_rr4_engine_claim_resolves_role_pair_before_allocating_execution(runtime, fallback_allowed):
    from backend.adapters.capabilities import freeze_capabilities
    from backend.worker.main import demo_v2_result
    engine, job_id = runtime
    analyze_and_confirm(engine, job_id)
    module_id = engine.store.snapshot(job_id)['modules'][0]['id']
    design = engine.claim(job_id, module_id, 'design', 'fixture')
    engine.finish(job_id, module_id, 'design', design['attempt']['id'], design['attempt']['token'], demo_v2_result(design))
    profile = role_capability_profile()
    caps = freeze_capabilities(profile)
    caps['tools']['opencode']['roles'] = ['reviewer']
    if not fallback_allowed:
        caps['tools']['codex']['roles'] = ['implementer']
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['execution'] = job['profile']['execution'] = 'bridge'
        job['profile'].update(agents=profile['agents'], runner='bridge', contract_capabilities=caps)
        engine.store.save(c, job, 'FIXTURE_FROZEN_ROLE_MATRIX')
    before = engine.store.snapshot(job_id)
    with engine.store.connection() as c:
        intents_before = c.execute('SELECT count(*) FROM launch_receipts').fetchone()[0]
    if fallback_allowed:
        claim = engine.claim(job_id, module_id, 'code', 'fixture')
        assert claim['attempt']['tool'] == 'claude'
        assert claim['attempt']['review_tool'] == 'codex'
        review = claim['attempt']['review_request']
        assert review['report_expectations']['author_tools'] == ['claude']
        assert review['session_id'] != claim['attempt']['session_id']
        assert review['report_id'] != claim['attempt']['request']['report_id']
    else:
        with pytest.raises(Conflict) as error:
            engine.claim(job_id, module_id, 'code', 'fixture')
        assert error.value.code == 'CAPABILITY_UNSUPPORTED'
        assert engine.store.snapshot(job_id) == before
        with engine.store.connection() as c:
            assert c.execute('SELECT count(*) FROM launch_receipts').fetchone()[0] == intents_before
            assert c.execute('SELECT count(*) FROM leases').fetchone()[0] == 0


def test_rr4_v1_policy_keeps_legacy_selection_without_role_negotiation():
    from backend.domain.policy import implementation_tool, reviewer
    profile = {'module_report_version': 1, 'contract_capabilities': {'tools': {}}}
    available = {'opencode': True, 'claude': True, 'codex': True}
    assert implementation_tool([], available, profile=profile) == ('opencode', 'configured')
    assert implementation_tool([], available, hard=True, profile=profile) == ('claude', 'opus')
    assert reviewer(['opencode'], available, profile=profile) == 'claude'
    assert reviewer(['claude'], available, profile=profile) == 'codex'


def analysis_envelope(claim, *, blocking=None, failed=False):
    request = claim['attempt']['request']
    wire = {key: deepcopy(request[key]) for key in ('job_id', 'module_id', 'stage', 'attempt_id', 'session_id',
            'report_id', 'plan_version', 'fingerprint', 'input_result_refs', 'source_revision')}
    digest = hashlib.sha256(b'fixture evidence\n').hexdigest()
    changes = [{'change_id': item.get('change_id', item.get('id')), 'disposition': 'already_upstream',
                'rationale': 'The new base contains the equivalent behavior.', 'affected_files': [item['path']],
                'dependency_module_ids': [], 'required_cases': []}
               for item in request['module']['vendor_changes']]
    wire.update(schema_version=2, message_type='module_result', outcome='FAILED' if failed else 'SUCCEEDED',
                evidence='See immutable fixture evidence.', error_class='ENVIRONMENT' if failed else '',
                cause_key='missing-header' if failed else '', report={'summary': 'Analysis result.',
                'details': {'vendor_changes': changes}, 'evidence_refs': [
                {'path': 'evidence.log', 'sha256': digest, 'kind': 'log'}], 'test_results': [], 'decision_requests': []})
    if blocking is not None:
        wire['report']['decision_requests'] = [{'candidate_key': 'api-choice', 'question': 'Choose API compatibility.',
              'options': ['upstream API', 'compatibility shim'], 'recommendation': 'upstream API',
              'affected_module_ids': [request['module_id']], 'affected_stages': ['design'],
              'blocking': blocking, 'evidence_paths': ['evidence.log']}]
    # This is an adapter double: private measured observations are separate from
    # the authored wire, including when a test uses the real-execution intake gate.
    observed = {'source_revision': request['source_revision'], 'before_source_revision': request['source_revision'],
                'source_identity': deepcopy(request['report_expectations']['source_identity'])}
    return {'envelope_version': 1, 'wire_result': wire, 'related_reports': [], 'observations': observed,
            'transport': {'status': 'SUCCEEDED', 'exit_code': 0}}


def commit_report(engine, claim, envelope):
    prepared = engine.reports.prepare(claim, envelope)
    assert prepared.error is None
    with engine.store.transaction() as c:
        return engine.reports.commit(c, engine.store.get(c, claim['job']['id']), prepared)


def coordinator_envelope(run, proposals=None, failed=False):
    request = run['request']
    wire = {key: deepcopy(request[key]) for key in ('job_id', 'orchestration_run_id', 'session_id', 'trigger_ids',
            'base_state_version', 'plan_version', 'fingerprint', 'result_refs')}
    wire.update(schema_version=1, message_type='orchestration_result', outcome='FAILED' if failed else 'SUCCEEDED',
                error_class='ENVIRONMENT' if failed else '', summary='Fixture coordinator result.', proposals=proposals or [])
    return {'envelope_version': 1, 'wire_result': wire, 'transport': {'status': 'SUCCEEDED'}}


def enqueue(engine, job_id, kind, event_id):
    with engine.store.transaction() as c:
        return engine.orchestration.enqueue(c, engine.store.get(c, job_id), kind, event_id)


def test_t72_queue_dedup_active_run_and_late_trigger_survive_independently(runtime):
    engine, job_id = runtime
    before = engine.store.snapshot(job_id)['version']
    first = enqueue(engine, job_id, 'JOB_STARTED', 'duplicate-start')
    assert enqueue(engine, job_id, 'JOB_STARTED', 'another-start') == first
    assert engine.store.snapshot(job_id)['version'] == before
    run = engine.orchestration.claim(job_id, 'owner-one')
    assert run is not None
    assert engine.orchestration.claim(job_id, 'owner-two') is None
    late = enqueue(engine, job_id, 'DEPENDENCY_CHANGED', 'late-event')
    assert late not in run['request']['trigger_ids']
    engine.orchestration.finish(run['id'], coordinator_envelope(run))
    next_run = engine.orchestration.claim(job_id, 'owner-two')
    assert next_run['request']['trigger_ids'] == [late]
    with engine.store.connection() as c:
        assert c.execute('SELECT status FROM orchestration_triggers WHERE id=?', (first,)).fetchone()[0] == 'CONSUMED'
        assert c.execute('SELECT status FROM orchestration_triggers WHERE id=?', (late,)).fetchone()[0] == 'ASSIGNED'


def test_t72_concurrent_coordinator_claim_has_one_winner(runtime):
    engine, job_id = runtime
    barrier = Barrier(2)
    def attempt(owner):
        barrier.wait(timeout=5)
        return engine.orchestration.claim(job_id, owner)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ['one', 'two']))
    assert sum(result is not None for result in results) == 1


def test_t73_response_audit_does_not_stale_its_own_proposal(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    commit_report(engine, claim, analysis_envelope(claim, failed=True))
    run = engine.orchestration.claim(job_id, 'coordinator')
    proposal = {'proposal_key': 'retry', 'kind': 'RETRY',
                'target': {'module_ids': [claim['module']['id']], 'stage': 'analysis'},
                'reason': 'Retry with the missing input supplied.', 'evidence_refs': run['request']['result_refs'],
                'data': {'previous_attempt_id': claim['attempt']['id'], 'cause_key': 'missing-header',
                         'changed_approach': 'Use the supplied header.'}}
    before = engine.store.snapshot(job_id)['version']
    envelope = coordinator_envelope(run, [proposal])
    engine.orchestration.finish(run['id'], envelope)
    assert engine.store.snapshot(job_id)['version'] == before
    record = engine.orchestration.summary(job_id)['proposals'][0]
    assert record['status'] == 'RECORDED'
    result = engine.orchestration.apply(job_id, record['id'], uid(), before, actor='orchestrator')
    assert result['status'] == 'WAITING_USER'
    assert engine.store.snapshot(job_id)['modules'][0]['stages']['analysis']['status'] == 'FAILED'
    assert engine.store.snapshot(job_id)['version'] == before
    # Replayed terminal coordinator response must preserve a single proposal.
    engine.orchestration.finish(run['id'], envelope)
    assert len(engine.orchestration.summary(job_id)['proposals']) == 1


def test_t74_report_replay_and_conflict_keep_first_full_report(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    envelope = analysis_envelope(claim)
    assert commit_report(engine, claim, envelope)['disposition'] == 'APPLIED'
    version = engine.store.snapshot(job_id)['version']
    assert commit_report(engine, claim, envelope)['disposition'] == 'REPLAY'
    conflicting = deepcopy(envelope)
    conflicting['wire_result']['report']['summary'] = 'Different facts under the same report ID.'
    assert commit_report(engine, claim, conflicting)['disposition'] == 'CONFLICT'
    assert engine.store.snapshot(job_id)['version'] == version
    reports = engine.reports.list(job_id)
    assert len(reports) == 1
    detail = engine.reports.detail(job_id, reports[0]['report_id'])
    assert detail['data']['wire_result']['report']['summary'] == envelope['wire_result']['report']['summary']
    with engine.store.connection() as c:
        receipts = c.execute('SELECT disposition,data FROM report_receipts ORDER BY rowid').fetchall()
    assert [row[0] for row in receipts] == ['APPLIED', 'REPLAY', 'CONFLICT']
    assert json.loads(receipts[-1][1])['wire_result'] == conflicting['wire_result']


@pytest.mark.parametrize('blocking', [True, False])
def test_t79_valid_analysis_keeps_facts_and_holds_only_reported_downstream_scope(runtime, blocking):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    commit_report(engine, claim, analysis_envelope(claim, blocking=blocking))
    snapshot = engine.store.snapshot(job_id)
    assert snapshot['modules'][0]['stages']['analysis']['status'] == 'SUCCEEDED'
    summary = engine.orchestration.summary(job_id)
    assert len(summary['candidates']) == 1
    assert len(snapshot['scope_holds']) == int(blocking)
    if blocking:
        assert snapshot['scope_holds'][0]['module_ids'] == [claim['module']['id']]
        assert snapshot['scope_holds'][0]['stages'] == ['design']
    assert analysis_claim(engine, job_id, 1)
    with engine.store.connection() as c:
        persisted = json.loads(c.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()[0])
    assert 'scope_holds' not in persisted


def test_t77_t79_stale_analysis_preserves_history_without_current_holds(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    prepared = engine.reports.prepare(claim, analysis_envelope(claim, blocking=True))
    assert prepared.error is None
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['fingerprint'] = 'changed-input'
        engine.store.save(c, job, 'SOURCE_CHANGED')
    with engine.store.transaction() as c:
        outcome = engine.reports.commit(c, engine.store.get(c, job_id), prepared)
    assert outcome['disposition'] == 'STALE'
    assert engine.reports.list(job_id)[0]['disposition'] == 'STALE'
    assert engine.orchestration.summary(job_id)['candidates'] == []
    assert engine.store.snapshot(job_id)['scope_holds'] == []
    assert engine.store.snapshot(job_id)['modules'][0]['stages']['analysis']['status'] != 'SUCCEEDED'


def test_t81_coordinator_failure_does_not_cancel_independent_module_intake(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id, 1)
    run = engine.orchestration.claim(job_id, 'coordinator')
    engine.orchestration.finish(run['id'], coordinator_envelope(run, failed=True))
    commit_report(engine, claim, analysis_envelope(claim))
    assert engine.store.snapshot(job_id)['modules'][1]['stages']['analysis']['status'] == 'SUCCEEDED'
    assert engine.orchestration.summary(job_id)['runs'][0]['status'] == 'FAILED'


def test_t81_max_calls_counts_unknown_run_and_retains_queued_work(runtime):
    engine, job_id = runtime
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['profile']['orchestration']['max_calls'] = 1
        engine.store.save(c, job, 'FIXTURE_BUDGET')
    run = engine.orchestration.claim(job_id, 'one')
    engine.orchestration.finish(run['id'], {'envelope_version': 1, 'wire_result': None,
                                          'transport': {'status': 'UNKNOWN', 'error': 'Unverified process state.'}})
    pending = enqueue(engine, job_id, 'USER_REPLAN_REQUESTED', 'user-request')
    assert engine.orchestration.claim(job_id, 'two') is None
    with engine.store.connection() as c:
        assert c.execute('SELECT status FROM orchestration_triggers WHERE id=?', (pending,)).fetchone()[0] == 'PENDING'
    # A known terminal failure also consumes the configured total call allowance.
    engine.orchestration.finish(run['id'], coordinator_envelope(run, failed=True))
    assert engine.orchestration.claim(job_id, 'three') is None


@pytest.mark.parametrize('budget', ['max_calls', 'max_stale_replans'])
def test_t81_coordinator_budget_exhaustion_preserves_pass_and_independent_intake(runtime, budget):
    engine, job_id = runtime
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['profile']['orchestration'][budget] = 1 if budget == 'max_calls' else 0
        engine.store.save(c, job, 'FIXTURE_COORDINATOR_BUDGET')
    passed = analysis_claim(engine, job_id, 0)
    commit_report(engine, passed, analysis_envelope(passed))
    independent = analysis_claim(engine, job_id, 1)
    run = engine.orchestration.claim(job_id, 'first-coordinator')
    engine.orchestration.finish(run['id'], coordinator_envelope(run, failed=True))
    with engine.store.transaction() as c:
        root = c.execute('SELECT root_id FROM orchestration_runs WHERE id=?', (run['id'],)).fetchone()[0]
        pending = engine.orchestration.enqueue(c, engine.store.get(c, job_id), 'USER_REPLAN_REQUESTED',
                                               'same-root-budget-check', {'root_id': root})
    before = engine.store.snapshot(job_id)
    assert engine.orchestration.claim(job_id, 'over-budget') is None
    assert engine.store.snapshot(job_id) == before
    with engine.store.connection() as c:
        assert c.execute('SELECT status FROM orchestration_triggers WHERE id=?', (pending,)).fetchone()[0] == 'PENDING'
        assert c.execute('SELECT count(*) FROM orchestration_runs WHERE job_id=?', (job_id,)).fetchone()[0] == 1
    commit_report(engine, independent, analysis_envelope(independent))
    snapshot = engine.store.snapshot(job_id)
    assert snapshot['modules'][0]['stages']['analysis'] == before['modules'][0]['stages']['analysis']
    assert snapshot['modules'][1]['stages']['analysis']['status'] == 'SUCCEEDED'


def test_t72_coordinator_snapshot_does_not_export_execution_tokens(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    run = engine.orchestration.claim(job_id, 'coordinator')
    raw = json.dumps(run['request'])
    assert claim['attempt']['token'] not in raw
    assert 'fixture-owner' not in raw


def action(engine, job_id, name, data):
    return engine.act(job_id, uid(), engine.store.snapshot(job_id)['version'], name, data)


def analyze_and_confirm(engine, job_id):
    for index in range(len(engine.store.snapshot(job_id)['modules'])):
        claim = analysis_claim(engine, job_id, index)
        commit_report(engine, claim, analysis_envelope(claim))
    action(engine, job_id, 'confirm', {'plan_version': engine.store.snapshot(job_id)['plan_version']})


def proposal(engine, job_id, kind, module_ids, stage, data, *, evidence=None, key=None):
    enqueue(engine, job_id, 'USER_REPLAN_REQUESTED', uid())
    run = engine.orchestration.claim(job_id, 'fixture-coordinator')
    assert run is not None
    wire = {'proposal_key': key or uid(), 'kind': kind, 'target': {'module_ids': module_ids, 'stage': stage},
            'reason': 'Fixture proposal justified by stored facts.',
            'evidence_refs': run['request']['result_refs'] if evidence is None else evidence, 'data': data}
    engine.orchestration.finish(run['id'], coordinator_envelope(run, [wire]))
    saved = [p for p in engine.orchestration.summary(job_id)['proposals'] if p['run_id'] == run['id']]
    assert len(saved) == 1, engine.orchestration.summary(job_id)['runs'][-1]
    return saved[0]


def apply(engine, job_id, saved, actor='human', key=None):
    return engine.orchestration.apply(job_id, saved['id'], key or uid(),
                                      engine.store.snapshot(job_id)['version'], actor)


def plan_view(module):
    return {key: deepcopy(module[key]) for key in ('name', 'stable_key', 'group', 'target_paths',
            'dependency_module_ids', 'required_cases', 'completion_conditions')}


def plan_update(module, **updates):
    before = plan_view(module)
    return {'operation': 'update', 'module_id': module['id'], 'new_module_key': None,
            'before': before, 'after': before | updates, 'reason': 'Preserve module identity while revising scope.'}


@pytest.mark.parametrize('invalid', ['before', 'cycle', 'unknown_dependency', 'duplicate_stable_key', 'active_unknown'])
def test_t75_invalid_plan_is_rejected_without_losing_modules_or_history(runtime, invalid):
    engine, job_id = runtime
    modules = engine.store.snapshot(job_id)['modules']
    change = plan_update(modules[0], name='Renamed BSP')
    if invalid == 'before':
        change['before']['name'] = 'incorrect before image'
    elif invalid == 'cycle':
        change['after']['dependency_module_ids'] = [modules[0]['id']]
    elif invalid == 'unknown_dependency':
        change['after']['dependency_module_ids'] = ['missing-module']
    elif invalid == 'duplicate_stable_key':
        change = {'operation': 'add', 'module_id': None, 'new_module_key': 'new', 'before': None,
                  'after': plan_view(modules[0]), 'reason': 'Duplicate key must fail.'}
    else:
        claim = analysis_claim(engine, job_id)
        engine.finish(job_id, claim['module']['id'], 'analysis', claim['attempt']['id'], claim['attempt']['token'],
                      {'envelope_version': 1, 'wire_result': None, 'transport': {'status': 'UNKNOWN'}})
    saved = proposal(engine, job_id, 'PLAN_CHANGE', [modules[0]['id']], None,
                     {'base_plan_version': 1, 'changes': [change]})
    before = engine.store.snapshot(job_id)
    assert apply(engine, job_id, saved)['status'] == 'BLOCKED'
    after = engine.store.snapshot(job_id)
    assert after['modules'] == before['modules']
    assert after['plan_version'] == before['plan_version']
    assert after['version'] == before['version']


def test_t75_plan_rename_keeps_ids_history_and_approved_scope(runtime):
    engine, job_id = runtime
    analyze_and_confirm(engine, job_id)
    before = engine.store.snapshot(job_id)
    module = before['modules'][0]
    saved = proposal(engine, job_id, 'PLAN_CHANGE', [module['id']], None,
                     {'base_plan_version': 1, 'changes': [plan_update(module, name='BSP renamed')]})
    assert apply(engine, job_id, saved, actor='orchestrator')['status'] == 'APPLIED'
    after = engine.store.snapshot(job_id)
    assert after['modules'][0]['id'] == module['id']
    assert after['modules'][0]['stable_key'] == module['stable_key']
    assert after['modules'][0]['name'] == 'BSP renamed'
    assert after['modules'][0]['stages']['analysis']['attempts'] == module['stages']['analysis']['attempts']
    assert after['confirmed_plan'] == after['plan_version'] == 2
    assert after['plan_history'][0]['modules'][0]['name'] == module['name']


def test_t75_new_scope_waits_for_human_then_requires_fresh_analysis_and_one_confirmation(runtime):
    engine, job_id = runtime
    analyze_and_confirm(engine, job_id)
    module = engine.store.snapshot(job_id)['modules'][0]
    saved = proposal(engine, job_id, 'PLAN_CHANGE', [module['id']], None,
                     {'base_plan_version': 1, 'changes': [plan_update(module, target_paths=['drivers/new'])]})
    assert apply(engine, job_id, saved, actor='orchestrator')['status'] == 'WAITING_USER'
    assert engine.store.snapshot(job_id)['confirmed_plan'] == 1
    assert apply(engine, job_id, saved)['status'] == 'APPLIED'
    changed = engine.store.snapshot(job_id)
    assert changed['modules'][0]['id'] == module['id']
    assert changed['confirmed_plan'] is None
    assert changed['modules'][0]['stages']['analysis']['status'] == 'PENDING'
    with pytest.raises(Conflict):
        action(engine, job_id, 'confirm', {'plan_version': 2})
    claim = analysis_claim(engine, job_id)
    commit_report(engine, claim, analysis_envelope(claim))
    action(engine, job_id, 'confirm', {'plan_version': 2})
    assert engine.claim(job_id, module['id'], 'design', 'fixture') is not None


def test_t75_plan_add_and_deactivate_preserve_original_id_and_attempt_history(runtime):
    engine, job_id = runtime
    analyze_and_confirm(engine, job_id)
    old = engine.store.snapshot(job_id)['modules'][0]
    new = {'name': 'New driver', 'stable_key': 'new-driver', 'group': 'main', 'target_paths': ['new'],
           'dependency_module_ids': [], 'required_cases': [], 'completion_conditions': ['Required cases pass.']}
    changes = [{'operation': 'add', 'module_id': None, 'new_module_key': 'new-driver', 'before': None,
                'after': new, 'reason': 'New vendor scope.'},
               {'operation': 'deactivate', 'module_id': old['id'], 'new_module_key': None,
                'before': plan_view(old), 'after': None, 'reason': 'Replaced scope; retain history.'}]
    saved = proposal(engine, job_id, 'PLAN_CHANGE', [old['id']], None, {'base_plan_version': 1, 'changes': changes})
    assert apply(engine, job_id, saved)['status'] == 'APPLIED'
    modules = engine.store.snapshot(job_id)['modules']
    assert modules[0]['id'] == old['id'] and modules[0]['active'] is False
    assert modules[0]['stages']['analysis']['attempts'] == old['stages']['analysis']['attempts']
    added = next(m for m in modules if m['stable_key'] == 'new-driver')
    assert added['id'] not in {m['id'] for m in modules[:-1]}
    assert added['stages']['analysis']['status'] == 'PENDING'


@pytest.mark.parametrize('failure_count,error_class,hard,expected', [
    (1, 'FIX', False, 'BLOCKED'), (2, 'FIX', False, 'APPLIED'),
    (2, 'ENVIRONMENT', False, 'BLOCKED'), (1, 'FIX', True, 'APPLIED')])
def test_t76_escalation_requires_actual_same_cause_fix_or_owned_difficulty(runtime, failure_count, error_class, hard, expected):
    from backend.worker.main import demo_v2_result
    engine, job_id = runtime
    analyze_and_confirm(engine, job_id)
    module_id = engine.store.snapshot(job_id)['modules'][0]['id']
    design = engine.claim(job_id, module_id, 'design', 'fixture')
    engine.finish(job_id, module_id, 'design', design['attempt']['id'], design['attempt']['token'], demo_v2_result(design))
    for ordinal in range(failure_count):
        code = engine.claim(job_id, module_id, 'code', 'fixture')
        assert code is not None
        envelope = demo_v2_result(code)
        envelope['wire_result'].update(outcome='FAILED', error_class=error_class, cause_key='api-mismatch')
        envelope['related_reports'] = []
        if hard:
            envelope['wire_result']['report']['details']['difficulty_evidence'] = {
                'reason': 'Conflicting ABI requirements demonstrated in this diff.',
                'evidence_paths': [envelope['wire_result']['report']['evidence_refs'][0]['path']]}
        engine.finish(job_id, module_id, 'code', code['attempt']['id'], code['attempt']['token'], envelope)
        if ordinal + 1 < failure_count:
            action(engine, job_id, 'retry', {'module_id': module_id, 'stage': 'code', 'previous_attempt_id': code['attempt']['id']})
    saved = proposal(engine, job_id, 'TOOL_ESCALATION', [module_id], 'code', {
        'previous_attempt_id': code['attempt']['id'], 'cause_key': 'api-mismatch', 'requested_tool': 'claude',
        'model_policy': 'opus', 'evidence': 'Use stored FIX history and owned report proof.'})
    assert apply(engine, job_id, saved, actor='orchestrator')['status'] == expected
    stage = engine.store.snapshot(job_id)['modules'][0]['stages']['code']
    assert len(stage['attempts']) == failure_count
    assert stage['status'] == 'FAILED'  # Accepting escalation cannot itself launch a process.
    if expected == 'APPLIED':
        assert stage['tool_escalation']['model'] == 'opus'


@pytest.mark.parametrize('problem', ['wrong_attempt', 'wrong_cause', 'unknown', 'lease'])
def test_t76_retry_requires_latest_terminal_attempt_cause_and_released_lease(runtime, problem):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    commit_report(engine, claim, analysis_envelope(claim, failed=True))
    if problem in {'unknown', 'lease'}:
        with engine.store.transaction() as c:
            job = engine.store.get(c, job_id)
            stage = job['modules'][0]['stages']['analysis']
            if problem == 'unknown':
                stage['status'] = stage['attempts'][-1]['status'] = 'UNKNOWN'
            else:
                c.execute('INSERT INTO leases VALUES(?,?,?)', ('fixture-resource', claim['attempt']['id'], 'fixture-token'))
            engine.store.save(c, job, 'FIXTURE_RETRY_BOUNDARY')
    saved = proposal(engine, job_id, 'RETRY', [claim['module']['id']], 'analysis', {
        'previous_attempt_id': 'wrong' if problem == 'wrong_attempt' else claim['attempt']['id'],
        'cause_key': 'wrong' if problem == 'wrong_cause' else 'missing-header', 'changed_approach': 'Use verified input.'})
    before = engine.store.snapshot(job_id)
    assert apply(engine, job_id, saved)['status'] == 'BLOCKED'
    assert engine.store.snapshot(job_id)['modules'] == before['modules']


def test_t74_human_retry_is_idempotent_and_first_effective_proposal_stales_rest(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    commit_report(engine, claim, analysis_envelope(claim, failed=True))
    run = engine.orchestration.claim(job_id, 'fixture-coordinator')
    first_proposal = {'proposal_key': 'first-retry', 'kind': 'RETRY',
        'target': {'module_ids': [claim['module']['id']], 'stage': 'analysis'},
        'reason': 'Retry with supplied input.', 'evidence_refs': run['request']['result_refs'],
        'data': {'previous_attempt_id': claim['attempt']['id'], 'cause_key': 'missing-header',
                 'changed_approach': 'Use supplied header.'}}
    second_proposal = deepcopy(first_proposal)
    second_proposal['proposal_key'] = 'second-retry'
    engine.orchestration.finish(run['id'], coordinator_envelope(run, [first_proposal, second_proposal]))
    records = engine.orchestration.summary(job_id)['proposals']
    saved = next(p for p in records if p['proposal_key'] == 'first-retry')
    other = next(p for p in records if p['proposal_key'] == 'second-retry')
    version = engine.store.snapshot(job_id)['version']
    command_id = uid()
    first = engine.orchestration.apply(job_id, saved['id'], command_id, version)
    assert first['status'] == 'APPLIED'
    assert engine.orchestration.apply(job_id, saved['id'], command_id, version) == first
    snapshot = engine.store.snapshot(job_id)
    assert snapshot['modules'][0]['stages']['analysis']['status'] == 'PENDING'
    assert len(snapshot['modules'][0]['stages']['analysis']['attempts']) == 1
    # A second stored proposal sharing the original snapshot must recheck the mutation.
    assert apply(engine, job_id, other)['status'] == 'STALE'


def retry_proposal_fixture(engine, job_id):
    claim = analysis_claim(engine, job_id)
    commit_report(engine, claim, analysis_envelope(claim, failed=True))
    run = engine.orchestration.claim(job_id, 'fixture-coordinator')
    wire = {'proposal_key': 'stable-retry', 'kind': 'RETRY',
            'target': {'module_ids': [claim['module']['id']], 'stage': 'analysis'},
            'reason': 'Retry with verified missing input.', 'evidence_refs': run['request']['result_refs'],
            'data': {'previous_attempt_id': claim['attempt']['id'], 'cause_key': 'missing-header',
                     'changed_approach': 'Use the supplied header.'}}
    return claim, run, wire


def test_t74_same_proposal_key_replays_identical_response_and_rejects_changed_content_after_restart(runtime):
    engine, job_id = runtime
    _, run, wire = retry_proposal_fixture(engine, job_id)
    envelope = coordinator_envelope(run, [wire])
    first = engine.orchestration.finish(run['id'], envelope)
    saved = engine.orchestration.summary(job_id)['proposals'][0]
    before = engine.store.snapshot(job_id)
    restarted = Engine(Store(engine.store.path), engine.artifacts)
    assert restarted.orchestration.finish(run['id'], envelope) == first
    changed = deepcopy(envelope)
    changed['wire_result']['proposals'][0]['data']['changed_approach'] = 'Use a different source inventory.'
    with pytest.raises(Conflict) as error:
        restarted.orchestration.finish(run['id'], changed)
    assert error.value.code == 'IDEMPOTENCY_CONFLICT'
    assert restarted.orchestration.summary(job_id)['proposals'] == [saved]
    assert restarted.store.snapshot(job_id) == before
    with restarted.store.connection() as c:
        assert c.execute('SELECT count(*) FROM commands WHERE key=?', (saved['command_id'],)).fetchone()[0] == 0


@pytest.mark.parametrize('crash_boundary', ['before_commit', 'after_commit_before_response'])
def test_t74_proposal_command_restart_replays_one_effect_across_commit_boundary(runtime, monkeypatch, crash_boundary):
    engine, job_id = runtime
    _, run, wire = retry_proposal_fixture(engine, job_id)
    engine.orchestration.finish(run['id'], coordinator_envelope(run, [wire]))
    saved = engine.orchestration.summary(job_id)['proposals'][0]
    before = engine.store.snapshot(job_id)
    command_key, version = saved['command_id'], before['version']
    with monkeypatch.context() as fault:
        if crash_boundary == 'before_commit':
            original_transaction = engine.store.transaction
            @contextmanager
            def interrupted_transaction():
                with original_transaction() as c:
                    yield c
                    raise RuntimeError('Injected loss before transaction commit.')
            fault.setattr(engine.store, 'transaction', interrupted_transaction)
        else:
            original_command = engine.command
            def lost_response(*args, **kwargs):
                original_command(*args, **kwargs)
                raise RuntimeError('Injected loss after command commit before response.')
            fault.setattr(engine, 'command', lost_response)
        with pytest.raises(RuntimeError, match='Injected loss'):
            engine.orchestration.apply(job_id, saved['id'], command_key, version)
    restarted = Engine(Store(engine.store.path), engine.artifacts)
    with restarted.store.connection() as c:
        count = c.execute('SELECT count(*) FROM commands WHERE key=?', (command_key,)).fetchone()[0]
    assert count == (0 if crash_boundary == 'before_commit' else 1)
    if crash_boundary == 'before_commit':
        assert restarted.store.snapshot(job_id) == before
        assert restarted.orchestration.summary(job_id)['proposals'][0]['status'] == 'RECORDED'
    result = restarted.orchestration.apply(job_id, saved['id'], command_key, version)
    assert result['status'] == 'APPLIED'
    after = restarted.store.snapshot(job_id)
    assert after['version'] == version + 1
    stage = after['modules'][0]['stages']['analysis']
    assert stage['status'] == 'PENDING' and len(stage['attempts']) == 1
    events = restarted.store.events(job_id)
    replayed = Engine(Store(engine.store.path), engine.artifacts)
    assert replayed.orchestration.apply(job_id, saved['id'], command_key, version) == result
    assert replayed.store.snapshot(job_id) == after
    assert replayed.store.events(job_id) == events
    assert len([event for event in events if event['type'] == 'PROPOSAL_RETRY']) == 1


@pytest.mark.parametrize('boundary', ['response_intake', 'proposal_application'])
@pytest.mark.parametrize('basis', ['state_version', 'plan_version', 'source_fingerprint'])
def test_t73_changed_snapshot_basis_stales_proposals_without_execution_effects(runtime, boundary, basis):
    engine, job_id = runtime
    _, run, wire = retry_proposal_fixture(engine, job_id)
    envelope = coordinator_envelope(run, [wire])
    if boundary == 'proposal_application':
        engine.orchestration.finish(run['id'], envelope)
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        if basis == 'state_version':
            engine.store.save(c, job, 'FIXTURE_CONCURRENT_STATE')
        else:
            # Isolate the plan/fingerprint check from the execution version check.
            if basis == 'plan_version':
                job['plan_version'] += 1
            else:
                job['fingerprint'] = 'changed-source-inventory'
            engine.store.audit(c, job, 'FIXTURE_CONCURRENT_BASIS')
    before = engine.store.snapshot(job_id)
    if boundary == 'response_intake':
        result = engine.orchestration.finish(run['id'], envelope)
        assert result['status'] == 'SUCCEEDED' and result['error_class'] == ''
        assert engine.orchestration.summary(job_id)['proposals'][0]['status'] == 'STALE'
    else:
        saved = engine.orchestration.summary(job_id)['proposals'][0]
        assert apply(engine, job_id, saved)['status'] == 'STALE'
    assert engine.store.snapshot(job_id) == before
    with engine.store.connection() as c:
        assert c.execute("SELECT count(*) FROM orchestration_triggers WHERE job_id=? AND status='PENDING' AND type='PLAN_OR_SOURCE_CHANGED'", (job_id,)).fetchone()[0] == 1


@pytest.mark.parametrize('evidence_problem', ['substituted_response_hash', 'evidence_unavailable_at_apply'])
def test_t73_evidence_basis_is_revalidated_without_mutating_execution(runtime, evidence_problem):
    engine, job_id = runtime
    _, run, wire = retry_proposal_fixture(engine, job_id)
    envelope = coordinator_envelope(run, [wire])
    before = engine.store.snapshot(job_id)
    if evidence_problem == 'substituted_response_hash':
        envelope['wire_result']['proposals'][0]['evidence_refs'][0]['sha256'] = 'f' * 64
        result = engine.orchestration.finish(run['id'], envelope)
        assert result['status'] == 'FAILED' and result['error_class'] == 'CONTRACT'
        assert engine.orchestration.summary(job_id)['proposals'] == []
    else:
        engine.orchestration.finish(run['id'], envelope)
        saved = engine.orchestration.summary(job_id)['proposals'][0]
        with engine.store.transaction() as c:
            c.execute('DELETE FROM agent_reports WHERE report_id=?', (wire['evidence_refs'][0]['report_id'],))
        assert apply(engine, job_id, saved)['status'] == 'REJECTED'
    assert engine.store.snapshot(job_id) == before


@pytest.mark.parametrize('invalid', ['candidate', 'evidence', 'impact'])
def test_t80_decision_requires_owned_candidate_evidence_and_full_impact(runtime, invalid):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    commit_report(engine, claim, analysis_envelope(claim, blocking=True))
    candidate = engine.orchestration.summary(job_id)['candidates'][0]
    saved = proposal(engine, job_id, 'DECISION', [claim['module']['id']], 'design', {
        'candidate_ids': ['foreign-candidate' if invalid == 'candidate' else candidate['id']],
        'question': candidate['question'], 'options': candidate['options'], 'recommendation': candidate['recommendation'],
        'affected_stages': ['code'] if invalid == 'impact' else ['design'], 'blocking': True},
        evidence=[] if invalid == 'evidence' else None)
    assert apply(engine, job_id, saved)['status'] == 'BLOCKED'
    assert engine.store.snapshot(job_id)['decisions'] == []
    assert len(engine.store.snapshot(job_id)['scope_holds']) == 1


@pytest.mark.parametrize('execution', ['demo', 'bridge'])
def test_t80_decision_reuses_link_and_only_applied_evidence_releases_hold(runtime, execution):
    engine, job_id = runtime
    if execution == 'bridge':
        with engine.store.transaction() as c:
            job = engine.store.get(c, job_id)
            job['execution'] = job['profile']['execution'] = 'bridge'
            from backend.adapters.capabilities import freeze_capabilities
            bridge_profile = role_capability_profile()
            job['profile'].update(runner='bridge', agents=bridge_profile['agents'],
                                  build_argv=bridge_profile['build_argv'],
                                  contract_capabilities=freeze_capabilities(bridge_profile))
            job['session']['status'] = 'READY'
            job['profile']['jira_url'] = 'https://fixture.invalid'
            engine.store.save(c, job, 'FIXTURE_JIRA_INTENT_ONLY')
    claim = analysis_claim(engine, job_id)
    commit_report(engine, claim, analysis_envelope(claim, blocking=True))
    candidate = engine.orchestration.summary(job_id)['candidates'][0]
    data = {'candidate_ids': [candidate['id']], 'question': candidate['question'], 'options': candidate['options'],
            'recommendation': candidate['recommendation'], 'affected_stages': ['design'], 'blocking': True}
    for _ in range(2):
        saved = proposal(engine, job_id, 'DECISION', [claim['module']['id']], 'design', data)
        assert apply(engine, job_id, saved)['status'] == 'APPLIED'
    snapshot = engine.store.snapshot(job_id)
    assert len(snapshot['decisions']) == 1
    decision = snapshot['decisions'][0]
    assert decision['status'] == 'OPEN' and decision['resolution'] is None
    assert decision['sync_status'] == ('QUEUED' if execution == 'bridge' else 'NOT_CONFIGURED')
    assert len(snapshot['scope_holds']) == 1
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['decisions'][0].update(jira_status='Done', sync_status='SYNCED', jira_key='FIXTURE-1')
        engine.store.audit(c, job, 'JIRA_REMOTE_DONE')
    assert len(engine.store.snapshot(job_id)['scope_holds']) == 1
    action(engine, job_id, 'resolve', {'decision_id': decision['id'], 'resolution': 'Use upstream API.'})
    assert len(engine.store.snapshot(job_id)['scope_holds']) == 1
    with pytest.raises(Conflict):
        action(engine, job_id, 'apply-decision', {'decision_id': decision['id'], 'source_revision': 'wrong', 'evidence': 'not current'})
    action(engine, job_id, 'apply-decision', {'decision_id': decision['id'], 'source_revision': snapshot['source_revision'],
                                           'evidence': 'Applied and verified compatibility against current source.'})
    assert engine.store.snapshot(job_id)['scope_holds'] == []
    hold = engine.orchestration.summary(job_id)['holds'][0]
    assert hold['status'] == 'RELEASED' and hold['release_source'] == 'decision-applied-verified'


@pytest.mark.parametrize('scenario,expected', [('addition', 'APPLIED'), ('removal', 'WAITING_USER'),
                                               ('source', 'BLOCKED'), ('image', 'BLOCKED')])
def test_t78_verification_plan_uses_current_source_image_and_invalidates_results(runtime, scenario, expected):
    engine, job_id = runtime
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        module = job['modules'][0]
        module['stages']['build']['result'] = {'artifact': {'id': 'fixture.bin', 'sha256': 'a' * 64}}
        module['stages']['verification'].update(status='SUCCEEDED', validity='CURRENT', required_cases=['boot'])
        module['stages']['device_test'].update(status='SUCCEEDED', validity='CURRENT')
        job['integration']['status'] = 'SUCCEEDED'
        job['final_review'] = {'reviewer': 'human', 'evidence': 'Old review.'}
        engine.store.save(c, job, 'FIXTURE_VERIFICATION_HISTORY')
    snapshot = engine.store.snapshot(job_id)
    module = snapshot['modules'][0]
    cases = [{'case_id': case, 'method': 'Registered fixture test.', 'expected_result': 'Ready.'}
             for case in (['extra'] if scenario == 'removal' else ['boot', 'extra'])]
    saved = proposal(engine, job_id, 'VERIFICATION_PLAN', [module['id']], 'verification', {
        'source_revision': 'wrong' if scenario == 'source' else snapshot['source_revision'],
        'artifact': {'path': 'fixture.bin', 'sha256': ('b' if scenario == 'image' else 'a') * 64}, 'cases': cases})
    assert apply(engine, job_id, saved)['status'] == expected
    after = engine.store.snapshot(job_id)
    if expected == 'APPLIED':
        for name in ('verification', 'device_test'):
            assert after['modules'][0]['stages'][name]['status'] == 'PENDING'
            assert after['modules'][0]['stages'][name]['validity'] == 'INVALIDATED'
        assert after['modules'][0]['stages']['verification']['required_cases'] == ['boot', 'extra']
        assert after['integration']['status'] == 'PENDING' and after['final_review'] is None
    else:
        assert after['modules'] == snapshot['modules']
        assert after['final_review'] == snapshot['final_review']


def test_t73_stale_replanning_budget_remains_on_original_root_across_new_run_ids(runtime):
    engine, job_id = runtime
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['profile']['orchestration']['max_stale_replans'] = 1
        engine.store.save(c, job, 'FIXTURE_STALE_BUDGET')
    roots, runs = [], []
    for _ in range(2):
        run = engine.orchestration.claim(job_id, 'coordinator')
        assert run is not None
        runs.append(run['id'])
        with engine.store.transaction() as c:
            roots.append(c.execute('SELECT root_id FROM orchestration_runs WHERE id=?', (run['id'],)).fetchone()[0])
            job = engine.store.get(c, job_id)
            job['fingerprint'] = uid()
            engine.store.save(c, job, 'CONCURRENT_SOURCE_CHANGE')
        engine.orchestration.finish(run['id'], coordinator_envelope(run))
    assert len(set(runs)) == 2 and len(set(roots)) == 1
    assert engine.orchestration.claim(job_id, 'third-run') is None
    with engine.store.connection() as c:
        assert c.execute("SELECT count(*) FROM orchestration_triggers WHERE status='PENDING' AND root_id=?", (roots[0],)).fetchone()[0] == 1


@pytest.mark.parametrize('damage', ['escape', 'hash', 'symlink_guard'])
def test_t78_report_intake_rejects_escaping_hash_mismatch_and_linked_evidence(runtime, monkeypatch, damage):
    from pathlib import Path
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    envelope = analysis_envelope(claim)
    reference = envelope['wire_result']['report']['evidence_refs'][0]
    if damage == 'escape':
        outside = Path(claim['job']['profile']['workspace']).parent / 'outside.log'
        outside.write_bytes(b'fixture evidence\n')
        reference['path'] = '../outside.log'
    elif damage == 'hash':
        reference['sha256'] = 'f' * 64
    else:
        original = Path.is_symlink
        monkeypatch.setattr(Path, 'is_symlink', lambda path: path.name == 'evidence.log' or original(path))
    prepared = engine.reports.prepare(claim, envelope)
    assert prepared.error
    with engine.store.transaction() as c:
        engine.reports.commit(c, engine.store.get(c, job_id), prepared)
    stage = engine.store.snapshot(job_id)['modules'][0]['stages']['analysis']
    assert stage['status'] == 'FAILED' and stage['result']['error_class'] == 'CONTRACT'
    assert engine.store.snapshot(job_id)['scope_holds'] == []


@pytest.mark.skipif(__import__('os').name != 'posix', reason='Actual POSIX file/directory symlink fixture; guard is also tested portably')
@pytest.mark.parametrize('directory_link', [False, True])
def test_t78_actual_in_workspace_symlinks_cannot_be_imported_as_immutable_evidence(runtime, directory_link):
    from pathlib import Path
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    root = Path(claim['job']['profile']['workspace'])
    envelope = analysis_envelope(claim)
    if directory_link:
        (root / 'linked').symlink_to(root, target_is_directory=True)
        path = 'linked/evidence.log'
    else:
        (root / 'linked.log').symlink_to(root / 'evidence.log')
        path = 'linked.log'
    envelope['wire_result']['report']['evidence_refs'][0]['path'] = path
    assert engine.reports.prepare(claim, envelope).error


def test_t82_durable_terminal_result_replay_is_idempotent_and_conflicts_do_not_overwrite(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    envelope = analysis_envelope(claim)
    owner = claim['attempt']['id']
    engine.orchestration.record_result(owner, envelope)
    engine.orchestration.record_result(owner, deepcopy(envelope))
    before = engine.orchestration.transport_context(owner)
    changed = deepcopy(envelope)
    changed['wire_result']['report']['summary'] = 'Conflicting terminal facts.'
    with pytest.raises(Conflict):
        engine.orchestration.record_result(owner, changed)
    after = engine.orchestration.transport_context(owner)
    assert after['result_envelope'] == before['result_envelope']
    assert after['result_sha256'] == before['result_sha256']


def test_t79_blocking_candidate_and_next_stage_claim_are_atomic(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    prepared = engine.reports.prepare(claim, analysis_envelope(claim, blocking=True))
    assert prepared.error is None
    # Reanalysis of an approved plan: only the active analysis and its newly
    # received design hold stand between the competing claim and dispatch.
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['confirmed_plan'] = 1
        engine.store.save(c, job, 'FIXTURE_PREVIOUSLY_APPROVED_PLAN')
    barrier = Barrier(2)
    def accept():
        barrier.wait(timeout=5)
        with engine.store.transaction() as c:
            return engine.reports.commit(c, engine.store.get(c, job_id), prepared)
    def dispatch():
        barrier.wait(timeout=5)
        return engine.claim(job_id, claim['module']['id'], 'design', 'competing-worker')
    with ThreadPoolExecutor(max_workers=2) as pool:
        accepted, dispatched = pool.submit(accept), pool.submit(dispatch)
        assert accepted.result(timeout=10)['disposition'] == 'APPLIED'
        assert dispatched.result(timeout=10) is None
    snapshot = engine.store.snapshot(job_id)
    assert snapshot['modules'][0]['stages']['analysis']['status'] == 'SUCCEEDED'
    assert snapshot['modules'][0]['stages']['design']['attempts'] == []
    assert len(snapshot['scope_holds']) == 1


def test_t79_candidate_hold_trigger_and_report_roll_back_together_on_commit_failure(runtime, monkeypatch):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    prepared = engine.reports.prepare(claim, analysis_envelope(claim, blocking=True))
    original_enqueue = engine.orchestration.enqueue
    def fail_trigger(c, job, trigger, event, detail=None):
        if trigger == 'DECISION_REQUESTED':
            raise RuntimeError('Injected commit interruption after candidate and hold insert.')
        return original_enqueue(c, job, trigger, event, detail)
    monkeypatch.setattr(engine.orchestration, 'enqueue', fail_trigger)
    with pytest.raises(RuntimeError):
        with engine.store.transaction() as c:
            engine.reports.commit(c, engine.store.get(c, job_id), prepared)
    assert engine.reports.list(job_id) == []
    assert engine.orchestration.summary(job_id)['candidates'] == []
    assert engine.store.snapshot(job_id)['scope_holds'] == []
    assert engine.store.snapshot(job_id)['modules'][0]['stages']['analysis']['status'] == 'RUNNING'
    with engine.store.connection() as c:
        assert c.execute('SELECT count(*) FROM report_receipts').fetchone()[0] == 0


def test_t83_saved_settings_change_only_new_job_frozen_contract(runtime):
    from backend.settings import Settings
    engine, old_id = runtime
    old = engine.store.snapshot(old_id)
    settings = Settings(engine.store)
    current = settings.get()
    profile = Profile(workspace=old['profile']['workspace'], module_report_version=1,
                      orchestration={'enabled': False}).model_dump()
    settings.save(current['version'], profile)
    new_id = engine.create(uid(), settings.get()['profile'], 'New legacy-contract job', 'linux')['job_id']
    assert engine.store.snapshot(old_id)['profile'] == old['profile']
    assert engine.store.snapshot(old_id)['profile']['module_report_version'] == 2
    assert engine.store.snapshot(new_id)['profile']['module_report_version'] == 1
    assert engine.store.snapshot(new_id)['profile']['orchestration']['enabled'] is False


def test_t76_positive_automatic_retry_allowance_is_consumed_without_launching(runtime):
    engine, job_id = runtime
    with engine.store.transaction() as c:
        job = engine.store.get(c, job_id)
        job['profile']['orchestration']['auto_retry_limit'] = 1
        engine.store.save(c, job, 'FIXTURE_RETRY_ALLOWANCE')
    for ordinal in range(2):
        claim = analysis_claim(engine, job_id)
        commit_report(engine, claim, analysis_envelope(claim, failed=True))
        saved = proposal(engine, job_id, 'RETRY', [claim['module']['id']], 'analysis', {
            'previous_attempt_id': claim['attempt']['id'], 'cause_key': 'missing-header',
            'changed_approach': 'Use the verified alternate header.'})
        result = apply(engine, job_id, saved, actor='orchestrator')
        assert result['status'] == ('APPLIED' if ordinal == 0 else 'WAITING_USER')
        stage = engine.store.snapshot(job_id)['modules'][0]['stages']['analysis']
        assert len(stage['attempts']) == ordinal + 1
        assert stage['automatic_retries'] == 1


def test_r1_needs_decision_without_candidate_never_approves_scope(runtime):
    engine, job_id = runtime
    for index in range(2):
        claim = analysis_claim(engine, job_id, index)
        envelope = analysis_envelope(claim)
        for change in envelope['wire_result']['report']['details']['vendor_changes']:
            change['disposition'] = 'needs_decision'
        # Intake may reject incomplete judgment evidence or preserve it as blocked;
        # neither outcome grants approval to the disposition string itself.
        prepared = engine.reports.prepare(claim, envelope)
        with engine.store.transaction() as c:
            engine.reports.commit(c, engine.store.get(c, job_id), prepared)
    with pytest.raises(Conflict):
        action(engine, job_id, 'confirm', {'plan_version': 1})
    module_id = engine.store.snapshot(job_id)['modules'][0]['id']
    assert engine.claim(job_id, module_id, 'design', 'fixture') is None
    with pytest.raises(Conflict):
        action(engine, job_id, 'final-review', {'reviewer': 'fixture', 'evidence': 'No resolved judgment exists.'})
    assert engine.store.snapshot(job_id)['confirmed_plan'] is None
    snapshot = engine.store.snapshot(job_id)
    assert all(m['stages']['analysis']['status'] == 'SUCCEEDED' for m in snapshot['modules'])
    action(engine, job_id, 'decision', {'title': 'Choose upstream compatibility.',
                                      'affected_modules': [m['id'] for m in snapshot['modules']]})
    decision_id = engine.store.snapshot(job_id)['decisions'][0]['id']
    action(engine, job_id, 'resolve', {'decision_id': decision_id, 'resolution': 'Retain upstream ABI.'})
    with pytest.raises(Conflict):
        action(engine, job_id, 'confirm', {'plan_version': 1})
    action(engine, job_id, 'apply-decision', {'decision_id': decision_id, 'source_revision': snapshot['source_revision'],
                                           'evidence': 'Verified the agreed ABI on the current source.'})
    for module in snapshot['modules']:
        for change in module['changes']:
            action(engine, job_id, 'link-vendor-decision', {'module_id': module['id'],
                'change_id': change.get('change_id', change.get('id')), 'decision_id': decision_id,
                'reason': 'Human explicitly links this vendor judgment to the verified decision.'})
    action(engine, job_id, 'confirm', {'plan_version': 1})
    assert engine.claim(job_id, module_id, 'design', 'fixture') is not None


@pytest.mark.parametrize('stale', [False, True])
def test_r2_review_candidates_retain_full_review_origin_and_block_build_atomically(runtime, stale):
    from backend.worker.main import demo_v2_result
    engine, job_id = runtime
    analyze_and_confirm(engine, job_id)
    module_id = engine.store.snapshot(job_id)['modules'][0]['id']
    design = engine.claim(job_id, module_id, 'design', 'fixture')
    engine.finish(job_id, module_id, 'design', design['attempt']['id'], design['attempt']['token'], demo_v2_result(design))
    code = engine.claim(job_id, module_id, 'code', 'fixture')
    envelope = demo_v2_result(code)
    review = envelope['related_reports'][0]['wire_result']
    review['report']['decision_requests'] = [{
        'candidate_key': 'review-build-compatibility', 'question': 'Choose the reviewed ABI compatibility rule.',
        'options': ['upstream ABI', 'compatibility shim'], 'recommendation': 'upstream ABI',
        'affected_module_ids': [module_id], 'affected_stages': ['build'], 'blocking': True,
        'evidence_paths': [review['report']['evidence_refs'][0]['path']]}]
    prepared = engine.reports.prepare(code, envelope)
    assert prepared.error is None
    if stale:
        with engine.store.transaction() as c:
            job = engine.store.get(c, job_id)
            job['fingerprint'] = 'changed-before-review-intake'
            engine.store.save(c, job, 'CONCURRENT_SOURCE_CHANGE')
    with engine.store.transaction() as c:
        result = engine.reports.commit(c, engine.store.get(c, job_id), prepared)
    summary = engine.orchestration.summary(job_id)
    assert result['disposition'] == ('STALE' if stale else 'APPLIED')
    assert len(summary['candidates']) == (0 if stale else 1)
    assert len(engine.store.snapshot(job_id)['scope_holds']) == (0 if stale else 1)
    full_review = engine.reports.detail(job_id, review['report_id'])
    assert full_review['data']['wire_result'] == review
    if not stale:
        assert summary['candidates'][0]['report_id'] == review['report_id']
        assert summary['candidates'][0]['report_id'] != code['attempt']['request']['report_id']
        assert engine.store.snapshot(job_id)['modules'][0]['stages']['code']['status'] == 'SUCCEEDED'
        assert engine.claim(job_id, module_id, 'build', 'competing-worker') is None
        with engine.store.transaction() as c:
            assert engine.reports.commit(c, engine.store.get(c, job_id), prepared)['disposition'] == 'REPLAY'
        assert len(engine.orchestration.summary(job_id)['candidates']) == 1


def test_r6_report_polling_returns_bounded_metadata_and_detail_is_explicit(runtime):
    engine, job_id = runtime
    claim = analysis_claim(engine, job_id)
    envelope = analysis_envelope(claim)
    envelope['wire_result']['report']['summary'] = 'private detailed facts ' * 600
    commit_report(engine, claim, envelope)
    original_id = envelope['wire_result']['report_id']
    # Populate independent historical records without allocating real processes.
    # The row format is existing persistence evidence, not a replacement intake path.
    with engine.store.transaction() as c:
        template = c.execute('SELECT * FROM agent_reports WHERE report_id=?', (original_id,)).fetchone()
        for index in range(150):
            c.execute('INSERT INTO agent_reports VALUES(?,?,?,?,?,?,?,?,?)',
                      (f'history-{index}', job_id, f'old-attempt-{index}', template['module_id'], 'analysis',
                       template['sha256'], 'STALE', template['data'], template['created_at']))
    metadata = engine.reports.list(job_id)
    assert 0 < len(metadata) <= 100
    assert len(json.dumps(metadata).encode()) < 100_000
    for item in metadata:
        assert 'report_id' in item and 'sha256' in item
        assert not {'data', 'wire_result', 'request', 'transport', 'files'} & item.keys()
    assert 'private detailed facts' not in json.dumps(metadata)
    first_page = engine.reports.page(job_id, limit=17)
    second_page = engine.reports.page(job_id, limit=17, before=first_page['next_cursor'])
    assert first_page['total'] == second_page['total'] == 151
    assert len(first_page['items']) == len(second_page['items']) == 17
    assert {r['report_id'] for r in first_page['items']}.isdisjoint(r['report_id'] for r in second_page['items'])
    detail = engine.reports.detail(job_id, original_id)
    assert detail['data']['wire_result']['report']['summary'] == envelope['wire_result']['report']['summary']


LEGACY_REJECTED_MARKERS = [
    {'schema_version': 2}, {'schema_version': 999}, {'schema_version': True},
    {'schema_version': None}, {'schema_version': 1.0},
    {'message_type': 'module_result'}, {'schema_version': 1, 'message_type': 'orchestration_result'}]


@pytest.mark.parametrize('marker', LEGACY_REJECTED_MARKERS)
@pytest.mark.parametrize('outcome', ['SUCCEEDED', 'FAILED'])
@pytest.mark.parametrize('integration', [False, True])
def test_rr1_frozen_v1_engine_rejects_explicit_other_protocol_before_legacy_effects(tmp_path, marker, outcome, integration):
    engine = Engine(Store(tmp_path / 'legacy.db'), tmp_path / 'artifacts')
    job_id = engine.create(uid(), Profile(workspace=str(tmp_path)).model_dump(), 'Legacy fixture', 'linux')['job_id']
    if integration:
        with engine.store.transaction() as c:
            job = engine.store.get(c, job_id)
            for module in job['modules']:
                for stage in module['stages'].values():
                    stage.update(status='SUCCEEDED', validity='CURRENT')
            engine.store.save(c, job, 'FIXTURE_COMPLETED_LEGACY_MODULES')
        claim = engine.claim_integration(job_id, 'fixture')
    else:
        claim = analysis_claim(engine, job_id)
    assert claim is not None
    raw = {'outcome': outcome, 'evidence': 'Explicit mismatched result must never downgrade.',
           'attempt_id': claim['attempt']['id'], 'fingerprint': claim['attempt']['fingerprint'],
           'error_class': '' if outcome == 'SUCCEEDED' else 'FIX', 'cause_key': 'must-not-count-as-fix', **marker}
    if integration:
        engine.finish_integration(claim, raw)
        stage = engine.store.snapshot(job_id)['integration']
    else:
        engine.finish(job_id, claim['module']['id'], 'analysis', claim['attempt']['id'], claim['attempt']['token'], raw)
        snapshot = engine.store.snapshot(job_id)
        stage = snapshot['modules'][0]['stages']['analysis']
        assert all(change['disposition'] == 'needs_analysis' for change in snapshot['modules'][0]['changes'])
    assert stage['status'] == 'FAILED'
    assert stage['result']['error_class'] == 'CONTRACT'
    with engine.store.connection() as c:
        receipts = [json.loads(row[0]) for row in c.execute('SELECT data FROM report_receipts')]
    assert any(receipt.get('raw_result') == raw for receipt in receipts)


@pytest.mark.parametrize('marker', [{}, {'schema_version': 1}])
def test_rr1_genuine_legacy_and_explicit_integer_one_remain_accepted_by_engine(tmp_path, marker):
    engine = Engine(Store(tmp_path / 'legacy.db'), tmp_path / 'artifacts')
    job_id = engine.create(uid(), Profile(workspace=str(tmp_path)).model_dump(), 'Legacy fixture', 'linux')['job_id']
    claim = analysis_claim(engine, job_id)
    engine.finish(job_id, claim['module']['id'], 'analysis', claim['attempt']['id'], claim['attempt']['token'],
                  {'outcome': 'SUCCEEDED', 'evidence': 'Genuine v1 evidence.', **marker})
    assert engine.store.snapshot(job_id)['modules'][0]['stages']['analysis']['status'] == 'SUCCEEDED'


@pytest.mark.parametrize('change', ['identical', 'options', 'impact', 'source'])
def test_rr3_repeated_candidate_reuses_current_resolution_or_reopens_material_change(runtime, change):
    engine, job_id = runtime
    first = analysis_claim(engine, job_id)
    first_envelope = analysis_envelope(first, blocking=True, failed=True)
    commit_report(engine, first, first_envelope)
    candidate = engine.orchestration.summary(job_id)['candidates'][0]
    saved = proposal(engine, job_id, 'DECISION', [first['module']['id']], 'design', {
        'candidate_ids': [candidate['id']], 'question': candidate['question'], 'options': candidate['options'],
        'recommendation': candidate['recommendation'], 'affected_stages': ['design'], 'blocking': True})
    assert apply(engine, job_id, saved)['status'] == 'APPLIED'
    decision_id = engine.store.snapshot(job_id)['decisions'][0]['id']
    action(engine, job_id, 'resolve', {'decision_id': decision_id, 'resolution': 'Use upstream API.'})
    source = engine.store.snapshot(job_id)['source_revision']
    action(engine, job_id, 'apply-decision', {'decision_id': decision_id, 'source_revision': source,
                                           'evidence': 'Verified the chosen behavior for current source.'})
    assert engine.store.snapshot(job_id)['scope_holds'] == []
    with engine.store.connection() as c:
        triggers_before = c.execute("SELECT count(*) FROM orchestration_triggers WHERE type='DECISION_REQUESTED'").fetchone()[0]
    if change == 'source':
        action(engine, job_id, 'invalidate', {'source_revision': 'new-source-basis', 'reason': 'Material source upgrade.'})
    else:
        action(engine, job_id, 'retry', {'module_id': first['module']['id'], 'stage': 'analysis',
                                       'previous_attempt_id': first['attempt']['id']})
    repeated = analysis_claim(engine, job_id)
    envelope = analysis_envelope(repeated, blocking=True, failed=True)
    request = envelope['wire_result']['report']['decision_requests'][0]
    if change == 'options':
        request['options'].append('new ABI migration')
    if change == 'impact':
        request['affected_module_ids'].append(engine.store.snapshot(job_id)['modules'][1]['id'])
        request['affected_stages'].append('build')
    commit_report(engine, repeated, envelope)
    snapshot = engine.store.snapshot(job_id)
    assert len(snapshot['decisions']) == 1 and snapshot['decisions'][0]['id'] == decision_id
    assert snapshot['decisions'][0]['status'] == 'APPLIED'
    current = engine.orchestration.detail(job_id, 'candidates', candidate['id'])
    assert current is not None
    # No second Jira create intent may appear for an unchanged fulfilled question.
    assert len(engine.orchestration.summary(job_id)['candidates']) == 1
    with engine.store.connection() as c:
        triggers_after = c.execute("SELECT count(*) FROM orchestration_triggers WHERE type='DECISION_REQUESTED'").fetchone()[0]
    if change == 'identical':
        assert snapshot['scope_holds'] == []
        assert current['decision_id'] == decision_id
        assert triggers_after == triggers_before
    else:
        assert current['status'] == 'OPEN' and current['decision_id'] is None
        assert len(snapshot['scope_holds']) == 1
        assert current['history']
        assert triggers_after > triggers_before
