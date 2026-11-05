"""T-71/73/77/78/83: untrusted reports cannot manufacture execution facts."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.contracts import (ContractError, canonical_json, parse_json, report_hash,
                               schema_for_request, validate_module_result,
                               validate_orchestration_result)


SHA = 'a' * 64


def role_capability_profile():
    """Explicit declarations, with every CLI configured regardless of eligibility."""
    roles = {'opencode': ['implementer'],
             'claude': ['analyst', 'designer', 'implementer', 'reviewer', 'orchestrator'],
             'codex': ['reviewer'], 'build': ['builder', 'verifier', 'integration']}
    documents = {tool: {'schema_version': 1, 'module_report_versions': [1, 2],
                       'orchestration_versions': [1] if tool == 'claude' else [], 'roles': values}
                 for tool, values in roles.items()}
    return {'execution': 'bridge', 'runner': 'bridge', 'module_report_version': 2,
            'orchestration': {'enabled': True},
            'agents': {tool: ['fixture-' + tool] for tool in ('opencode', 'claude', 'codex')},
            'build_argv': ['fixture-build'],
            'bridge_capabilities': {tool: {'kind': 'document', 'document': doc}
                                    for tool, doc in documents.items()}}


@pytest.mark.parametrize('mutation,accepted', [
    ('opencode_reviewer_only', True), ('claude_not_implementer', True),
    ('codex_not_reviewer', True), ('no_implementation_role', False),
    ('fallback_without_codex_review', False), ('arbitrary_reviewer_only', False),
    ('orchestrator_role_missing', False)])
def test_rr4_freeze_requires_a_configured_policy_compatible_role_pair(mutation, accepted):
    from backend.adapters.capabilities import freeze_capabilities
    from backend.domain.policy import Conflict
    profile = role_capability_profile()
    docs = {tool: source['document'] for tool, source in profile['bridge_capabilities'].items()}
    if mutation in {'opencode_reviewer_only', 'no_implementation_role',
                    'fallback_without_codex_review', 'arbitrary_reviewer_only'}:
        docs['opencode']['roles'] = ['reviewer']
    if mutation in {'claude_not_implementer', 'no_implementation_role'}:
        docs['claude']['roles'].remove('implementer')
    if mutation in {'codex_not_reviewer', 'fallback_without_codex_review', 'arbitrary_reviewer_only'}:
        docs['codex']['roles'] = ['implementer']
    if mutation == 'orchestrator_role_missing':
        docs['claude']['roles'].remove('orchestrator')
    if accepted:
        frozen = freeze_capabilities(profile)
        assert frozen['module_report_versions'] == [1, 2]
        assert frozen['tools']['opencode']['roles'] == docs['opencode']['roles']
    else:
        with pytest.raises(Conflict) as error:
            freeze_capabilities(profile)
        assert error.value.code == 'CAPABILITY_UNSUPPORTED'


@pytest.mark.parametrize('runner', ['native', 'bridge'])
@pytest.mark.parametrize('tool,stage,role', [
    ('opencode', 'code', 'implementer'), ('claude', 'analysis', 'analyst'),
    ('codex', 'review', 'reviewer'), ('claude', 'orchestrate', 'orchestrator')])
@pytest.mark.parametrize('ineligible', ['role', 'version', 'missing_snapshot'])
def test_rr4_direct_dispatch_rejects_ineligible_frozen_tool_before_process(
        tmp_path, monkeypatch, runner, tool, stage, role, ineligible):
    import backend.adapters.native as native
    import backend.adapters.process as process
    from backend.adapters.bridge import Bridge
    from backend.adapters.capabilities import freeze_capabilities
    profile = role_capability_profile()
    profile['contract_capabilities'] = freeze_capabilities(profile)
    profile.update(workspace=str(tmp_path), runner=runner, timeout_seconds=5,
                   instruction_snapshots={stage: ''})
    cap = profile['contract_capabilities']['tools'][tool]
    if ineligible == 'role':
        cap['roles'] = [value for value in cap['roles'] if value != role]
    elif ineligible == 'version':
        cap['orchestration_versions' if stage == 'orchestrate' else 'module_report_versions'] = []
    else:
        del profile['contract_capabilities']['tools'][tool]
    request = module_request(stage if stage != 'orchestrate' else 'analysis')
    request.update(role=role, stage=stage)
    if stage == 'review':
        request['report_expectations']['author_tools'] = ['claude']
    if stage == 'orchestrate':
        request = orchestration_pair()[0] | {'schema_version': 1, 'stage': stage, 'role': role}
    def forbidden(*_args, **_kwargs):
        pytest.fail('An unsupported frozen role/version reached process launch or workspace observation.')
    monkeypatch.setattr(native, 'run_process', forbidden)
    monkeypatch.setattr(process, 'run_process', forbidden)
    monkeypatch.setattr(native, '_file_observations', forbidden)
    adapter = native.Native() if runner == 'native' else Bridge()
    result = adapter.invoke(profile, tool, request)
    assert result['transport']['status'] == 'FAILED'
    assert result['transport']['error_class'] == 'CAPABILITY_UNSUPPORTED'


@pytest.mark.parametrize('runner', ['native', 'bridge'])
@pytest.mark.parametrize('author,wrong_reviewer', [('claude', 'claude'), ('opencode', 'codex'), (None, 'claude')])
def test_rr4_direct_review_dispatch_cannot_bypass_author_cross_review_policy(
        tmp_path, monkeypatch, runner, author, wrong_reviewer):
    import backend.adapters.native as native
    import backend.adapters.process as process
    from backend.adapters.bridge import Bridge
    from backend.adapters.capabilities import freeze_capabilities
    profile = role_capability_profile()
    profile['contract_capabilities'] = freeze_capabilities(profile)
    profile.update(workspace=str(tmp_path), runner=runner, timeout_seconds=5)
    request = module_request('review')
    request.update(role='reviewer')
    if author is not None:
        request['report_expectations']['author_tools'] = [author]
    def forbidden(*_args, **_kwargs):
        pytest.fail('An author-incompatible reviewer reached process launch.')
    monkeypatch.setattr(native, 'run_process', forbidden)
    monkeypatch.setattr(process, 'run_process', forbidden)
    result = (native.Native() if runner == 'native' else Bridge()).invoke(profile, wrong_reviewer, request)
    assert result['transport']['status'] == 'FAILED'
    assert result['transport']['error_class'] == 'CAPABILITY_UNSUPPORTED'


def module_request(stage='analysis'):
    return dict(schema_version=2, message_type='module_request', job_id='job',
                module_id='module', stage=stage, attempt_id='attempt', session_id='session',
                report_id='report', plan_version=1, fingerprint='frozen-input',
                source_revision='revision', input_result_refs=[{'report_id': 'prior', 'sha256': SHA}],
                report_expectations={})


def module_result(request=None):
    request = request or module_request()
    details = {
        'analysis': {'vendor_changes': [{'change_id': 'change-1', 'disposition': 'already_upstream',
                     'rationale': 'The new base contains this change.', 'affected_files': ['driver.c'],
                     'dependency_module_ids': [], 'required_cases': ['boot']}]},
        'design': {'design_summary': 'Keep the upstream API.', 'target_files': ['driver.c'],
                   'interface_impacts': [], 'dependency_module_ids': [],
                   'verification_plan': [{'case_id': 'boot', 'method': 'boot board', 'expected_result': 'ready'}]},
        'code': {'changed_files': ['driver.c'], 'diff_path': 'change.diff',
                 'fix_description': 'Adapt the call.', 'previous_attempt_difference': 'First implementation.'},
        'review': {'reviewed_source_revision': 'revision', 'reviewed_diff_sha256': SHA, 'findings': []},
        'build': {'build_profile': 'debug', 'command_summary': 'registered build', 'exit_code': 0,
                  'target_description': 'board image'},
        'verification': {'verification_scope': 'boot smoke', 'required_case_ids': ['boot'], 'limitations': []},
        'integration': {'included_modules': [{'module_id': 'module', 'source_revision': 'revision', 'report_id': 'code-report'}],
                        'build_profile': 'debug', 'required_case_ids': ['boot'], 'limitations': []},
    }[request['stage']]
    result = {key: deepcopy(request[key]) for key in ('job_id', 'module_id', 'stage', 'attempt_id',
              'session_id', 'report_id', 'plan_version', 'fingerprint', 'input_result_refs', 'source_revision')}
    result.update(schema_version=2, message_type='module_result', outcome='SUCCEEDED', evidence='Recorded evidence.',
                  report={'summary': 'Completed assigned scope.', 'details': details,
                          'evidence_refs': [{'path': 'evidence.log', 'sha256': SHA, 'kind': 'log'}],
                          'test_results': [], 'decision_requests': []})
    if request['stage'] == 'code':
        result['report']['evidence_refs'].append({'path': 'change.diff', 'sha256': SHA, 'kind': 'diff'})
    if request['stage'] == 'build':
        result['artifact'] = {'path': 'image.bin', 'sha256': SHA}
    if request['stage'] in {'verification', 'integration'}:
        result['report']['test_results'] = [{'case_id': 'boot', 'status': 'PASS', 'source_revision': 'revision',
                                            'artifact_sha256': SHA, 'evidence_paths': ['evidence.log']}]
    return result


def orchestration_pair():
    request = dict(job_id='job', orchestration_run_id='run', session_id='coordinator', trigger_ids=['trigger'],
                   base_state_version=4, plan_version=1, fingerprint='frozen',
                   result_refs=[{'report_id': 'prior', 'sha256': SHA}], message_type='orchestration_request')
    result = {key: deepcopy(request[key]) for key in ('job_id', 'orchestration_run_id', 'session_id',
               'trigger_ids', 'base_state_version', 'plan_version', 'fingerprint', 'result_refs')}
    result.update(schema_version=1, message_type='orchestration_result', outcome='SUCCEEDED',
                  summary='No additional action.', proposals=[])
    return request, result


def retry_proposal():
    return dict(proposal_key='retry-1', kind='RETRY', target={'module_ids': ['module'], 'stage': 'analysis'},
                reason='Use the supplied missing header.', evidence_refs=[{'report_id': 'prior', 'sha256': SHA}],
                data={'previous_attempt_id': 'attempt', 'cause_key': 'missing-header',
                      'changed_approach': 'Read the frozen header inventory.'})


@pytest.mark.parametrize('raw', ['{"a":1,"a":2}', '{"a":{"b":1,"b":2}}',
                                '{"value":NaN}', '{"value":Infinity}', '[]', 'null', b'\xff'])
def test_t77_wire_rejects_ambiguous_or_non_object_json(raw):
    with pytest.raises(ContractError):
        parse_json(raw)


def test_t77_canonical_hash_is_order_independent_and_utf8():
    first = {'message': '한글', 'nested': {'b': 2, 'a': 1}}
    second = {'nested': {'a': 1, 'b': 2}, 'message': '한글'}
    assert canonical_json(first) == canonical_json(second)
    assert report_hash(first) == hashlib.sha256(canonical_json(second)).hexdigest()
    assert report_hash(first) != report_hash(first | {'message': 'changed'})
    with pytest.raises(ContractError):
        canonical_json({'value': float('nan')})


def test_t77_wire_size_and_depth_are_bounded():
    with pytest.raises(ContractError):
        parse_json('{"message":"' + 'x' * 1_048_576 + '"}')
    with pytest.raises(ContractError):
        parse_json('{"deep":' * 50 + '0' + '}' * 50)


@pytest.mark.parametrize('stage', ['analysis', 'design', 'code', 'build', 'review', 'verification', 'integration'])
def test_t78_complete_role_reports_are_accepted_without_inventing_fields(stage):
    request = module_request(stage)
    if stage == 'integration':
        request['module_id'] = None
    result = module_result(request)
    assert validate_module_result(result, request)['report'] == result['report']


@pytest.mark.parametrize('outcome', ['SUCCEEDED', 'FAILED'])
@pytest.mark.parametrize('key,value', [('job_id', 'other'), ('module_id', 'other'), ('stage', 'design'),
    ('attempt_id', 'other'), ('session_id', 'other'), ('report_id', 'other'), ('plan_version', 2),
    ('fingerprint', 'other'), ('input_result_refs', [{'report_id': 'prior', 'sha256': 'b' * 64}])])
def test_t77_success_and_failure_correlate_every_frozen_identity(outcome, key, value):
    request = module_request()
    result = module_result(request)
    result.update(outcome=outcome)
    if outcome == 'FAILED':
        result['error_class'] = 'ENVIRONMENT'
    result[key] = value
    with pytest.raises(ContractError):
        validate_module_result(result, request)


@pytest.mark.parametrize('mutation', ['unknown_top', 'unknown_nested', 'bool_version', 'bool_build_exit'])
def test_t83_unknown_fields_and_coerced_integer_values_are_rejected(mutation):
    request = module_request('build' if mutation == 'bool_build_exit' else 'analysis')
    result = module_result(request)
    if mutation == 'unknown_top':
        result['progress'] = 100
    elif mutation == 'unknown_nested':
        result['report']['details']['shell'] = 'arbitrary command'
    elif mutation == 'bool_version':
        result['plan_version'] = True
    else:
        result['report']['details']['exit_code'] = False
    with pytest.raises(ContractError):
        validate_module_result(result, request)


def test_t78_prelaunch_failure_preserves_explicitly_unavailable_data():
    request = module_request()
    result = module_result(request)
    result.update(outcome='FAILED', error_class='ENVIRONMENT', source_revision=None)
    result['report']['details'] = {'vendor_changes': None, 'unavailable_reasons': {
        'vendor_changes': 'The source mount could not be read.', 'source_revision': 'Source mount unavailable.'}}
    accepted = validate_module_result(result, request)
    assert accepted['source_revision'] is None
    assert accepted['report']['details']['vendor_changes'] is None
    del result['report']['details']['unavailable_reasons']['vendor_changes']
    with pytest.raises(ContractError):
        validate_module_result(result, request)


@pytest.mark.parametrize('status,revision', [('NOT_RUN', 'revision'), ('FAIL', 'revision'), ('PASS', 'obsolete')])
def test_t78_required_cases_need_actual_pass_on_requested_source(status, revision):
    request = module_request('verification')
    result = module_result(request)
    result['report']['test_results'][0].update(status=status, source_revision=revision)
    with pytest.raises(ContractError):
        validate_module_result(result, request)


def test_t78_case_evidence_must_be_registered_and_case_ids_unique():
    request = module_request('verification')
    result = module_result(request)
    result['report']['test_results'][0]['evidence_paths'] = ['unregistered.log']
    with pytest.raises(ContractError):
        validate_module_result(result, request)
    result = module_result(request)
    result['report']['test_results'].append(deepcopy(result['report']['test_results'][0]))
    with pytest.raises(ContractError):
        validate_module_result(result, request)


@pytest.mark.parametrize('mutation', ['revision', 'diff', 'session', 'report'])
def test_t78_review_must_identify_the_exact_code_and_separate_review(mutation):
    request = module_request('review')
    request['implementation'] = {'session_id': 'author-session', 'report_id': 'author-report', 'source_revision': 'revision'}
    request['report_expectations']['reviewed_diff_sha256'] = SHA
    result = module_result(request)
    if mutation == 'revision':
        result['report']['details']['reviewed_source_revision'] = 'obsolete'
    elif mutation == 'diff':
        result['report']['details']['reviewed_diff_sha256'] = 'b' * 64
    else:
        key = 'session_id' if mutation == 'session' else 'report_id'
        result[key] = request[key] = request['implementation'][key]
    with pytest.raises(ContractError):
        validate_module_result(result, request)


@pytest.mark.parametrize('outcome', ['SUCCEEDED', 'FAILED'])
@pytest.mark.parametrize('key,value', [('job_id', 'wrong'), ('orchestration_run_id', 'wrong'),
    ('session_id', 'wrong'), ('trigger_ids', ['wrong']), ('base_state_version', 5),
    ('plan_version', 2), ('fingerprint', 'wrong')])
def test_t73_orchestration_correlation_applies_to_failed_calls_too(outcome, key, value):
    request, result = orchestration_pair()
    result.update(outcome=outcome)
    if outcome == 'FAILED':
        result['error_class'] = 'ENVIRONMENT'
    result[key] = value
    with pytest.raises(ContractError):
        validate_orchestration_result(result, request)


@pytest.mark.parametrize('mutation', ['unknown_kind', 'shell_data', 'duplicate_key', 'changed_evidence', 'failed_actions'])
def test_t71_entire_actionable_batch_is_rejected_for_unsafe_proposals(mutation):
    request, result = orchestration_pair()
    result['proposals'] = [retry_proposal()]
    bad = deepcopy(retry_proposal())
    bad['proposal_key'] = 'second'
    if mutation == 'unknown_kind':
        bad['kind'] = 'RUN_SHELL'
    elif mutation == 'shell_data':
        bad['data']['command'] = 'run anything'
    elif mutation == 'duplicate_key':
        bad['proposal_key'] = 'retry-1'
    elif mutation == 'changed_evidence':
        bad['evidence_refs'][0]['sha256'] = 'b' * 64
    else:
        result.update(outcome='FAILED', error_class='CONTRACT')
    result['proposals'].append(bad)
    with pytest.raises(ContractError):
        validate_orchestration_result(result, request)


def test_t73_orchestration_result_cannot_substitute_input_report_hash():
    request, result = orchestration_pair()
    result['result_refs'][0]['sha256'] = 'b' * 64
    with pytest.raises(ContractError):
        validate_orchestration_result(result, request)


def test_t83_generated_response_schema_freezes_server_correlation():
    request = module_request()
    schema = schema_for_request(request)
    assert schema['additionalProperties'] is False
    for field in ('attempt_id', 'session_id', 'report_id', 'plan_version', 'fingerprint', 'input_result_refs'):
        assert schema['properties'][field] == {'const': request[field]}


def three_trees(tmp_path):
    profile = {'execution': 'bridge', 'modules': [{'name': 'driver', 'stable_key': 'driver',
               'target_paths': ['drivers']}]}
    for name in ('old_base', 'vendor_tree', 'new_base'):
        folder = tmp_path / name
        (folder / 'drivers').mkdir(parents=True)
        (folder / 'drivers' / 'changed.c').write_text('old API\n')
        (folder / 'drivers' / 'removed.c').write_text('removed later\n')
        profile[name] = str(folder)
    vendor = Path(profile['vendor_tree'])
    (vendor / 'drivers' / 'changed.c').write_text('vendor API\n')
    (vendor / 'drivers' / 'removed.c').unlink()
    (vendor / 'new-board.txt').write_text('discover new module\n')
    return profile


def test_t78_inventory_covers_real_changes_and_leaves_unattributed_paths_discoverable(tmp_path):
    from backend.adapters.inventory import build_vendor_inventory
    profile = three_trees(tmp_path)
    inventory = build_vendor_inventory(profile)
    again = build_vendor_inventory(profile)
    assert inventory == again
    assert inventory['simulation'] is False
    changes = {item['path']: item for item in inventory['changes']}
    assert set(changes) == {'drivers/changed.c', 'drivers/removed.c', 'new-board.txt'}
    assert changes['drivers/changed.c']['kind'] == 'modify'
    assert changes['drivers/removed.c']['kind'] == 'delete'
    assert changes['new-board.txt']['kind'] == 'add'
    assert changes['drivers/changed.c']['module_keys'] == ['driver']
    assert changes['new-board.txt']['module_keys'] == []
    assert len({item['change_id'] for item in changes.values()}) == 3
    assert (Path(profile['vendor_tree']) / 'drivers' / 'changed.c').read_text() == 'vendor API\n'


def test_t78_inventory_refuses_unreadable_or_mutating_tree(tmp_path, monkeypatch):
    import backend.adapters.inventory as inventory
    from backend.domain.policy import Conflict
    profile = three_trees(tmp_path)
    real_digest = inventory.hashlib.file_digest
    calls = []
    def change_after_read(stream, algorithm):
        digest = real_digest(stream, algorithm)
        if not calls:
            calls.append(True)
            (Path(profile['old_base']) / 'late-addition.c').write_text('changed during inventory')
        return digest
    monkeypatch.setattr(inventory.hashlib, 'file_digest', change_after_read)
    with pytest.raises(Conflict) as error:
        inventory.build_vendor_inventory(profile)
    assert error.value.code == 'ENVIRONMENT'
    monkeypatch.setattr(inventory.hashlib, 'file_digest', real_digest)
    original_open = Path.open
    def deny_file(path, *args, **kwargs):
        if path.name == 'changed.c':
            raise PermissionError('fixture access denied')
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', deny_file)
    with pytest.raises(Conflict):
        inventory.build_vendor_inventory(profile)


def test_t83_unsupported_v2_capability_cannot_silently_downgrade():
    from backend.adapters.capabilities import freeze_capabilities
    from backend.domain.policy import Conflict
    profile = {'execution': 'bridge', 'runner': 'bridge', 'module_report_version': 2,
               'orchestration': {'enabled': False}, 'bridge_capabilities': {}}
    with pytest.raises(Conflict) as error:
        freeze_capabilities(profile)
    assert error.value.code == 'CAPABILITY_UNSUPPORTED'
    profile['module_report_version'] = 1
    assert freeze_capabilities(profile)['module_report_versions'] == [1]


def test_t83_explicit_capability_command_is_bounded_and_never_guesses_flags(tmp_path, monkeypatch):
    import backend.adapters.process as process
    from backend.adapters.capabilities import freeze_capabilities
    document = {'schema_version': 1, 'module_report_versions': [1], 'orchestration_versions': [], 'roles': []}
    observed = []
    def fake_process(argv, **kwargs):
        observed.append((argv, kwargs))
        return SimpleNamespace(unknown=False, error=None, code=0, stdout=canonical_json(document))
    monkeypatch.setattr(process, 'run_process', fake_process)
    argv = ['C:/fixture/tool.exe', 'documented-probe']
    profile = {'execution': 'bridge', 'runner': 'bridge', 'workspace': str(tmp_path),
               'module_report_version': 1, 'bridge_capabilities': {'claude': {'kind': 'command', 'argv': argv}}}
    frozen = freeze_capabilities(profile)
    assert observed == [(argv, {'cwd': str(tmp_path), 'timeout': 5, 'limit': 65536})]
    assert frozen['tools']['claude']['inference'] == 'UNVERIFIED'
    assert frozen['tools']['claude']['provenance']['kind'] == 'command'


@pytest.mark.parametrize('stage', ['build', 'review', 'verification', 'integration'])
def test_r3_read_only_results_require_actual_frozen_content_identity_even_if_source_was_already_changed(tmp_path, stage):
    from backend.adapters.native import _file_observations, _observations, workspace_revision
    (tmp_path / 'driver.c').write_text('frozen source\n')
    profile = {'workspace': str(tmp_path), 'module_report_version': 2, 'artifact_path': ''}
    frozen = workspace_revision(profile)
    profile.update(source_origin_revision='a' * 40, source_revision=frozen,
                   source_identity={'kind': 'workspace-content-sha256-v1', 'sha256': frozen})
    payload = {'stage': stage, 'source_revision': frozen,
               'report_expectations': {'source_identity': deepcopy(profile['source_identity'])}}
    wire = {'source_revision': frozen, 'report': {'details': {'reviewed_diff_sha256': SHA}}}
    current = _observations(profile, payload, _file_observations(profile), wire)
    assert current['source_revision'] == frozen
    assert len(frozen) == 64 and len(profile['source_origin_revision']) == 40
    # Mutation precedes the role's own before snapshot: unchanged-during-call
    # checks alone cannot detect this obsolete launch baseline.
    (tmp_path / 'driver.c').write_text('different source before launch\n')
    before_launch = _file_observations(profile)
    with pytest.raises(ContractError):
        _observations(profile, payload, before_launch, wire)


@pytest.mark.parametrize('diff_kind', ['canonical', 'arbitrary', 'omitted_change'])
def test_r5_code_diff_must_prove_actual_before_after_including_added_and_deleted_files(tmp_path, diff_kind):
    from backend.adapters.native import (_file_observations, _observations, workspace_revision,
                                         canonical_workspace_diff)
    (tmp_path / 'driver.c').write_bytes(b'before\n')
    (tmp_path / 'gone.c').write_bytes(b'deleted\n')
    profile = {'workspace': str(tmp_path), 'module_report_version': 2, 'artifact_path': ''}
    frozen = workspace_revision(profile)
    before = _file_observations(profile)
    profile.update(source_revision=frozen, source_identity={'kind': 'workspace-content-sha256-v1', 'sha256': frozen})
    (tmp_path / 'driver.c').write_bytes(b'after\n')
    (tmp_path / 'gone.c').unlink()
    (tmp_path / 'added.c').write_bytes(b'added\x00binary\n')
    after = _file_observations(profile)
    descriptor = canonical_workspace_diff(before, after)
    if diff_kind == 'arbitrary':
        descriptor = b'This is unrelated to the real implementation changes.\n'
    elif diff_kind == 'omitted_change':
        incomplete = json.loads(descriptor)
        incomplete['changes'] = [c for c in incomplete['changes'] if c['path'] != 'gone.c']
        descriptor = canonical_json(incomplete)
    evidence = tmp_path / '.bsp-dashboard' / 'proof.diff'
    evidence.parent.mkdir()
    evidence.write_bytes(descriptor)
    digest = hashlib.sha256(descriptor).hexdigest()
    payload = {'stage': 'code', 'source_revision': frozen, 'report_expectations': {
        'source_identity': deepcopy(profile['source_identity']), 'allowed_write_paths': ['driver.c', 'gone.c', 'added.c']}}
    wire = {'source_revision': workspace_revision(profile), 'report': {'details': {
        'changed_files': ['driver.c', 'gone.c', 'added.c'], 'diff_path': '.bsp-dashboard/proof.diff'},
        'evidence_refs': [{'path': '.bsp-dashboard/proof.diff', 'sha256': digest, 'kind': 'diff'}]}}
    if diff_kind == 'canonical':
        observed = _observations(profile, payload, before, wire)
        assert observed['diff_sha256'] == digest
        assert {item['path'] for item in observed['files']} == {'driver.c', 'gone.c', 'added.c'}
        parsed = json.loads(descriptor)
        assert next(c for c in parsed['changes'] if c['path'] == 'added.c')['before'] is None
        assert next(c for c in parsed['changes'] if c['path'] == 'gone.c')['after'] is None
    else:
        with pytest.raises(ContractError):
            _observations(profile, payload, before, wire)


@pytest.mark.parametrize('runner', ['native', 'bridge'])
@pytest.mark.parametrize('outcome', ['SUCCEEDED', 'FAILED'])
@pytest.mark.parametrize('marker', [
    {'schema_version': 2}, {'schema_version': 999}, {'schema_version': True}, {'schema_version': None},
    {'message_type': 'module_result'}, {'schema_version': 1, 'message_type': 'orchestration_result'},
    {}, {'schema_version': 1}])
def test_rr1_legacy_adapter_paths_reject_named_or_mismatched_protocol_before_normalization(tmp_path, monkeypatch, runner, outcome, marker):
    import backend.adapters.native as native
    import backend.adapters.process as process
    from backend.adapters.bridge import Bridge
    from backend.settings import Profile
    raw = {'outcome': outcome, 'evidence': 'Harmless legacy adapter fixture.', 'source_revision': 'legacy-source',
           'error_class': '' if outcome == 'SUCCEEDED' else 'ENVIRONMENT', 'cause_key': '',
           'attempt_id': 'attempt', 'fingerprint': 'fingerprint', **marker}
    native_output = {'subtype': 'success', 'is_error': False, 'session_id': 'fixture-session', 'structured_output': raw}
    def completed(*_args, **_kwargs):
        return process.ProcessResult(0, stdout=json.dumps(native_output if runner == 'native' else raw).encode())
    monkeypatch.setattr(native, 'run_process', completed)
    monkeypatch.setattr(process, 'run_process', completed)
    profile = Profile(workspace=str(tmp_path), runner=runner, agents={'claude': ['fixture-cli']}).model_dump()
    profile.update(instruction_snapshots={'analysis': ''}, _launch_context={'launch_id': 'fixture-launch'})
    payload = {'schema_version': 1, 'stage': 'analysis', 'attempt_id': 'attempt', 'fingerprint': 'fingerprint',
               'source_revision': 'legacy-source'}
    result = Bridge().invoke(profile, 'claude', payload)
    accepted = marker == {} or type(marker.get('schema_version')) is int and marker['schema_version'] == 1 and 'message_type' not in marker
    if accepted:
        assert result['outcome'] == outcome
        assert result['evidence'] == raw['evidence']
    else:
        assert result['outcome'] == 'FAILED'
        assert result['error_class'] == 'CONTRACT'
