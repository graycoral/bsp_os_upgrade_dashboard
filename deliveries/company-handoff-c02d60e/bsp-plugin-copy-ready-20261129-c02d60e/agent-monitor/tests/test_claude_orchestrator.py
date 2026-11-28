"""Offline acceptance for the user-invoked Claude package; never invokes an LLM."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from scripts.claude_orchestrator import (AGENT, ROOT, ContractError, check_agent,
    export_package, json_file, request_check, validate)


@pytest.fixture
def sample(tmp_path):
    workspace = tmp_path / 'evidence'
    shutil.copytree(ROOT / 'examples/claude-orchestrator', workspace)
    return json_file(workspace / 'request.json'), json_file(workspace / 'result.example.json'), workspace


def test_agent_definition_and_readonly_tools():
    assert check_agent()['tools'] == 'Read, Glob, Grep'
    assert not check_agent()['claude_invoked']


@pytest.mark.parametrize('change', ['Bash', 'Write', 'Agent', 'model'])
def test_agent_permission_drift_is_rejected(tmp_path, change):
    export_package(tmp_path / 'package')
    path = tmp_path / 'package' / AGENT
    original = path.read_text()
    path.write_text(original.replace('model: inherit', 'model: opus') if change == 'model'
                    else original.replace('Read, Glob, Grep', 'Read, Glob, Grep, ' + change))
    with pytest.raises(ContractError):
        check_agent(tmp_path / 'package')


def test_example_never_executes_and_hash_is_stable(sample):
    request, result, workspace = sample
    before = deepcopy(request)
    checked = validate(request, result, workspace)
    assert checked['status'] == 'VALID_REVIEW_ONLY'
    assert checked['freshness'] == 'NOT_CHECKED'
    assert checked['proposal_reviews'][0]['status'] == 'WAITING_USER'
    assert not checked['execution_performed'] and request == before
    reordered = dict(reversed(list(result.items())))
    assert validate(request, reordered, workspace)['result_sha256'] == checked['result_sha256']
    result['summary'] += ' updated'
    assert validate(request, result, workspace)['result_sha256'] != checked['result_sha256']


@pytest.mark.parametrize('key', ['job_id', 'session_id', 'orchestration_run_id', 'fingerprint',
                               'trigger_ids', 'base_state_version', 'plan_version'])
def test_correlation_mismatch(sample, key):
    request, result, workspace = sample
    result[key] = {'base_state_version': 99, 'plan_version': 99, 'trigger_ids': ['foreign']}.get(key, 'foreign')
    with pytest.raises(ContractError, match='Correlation'):
        validate(request, result, workspace)


@pytest.mark.parametrize('field,value', [('base_state_version', True), ('schema_version', True),
                                       ('outcome', 'PASS'), ('approved', True), ('percent', 100)])
def test_invalid_result_fields(sample, field, value):
    request, result, workspace = sample
    result[field] = value
    with pytest.raises(ContractError):
        validate(request, result, workspace)


@pytest.mark.parametrize('tamper', ['module', 'attempt', 'cause', 'kind', 'key', 'command', 'hash', 'used_refs', 'empty_refs'])
def test_invalid_proposals(sample, tamper):
    request, result, workspace = sample
    proposal = result['proposals'][0]
    if tamper == 'module': proposal['target']['module_ids'] = ['foreign']
    if tamper == 'attempt': proposal['data']['previous_attempt_id'] = 'foreign'
    if tamper == 'cause': proposal['data']['cause_key'] = 'foreign'
    if tamper == 'kind': proposal['kind'] = 'EXECUTE'
    if tamper == 'key': result['proposals'].append(deepcopy(proposal))
    if tamper == 'command': proposal['data']['command'] = 'touch never-created'
    if tamper == 'hash': proposal['evidence_refs'][0]['sha256'] = '0' * 64
    if tamper == 'used_refs': result['result_refs'] = []
    if tamper == 'empty_refs': proposal['evidence_refs'] = []
    with pytest.raises(ContractError):
        validate(request, result, workspace)
    assert not (workspace / 'never-created').exists()


def test_stale_and_current_versions(sample):
    request, result, workspace = sample
    current = deepcopy(request)
    assert validate(request, result, workspace, current)['freshness'] == 'MATCH'
    for key in ('base_state_version', 'plan_version', 'fingerprint'):
        current = deepcopy(request)
        current[key] = 'changed' if key == 'fingerprint' else current[key] + 1
        output = validate(request, result, workspace, current)
        assert output['freshness'] == 'STALE' and output['proposal_reviews'][0]['status'] == 'STALE'
    current['job_id'] = 'other-job'
    with pytest.raises(ContractError, match='another job'):
        validate(request, result, workspace, current)


@pytest.mark.parametrize('change,reason', [
    ('unknown', 'PREVIOUS_PROCESS_NOT_CONFIRMED_STOPPED'),
    ('alive', 'PREVIOUS_PROCESS_NOT_CONFIRMED_STOPPED'),
    ('paused', 'PAUSED'), ('plan', 'PLAN_NOT_CONFIRMED'),
    ('boot', 'PREREQUISITES_INCOMPLETE'), ('writer', 'WRITER_UNKNOWN'), ('decision', 'DECISION_HOLD')])
def test_retry_preview_respects_known_holds(sample, change, reason):
    request, result, workspace = sample
    snapshot = request['snapshot']; module = snapshot['modules'][0]
    if change == 'unknown': module['attempts'][0]['status'] = 'UNKNOWN'
    if change == 'alive': module['attempts'][0]['process_terminated'] = False
    if change == 'paused': snapshot['paused'] = True
    if change == 'plan': snapshot['plan_confirmed'] = False
    if change == 'boot': snapshot['prerequisite_complete'] = False
    if change == 'writer': snapshot['writer_unknown'] = True
    if change == 'decision': module['blocked_stages'] = ['code']
    preview = validate(request, result, workspace)['proposal_reviews'][0]
    assert preview['status'] == 'BLOCKED' and reason in preview['reasons']
    assert not preview['execution_performed']


def test_analysis_is_independent_of_plan_and_boot(sample):
    request, result, workspace = sample
    request['snapshot'].update(plan_confirmed=False, prerequisite_complete=False, writer_unknown=True)
    request['snapshot']['modules'][0]['attempts'][0]['stage'] = 'analysis'
    result['proposals'][0]['target']['stage'] = 'analysis'
    assert validate(request, result, workspace)['proposal_reviews'][0]['status'] == 'WAITING_USER'


def test_latest_attempt_required(sample):
    request, result, workspace = sample
    latest = deepcopy(request['snapshot']['modules'][0]['attempts'][0]); latest['attempt_id'] = 'new-attempt'
    request['snapshot']['modules'][0]['attempts'].append(latest)
    with pytest.raises(ContractError, match='latest'):
        validate(request, result, workspace)


@pytest.mark.parametrize('failure', ['modified', 'missing', 'traversal', 'absolute', 'symlink'])
def test_evidence_files_checked(sample, failure, tmp_path):
    request, result, workspace = sample
    ref = request['constraints']['readable_evidence'][0]
    outside = tmp_path / 'outside.json'; outside.write_bytes((workspace / 'report-code.json').read_bytes())
    if failure == 'modified': (workspace / ref['path']).write_text('changed')
    if failure == 'missing': (workspace / ref['path']).unlink()
    if failure == 'traversal': ref['path'] = '../outside.json'
    if failure == 'absolute': ref['path'] = str(outside)
    if failure == 'symlink':
        (workspace / 'linked.json').symlink_to(outside); ref['path'] = 'linked.json'
    with pytest.raises((ContractError, OSError)):
        validate(request, result, workspace)


def test_failed_response_retains_identity_and_no_proposals(sample):
    request, result, workspace = sample
    result.update(outcome='FAILED', error_class='INSUFFICIENT_EVIDENCE')
    with pytest.raises(ContractError, match='cannot propose'):
        validate(request, result, workspace)
    result['proposals'] = []
    assert validate(request, result, workspace)['outcome'] == 'FAILED'
    result['job_id'] = 'foreign'
    with pytest.raises(ContractError): validate(request, result, workspace)


@pytest.mark.parametrize('kind', ['PLAN_CHANGE', 'TOOL_ESCALATION', 'DECISION', 'VERIFICATION_PLAN'])
def test_other_proposal_kinds_are_review_only(sample, kind):
    request, result, workspace = sample
    proposal = result['proposals'][0]; proposal['kind'] = kind
    description = {'name': 'Ethernet', 'group': 'main', 'scope': 'RX ring fix', 'dependency_module_ids': [], 'required_cases': ['compile']}
    data = {
        'PLAN_CHANGE': {'base_plan_version': 2, 'changes': [{'operation': 'update', 'module_id': 'module-ethernet-example', 'new_module_key': None, 'before': description, 'after': dict(description, scope='RX and TX ring fixes'), 'reason': 'Shared API changed'}]},
        'TOOL_ESCALATION': {'previous_attempt_id': 'attempt-code-example', 'cause_key': 'ethernet.rx-ring.api-mismatch', 'requested_tool': 'claude', 'model_policy': 'opus', 'difficulty_evidence': 'API contract requires design review; inspect cited report'},
        'DECISION': {'candidate_ids': [], 'question': 'Which API compatibility policy?', 'options': ['Preserve old behavior', 'Adopt new behavior'], 'recommendation': 'Preserve old behavior', 'affected_stages': ['design', 'code'], 'blocking': True},
        'VERIFICATION_PLAN': {'source_revision': 'fixture-revision-1', 'image_refs': [], 'cases': [{'case_id': 'rx-ring', 'method': 'Manual RX loopback', 'expected_result': 'No packet loss'}]}}
    proposal['data'] = data[kind]
    assert validate(request, result, workspace)['proposal_reviews'][0]['status'] == 'WAITING_USER'
    proposal['data']['arbitrary_command'] = 'anything'
    with pytest.raises(ContractError): validate(request, result, workspace)


def test_environment_error_does_not_justify_opus(sample):
    request, result, workspace = sample
    request['snapshot']['modules'][0]['attempts'][0]['error_class'] = 'ENVIRONMENT'
    proposal = result['proposals'][0]; proposal['kind'] = 'TOOL_ESCALATION'
    proposal['data'] = dict(previous_attempt_id='attempt-code-example', cause_key='ethernet.rx-ring.api-mismatch', requested_tool='claude', model_policy='opus', difficulty_evidence='Network down')
    with pytest.raises(ContractError, match='FIX'): validate(request, result, workspace)


@pytest.mark.parametrize('operation', ['add', 'deactivate'])
def test_plan_change_preserves_server_id_ownership(sample, operation):
    request, result, workspace = sample
    proposal = result['proposals'][0]; proposal['kind'] = 'PLAN_CHANGE'
    description = {'name': 'Camera', 'group': 'main', 'scope': 'Camera API port', 'dependency_module_ids': [], 'required_cases': ['capture']}
    change = {'operation': operation, 'module_id': None if operation == 'add' else 'module-ethernet-example',
              'new_module_key': 'new-camera' if operation == 'add' else None,
              'before': None if operation == 'add' else description,
              'after': description if operation == 'add' else None, 'reason': 'Scope review required'}
    proposal['data'] = {'base_plan_version': 2, 'changes': [change]}
    assert validate(request, result, workspace)['proposal_reviews'][0]['status'] == 'WAITING_USER'
    if operation == 'add': change['module_id'] = 'invented-server-id'
    else: change['new_module_key'] = 'renumber-existing'
    with pytest.raises(ContractError): validate(request, result, workspace)


@pytest.mark.parametrize('field', ['module', 'attempt', 'report', 'allowed_kind', 'candidate', 'manual_test'])
def test_duplicate_or_unowned_request_values(sample, field):
    request, result, workspace = sample
    if field == 'module': request['snapshot']['modules'].append(deepcopy(request['snapshot']['modules'][0]))
    if field == 'attempt': request['snapshot']['modules'][0]['attempts'] *= 2
    if field == 'report': request['result_refs'] *= 2
    if field == 'allowed_kind': request['constraints']['allowed_proposals'] = []
    if field == 'candidate':
        result['proposals'][0].update(kind='DECISION', data={'candidate_ids': ['made-up'], 'question': 'Policy?', 'options': ['A', 'B'], 'recommendation': 'A', 'affected_stages': ['code'], 'blocking': True})
    if field == 'manual_test':
        result['proposals'][0]['target']['stage'] = 'device_test'
        request['snapshot']['modules'][0]['attempts'][0]['stage'] = 'device_test'
    with pytest.raises(ContractError): validate(request, result, workspace)


@pytest.mark.parametrize('field,value', [('auto_retry_limit', 1), ('profile', 'unknown'), ('token', 'no-secrets')])
def test_manual_profile_disallows_automatic_execution(sample, field, value):
    request, _, workspace = sample
    request['constraints'][field] = value
    with pytest.raises(ContractError): request_check(request, workspace)


@pytest.mark.parametrize('raw', ['{"a":1,"a":2}', '{"a":NaN}', '```json\n{}\n```', '{}{}', 'x' * (1024 * 1024 + 1)])
def test_bad_json_is_rejected(tmp_path, raw):
    path = tmp_path / 'bad.json'; path.write_text(raw)
    with pytest.raises((ContractError, ValueError)): json_file(path)


def test_export_is_portable_and_never_overwrites(tmp_path):
    destination = tmp_path / 'standalone package'
    result = export_package(destination)
    assert result['status'] == 'EXPORTED'
    manifest = json_file(destination / 'package-manifest.json')
    for path, digest in manifest.items():
        assert hashlib.sha256((destination / path).read_bytes()).hexdigest() == digest
    assert not (destination / 'CLAUDE.md').exists()
    assert not (destination / '.runtime').exists()
    assert check_agent(destination)['status'] == 'PASS'
    for args in [['check-agent'], ['validate', '--request', 'examples/claude-orchestrator/request.json',
            '--result', 'examples/claude-orchestrator/result.example.json', '--workspace', 'examples/claude-orchestrator']]:
        process = subprocess.run([sys.executable, 'scripts/claude_orchestrator.py', *args], cwd=destination, capture_output=True, text=True)
        assert process.returncode == 0, process.stderr
        assert json.loads(process.stdout)
    with pytest.raises(ContractError, match='already exists'): export_package(destination)
    assert manifest == json_file(destination / 'package-manifest.json')


def test_cli_error_is_structured(sample):
    request, result, workspace = sample
    result['completed'] = True
    (workspace / 'bad-result.json').write_text(json.dumps(result))
    process = subprocess.run([sys.executable, str(ROOT / 'scripts/claude_orchestrator.py'), 'validate',
        '--request', str(workspace / 'request.json'), '--result', str(workspace / 'bad-result.json'),
        '--workspace', str(workspace)], capture_output=True, text=True)
    assert process.returncode == 2 and process.stdout == ''
    assert json.loads(process.stderr)['execution_performed'] is False
