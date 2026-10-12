"""Offline Claude agent packaging and contract checks; never executes proposals.

Python 3.11+, standard library only. The manual profile is separate from the
dashboard's currently supported module protocol. No DB, HTTP or subprocess use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
AGENT = Path('.claude/agents/bsp-upgrade-orchestrator.md')
GUIDE = Path('docs/agents/CLAUDE_ORCHESTRATOR_GUIDE.md')
REFERENCES = [Path('docs/design/ORCHESTRATOR_SPEC.md'),
              Path('docs/design/AGENT_STATUS_CONTRACT.md'),
              Path('docs/roles/RUNTIME_ROLES.md')]
STAGES = {'analysis', 'design', 'code', 'build', 'verification', 'device_test'}
KINDS = {'PLAN_CHANGE', 'RETRY', 'TOOL_ESCALATION', 'DECISION', 'VERIFICATION_PLAN'}
TRIGGERS = {'JOB_STARTED', 'ANALYSIS_SET_COMPLETED', 'ATTEMPT_FAILED',
            'DECISION_REQUESTED', 'PLAN_OR_SOURCE_CHANGED', 'DEPENDENCY_CHANGED',
            'DECISION_UPDATED', 'INTEGRATION_FINISHED', 'USER_REPLAN_REQUESTED'}
STATUSES = {'PENDING', 'RUNNING', 'UNKNOWN', 'FAILED', 'CANCELLED', 'SUCCEEDED'}
MAX_JSON = 1024 * 1024


class ContractError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ContractError(message)


def obj(value, required, optional=()):
    require(type(value) is dict, 'Expected object')
    require(set(required) <= set(value), 'Missing fields: ' + ', '.join(sorted(set(required) - set(value))))
    require(set(value) <= set(required) | set(optional), 'Unknown fields: ' + ', '.join(sorted(set(value) - set(required) - set(optional))))


def string(value):
    require(type(value) is str and bool(value.strip()), 'Expected nonempty string')


def integer(value):
    require(type(value) is int and value >= 0, 'Expected nonnegative integer')


def boolean(value):
    require(type(value) is bool, 'Expected boolean')


def seq(value, nonempty=False):
    require(type(value) is list and (not nonempty or bool(value)), 'Expected array' + (' with items' if nonempty else ''))


def strings(value, allowed=None, nonempty=False):
    seq(value, nonempty)
    for item in value:
        string(item)
    require(len(set(value)) == len(value), 'Duplicate array entry')
    if allowed is not None:
        require(set(value) <= set(allowed), 'Unknown array value')


def enum(value, allowed):
    string(value)
    require(value in allowed, 'Unknown value: ' + value)


def refs(value):
    seq(value)
    found = {}
    for ref in value:
        obj(ref, {'report_id', 'sha256'})
        string(ref['report_id'])
        digest = ref['sha256']
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'Invalid SHA-256')
        require(ref['report_id'] not in found, 'Duplicate report ID')
        found[ref['report_id']] = digest
    return found


def subset_refs(value, allowed):
    found = refs(value)
    require(all(allowed.get(k) == v for k, v in found.items()), 'Unowned or mismatched evidence reference')
    return found


def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def json_file(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    # Bounded read, including pipes and files that grow after stat().
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_JSON + 1)
    require(len(raw) <= MAX_JSON, 'JSON exceeds 1 MiB')
    def invalid_constant(value):
        raise ContractError('Non-finite JSON number: ' + value)
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def request_check(request, workspace):
    obj(request, {'schema_version', 'message_type', 'stage', 'job_id', 'orchestration_run_id',
                  'session_id', 'trigger_ids', 'trigger_types', 'base_state_version', 'plan_version',
                  'fingerprint', 'snapshot', 'result_refs', 'constraints', 'request'})
    require(type(request['schema_version']) is int and request['schema_version'] == 1, 'Unsupported schema')
    require(request['message_type'] == 'orchestration_request' and request['stage'] == 'orchestrate', 'Wrong request protocol')
    for key in ('job_id', 'orchestration_run_id', 'session_id', 'fingerprint'):
        string(request[key])
    for key in ('base_state_version', 'plan_version'):
        integer(request[key])
    strings(request['trigger_ids'], nonempty=True)
    strings(request['trigger_types'], TRIGGERS, nonempty=True)
    if request['request'] is not None:
        string(request['request'])
    evidence = refs(request['result_refs'])
    snapshot = request['snapshot']
    obj(snapshot, {'source_revision', 'plan_confirmed', 'prerequisite_complete', 'paused',
                   'writer_unknown', 'modules', 'decision_candidate_ids'})
    string(snapshot['source_revision'])
    for key in ('plan_confirmed', 'prerequisite_complete', 'paused', 'writer_unknown'):
        boolean(snapshot[key])
    strings(snapshot['decision_candidate_ids'])
    seq(snapshot['modules'], nonempty=True)
    modules, attempts = {}, set()
    for module in snapshot['modules']:
        obj(module, {'module_id', 'group', 'blocked_stages', 'attempts'})
        string(module['module_id'])
        require(module['module_id'] not in modules, 'Duplicate module ID')
        modules[module['module_id']] = module
        enum(module['group'], {'boot', 'main'})
        strings(module['blocked_stages'], STAGES)
        seq(module['attempts'])
        for attempt in module['attempts']:
            obj(attempt, {'attempt_id', 'stage', 'status', 'tool', 'error_class', 'cause_key', 'process_terminated'})
            string(attempt['attempt_id'])
            require(attempt['attempt_id'] not in attempts, 'Duplicate attempt ID')
            attempts.add(attempt['attempt_id'])
            enum(attempt['stage'], STAGES)
            enum(attempt['status'], STATUSES)
            enum(attempt['tool'], {'opencode', 'claude', 'codex', 'build', 'human'})
            boolean(attempt['process_terminated'])
            for key in ('error_class', 'cause_key'):
                if attempt[key] is not None:
                    string(attempt[key])
    constraints = request['constraints']
    obj(constraints, {'profile', 'allowed_proposals', 'auto_retry_limit', 'readable_evidence'})
    require(constraints['profile'] == 'claude-manual-v1', 'Unsupported offline profile')
    strings(constraints['allowed_proposals'], KINDS)
    require(type(constraints['auto_retry_limit']) is int and constraints['auto_retry_limit'] == 0, 'Manual profile requires auto_retry_limit 0')
    seq(constraints['readable_evidence'])
    workspace = Path(workspace).resolve(strict=True)
    require(workspace.is_dir(), 'Evidence workspace must be a directory')
    seen = set()
    for item in constraints['readable_evidence']:
        obj(item, {'report_id', 'sha256', 'path'})
        subset_refs([{'report_id': item['report_id'], 'sha256': item['sha256']}], evidence)
        require(item['report_id'] not in seen, 'Duplicate readable evidence')
        seen.add(item['report_id'])
        string(item['path'])
        relative = Path(item['path'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'Evidence path must stay within workspace')
        resolved = (workspace / relative).resolve(strict=True)
        require(resolved.is_relative_to(workspace) and resolved.is_file(), 'Evidence path escapes workspace or is not a file')
        require(file_digest(resolved) == item['sha256'], 'Evidence file hash mismatch')
    require(seen == set(evidence), 'Every report must have a readable evidence file')
    return modules, evidence


def attempt_for(proposal, modules):
    target = proposal['target']
    require(len(target['module_ids']) == 1 and target['stage'] in STAGES - {'device_test'}, 'Retry/escalation requires one executable module stage')
    attempts = [a for a in modules[target['module_ids'][0]]['attempts'] if a['stage'] == target['stage']]
    require(bool(attempts), 'No previous attempt for target')
    previous = attempts[-1]
    require(previous['attempt_id'] == proposal['data']['previous_attempt_id'], 'Previous attempt is not the latest target attempt')
    require(previous['cause_key'] == proposal['data']['cause_key'], 'Cause does not match previous attempt')
    return previous, attempts


def proposal_check(proposal, request, modules, used_refs):
    obj(proposal, {'proposal_key', 'kind', 'target', 'reason', 'evidence_refs', 'data'})
    string(proposal['proposal_key']); string(proposal['reason'])
    enum(proposal['kind'], request['constraints']['allowed_proposals'])
    obj(proposal['target'], {'module_ids', 'stage'})
    strings(proposal['target']['module_ids'], modules)
    if proposal['target']['stage'] is not None:
        enum(proposal['target']['stage'], STAGES | {'integration', 'review'})
    subset_refs(proposal['evidence_refs'], used_refs)
    require(bool(proposal['evidence_refs']), 'Proposal requires evidence')
    kind, data = proposal['kind'], proposal['data']
    if kind in {'RETRY', 'TOOL_ESCALATION'}:
        fields = {'previous_attempt_id', 'cause_key'} | ({'changed_approach'} if kind == 'RETRY' else {'requested_tool', 'model_policy', 'difficulty_evidence'})
        obj(data, fields)
        for value in data.values():
            string(value)
        previous, attempts = attempt_for(proposal, modules)
        if kind == 'TOOL_ESCALATION':
            require(proposal['target']['stage'] == 'code', 'Opus escalation only applies to implementation')
            require(data['requested_tool'] == 'claude' and data['model_policy'] == 'opus', 'Escalation must use Claude Opus')
            require(previous['tool'] == 'opencode' and previous['error_class'] == 'FIX', 'Escalation requires code FIX evidence; environment errors do not count')
    elif kind == 'PLAN_CHANGE':
        obj(data, {'base_plan_version', 'changes'})
        integer(data['base_plan_version'])
        require(data['base_plan_version'] == request['plan_version'], 'Plan version mismatch')
        seq(data['changes'], nonempty=True)
        keys = set()
        for change in data['changes']:
            obj(change, {'operation', 'module_id', 'new_module_key', 'before', 'after', 'reason'})
            enum(change['operation'], {'add', 'update', 'deactivate'})
            string(change['reason'])
            if change['operation'] == 'add':
                string(change['new_module_key'])
                require(change['module_id'] is None and change['before'] is None, 'New modules cannot supply server IDs or before state')
                key = ('new', change['new_module_key'])
            else:
                enum(change['module_id'], modules)
                require(change['module_id'] in proposal['target']['module_ids'], 'Changed module outside target')
                require(change['new_module_key'] is None, 'Existing module cannot be renumbered')
                key = ('existing', change['module_id'])
                plan_description(change['before'], modules)
            require(key not in keys, 'Duplicate plan change')
            keys.add(key)
            if change['operation'] == 'deactivate':
                require(change['after'] is None, 'Deactivation after must be null')
            else:
                plan_description(change['after'], modules)
                require(change['module_id'] not in change['after']['dependency_module_ids'], 'Self dependency')
    elif kind == 'DECISION':
        obj(data, {'candidate_ids', 'question', 'options', 'recommendation', 'affected_stages', 'blocking'})
        strings(data['candidate_ids'], request['snapshot']['decision_candidate_ids'])
        string(data['question']); string(data['recommendation'])
        strings(data['options'], nonempty=True)
        require(len(data['options']) >= 2, 'Decision needs at least two alternatives')
        strings(data['affected_stages'], STAGES, nonempty=True)
        require(bool(proposal['target']['module_ids']), 'Decision requires affected modules')
        boolean(data['blocking'])
    else:
        obj(data, {'source_revision', 'image_refs', 'cases'})
        require(data['source_revision'] == request['snapshot']['source_revision'], 'Verification source mismatch')
        subset_refs(data['image_refs'], used_refs)
        seq(data['cases'], nonempty=True)
        seen = set()
        for case in data['cases']:
            obj(case, {'case_id', 'method', 'expected_result'})
            for value in case.values():
                string(value)
            require(case['case_id'] not in seen, 'Duplicate verification case')
            seen.add(case['case_id'])
    return preview(proposal, request, modules)


def plan_description(value, modules):
    # A conservative manual-only subset. DAG correctness still belongs to O1/O3.
    obj(value, {'name', 'group', 'scope', 'dependency_module_ids', 'required_cases'})
    string(value['name']); string(value['scope'])
    enum(value['group'], {'boot', 'main'})
    strings(value['dependency_module_ids'], modules)
    strings(value['required_cases'], nonempty=True)


def preview(proposal, request, modules):
    reasons = []
    if proposal['kind'] in {'RETRY', 'TOOL_ESCALATION'}:
        previous, _ = attempt_for(proposal, modules)
        snapshot, target = request['snapshot'], proposal['target']
        module, stage = modules[target['module_ids'][0]], target['stage']
        if previous['status'] not in {'FAILED', 'CANCELLED'} or not previous['process_terminated']:
            reasons.append('PREVIOUS_PROCESS_NOT_CONFIRMED_STOPPED')
        if snapshot['paused']:
            reasons.append('PAUSED')
        if stage != 'analysis' and not snapshot['plan_confirmed']:
            reasons.append('PLAN_NOT_CONFIRMED')
        if stage != 'analysis' and module['group'] == 'main' and not snapshot['prerequisite_complete']:
            reasons.append('PREREQUISITES_INCOMPLETE')
        if stage in {'code', 'build'} and snapshot['writer_unknown']:
            reasons.append('WRITER_UNKNOWN')
        if stage in module['blocked_stages']:
            reasons.append('DECISION_HOLD')
    return {'proposal_key': proposal['proposal_key'], 'status': 'BLOCKED' if reasons else 'WAITING_USER',
            'reasons': reasons or ['MANUAL_REVIEW_REQUIRED'], 'execution_performed': False}


def validate(request, result, workspace, current_request=None):
    modules, evidence = request_check(request, workspace)
    obj(result, {'schema_version', 'message_type', 'job_id', 'orchestration_run_id', 'session_id',
                 'trigger_ids', 'base_state_version', 'plan_version', 'fingerprint', 'outcome',
                 'summary', 'result_refs', 'proposals'}, {'error_class'})
    require(type(result['schema_version']) is int and result['schema_version'] == 1, 'Unsupported result schema')
    require(result['message_type'] == 'orchestration_result', 'Wrong result protocol')
    for key in ('job_id', 'orchestration_run_id', 'session_id', 'trigger_ids', 'base_state_version', 'plan_version', 'fingerprint'):
        require(type(result[key]) is type(request[key]) and result[key] == request[key], 'Correlation mismatch: ' + key)
    enum(result['outcome'], {'SUCCEEDED', 'FAILED'})
    string(result['summary'])
    used = subset_refs(result['result_refs'], evidence)
    seq(result['proposals'])
    if result['outcome'] == 'FAILED':
        require('error_class' in result, 'Failed result needs error_class')
        enum(result['error_class'], {'ENVIRONMENT', 'CONTRACT', 'INSUFFICIENT_EVIDENCE'})
        require(not result['proposals'], 'Failed result cannot propose actions')
    else:
        require('error_class' not in result, 'Successful result cannot contain error_class')
    reviews, seen = [], set()
    for proposal in result['proposals']:
        review = proposal_check(proposal, request, modules, used)
        require(proposal['proposal_key'] not in seen, 'Duplicate proposal key')
        seen.add(proposal['proposal_key'])
        reviews.append(review)
    freshness = 'NOT_CHECKED'
    if current_request is not None:
        request_check(current_request, workspace)
        require(current_request['job_id'] == request['job_id'], 'Current snapshot belongs to another job')
        freshness = 'MATCH' if all(current_request[k] == request[k] for k in ('base_state_version', 'plan_version', 'fingerprint')) else 'STALE'
        if freshness == 'STALE':
            reviews = [dict(x, status='STALE', reasons=['SNAPSHOT_CHANGED']) for x in reviews]
    canonical = json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return {'status': 'VALID_REVIEW_ONLY', 'outcome': result['outcome'], 'freshness': freshness,
            'execution_performed': False, 'result_sha256': hashlib.sha256(canonical).hexdigest(),
            'proposal_reviews': reviews}


def check_agent(root=ROOT):
    text = (root / AGENT).read_text()
    parts = text.split('---', 2)
    require(len(parts) == 3 and not parts[0].strip(), 'Missing YAML frontmatter')
    # Deliberately support only this package's simple four-scalar format.
    metadata = {}
    for line in parts[1].strip().splitlines():
        key, sep, value = line.partition(':')
        require(bool(sep) and key not in metadata, 'Invalid or duplicate frontmatter field')
        metadata[key] = value.strip()
    obj(metadata, {'name', 'description', 'tools', 'model'})
    require(metadata['name'] == 'bsp-upgrade-orchestrator', 'Agent name mismatch')
    string(metadata['description'])
    require(metadata['tools'] == 'Read, Glob, Grep' and metadata['model'] == 'inherit', 'Agent permissions or model changed')
    require(len(parts[2].strip()) > 100, 'Agent instructions missing')
    for path in [GUIDE, *REFERENCES]:
        require((root / path).is_file(), 'Missing agent reference: ' + str(path))
        require(str(path) in parts[2], 'Agent does not reference: ' + str(path))
    return {'status': 'PASS', 'name': metadata['name'], 'tools': metadata['tools'], 'claude_invoked': False}


def export_package(destination, root=ROOT):
    check_agent(root)
    destination = Path(destination)
    require(not destination.exists() and not destination.is_symlink(), 'Export destination already exists; choose a new directory')
    files = [AGENT, GUIDE, Path('scripts/claude_orchestrator.py'), *REFERENCES,
             *sorted((root / 'examples/claude-orchestrator').rglob('*'))]
    files = [p.relative_to(root) if p.is_absolute() else p for p in files if not p.is_absolute() or p.is_file()]
    # Read everything before creating the output; never install globally or merge
    # into a user's existing .claude directory.
    payloads = {}
    for relative in files:
        path = root / relative
        require(not path.is_symlink(), 'Package source symlink is not supported')
        content = path.read_bytes()
        if relative in REFERENCES:
            # Reference copies are frozen excerpts. Their repository cross-links
            # become text; no broken links or hidden dependency on source checkout.
            content = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                             lambda m: m[0] if '://' in m[2] or m[2].startswith('#') else f'{m[1]} (repository reference: {m[2]})',
                             content.decode()).encode()
        payloads[relative] = content
    destination.mkdir(parents=True, exist_ok=False)
    for relative, content in payloads.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = {str(p): hashlib.sha256(content).hexdigest() for p, content in payloads.items()}
    (destination / 'package-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return {'status': 'EXPORTED', 'path': str(destination.resolve()), 'files': len(manifest), 'claude_invoked': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check-agent')
    export = sub.add_parser('export'); export.add_argument('--output', required=True)
    for command in ('check-request', 'validate'):
        p = sub.add_parser(command)
        p.add_argument('--request', required=True); p.add_argument('--workspace', required=True)
        if command == 'validate':
            p.add_argument('--result', required=True); p.add_argument('--current-request')
    args = parser.parse_args(argv)
    try:
        if args.command == 'check-agent':
            output = check_agent()
        elif args.command == 'export':
            output = export_package(args.output)
        else:
            request = json_file(args.request)
            if args.command == 'check-request':
                request_check(request, args.workspace)
                output = {'status': 'VALID_MANUAL_REQUEST', 'execution_performed': False}
            else:
                current = json_file(args.current_request) if args.current_request else None
                output = validate(request, json_file(args.result), args.workspace, current)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (ContractError, OSError, ValueError, RecursionError) as error:
        print(json.dumps({'status': 'INVALID', 'error': str(error), 'execution_performed': False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
