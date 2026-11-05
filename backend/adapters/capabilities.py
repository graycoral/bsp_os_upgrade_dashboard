"""Explicit, bounded capability negotiation. Never infer an undocumented probe flag."""
from datetime import datetime, timezone

from pydantic import ValidationError

from backend.contracts import CapabilityDocument, ContractError, parse_json, report_hash
from backend.contracts.wire import ROLE_STAGE
from backend.domain.policy import Conflict

ROLES = ['analyst', 'designer', 'implementer', 'builder', 'reviewer', 'verifier', 'integration', 'orchestrator']
TOOL_ROLES = {
    'opencode': {'implementer'},
    'claude': {'analyst', 'designer', 'implementer', 'reviewer', 'orchestrator'},
    'codex': {'reviewer'},
    'build': {'builder', 'verifier', 'integration'},
}


def tool_supports_role(profile, tool, role, *, module_report_version=2, orchestration_version=None):
    """Consult the frozen capability and the fixed tool policy, never live probes."""
    if role not in TOOL_ROLES.get(tool, set()):
        return False
    snapshot = profile.get('contract_capabilities', {})
    if profile.get('execution') == 'demo' and snapshot.get('adapter') == 'simulation':
        cap = snapshot
    else:
        cap = snapshot.get('tools', {}).get(tool, {})
    if role not in cap.get('roles', []):
        return False
    if orchestration_version is not None:
        return role == 'orchestrator' and orchestration_version in cap.get('orchestration_versions', [])
    return role != 'orchestrator' and module_report_version in cap.get('module_report_versions', [])


def validate_tool_capability(profile, tool, payload, *, author_tools=None):
    """Reject unsupported frozen roles/protocols before any external launch."""
    def unsupported():
        raise ContractError('CAPABILITY_UNSUPPORTED', '$', 'Requested frozen tool role or protocol is unsupported.')

    expectations = payload.get('report_expectations', {})
    if not isinstance(expectations, dict):
        unsupported()
    if expectations.get('selected_tool', tool) != tool:
        unsupported()
    if payload.get('message_type') == 'orchestration_request':
        if (type(payload.get('schema_version')) is not int or payload['schema_version'] != 1
                or payload.get('stage') != 'orchestrate'
                or not tool_supports_role(profile, tool, 'orchestrator', orchestration_version=1)):
            unsupported()
        return
    role = payload.get('role')
    if (payload.get('message_type') != 'module_request'
            or type(payload.get('schema_version')) is not int or payload['schema_version'] != 2
            or not isinstance(role, str) or ROLE_STAGE.get(role) != payload.get('stage')
            or not tool_supports_role(profile, tool, role)):
        unsupported()
    if role == 'reviewer':
        bindings = [value for value in (author_tools, profile.get('_author_tools'), expectations.get('author_tools')) if value is not None]
        if not bindings:
            unsupported()
        for authors in bindings:
            if (not isinstance(authors, (list, tuple)) or not authors
                    or any(not isinstance(author, str) or author not in {'opencode', 'claude'} for author in authors)
                    or tool != ('codex' if 'claude' in authors else 'claude')
                    or tool in authors):
                unsupported()
        if bindings and any(list(value) != list(bindings[0]) for value in bindings[1:]):
            unsupported()


def _document(source, profile):
    if source.get('kind') == 'document':
        data = source.get('document')
        provenance = {'kind': 'document', 'sha256': report_hash(data)}
    elif source.get('kind') == 'command':
        from backend.adapters.process import run_process
        argv = source.get('argv')
        if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg and '\x00' not in arg for arg in argv):
            raise ValueError('Explicit capability command required.')
        result = run_process(argv, cwd=profile['workspace'], timeout=5, limit=65536)
        if result.unknown or result.error or result.code != 0:
            raise ValueError('Capability command failed.')
        data = parse_json(result.stdout, max_bytes=65536)
        provenance = {'kind': 'command', 'argv_sha256': report_hash(argv), 'response_sha256': report_hash(data),
                      'timeout_seconds': 5, 'max_bytes': 65536}
    else:
        raise ValueError('Capability source required.')
    document = CapabilityDocument.model_validate(data).model_dump(mode='json')
    return document, provenance


def freeze_capabilities(profile):
    requested = profile.get('module_report_version', 1)
    orchestration = profile.get('orchestration', {}).get('enabled', False)
    snapshot = {'schema_version': 1, 'adapter': profile.get('runner', 'bridge'),
                'module_report_versions': [1], 'orchestration_versions': [], 'roles': [],
                'tools': {}, 'authentication': 'UNVERIFIED', 'inference': 'UNVERIFIED',
                'captured_at': datetime.now(timezone.utc).isoformat()}
    if profile.get('execution', 'demo') == 'demo':
        snapshot.update(adapter='simulation', module_report_versions=[1, 2], orchestration_versions=[1], roles=ROLES)
        snapshot['provenance'] = {'kind': 'builtin-simulation', 'actual_model_call': False}
        return snapshot
    try:
        if profile.get('runner', 'bridge') == 'native':
            # prepare_job_profile has already performed the documented help/version
            # probes. No duplicate inference, authentication or invented flag probe.
            checks = profile.get('tool_checks', [])
            for check in checks:
                if check.get('status') != 'CLI_READY':
                    continue
                tool = check['name']
                roles = (['implementer'] if tool == 'opencode' else ['reviewer'] if tool == 'codex' else
                         ['analyst', 'designer', 'implementer', 'reviewer', 'orchestrator'])
                snapshot['tools'][tool] = {'module_report_versions': [1, 2], 'orchestration_versions': [1] if tool == 'claude' else [],
                                           'roles': roles, 'authentication': 'UNVERIFIED', 'inference': 'UNVERIFIED',
                                           'provenance': {'kind': 'native-help-version', 'version': check.get('version', ''),
                                                          'status': check['status']}}
            if profile.get('build_command'):
                snapshot['tools']['build'] = {'module_report_versions': [1, 2], 'orchestration_versions': [],
                    'command_result_versions': [1], 'roles': ['builder', 'verifier', 'integration'],
                    'provenance': {'kind': 'registered-command-contract', 'execution_verified': False}}
        else:
            for tool, source in profile.get('bridge_capabilities', {}).items():
                document, provenance = _document(source, profile)
                snapshot['tools'][tool] = document | {'provenance': provenance, 'authentication': 'UNVERIFIED', 'inference': 'UNVERIFIED'}
        required = {'claude': ['analyst', 'designer'], 'build': ['builder', 'verifier', 'integration']}
        if requested == 2:
            frozen_profile = dict(profile, contract_capabilities=snapshot)

            def eligible(tool, role):
                if tool == 'build':
                    configured = profile.get('build_command') if profile.get('runner') == 'native' else profile.get('build_argv')
                else:
                    configured = profile.get('agents', {}).get(tool)
                return bool(configured) and tool_supports_role(frozen_profile, tool, role)

            for tool, roles in required.items():
                if not all(eligible(tool, role) for role in roles):
                    raise ValueError('Required v2 role capability missing.')
            if not any(eligible(author, 'implementer') and eligible(reviewer, 'reviewer')
                       for author, reviewer in (('opencode', 'claude'), ('claude', 'codex'))):
                raise ValueError('No policy-compatible v2 implementation and independent review pair.')
            snapshot['module_report_versions'] = [1, 2]
        if orchestration:
            if (requested != 2 or not profile.get('agents', {}).get('claude')
                    or not tool_supports_role(dict(profile, contract_capabilities=snapshot), 'claude', 'orchestrator', orchestration_version=1)):
                raise ValueError('Orchestration capability missing.')
            snapshot['orchestration_versions'] = [1]
        snapshot['roles'] = sorted({role for cap in snapshot['tools'].values() for role in cap.get('roles', [])})
        return snapshot
    except (ValueError, OSError, ValidationError):
        raise Conflict('Requested module/orchestration contract capability is unsupported or could not be verified.', 'CAPABILITY_UNSUPPORTED', 422) from None
