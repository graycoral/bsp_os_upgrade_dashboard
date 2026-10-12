import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from backend.domain.policy import (STAGES, ACTIVE, Conflict, uid, now, fingerprint, valid, gate,
                                   module_done, implementation_tool, reviewer, project, file_hash, demo_complete_reason)

DEFAULT_MODULES = [('Bootloader', 'boot'), ('Kernel / BSP', 'boot'), ('Ethernet', 'main'), ('Display', 'main'), ('Camera', 'main')]


def new_stage(name):
    return {'status': 'PENDING', 'validity': 'UNVERIFIED', 'attempts': [], 'result': None,
            'required_cases': ['boot', 'functional'] if name == 'device_test' else ['required']}


class Engine:
    def __init__(self, store, artifacts):
        self.store, self.artifacts = store, Path(artifacts)
        self.artifacts.mkdir(parents=True, exist_ok=True)

    def command(self, key, payload, operation, job_id=None, expected=None):
        if not key or len(key) > 180:
            raise Conflict('명령 식별자가 필요합니다.', 'IDEMPOTENCY_REQUIRED', 400)
        digest = fingerprint({'job_id': job_id, 'payload': payload, 'expected': expected})
        with self.store.transaction() as c:
            old = c.execute('SELECT * FROM commands WHERE key=?', (key,)).fetchone()
            if old:
                if old['payload_hash'] != digest:
                    raise Conflict('같은 명령 식별자에 다른 내용이 있습니다.', 'IDEMPOTENCY_CONFLICT')
                return json.loads(old['result'])
            job = self.store.get(c, job_id) if job_id else None
            if job and expected != job['version']:
                raise Conflict('상태가 변경되었습니다. 최신 상태에서 다시 시도하세요.', 'VERSION_CONFLICT')
            result = operation(c, job)
            c.execute('INSERT INTO commands VALUES(?,?,?,?)', (key, digest, json.dumps(result), now()))
            return result

    def create(self, key, config, title, mode, modules=None):
        def run(c, _):
            from backend.settings import prepare_job_profile
            prepared = prepare_job_profile(config)
            specs = modules or prepared.get('modules') or [{'name': n, 'group': g} for n, g in DEFAULT_MODULES]
            if not specs or len(specs) > 100 or len({x['name'] for x in specs}) != len(specs):
                raise Conflict('모듈 목록이 비어 있거나 중복되었습니다.', 'INVALID_MODULES', 422)
            job = {'id': uid(), 'title': title, 'mode': mode, 'execution': config['execution'], 'version': 0,
                   'created_at': now(), 'paused': False, 'plan_version': 1, 'confirmed_plan': None,
                   'profile': prepared, 'fingerprint': fingerprint(prepared), 'source_revision': prepared['source_revision'],
                   'session': {'id': uid(), 'tool': 'claude', 'status': 'SIMULATED' if config['execution'] == 'demo' else 'NOT_CONNECTED'},
                   'modules': [{'id': uid(), 'name': x['name'], 'group': x['group'], 'stages': {n: new_stage(n) for n in STAGES}, 'changes': [{'id': uid(), 'intent': '벤더 변경 보존', 'disposition': 'needs_analysis', 'evidence': None}]} for x in specs],
                   'decisions': [], 'prompts': [], 'integration': {'status': 'PENDING', 'evidence': None}, 'final_review': None}
            self.store.save(c, job, 'JOB_CREATED', {'execution': config['execution']})
            return {'job_id': job['id'], 'version': job['version']}
        return self.command(key, {'action': 'start', 'config': config, 'title': title, 'mode': mode, 'modules': modules}, run)

    def snapshot(self, job_id):
        return project(self.store.snapshot(job_id))

    @staticmethod
    def module(job, module_id):
        m = next((m for m in job['modules'] if m['id'] == module_id), None)
        if not m:
            raise Conflict('모듈을 찾을 수 없습니다.', 'NOT_FOUND', 404)
        return m

    def act(self, job_id, key, expected, action, data):
        def run(c, job):
            if action == 'confirm':
                if data.get('plan_version') != job['plan_version']:
                    raise Conflict('현재 계획 버전을 확인해 주세요.')
                if not all(valid(m['stages']['analysis']) for m in job['modules']):
                    raise Conflict('모든 필수 분석을 먼저 완료해야 합니다.')
                job['confirmed_plan'] = job['plan_version']
            elif action in {'pause', 'resume'}:
                job['paused'] = action == 'pause'
            elif action == 'retry-session':
                if job['execution'] != 'bridge' or job['session']['status'] != 'FAILED':
                    raise Conflict('종료가 확인된 연결 실패만 재시도할 수 있습니다. 실행 불명은 먼저 확인하세요.')
                job['session'].setdefault('history', []).append({k: v for k, v in job['session'].items() if k != 'history'})
                job['session'].update(id=uid(), status='NOT_CONNECTED')
                job['session'].pop('external_id', None)
            elif action == 'retry':
                m = self.module(job, data.get('module_id'))
                name = data.get('stage')
                if name not in STAGES:
                    raise Conflict('알 수 없는 단계입니다.', status=422)
                s = m['stages'][name]
                if s['status'] not in {'FAILED', 'CANCELLED'}:
                    raise Conflict('실패/취소된 단계만 재시도할 수 있습니다.')
                if s['attempts'][-1]['id'] != data.get('previous_attempt_id'):
                    raise Conflict('이전 실행 식별자가 일치하지 않습니다.')
                reason = gate(job, m, name)
                if reason:
                    raise Conflict(reason, 'GATE_BLOCKED')
                s['status'] = 'PENDING'
                s['validity'] = 'UNVERIFIED'
            elif action == 'decision':
                affected = data.get('affected_modules', [])
                if not affected or any(x != '*' and not any(m['id'] == x for m in job['modules']) for x in affected):
                    raise Conflict('판단의 영향 모듈을 지정하세요.', status=422)
                title = str(data.get('title', '')).strip()
                if not title:
                    raise Conflict('판단할 내용을 입력하세요.', status=422)
                job['decisions'].append({'id': uid(), 'title': title[:2000], 'affected_modules': affected, 'status': 'OPEN', 'resolution': None, 'jira_key': None, 'sync_status': 'QUEUED' if job['execution'] == 'bridge' and (job['profile'].get('jira_url') or job['profile'].get('mcp_argv')) else 'NOT_CONFIGURED', 'created_at': now()})
            elif action == 'resolve':
                d = next((d for d in job['decisions'] if d['id'] == data.get('decision_id')), None)
                if not d or not data.get('resolution'):
                    raise Conflict('결정과 근거를 입력하세요.', status=422)
                d['status'] = 'RESOLVED'
                d['resolution'] = str(data['resolution'])[:4000]
            elif action == 'apply-decision':
                d = next((d for d in job['decisions'] if d['id'] == data.get('decision_id')), None)
                if not d or d['status'] != 'RESOLVED' or data.get('source_revision') != job['source_revision'] or not data.get('evidence'):
                    raise Conflict('결정 내용·현재 소스·반영 근거가 필요합니다.', status=422)
                d['status'] = 'APPLIED'
                d['applied_evidence'] = str(data['evidence'])[:4000]
            elif action == 'prompt':
                text = str(data.get('prompt', '')).strip()
                if not text:
                    raise Conflict('명령을 입력하세요.', status=422)
                intent = data.get('intent', 'note')
                if intent not in {'note', 'question', 'retry', 'pause', 'resume'}:
                    raise Conflict('명령 의도를 선택하세요.', status=422)
                if intent in {'pause', 'resume'}:
                    job['paused'] = intent == 'pause'
                if intent == 'retry':
                    m = self.module(job, data.get('module_id'))
                    stage = next((n for n in STAGES if not valid(m['stages'][n])), None)
                    if not stage or m['stages'][stage]['status'] not in {'FAILED', 'CANCELLED'}:
                        raise Conflict('대상 모듈에 재시도할 실패 단계가 없습니다.')
                    reason = gate(job, m, stage)
                    if reason:
                        raise Conflict(reason, 'GATE_BLOCKED')
                    m['stages'][stage].update(status='PENDING', validity='UNVERIFIED')
                job['prompts'].append({'id': uid(), 'text': text[:4000], 'target': data.get('module_id'), 'intent': intent, 'status': 'PENDING' if intent == 'question' else 'RECORDED', 'note': '실행 정책을 검사한 명령' if intent != 'note' else '요청 기록됨 · 자동 실행하지 않음', 'created_at': now()})
            elif action == 'manual-test':
                self.manual(c, job, data)
            elif action == 'demo-complete-module':
                self.complete_demo_module(c, job, data)
            elif action == 'retry-integration':
                if job['integration']['status'] not in {'FAILED', 'CANCELLED'}:
                    raise Conflict('실패한 통합 검증만 재시도할 수 있습니다.')
                job['integration'].setdefault('history', []).append({k:v for k,v in job['integration'].items() if k != 'history'})
                job['integration']['status'] = 'PENDING'
            elif action == 'final-review':
                if job['integration']['status'] != 'SUCCEEDED' or not all(module_done(m) for m in job['modules']) or any(d['status'] != 'APPLIED' for d in job['decisions']):
                    raise Conflict('필수 단계·통합 검증·결정 반영을 먼저 완료하세요.')
                if any(x['disposition'] == 'needs_analysis' or not x['evidence'] for m in job['modules'] for x in m['changes']):
                    raise Conflict('근거 없는 벤더 변경이 있습니다.')
                if not data.get('reviewer') or not data.get('evidence'):
                    raise Conflict('최종 검토자와 근거가 필요합니다.', status=422)
                job['final_review'] = {'reviewer': data['reviewer'], 'evidence': data['evidence'], 'at': now(), 'fingerprint': job['fingerprint']}
            elif action == 'invalidate':
                if not data.get('source_revision') or not data.get('reason'):
                    raise Conflict('새 소스 기준과 변경 사유가 필요합니다.', status=422)
                if any(s['status'] in ACTIVE for m in job['modules'] for s in m['stages'].values()):
                    raise Conflict('실행 종료를 확인한 뒤 소스 기준을 변경하세요.')
                job['source_revision'] = data['source_revision']
                job['fingerprint'] = fingerprint([job['fingerprint'], data['source_revision']])
                job['plan_version'] += 1
                job['confirmed_plan'] = None
                job['integration'] = {'status': 'PENDING', 'evidence': None, 'history': [job['integration']]}
                job['final_review'] = None
                for m in job['modules']:
                    for s in m['stages'].values():
                        s['validity'] = 'INVALIDATED'
                        s['status'] = 'PENDING'
                        s['invalidation_reason'] = data['reason']
                    for change in m['changes']:
                        change['disposition'] = 'needs_analysis'
                        change['evidence'] = None
            elif action == 'reconcile-demo':
                if job['execution'] != 'demo':
                    raise Conflict('실제 실행 상태는 브리지에서 확인해야 합니다.')
                for m in job['modules']:
                    for s in m['stages'].values():
                        if s['status'] == 'UNKNOWN':
                            a = s['attempts'][-1]
                            a.update(status='FAILED', ended_at=now(), result={'evidence': '모의 작업은 외부 프로세스가 없음을 확인'})
                            s['status'] = 'FAILED'
                            c.execute('DELETE FROM leases WHERE attempt=?', (a['id'],))
            elif action == 'cancel':
                m = self.module(job, data.get('module_id'))
                name = data.get('stage')
                if name not in STAGES:
                    raise Conflict('단계를 지정하세요.', status=422)
                s = m['stages'][name]
                if s['status'] not in {'RUNNING', 'UNKNOWN', 'WAITING_INPUT'}:
                    raise Conflict('취소할 실행이 없습니다.')
                if s['status'] == 'WAITING_INPUT':
                    s['status'] = 'CANCELLED'
                    s['attempts'][-1].update(status='CANCELLED', ended_at=now(), cancellation_evidence='수동 결과 대기: 외부 실행 없음')
                else:
                    s['status'] = 'CANCEL_REQUESTED'
                    s['attempts'][-1]['status'] = 'CANCEL_REQUESTED'
            else:
                raise Conflict('지원하지 않는 동작입니다.', 'UNSUPPORTED', 422)
            self.store.save(c, job, action.upper(), {'module_id': data.get('module_id')})
            return {'job_id': job_id, 'version': job['version']}
        return self.command(key, {'action': action, 'data': data}, run, job_id, expected)

    def claim(self, job_id, module_id, name, owner):
        with self.store.transaction() as c:
            job = self.store.get(c, job_id)
            m = self.module(job, module_id)
            s = m['stages'][name]
            if s['status'] != 'PENDING' or gate(job, m, name):
                return None
            writable = name in {'code', 'build'} or (name == 'verification' and job['profile'].get('runner') == 'native')
            resource = job['profile']['workspace']
            if writable and c.execute('SELECT 1 FROM leases WHERE resource=?', (resource,)).fetchone():
                return None
            available = {x: bool(job['profile']['agents'].get(x)) for x in ['opencode', 'claude', 'codex']}
            if job['execution'] == 'demo':
                available = dict.fromkeys(available, True)
            if name == 'code':
                tool, model = implementation_tool(s['attempts'], available)
            else:
                tool, model = ('manual', '') if name == 'device_test' else ('build', '') if name == 'build' else ('verification', '') if name == 'verification' and job['profile'].get('runner') == 'native' else ('claude', 'configured')
            a = {'id': uid(), 'ordinal': len(s['attempts']) + 1, 'status': 'WAITING_INPUT' if name == 'device_test' else 'RUNNING', 'tool': tool, 'model': model, 'session_id': uid(), 'fingerprint': job['fingerprint'], 'started_at': now(), 'ended_at': None, 'owner': owner, 'token': uid(), 'execution': job['execution']}
            if writable:
                c.execute('INSERT INTO leases VALUES(?,?,?)', (resource, a['id'], a['token']))
            s['attempts'].append(a)
            s['status'] = a['status']
            self.store.save(c, job, 'ATTEMPT_STARTED', {'attempt_id': a['id'], 'module_id': m['id'], 'stage': name})
            return {'job': job, 'module': m, 'stage': name, 'attempt': a}

    def finish(self, job_id, module_id, name, attempt_id, token, result):
        with self.store.transaction() as c:
            job = self.store.get(c, job_id)
            m = self.module(job, module_id)
            s = m['stages'][name]
            a = s['attempts'][-1]
            if a['id'] != attempt_id or a['token'] != token or a['fingerprint'] != job['fingerprint'] or s['status'] not in {'RUNNING', 'CANCEL_REQUESTED'}:
                return False
            if (name in {'code', 'build'} or (name == 'verification' and job['profile'].get('runner') == 'native')) and not c.execute('SELECT 1 FROM leases WHERE attempt=? AND token=?', (attempt_id, token)).fetchone():
                return False
            if result.get('outcome') == 'UNKNOWN':
                a.update(status='UNKNOWN', result=result)
                s.update(status='UNKNOWN', validity='UNVERIFIED', result=result)
                self.store.save(c, job, 'EXECUTION_UNKNOWN', {'attempt_id': attempt_id})
                return True
            if s['status'] == 'CANCEL_REQUESTED':
                outcome = 'CANCELLED'
            else:
                outcome = result.get('outcome')
                if outcome not in {'SUCCEEDED', 'FAILED'} or not result.get('evidence'):
                    outcome = 'FAILED'
                    result = {'outcome': outcome, 'evidence': '필수 구조화 결과/근거 누락', 'error_class': 'CONTRACT'}
                if outcome == 'SUCCEEDED' and gate(job | {'paused': False}, m, name):
                    outcome = 'FAILED'
                    result = {'evidence': '실행 중 의존 조건 변경: 결과 보류', 'error_class': 'DEPENDENCY'}
                if outcome == 'SUCCEEDED' and name == 'code':
                    rev = result.get('review', {})
                    available = dict.fromkeys(['claude', 'codex'], True) if job['execution'] == 'demo' else {k: bool(job['profile']['agents'].get(k)) for k in ['claude', 'codex']}
                    if rev.get('tool') != reviewer([a['tool']], available) or rev.get('outcome') != 'PASS' or rev.get('revision') != result.get('source_revision', job['source_revision']) or not rev.get('session_id') or rev['session_id'] == a['session_id'] or not rev.get('evidence'):
                        outcome = 'FAILED'
                        result['error_class'] = 'REVIEW'
                        result['evidence'] = '현재 변경에 대한 별도 리뷰 근거 필요'
            if outcome == 'SUCCEEDED' and name == 'build':
                artifact = result.get('artifact', {})
                file = (self.artifacts / job_id / str(artifact.get('id', ''))).resolve()
                if file.parent != (self.artifacts / job_id).resolve() or not file.is_file() or not artifact.get('sha256') or file_hash(file) != artifact['sha256']:
                    outcome = 'FAILED'
                    result['error_class'] = 'ARTIFACT'
                    result['evidence'] = '등록된 산출물 파일/해시가 필요합니다.'
            a.update(status=outcome, ended_at=now(), result=result, error_class=result.get('error_class'), cause_key=result.get('cause_key'))
            s.update(status=outcome, validity='CURRENT' if outcome == 'SUCCEEDED' else 'UNVERIFIED', result=result)
            if outcome == 'SUCCEEDED' and name == 'analysis':
                for change in m['changes']:
                    change.update(disposition='port_required', evidence=result['evidence'])
            c.execute('DELETE FROM leases WHERE attempt=? AND token=?', (attempt_id, token))
            self.store.save(c, job, 'ATTEMPT_FINISHED', {'attempt_id': attempt_id, 'outcome': outcome})
            return True

    def manual(self, c, job, data):
        m = self.module(job, data.get('module_id'))
        s = m['stages']['device_test']
        if s['status'] != 'WAITING_INPUT' or data.get('attempt_id') != s['attempts'][-1]['id']:
            raise Conflict('현재 수동 시험 실행이 아닙니다.')
        reason = gate(job, m, 'device_test')
        if reason:
            raise Conflict(reason)
        build = m['stages']['build']['result'] or {}
        artifact = build.get('artifact', {})
        if not artifact.get('sha256') or not artifact.get('id'):
            raise Conflict('검증된 이미지 산출물이 없습니다.', status=422)
        cases = data.get('cases', {})
        if s['attempts'][-1]['fingerprint'] != job['fingerprint']:
            raise Conflict('현재 입력 기준의 수동 시험이 아닙니다.')
        if data.get('performed_at'):
            try:
                performed = datetime.fromisoformat(str(data['performed_at']).replace('Z', '+00:00'))
                if performed.tzinfo is None or performed > datetime.now(timezone.utc) + timedelta(minutes=5):
                    raise ValueError()
            except ValueError:
                raise Conflict('시간대가 있는 유효한 수행 시각을 입력하세요.', status=422)
        if data.get('evidence_id'):
            evidence_path = (self.artifacts / job['id'] / str(data['evidence_id'])).resolve()
            if evidence_path.parent != (self.artifacts / job['id']).resolve() or not evidence_path.is_file() or evidence_path.stat().st_size == 0:
                raise Conflict('해당 작업의 유효한 근거 파일을 선택하세요.', status=422)
        context = {'sha256': artifact['sha256'], 'source_revision': artifact.get('source_revision', job['source_revision']),
                   'test_plan_version': job['plan_version']}
        if any(data.get(k) not in (None, '', v) for k, v in context.items()):
            raise Conflict('이미지·소스·시험 계획 기준이 일치하지 않습니다.', status=422)
        if not isinstance(cases, dict) or set(cases) != set(s['required_cases']) or any(v not in ('PASS', 'FAIL') for v in cases.values()):
            raise Conflict('모든 필수 사례의 PASS/FAIL을 기록하세요.', status=422)
        outcome = 'SUCCEEDED' if all(v == 'PASS' for v in cases.values()) else 'FAILED'
        result = {k: data.get(k) or None for k in ['board_id', 'operator', 'performed_at', 'evidence_id']}
        result.update(context, module_id=m['id'], attempt_id=s['attempts'][-1]['id'], cases=cases,
                      artifact_id=artifact['id'], fingerprint=job['fingerprint'], submitted_at=now(),
                      simulation=job['execution'] == 'demo')
        s.update(status=outcome, validity='CURRENT' if outcome == 'SUCCEEDED' else 'UNVERIFIED', result=result)
        s['attempts'][-1].update(status=outcome, ended_at=now(), result=result)

    def complete_demo_module(self, c, job, data):
        m = self.module(job, data.get('module_id'))
        reason = demo_complete_reason(job, m)
        if reason:
            raise Conflict(reason, 'GATE_BLOCKED')
        if data.get('plan_version') != job['plan_version'] or data.get('fingerprint') != job['fingerprint']:
            raise Conflict('현재 데모 계획과 입력 기준을 확인하세요.')
        completed_at = now()
        for name, s in m['stages'].items():
            if valid(s):
                continue
            if s['attempts'] and s['attempts'][-1]['status'] in ACTIVE | {'WAITING_INPUT'}:
                previous = s['attempts'][-1]
                previous.update(status='CANCELLED', ended_at=completed_at,
                                cancellation_evidence='데모 수동 완료로 대체 · 외부 프로세스 없음')
                c.execute('DELETE FROM leases WHERE attempt=? AND token=?', (previous['id'], previous['token']))
            result = {'simulation': True, 'manual_override': True,
                      'evidence': f'데모 수동 완료 · {m["name"]} / {name} · 실제 실행/시험 아님'}
            s['attempts'].append({'id': uid(), 'ordinal': len(s['attempts']) + 1, 'status': 'SUCCEEDED',
                                  'tool': 'manual-demo', 'model': '', 'session_id': uid(),
                                  'fingerprint': job['fingerprint'], 'started_at': completed_at,
                                  'ended_at': completed_at, 'owner': 'dashboard', 'token': uid(),
                                  'execution': 'demo', 'result': result})
            s.update(status='SUCCEEDED', validity='CURRENT', result=result)

    def recover(self):
        """Called only by the single worker while holding its OS lock."""
        with self.store.transaction() as c:
            for row in c.execute('SELECT data FROM jobs').fetchall():
                job = json.loads(row[0]); changed = False
                for m in job['modules']:
                    for s in m['stages'].values():
                        if s['status'] in {'RUNNING', 'DISPATCHING', 'CANCEL_REQUESTED'}:
                            s['status'] = 'UNKNOWN'
                            s['attempts'][-1]['status'] = 'UNKNOWN'
                            changed = True
                if job['execution'] == 'bridge' and job['session']['status'] in {'READY', 'CONNECTING'}:
                    job['session']['status'] = 'NEEDS_RECONCILIATION'
                    changed = True
                for p in job['prompts']:
                    if p['status'] == 'RUNNING':
                        p['status'] = 'UNKNOWN'
                        changed = True
                if job['integration']['status'] == 'RUNNING':
                    job['integration']['status'] = 'UNKNOWN'
                    changed = True
                for d in job['decisions']:
                    if d['sync_status'] == 'SENDING':
                        d['sync_status'] = 'UNKNOWN'
                        changed = True
                if changed:
                    self.store.save(c, job, 'RECOVERY_REQUIRED')

    def claim_integration(self, job_id, owner):
        with self.store.transaction() as c:
            job = self.store.get(c, job_id)
            if job['paused'] or job['integration']['status'] != 'PENDING' or not all(module_done(m) for m in job['modules']) or any(d['status'] != 'APPLIED' for d in job['decisions']):
                return None
            resource = job['profile']['workspace']
            if c.execute('SELECT 1 FROM leases WHERE resource=?', (resource,)).fetchone():
                return None
            a = {'id': uid(), 'token': uid(), 'owner': owner, 'status': 'RUNNING', 'fingerprint': job['fingerprint'], 'tool': 'build', 'model': '', 'session_id': uid()}
            c.execute('INSERT INTO leases VALUES(?,?,?)', (resource, a['id'], a['token']))
            job['integration'].update(status='RUNNING', attempt=a)
            self.store.save(c, job, 'INTEGRATION_STARTED')
            return {'job': job, 'module': {'id': None, 'name': '전체 통합', 'stages': {}, 'modules': job['modules']}, 'stage': 'integration', 'attempt': a}

    def finish_integration(self, claim, result):
        with self.store.transaction() as c:
            job = self.store.get(c, claim['job']['id']); a = claim['attempt']
            current = job['integration']
            if current['status'] != 'RUNNING' or current.get('attempt', {}).get('id') != a['id'] or job['fingerprint'] != a['fingerprint']:
                return False
            if not c.execute('SELECT 1 FROM leases WHERE attempt=? AND token=?', (a['id'], a['token'])).fetchone():
                return False
            if result.get('outcome') == 'UNKNOWN':
                current.update(status='UNKNOWN', evidence=result.get('evidence'), result=result)
                self.store.save(c, job, 'INTEGRATION_UNKNOWN', {'attempt_id': a['id']})
                return True
            passed = result.get('outcome') == 'SUCCEEDED' and bool(result.get('evidence')) and all(module_done(m) for m in job['modules'])
            current.update(status='SUCCEEDED' if passed else 'FAILED', evidence=result.get('evidence'), result=result, ended_at=now())
            c.execute('DELETE FROM leases WHERE attempt=? AND token=?', (a['id'], a['token']))
            self.store.save(c, job, 'INTEGRATION_FINISHED', {'outcome': current['status']})
            return True
