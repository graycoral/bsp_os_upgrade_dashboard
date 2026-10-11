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
    return all(valid(s) for s in module['stages'].values())


def boot_done(job):
    return all(module_done(m) for m in job['modules'] if m['group'] == 'boot')


def demo_complete_reason(job, module):
    if job['execution'] != 'demo' or module['group'] != 'boot':
        return '데모의 부트로더 선행 모듈만 수동 완료할 수 있습니다.'
    if module_done(module):
        return '이미 완료된 모듈입니다.'
    return gate(job, module, 'design')


def gate(job, module, name):
    if job['execution'] == 'bridge' and job['session']['status'] != 'READY':
        return 'Claude 조정 세션 연결/복구 확인 필요'
    if job['paused']:
        return '신규 배정 일시 중지'
    for d in job['decisions']:
        if d['status'] != 'APPLIED' and (module['id'] in d['affected_modules'] or '*' in d['affected_modules']):
            return f"사람 판단 대기: {d['title']}"
    if name == 'analysis':
        return None
    if job['confirmed_plan'] != job['plan_version']:
        return '최초 분석 계획 확인 필요'
    if module['group'] != 'boot' and not boot_done(job):
        return '부트로더 선행 그룹 전체 완료 대기'
    before = STAGES[:STAGES.index(name)]
    if any(not valid(module['stages'][n]) for n in before):
        return '이전 단계의 유효한 완료 결과 필요'
    return None


def implementation_tool(attempts, available, hard=False):
    failures = {}
    for a in attempts:
        if a['status'] == 'FAILED' and a.get('error_class') == 'FIX' and a.get('cause_key'):
            failures[a['cause_key']] = failures.get(a['cause_key'], 0) + 1
    escalate = hard or max(failures.values(), default=0) >= 2
    if available.get('opencode') and not escalate:
        return 'opencode', 'configured'
    if available.get('claude'):
        return 'claude', 'opus' if escalate else 'configured'
    raise Conflict('사용 가능한 구현 도구가 없습니다.', 'TOOL_UNAVAILABLE')


def reviewer(authors, available):
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
