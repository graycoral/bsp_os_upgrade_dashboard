"""Execution policy shared by API, scheduler and retries."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

STAGES = ('analysis', 'design', 'code', 'build', 'verification', 'device_test')
LABELS = dict(zip(STAGES, ('요구사항 분석', '설계', '코드 구현', '빌드', '검증', '장비 테스트')))
ACTIVE = {'RUNNING', 'DISPATCHING', 'CANCEL_REQUESTED', 'UNKNOWN'}


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Conflict(Exception):
    def __init__(self, message, code='CONFLICT', status=409):
        self.message, self.code, self.status = message, code, status


def valid(stage):
    return stage['status'] == 'SUCCEEDED' and stage.get('validity') == 'CURRENT'


def module_done(module):
    return module.get('active', True) is False or all(valid(s) for s in module['stages'].values())


def boot_done(job):
    return all(module_done(m) for m in job['modules'] if m['group'] == 'boot')


def demo_complete_reason(job, module):
    if job['execution'] != 'demo' or module['group'] != 'boot':
        return '데모의 부트로더 선행 모듈만 수동 완료할 수 있습니다.'
    if module_done(module):
        return '이미 완료된 모듈입니다.'
    return gate(job, module, 'design')


def gate(job, module, name):
    if not module.get('active', True):
        return '비활성 모듈'
    if job['execution'] == 'bridge' and job['session']['status'] != 'READY' and not job['profile'].get('orchestration', {}).get('enabled', False):
        return 'Claude 조정 세션 연결/복구 확인 필요'
    if job['paused']:
        return '신규 배정 일시 중지'
    for hold in job.get('scope_holds', []):
        affected_stages = hold.get('stages', STAGES)
        downstream = any(stage in STAGES and STAGES.index(stage) <= STAGES.index(name) for stage in affected_stages)
        if hold.get('status', 'ACTIVE') == 'ACTIVE' and module['id'] in hold.get('module_ids', []) and downstream:
            return '판단 후보 확인 대기: ' + hold.get('reason', hold['id'])
    for d in job['decisions']:
        if d['status'] != 'APPLIED' and name in d.get('affected_stages', STAGES) and (module['id'] in d['affected_modules'] or '*' in d['affected_modules']):
            return f"사람 판단 대기: {d['title']}"
    if name == 'analysis':
        return None
    if job['profile'].get('module_report_version', 1) == 2:
        for change in module.get('changes', []):
            if change.get('disposition') == 'needs_decision' and not applied_vendor_decision(job, module['id'], change):
                return '벤더 변경 판단 반영 대기: ' + str(change.get('change_id', change.get('id')))
    if job['confirmed_plan'] != job['plan_version']:
        return '최초 분석 계획 확인 필요'
    if module['group'] != 'boot' and not boot_done(job):
        return '부트로더 선행 그룹 전체 완료 대기'
    for dependency in module.get('dependency_module_ids', []):
        other = next((m for m in job['modules'] if m['id'] == dependency), None)
        if not other or not module_done(other):
            return '모듈 선행 조건 완료 대기'
    before = STAGES[:STAGES.index(name)]
    if any(not valid(module['stages'][n]) for n in before):
        return '이전 단계의 유효한 완료 결과 필요'
    return None


def applied_vendor_decision(job, module_id, change):
    """A classification is not an approval; require explicit current human application proof."""
    decision = next((item for item in job['decisions'] if item['id'] == change.get('decision_id')), None)
    return bool(decision and decision['status'] == 'APPLIED' and decision.get('resolution') and decision.get('applied_evidence') and decision.get('applied_source_revision') == job['source_revision'] and (module_id in decision['affected_modules'] or '*' in decision['affected_modules']))


def satisfied_candidate_decision(job, candidate):
    decision = next((item for item in job['decisions'] if item['id'] == candidate.get('decision_id')), None)
    if not decision or decision['status'] != 'APPLIED' or not decision.get('resolution') or not decision.get('applied_evidence') or decision.get('applied_source_revision') != job['source_revision']:
        return False
    if candidate.get('source_context', {}).get('source_revision') != job['source_revision']:
        return False
    modules = set(decision['affected_modules'])
    return ('*' in modules or set(candidate['affected_module_ids']) <= modules) and set(candidate['affected_stages']) <= set(decision.get('affected_stages', STAGES))


def vendor_traceability(job):
    """Global inventory coverage is needed for approval, never for analysis dispatch."""
    if job['profile'].get('module_report_version', 1) != 2:
        return None
    inventory = job['profile'].get('vendor_inventory', {})
    changes = inventory.get('changes', []) if isinstance(inventory, dict) else inventory
    for item in changes:
        change_id = item.get('change_id', item.get('id'))
        facts = [(m['id'], x) for m in job['modules'] if m.get('active', True) for x in m.get('changes', []) if x.get('change_id', x.get('id')) == change_id and x.get('disposition') not in {'needs_analysis', 'unclassified'}]
        if not facts or len({x.get('disposition') for _, x in facts}) != 1:
            return '벤더 변경 분류 누락 또는 충돌: ' + str(change_id)
        for module_id, fact in facts:
            if not fact.get('evidence'):
                return '벤더 변경 분류 근거 누락'
            if fact.get('disposition') in {'excluded', 'needs_decision'} and not applied_vendor_decision(job, module_id, fact):
                return '벤더 변경 판단·제외 승인 반영 근거 필요: ' + str(change_id)
    return None


def implementation_tool(attempts, available, hard=False, profile=None):
    failures = {}
    for a in attempts:
        if a['status'] == 'FAILED' and a.get('error_class') == 'FIX' and a.get('cause_key'):
            failures[a['cause_key']] = failures.get(a['cause_key'], 0) + 1
    escalate = hard or max(failures.values(), default=0) >= 2
    if profile and profile.get('module_report_version', 1) == 2:
        from backend.adapters.capabilities import tool_supports_role
        def eligible_pair(tool):
            if not available.get(tool) or not tool_supports_role(profile, tool, 'implementer'):
                return False
            try:
                reviewer([tool], available, profile=profile)
                return True
            except Conflict:
                return False
        if not escalate and eligible_pair('opencode'):
            return 'opencode', 'configured'
        if eligible_pair('claude'):
            return 'claude', 'opus' if escalate else 'configured'
        raise Conflict('No configured implementation and independent review pair supports the frozen v2 roles.', 'CAPABILITY_UNSUPPORTED', 422)
    if available.get('opencode') and not escalate:
        return 'opencode', 'configured'
    if available.get('claude'):
        return 'claude', 'opus' if escalate else 'configured'
    raise Conflict('사용 가능한 구현 도구가 없습니다.', 'TOOL_UNAVAILABLE')


def reviewer(authors, available, profile=None):
    if profile and profile.get('module_report_version', 1) == 2:
        from backend.adapters.capabilities import tool_supports_role
        if len(authors) != 1 or authors[0] not in {'opencode', 'claude'}:
            raise Conflict('The frozen v2 author has no permitted independent review policy.', 'CAPABILITY_UNSUPPORTED', 422)
        if not available.get(authors[0]) or not tool_supports_role(profile, authors[0], 'implementer'):
            raise Conflict('The author does not support the frozen v2 implementation role.', 'CAPABILITY_UNSUPPORTED', 422)
        desired = 'codex' if authors[0] == 'claude' else 'claude'
        if available.get(desired) and tool_supports_role(profile, desired, 'reviewer'):
            return desired
        raise Conflict('The required independent reviewer does not support the frozen v2 role.', 'CAPABILITY_UNSUPPORTED', 422)
    desired = 'codex' if 'claude' in authors else 'claude'
    if available.get(desired):
        return desired
    if available.get('claude'):
        return 'claude'
    raise Conflict('리뷰 도구를 설정해 주세요.', 'TOOL_UNAVAILABLE')


def progress(stages):
    units = []
    for s in stages:
        if s['status'] == 'NOT_APPLICABLE' and s.get('exclusion_reason'):
            continue
        count = max(1, len(s.get('required_cases', [])))
        units.extend([valid(s)] * count)
    done = sum(units)
    return {'done': done, 'total': len(units), 'percent': int(100 * done / len(units)) if units else None}


def project(job):
    """Decorate a detached snapshot; never persist display-derived state."""
    for m in job['modules']:
        for name, stage in m['stages'].items():
            stage['blocked_reason'] = gate(job, m, name) if not valid(stage) else None
            stage['can_retry'] = stage['status'] in {'FAILED', 'CANCELLED'} and not stage['blocked_reason']
        pending = next((n for n in STAGES if not valid(m['stages'][n])), None)
        m['current_stage'] = pending
        m['progress'] = progress(m['stages'].values())
        m['demo_complete_reason'] = demo_complete_reason(job, m)
        m['can_demo_complete'] = m['demo_complete_reason'] is None
    mapping = {'analysis': ['analysis'], 'implementation': ['design', 'code'], 'verification': ['verification'], 'build': ['build'], 'test': ['device_test']}
    job['progress'] = {key: progress([m['stages'][n] for m in job['modules'] for n in names]) for key, names in mapping.items()}
    units = [s for m in job['modules'] for s in m['stages'].values()]
    overall = progress(units)
    extra_done = 1 + int(job['confirmed_plan'] == job['plan_version']) + int(job['integration']['status'] == 'SUCCEEDED') + int(job['final_review'] is not None)
    total = overall['total'] + 4
    job['overall'] = {'done': overall['done'] + extra_done, 'total': total, 'percent': int(100 * (overall['done'] + extra_done) / total)}
    job['boot_ready'] = boot_done(job)
    job['groups'] = {g: progress([s for m in job['modules'] if m['group'] == g for s in m['stages'].values()]) for g in ['boot', 'main']}
    states = [s['status'] for s in units]
    job['health'] = 'UNKNOWN' if 'UNKNOWN' in states else 'DEGRADED' if 'FAILED' in states else 'OK'
    if job['final_review']:
        job['state'] = 'COMPLETED'
    elif all(module_done(m) for m in job['modules']):
        job['state'] = 'AWAITING_FINAL_REVIEW' if job['integration']['status'] == 'SUCCEEDED' else 'INTEGRATING'
    elif all(valid(m['stages']['analysis']) for m in job['modules']) and not job['confirmed_plan']:
        job['state'] = 'AWAITING_PLAN_CONFIRMATION'
    else:
        job['state'] = 'RUNNING' if job['confirmed_plan'] else 'ANALYZING'
    return job


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
