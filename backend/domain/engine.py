import json
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from backend.domain.policy import (STAGES, ACTIVE, Conflict, uid, now, fingerprint, valid, gate,
                                   module_done, implementation_tool, reviewer, project, file_hash, demo_complete_reason, vendor_traceability)

DEFAULT_MODULES = [('Bootloader', 'boot'), ('Kernel / BSP', 'boot'), ('Ethernet', 'main'), ('Display', 'main'), ('Camera', 'main')]
_NO_COMMAND = object()


def new_stage(name):
    return {'status': 'PENDING', 'validity': 'UNVERIFIED', 'attempts': [], 'result': None,
            'required_cases': ['boot', 'functional'] if name == 'device_test' else ['required']}


class Engine:
    def __init__(self, store, artifacts):
        self.store, self.artifacts = store, Path(artifacts)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        from backend.domain.reports import ReportIntake
        from backend.domain.orchestration import Orchestration
        self.reports = ReportIntake(self)
        self.orchestration = Orchestration(self)

    @staticmethod
    def _command_digest(key, payload, job_id=None, expected=None):
        if not isinstance(key, str) or not key or len(key) > 180:
            raise Conflict('명령 식별자가 필요합니다.', 'IDEMPOTENCY_REQUIRED', 400)
        return fingerprint({'job_id': job_id, 'payload': payload, 'expected': expected})

    @staticmethod
    def _command_replay(c, key, digest):
        old = c.execute('SELECT payload_hash,result FROM commands WHERE key=?', (key,)).fetchone()
        if not old:
            return _NO_COMMAND
        if old['payload_hash'] != digest:
            raise Conflict('같은 명령 식별자에 다른 내용이 있습니다.', 'IDEMPOTENCY_CONFLICT')
        return json.loads(old['result'])

    def command(self, key, payload, operation, job_id=None, expected=None):
        digest = self._command_digest(key, payload, job_id, expected)
        with self.store.transaction() as c:
            replay = self._command_replay(c, key, digest)
            if replay is not _NO_COMMAND:
                return replay
            job = self.store.get(c, job_id) if job_id else None
            if job and expected != job['version']:
                raise Conflict('상태가 변경되었습니다. 최신 상태에서 다시 시도하세요.', 'VERSION_CONFLICT')
            result = operation(c, job)
            c.execute('INSERT INTO commands VALUES(?,?,?,?)', (key, digest, json.dumps(result), now()))
            return result

    def create(self, key, config, title, mode, modules=None):
        payload = deepcopy({'action': 'start', 'config': config, 'title': title, 'mode': mode, 'modules': modules})
        digest = self._command_digest(key, payload)
        with self.store.connection() as c:
            replay = self._command_replay(c, key, digest)
        if replay is not _NO_COMMAND:
            return replay
        from backend.settings import prepare_job_profile
        # Capability/source/file probes can launch local commands; never hold SQLite locks.
        prepared = prepare_job_profile(deepcopy(payload['config']))
        def run(c, _):
            specs = payload['modules'] or prepared.get('modules') or [{'name': n, 'group': g} for n, g in DEFAULT_MODULES]
            if not specs or len(specs) > 100 or len({x['name'] for x in specs}) != len(specs):
                raise Conflict('모듈 목록이 비어 있거나 중복되었습니다.', 'INVALID_MODULES', 422)
            job = {'id': uid(), 'title': payload['title'], 'mode': payload['mode'], 'execution': payload['config']['execution'], 'version': 0,
                   'created_at': now(), 'paused': False, 'plan_version': 1, 'confirmed_plan': None,
                   'profile': prepared, 'fingerprint': fingerprint(prepared), 'source_revision': prepared['source_revision'],
                   'session': {'id': uid(), 'tool': 'claude', 'status': 'SIMULATED' if payload['config']['execution'] == 'demo' else 'NOT_CONNECTED'},
                   'modules': [{'id': uid(), 'name': x['name'], 'group': x['group'], 'stages': {n: new_stage(n) for n in STAGES}, 'changes': [{'id': uid(), 'intent': '벤더 변경 보존', 'disposition': 'needs_analysis', 'evidence': None}]} for x in specs],
                   'decisions': [], 'prompts': [], 'integration': {'status': 'PENDING', 'evidence': None}, 'final_review': None}
            if prepared.get('module_report_version', 1) == 2:
                inventory = prepared['vendor_inventory']['changes']
                for module, spec in zip(job['modules'], specs):
                    module.update(stable_key=spec.get('stable_key') or spec['name'], target_paths=spec.get('target_paths', []), dependency_module_ids=[], required_cases=[], completion_conditions=[], active=True, introduced_version=1)
                    paths = module['target_paths']
                    module['changes'] = [dict(item, id=item['change_id'], disposition='needs_analysis', evidence=None) for item in inventory if module['stable_key'] in item.get('module_keys', []) or any(item['path'] == path or item['path'].startswith(path.rstrip('/') + '/') for path in paths)]
            self.store.save(c, job, 'JOB_CREATED', {'execution': payload['config']['execution']})
            self.orchestration.enqueue(c, job, 'JOB_STARTED', job['id'])
            return {'job_id': job['id'], 'version': job['version']}
        # Recheck atomically after preparation: another creator may have committed meanwhile.
        return self.command(key, payload, run)

    def snapshot(self, job_id, metadata=False):
        job = project(self.store.snapshot(job_id))
        if not metadata or job['profile'].get('module_report_version', 1) == 1 and not self.orchestration.enabled(job):
            return job
        profile = job['profile']
        job['profile'] = {key: profile[key] for key in ['workspace', 'host', 'account', 'execution', 'runner', 'module_report_version', 'orchestration', 'max_analysis'] if key in profile}
        for key in ['plan_history', 'vendor_inventory']:
            job.pop(key, None)
        job['session'].pop('history', None)
        def result_metadata(result):
            if not isinstance(result, dict):
                return result
            keys = ['outcome', 'error_class', 'cause_key', 'source_revision', 'report_id', 'report_sha256', 'review_report_id', 'artifact', 'review', 'simulation', 'manual_override', 'cases', 'sha256', 'artifact_id', 'test_plan_version']
            value = {key: result[key] for key in keys if key in result}
            if result.get('evidence'):
                value['evidence'] = str(result['evidence'])[:2000]
            return value
        for module in job['modules']:
            module.pop('plan_history', None)
            module['change_count'] = len(module.get('changes', []))
            module['changes'] = [{key: change[key] for key in ['id', 'change_id', 'disposition', 'decision_id', 'report_id'] if key in change} for change in module.get('changes', [])[:50]]
            for stage in module['stages'].values():
                stage['result'] = result_metadata(stage.get('result'))
                stage['attempt_count'] = len(stage['attempts'])
                stage['attempts'] = [{key: (result_metadata(value) if key == 'result' else value) for key, value in attempt.items() if key not in {'request', 'review_request', 'token', 'owner', 'transport', 'process_receipt'}} for attempt in stage['attempts'][-10:]]
        job['integration'].pop('history', None)
        job['integration']['result'] = result_metadata(job['integration'].get('result'))
        if 'attempt' in job['integration']:
            job['integration']['attempt'] = {key: value for key, value in job['integration']['attempt'].items() if key not in {'request', 'token', 'owner', 'result', 'transport', 'process_receipt'}}
        job['decision_count'] = len(job['decisions'])
        job['decisions'] = [{key: value for key, value in decision.items() if key not in {'history', 'transport'}} for decision in job['decisions'][-100:]]
        job['prompt_count'] = len(job['prompts'])
        job['prompts'] = job['prompts'][-20:]
        job['scope_hold_count'] = len(job.get('scope_holds', []))
        job['scope_holds'] = job.get('scope_holds', [])[-50:]
        return job

    def automatic_device_test(self, run):
        from backend.services.gui_test_host import automatic_result
        return automatic_result(self, run)

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
                if not all(valid(m['stages']['analysis']) for m in job['modules'] if m.get('active', True)):
                    raise Conflict('모든 필수 분석을 먼저 완료해야 합니다.')
                reason = vendor_traceability(job)
                if reason or job.get('scope_holds'):
                    raise Conflict(reason or '판단 후보 보류를 먼저 해결하세요.', 'GATE_BLOCKED')
                job['confirmed_plan'] = job['plan_version']
            elif action in {'pause', 'resume'}:
                if action == 'resume' and job.get('gui_revalidation', {}).get('status') == 'AWAITING_APPROVAL':
                    raise Conflict('GUI 재검증 대상과 순서를 먼저 승인하세요.')
                job['paused'] = action == 'pause'
            elif action == 'approve-gui-revalidation':
                proposal = job.get('gui_revalidation', {})
                if proposal.get('status') != 'AWAITING_APPROVAL' or data.get('run_id') != proposal.get('run_id'):
                    raise Conflict('현재 GUI 재검증 계획이 아닙니다.')
                proposal['status'] = 'APPROVED'
                proposal['approved_at'] = now()
                job['paused'] = False
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
                d['applied_source_revision'] = job['source_revision']
                d['applied_plan_version'] = job['plan_version']
                d['applied_at'] = now()
                self.orchestration.decision_applied(c, job, d['id'], d['applied_evidence'])
            elif action == 'link-vendor-decision':
                module = self.module(job, data.get('module_id'))
                change = next((item for item in module.get('changes', []) if item.get('change_id', item.get('id')) == data.get('change_id')), None)
                decision = next((item for item in job['decisions'] if item['id'] == data.get('decision_id')), None)
                if not change or change.get('disposition') not in {'needs_decision', 'excluded'} or not decision or not str(data.get('reason', '')).strip():
                    raise Conflict('A vendor judgment, explicit decision, and linking reason are required.', status=422)
                if module['id'] not in decision['affected_modules'] and '*' not in decision['affected_modules']:
                    raise Conflict('Decision does not cover this vendor change module.', status=422)
                change.setdefault('decision_history', []).append({'decision_id': change.get('decision_id'), 'reason': data['reason'], 'at': now()})
                change['decision_id'] = decision['id']
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
                reason = vendor_traceability(job)
                if reason or job.get('scope_holds'):
                    raise Conflict(reason or 'Active scope holds prevent final review.', 'GATE_BLOCKED')
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
            elif action == 'replan':
                if not self.orchestration.enabled(job) or not str(data.get('request', '')).strip():
                    raise Conflict('Enabled orchestration and a replan request are required.', status=422)
                self.orchestration.enqueue(c, job, 'USER_REPLAN_REQUESTED', key, {'request': data['request'][:4000]})
                return {'job_id': job_id, 'version': job['version']}
            elif action in {'classify-candidate', 'dismiss-candidate'}:
                self.orchestration.classify(c, job, data, dismiss=action == 'dismiss-candidate')
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
            if action == 'prompt' and data.get('intent', 'note') in {'note', 'question'} and self.orchestration.enabled(job):
                self.store.audit(c, job, action.upper())
            else:
                self.store.save(c, job, action.upper(), {'module_id': data.get('module_id')})
            trigger = {'invalidate': 'PLAN_OR_SOURCE_CHANGED', 'resolve': 'DECISION_UPDATED', 'apply-decision': 'DECISION_UPDATED', 'link-vendor-decision': 'DECISION_UPDATED', 'decision': 'DECISION_REQUESTED'}.get(action)
            if trigger:
                self.orchestration.enqueue(c, job, trigger, key)
            return {'job_id': job_id, 'version': job['version']}
        if action == 'apply-proposal':
            return self.orchestration.apply(job_id, data.get('proposal_id'), key, expected, 'human')
        if action == 'reconcile-run':
            return self.orchestration.reconcile(job_id, data.get('run_id'), key, expected)
        if action == 'reconcile-attempt':
            return self.reconcile_attempt(job_id, data.get('module_id'), data.get('stage'), key, expected)
        return self.command(key, {'action': action, 'data': data}, run, job_id, expected)

    def module_request(self, c, job, module, name, attempt):
        roles = {'analysis': 'analyst', 'design': 'designer', 'code': 'implementer', 'build': 'builder', 'review': 'reviewer', 'verification': 'verifier', 'integration': 'integration'}
        refs = []
        stages = module.get('stages', {}) if module else {}
        predecessors = STAGES[:STAGES.index(name)] if name in STAGES else STAGES[:-1]
        for previous in predecessors:
            result = (stages.get(previous, {}).get('result') or {})
            if result.get('report_id') and result.get('report_sha256'):
                refs.append({'report_id': result['report_id'], 'sha256': result['report_sha256']})
        source = (stages.get('code', {}).get('result') or {}).get('source_revision') or job['source_revision']
        artifact = (stages.get('build', {}).get('result') or {}).get('artifact') or {}
        if name in {'design', 'code', 'review', 'build', 'integration'}:
            source = job.get('working_source_revision', source)
        elif name == 'verification':
            source = artifact.get('source_revision', source)
        profile = job['profile']
        included = []
        if name == 'integration':
            for item in job['modules']:
                if not item.get('active', True):
                    continue
                result = item['stages']['verification']['result'] or {}
                included.append({'module_id': item['id'], 'source_revision': result.get('source_revision', job['source_revision']), 'report_id': result.get('report_id')})
                if result.get('report_id'):
                    refs.append({'report_id': result['report_id'], 'sha256': result['report_sha256']})
        expectations = {'required_case_ids': stages.get(name, {}).get('required_cases', []) if name in {'verification', 'integration'} else [], 'source_revision': source, 'source_identity': {'kind': 'workspace-content-sha256-v1', 'sha256': source}, 'artifact_sha256': artifact.get('sha256'), 'allowed_read_roots': [profile.get(key, '') for key in ['workspace', 'old_base', 'vendor_tree', 'new_base']], 'allowed_write_paths': (module or {}).get('target_paths', []) if name == 'code' else [], 'instruction_revision': profile.get('instruction_snapshots', {}).get(roles[name], {}).get('sha256'), 'included_modules': included, 'reviewed_source_revision': None, 'reviewed_diff_sha256': None}
        if name == 'analysis':
            source = profile['vendor_inventory']['sha256']
            expectations['source_revision'] = source
            expectations['source_identity'] = {'kind': 'input-inventory-sha256-v1', 'sha256': source}
        elif name in {'verification', 'integration'} and artifact.get('id'):
            expectations['source_identity'] = {'kind': 'artifact-source-sha256-v1', 'sha256': source, 'artifact': {'path': str((self.artifacts / job['id'] / artifact['id']).resolve()), 'sha256': artifact['sha256']}}
        if name == 'code':
            expectations['diff_format'] = 'bsp-workspace-diff-v1'
        request_module = {key: value for key, value in (module or {}).items() if key not in {'stages', 'changes'}}
        request_module['vendor_changes'] = profile.get('vendor_inventory', {}).get('changes', []) if name == 'analysis' else (module or {}).get('changes', [])
        request_module['scope_change_ids'] = [change.get('change_id', change.get('id')) for change in (module or {}).get('changes', [])]
        return {'schema_version': 2, 'message_type': 'module_request', 'job_id': job['id'], 'module_id': module['id'] if module else None, 'stage': name, 'attempt_id': attempt['id'], 'session_id': attempt['session_id'], 'report_id': uid(), 'plan_version': job['plan_version'], 'fingerprint': job['fingerprint'], 'role': roles[name], 'source_revision': source, 'input_result_refs': refs, 'report_expectations': expectations, 'module': request_module, 'model_policy': attempt['model'], 'source_paths': {key: profile.get(key, '') for key in ['old_base', 'vendor_tree', 'new_base']}}

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
            profile = job['profile']
            v2 = profile.get('module_report_version', 1) == 2
            review_tool = None
            if name == 'code':
                tool, model = implementation_tool(s['attempts'], available, hard=bool(s.get('tool_escalation')), profile=profile)
                if v2:
                    review_tool = reviewer([tool], available, profile=profile)
            else:
                tool, model = ('manual', '') if name == 'device_test' else ('build', '') if name == 'build' else ('verification', '') if name == 'verification' and job['profile'].get('runner') == 'native' else ('claude', 'configured')
                if v2 and name == 'verification' and profile.get('runner') != 'native':
                    tool = 'build'
            if v2 and name != 'device_test':
                from backend.adapters.capabilities import tool_supports_role
                roles = {'analysis': 'analyst', 'design': 'designer', 'code': 'implementer', 'build': 'builder', 'verification': 'verifier'}
                dispatch_tool = 'build' if name in {'build', 'verification'} else tool
                if not tool_supports_role(profile, dispatch_tool, roles[name]):
                    raise Conflict('The configured tool does not support this frozen v2 role.', 'CAPABILITY_UNSUPPORTED', 422)
            a = {'id': uid(), 'ordinal': len(s['attempts']) + 1, 'status': 'WAITING_INPUT' if name == 'device_test' else 'RUNNING', 'tool': tool, 'model': model, 'session_id': uid(), 'fingerprint': job['fingerprint'], 'started_at': now(), 'ended_at': None, 'owner': owner, 'token': uid(), 'execution': job['execution']}
            a['writable'] = writable
            if v2 and name != 'device_test':
                a['request'] = self.module_request(c, job, m, name, a)
                a['request']['report_expectations']['selected_tool'] = dispatch_tool
                self.orchestration.launch_intent(c, job_id, a['id'], name)
                if name == 'code':
                    a['review_tool'] = review_tool
                    review = dict(a, session_id=uid(), model='configured')
                    a['review_request'] = self.module_request(c, job, m, 'review', review)
                    a['review_request']['input_result_refs'] = a['request']['input_result_refs']
                    a['review_request']['report_expectations'].update(selected_tool=review_tool, author_tools=[a['tool']])
                    self.orchestration.launch_intent(c, job_id, a['review_request']['report_id'], 'review')
            if writable:
                c.execute('INSERT INTO leases VALUES(?,?,?)', (resource, a['id'], a['token']))
            s['attempts'].append(a)
            if name == 'device_test':
                if s.get('automation'):
                    s['attempts'][-2]['automation'] = s.pop('automation')
                s.pop('automation_blocked', None)
                s['result'] = None  # The prior attempt retains its result; a new test has none yet.
            s['status'] = a['status']
            self.store.save(c, job, 'ATTEMPT_STARTED', {'attempt_id': a['id'], 'module_id': m['id'], 'stage': name})
            return {'job': job, 'module': m, 'stage': name, 'attempt': a}

    def finish(self, job_id, module_id, name, attempt_id, token, result):
        snapshot = self.store.snapshot(job_id)
        module = self.module(snapshot, module_id)
        attempt = next((a for a in module['stages'][name]['attempts'] if a['id'] == attempt_id), None)
        if attempt and attempt.get('request'):
            claim = {'job': snapshot, 'module': module, 'stage': name, 'attempt': dict(attempt, token=token), '_observations': result.get('observations', {})}
            prepared = self.reports.prepare(claim, result)
            with self.store.transaction() as c:
                return self.reports.commit(c, self.store.get(c, job_id), prepared)
        with self.store.transaction() as c:
            job = self.store.get(c, job_id)
            m = self.module(job, module_id)
            s = m['stages'][name]
            a = s['attempts'][-1]
            if a['id'] != attempt_id or a['token'] != token or a['fingerprint'] != job['fingerprint'] or s['status'] not in {'RUNNING', 'CANCEL_REQUESTED'}:
                return False
            if (name in {'code', 'build'} or (name == 'verification' and job['profile'].get('runner') == 'native')) and not c.execute('SELECT 1 FROM leases WHERE attempt=? AND token=?', (attempt_id, token)).fetchone():
                return False
            result = self._legacy_completion(c, job, a['id'], result, review=name == 'code')
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
            if self.orchestration.enabled(job):
                from backend.contracts import report_hash
                identifier = 'legacy-' + attempt_id
                raw = json.loads(json.dumps(result))
                digest = report_hash(raw)
                normalized = {'legacy_report': True, 'wire_result': raw, 'files': [], 'missing_fields': ['classification', 'test_results', 'decision_requests']}
                c.execute('INSERT OR IGNORE INTO agent_reports VALUES(?,?,?,?,?,?,?,?,?)', (identifier, job_id, attempt_id, module_id, name, digest, 'APPLIED', json.dumps(normalized), now()))
            if outcome == 'FAILED':
                self.orchestration.enqueue(c, job, 'ATTEMPT_FAILED', attempt_id)
            if name == 'analysis' and all(valid(item['stages']['analysis']) for item in job['modules']):
                self.orchestration.enqueue(c, job, 'ANALYSIS_SET_COMPLETED', 'analysis:' + str(job['plan_version']))
            return True

    def _legacy_completion(self, c, job, attempt_id, result, review=False):
        """Frozen v1 is enforced here even when callers bypass every transport adapter."""
        from backend.contracts import ContractError, report_hash, validate_legacy_result
        try:
            validated = validate_legacy_result(result)
            if review and validated.get('review') is not None:
                validate_legacy_result(validated['review'])
            if job['profile'].get('module_report_version', 1) != 1:
                raise ContractError(safe_message='Frozen v2 attempt is missing its allocated v2 request.')
            return validated
        except ContractError as exc:
            c.execute('INSERT INTO report_receipts VALUES(?,?,?,?,?,?,?)', (uid(), 'legacy-rejected:' + attempt_id, job['id'], report_hash(result), 'CONFLICT', json.dumps({'raw_result': result, 'contract_error': exc.safe_message}), now()))
            return {'outcome': 'FAILED', 'evidence': exc.safe_message, 'error_class': 'CONTRACT'}

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
                job = json.loads(row[0]); changed = False; execution_changed = False
                for m in job['modules']:
                    for s in m['stages'].values():
                        if s['status'] in {'RUNNING', 'DISPATCHING', 'CANCEL_REQUESTED'}:
                            s['status'] = 'UNKNOWN'
                            s['attempts'][-1]['status'] = 'UNKNOWN'
                            changed = True
                            execution_changed = True
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
                    execution_changed = True
                for d in job['decisions']:
                    if d['sync_status'] == 'SENDING':
                        d['sync_status'] = 'UNKNOWN'
                        changed = True
                if changed:
                    persist = self.store.save if execution_changed or not self.orchestration.enabled(job) else self.store.audit
                    persist(c, job, 'RECOVERY_REQUIRED')
            for row in c.execute("SELECT * FROM orchestration_runs WHERE status IN ('PENDING','RUNNING')").fetchall():
                data = json.loads(row['data'])
                data.update(status='UNKNOWN', error='Worker restarted; process identity reconciliation is required.')
                c.execute("UPDATE orchestration_runs SET status='UNKNOWN',data=? WHERE id=?", (json.dumps(data), row['id']))
            c.execute("UPDATE coordinator_lanes SET status='UNKNOWN'")
        # Verification and immutable evidence preparation happen after the recovery commit.
        for job in self.store.all():
            for module in job['modules']:
                for name, stage in module['stages'].items():
                    if stage['status'] == 'UNKNOWN' and stage['attempts'] and stage['attempts'][-1].get('request'):
                        try:
                            self.reconcile_attempt(job['id'], module['id'], name, 'recover:' + stage['attempts'][-1]['id'], self.store.snapshot(job['id'])['version'])
                        except Conflict:
                            pass
            if job['integration']['status'] == 'UNKNOWN' and job['integration'].get('attempt', {}).get('request'):
                try:
                    self.reconcile_attempt(job['id'], None, 'integration', 'recover:' + job['integration']['attempt']['id'], self.store.snapshot(job['id'])['version'])
                except Conflict:
                    pass
            from backend.adapters.process import verify_receipt
            for run in self.orchestration.summary(job['id'])['runs']:
                if run['status'] == 'UNKNOWN':
                    receipt = self.orchestration.transport_context(run['id'])
                    if verify_receipt(receipt.get('process_receipt', {})).state == 'TERMINATED':
                        try:
                            self.orchestration.reconcile(job['id'], run['id'], 'recover-control:' + run['id'], self.store.snapshot(job['id'])['version'])
                        except Conflict:
                            pass

    def reconcile_attempt(self, job_id, module_id, name, key, expected):
        """Only stored launch identities are inspectable; no client PID or termination override."""
        import copy
        from backend.adapters.process import verify_receipt
        job = self.store.snapshot(job_id)
        module = self.module(job, module_id) if module_id is not None else None
        stage = module['stages'].get(name) if module else job['integration'] if name == 'integration' else None
        if not stage or stage['status'] != 'UNKNOWN':
            raise Conflict('Only UNKNOWN attempts can be reconciled.')
        attempt = stage['attempts'][-1] if module else stage['attempt']
        if not attempt.get('request'):
            raise Conflict('Legacy attempts require their existing external reconciliation path.')
        receipt = self.orchestration.transport_context(attempt['id'])
        process = receipt.get('process_receipt', {})
        verification = verify_receipt(process)
        process_state = getattr(verification, 'state', None)
        envelope = copy.deepcopy(receipt.get('result_envelope'))
        simulation_terminal = job['execution'] == 'demo' and envelope and envelope.get('transport', {}).get('simulation') is True
        if process_state != 'TERMINATED' and not simulation_terminal:
            # Do not consume the automatic recovery idempotency key for an unresolved process.
            return {'status': 'UNKNOWN', 'process_status': process_state or 'UNKNOWN', 'attempt_id': attempt['id'], 'version': job['version']}
        if name == 'code' and attempt.get('review_request') and not simulation_terminal:
            review_receipt = self.orchestration.transport_context(attempt['review_request']['report_id'])
            review_state = verify_receipt(review_receipt.get('process_receipt', {})).state
            positive_no_launch = self.orchestration.valid_not_launched(review_receipt)
            if review_state != 'TERMINATED' and not positive_no_launch:
                return {'status': 'UNKNOWN', 'process_status': review_state, 'attempt_id': attempt['id'], 'version': job['version']}
        if envelope is None:
            envelope = {'envelope_version': 1, 'wire_result': None, 'related_reports': [], 'observations': {}, 'transport': {'status': 'FAILED', 'error_class': 'ENVIRONMENT', 'error': 'Stored process termination verified; execution was interrupted without a durable authored result.'}}
        elif envelope.get('transport', {}).get('status') == 'UNKNOWN':
            envelope['transport']['status'] = 'FAILED'
            envelope['transport']['error'] = 'Previous interrupted process termination verified.'
            for related in envelope.get('related_reports', []):
                if related.get('transport', {}).get('status') == 'UNKNOWN':
                    related['transport']['status'] = 'FAILED'
        claim = {'job': job, 'module': module, 'stage': name, 'attempt': attempt, '_verified_terminal': True, '_observations': envelope.get('observations', {})}
        prepared = self.reports.prepare(claim, envelope)
        def apply(c, current):
            return self.reports.commit(c, current, prepared)
        return self.command(key, {'action': 'reconcile-attempt', 'attempt_id': attempt['id']}, apply, job_id, expected)

    def claim_integration(self, job_id, owner):
        with self.store.transaction() as c:
            job = self.store.get(c, job_id)
            if job['paused'] or job.get('scope_holds') or vendor_traceability(job) or job['integration']['status'] != 'PENDING' or not all(module_done(m) for m in job['modules']) or any(d['status'] != 'APPLIED' for d in job['decisions']):
                return None
            resource = job['profile']['workspace']
            if c.execute('SELECT 1 FROM leases WHERE resource=?', (resource,)).fetchone():
                return None
            if job['profile'].get('module_report_version', 1) == 2:
                from backend.adapters.capabilities import tool_supports_role
                if not tool_supports_role(job['profile'], 'build', 'integration'):
                    raise Conflict('The configured command does not support frozen v2 integration.', 'CAPABILITY_UNSUPPORTED', 422)
            a = {'id': uid(), 'token': uid(), 'owner': owner, 'status': 'RUNNING', 'fingerprint': job['fingerprint'], 'tool': 'build', 'model': '', 'session_id': uid()}
            a['writable'] = True
            if job['profile'].get('module_report_version', 1) == 2:
                a['request'] = self.module_request(c, job, None, 'integration', a)
                a['request']['report_expectations']['selected_tool'] = 'build'
                self.orchestration.launch_intent(c, job_id, a['id'], 'integration')
            c.execute('INSERT INTO leases VALUES(?,?,?)', (resource, a['id'], a['token']))
            job['integration'].update(status='RUNNING', attempt=a)
            self.store.save(c, job, 'INTEGRATION_STARTED')
            return {'job': job, 'module': {'id': None, 'name': '전체 통합', 'stages': {}, 'modules': job['modules']}, 'stage': 'integration', 'attempt': a}

    def finish_integration(self, claim, result):
        if claim['attempt'].get('request'):
            prepared = self.reports.prepare(claim, result)
            with self.store.transaction() as c:
                return self.reports.commit(c, self.store.get(c, claim['job']['id']), prepared)
        with self.store.transaction() as c:
            job = self.store.get(c, claim['job']['id']); a = claim['attempt']
            current = job['integration']
            if current['status'] != 'RUNNING' or current.get('attempt', {}).get('id') != a['id'] or job['fingerprint'] != a['fingerprint']:
                return False
            if not c.execute('SELECT 1 FROM leases WHERE attempt=? AND token=?', (a['id'], a['token'])).fetchone():
                return False
            result = self._legacy_completion(c, job, a['id'], result)
            if result.get('outcome') == 'UNKNOWN':
                current.update(status='UNKNOWN', evidence=result.get('evidence'), result=result)
                self.store.save(c, job, 'INTEGRATION_UNKNOWN', {'attempt_id': a['id']})
                return True
            passed = result.get('outcome') == 'SUCCEEDED' and bool(result.get('evidence')) and all(module_done(m) for m in job['modules'])
            current.update(status='SUCCEEDED' if passed else 'FAILED', evidence=result.get('evidence'), result=result, ended_at=now())
            c.execute('DELETE FROM leases WHERE attempt=? AND token=?', (a['id'], a['token']))
            self.store.save(c, job, 'INTEGRATION_FINISHED', {'outcome': current['status']})
            self.orchestration.enqueue(c, job, 'INTEGRATION_FINISHED', a['id'])
            return True
