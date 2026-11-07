import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from backend.domain.engine import Engine
from backend.domain.policy import STAGES, uid, module_done, now, Conflict
from backend.storage.store import Store
from backend.adapters.bridge import Bridge


def demo_v2_result(claim):
    """Deterministic simulation evidence; never represents actual BSP/model testing."""
    from copy import deepcopy
    from backend.contracts import report_hash
    request = claim['attempt']['request']
    stage = request['stage']
    root = Path(claim['job']['profile']['workspace']).resolve()
    folder = root / '.bsp-dashboard' / 'simulation' / request['report_id']
    folder.mkdir(parents=True, exist_ok=True)
    log = folder / 'simulation.log'
    log.write_text('Simulation fixture: no model, BSP build, hardware, or external test executed.\n', encoding='utf-8')
    def ref(path, kind):
        return {'path': path.relative_to(root).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'kind': kind}
    evidence = [ref(log, 'log')]
    cases = request['report_expectations']['required_case_ids']
    details = {
        'analysis': {'vendor_changes': [{'change_id': item['change_id'], 'disposition': 'port_required', 'rationale': 'Simulation inventory fixture requires a simulated port.', 'affected_files': [item['path']], 'dependency_module_ids': [], 'required_cases': []} for item in request['module']['vendor_changes']]},
        'design': {'design_summary': 'Simulation fixture design.', 'target_files': [], 'interface_impacts': [], 'dependency_module_ids': [], 'verification_plan': []},
        'code': {'changed_files': [], 'diff_path': None, 'fix_description': 'Simulation fixture; no source edited.', 'previous_attempt_difference': 'No real retry or code execution.'},
        'build': {'build_profile': 'simulation', 'command_summary': 'No actual build command ran.', 'exit_code': 0, 'target_description': 'Simulation manifest'},
        'verification': {'verification_scope': 'Simulation fixture only.', 'required_case_ids': cases, 'limitations': ['No actual product or device verification.']},
        'integration': {'included_modules': request['report_expectations']['included_modules'], 'build_profile': 'simulation', 'required_case_ids': cases, 'limitations': ['No actual integration command executed.']},
    }[stage]
    if stage == 'code':
        diff = folder / 'simulation.diff'
        diff.write_text('# Simulation fixture: empty source change.\n', encoding='utf-8')
        evidence.append(ref(diff, 'diff'))
        details['diff_path'] = evidence[-1]['path']
    wire = {key: deepcopy(request[key]) for key in ['job_id', 'module_id', 'stage', 'attempt_id', 'session_id', 'report_id', 'plan_version', 'fingerprint', 'input_result_refs', 'source_revision']}
    wire.update(schema_version=2, message_type='module_result', outcome='SUCCEEDED', evidence='Explicit simulation fixture; no external execution.', error_class='', cause_key='', report={'summary': 'Simulation fixture evidence.', 'details': details, 'evidence_refs': evidence, 'test_results': [{'case_id': case, 'status': 'PASS', 'source_revision': request['source_revision'], 'artifact_sha256': request['report_expectations']['artifact_sha256'], 'evidence_paths': [evidence[0]['path']]} for case in cases], 'decision_requests': []})
    if stage == 'build':
        image = folder / 'simulation.json'
        image.write_text(json.dumps({'simulation': True, 'job_id': request['job_id'], 'source_revision': request['source_revision']}), encoding='utf-8')
        wire['artifact'] = {key: value for key, value in ref(image, 'image').items() if key != 'kind'}
    related = []
    if stage == 'code':
        review_request = claim['attempt']['review_request']
        review = dict(wire, stage='review', session_id=review_request['session_id'], report_id=review_request['report_id'], input_result_refs=wire['input_result_refs'] + [{'report_id': wire['report_id'], 'sha256': report_hash(wire)}])
        review['report'] = {'summary': 'Simulation independent review fixture.', 'details': {'reviewed_source_revision': wire['source_revision'], 'reviewed_diff_sha256': evidence[-1]['sha256'], 'findings': []}, 'evidence_refs': evidence, 'test_results': [], 'decision_requests': []}
        related = [{'envelope_version': 1, 'wire_result': review, 'related_reports': [], 'observations': {'source_revision': wire['source_revision'], 'before_source_revision': wire['source_revision'], 'source_identity': {'kind': 'workspace-content-sha256-v1', 'sha256': wire['source_revision']}, 'diff_sha256': evidence[-1]['sha256']}, 'transport': {'status': 'COMPLETED', 'simulation': True, 'tool': 'codex' if claim['attempt']['tool'] == 'claude' else 'claude'}}]
    observations = {'source_revision': request['source_revision'], 'before_source_revision': request['source_revision'], 'source_identity': deepcopy(request['report_expectations']['source_identity']), 'diff_format': 'bsp-workspace-diff-v1' if stage == 'code' else None, 'diff_sha256': evidence[-1]['sha256'] if stage == 'code' else None}
    return {'envelope_version': 1, 'wire_result': wire, 'related_reports': related, 'observations': observations, 'transport': {'status': 'COMPLETED', 'simulation': True}}


def demo_result(claim, artifacts):
    job, m, name, a = claim['job'], claim['module'], claim['stage'], claim['attempt']
    result = {'outcome': 'SUCCEEDED', 'evidence': f'모의 실행 · {m["name"]} / {name} · 소스 {job["source_revision"]}'}
    if name == 'code':
        result['review'] = {'tool': 'codex' if a['tool'] == 'claude' else 'claude', 'outcome': 'PASS', 'session_id': uid(), 'revision': job['source_revision'], 'evidence': '모의 교차 리뷰'}
    if name == 'build':
        content = json.dumps({'simulation': True, 'message': '시연용 manifest입니다. 보드에 적용할 실제 이미지가 아닙니다.', 'job': job['id'], 'module': m['id'], 'source': job['source_revision']}, ensure_ascii=False).encode()
        folder = artifacts / job['id']; folder.mkdir(exist_ok=True)
        filename = uid() + '.json'
        (folder / filename).write_bytes(content)
        result['artifact'] = {'id': filename, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content), 'name': m['name'] + '-demo-manifest.json'}
    return result


class Worker:
    def __init__(self, engine, delay=1.2):
        self.engine = engine
        self.owner = uid()
        self.delay = delay
        self.pool = ThreadPoolExecutor(max_workers=8)
        self.pending = {}
        self.control_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='bsp-control')
        self.jira_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='bsp-jira')
        self.control_pending = {}
        self.jira_pending = {}
        self.closed = False

    def execute(self, claim):
        result = self._execute(claim)
        if claim['attempt'].get('request'):
            self.engine.orchestration.record_result(claim['attempt']['id'], result)
            if claim['attempt'].get('review_request'):
                for envelope in result.get('related_reports', []):
                    self.engine.orchestration.record_result(claim['attempt']['review_request']['report_id'], envelope)
        return result

    def _execute(self, claim):
        if claim['job']['execution'] == 'demo':
            time.sleep(self.delay)
            return demo_v2_result(claim) if claim['attempt'].get('request') else demo_result(claim, self.engine.artifacts)
        from copy import deepcopy
        claim = deepcopy(claim)
        if claim['attempt'].get('request'):
            profile = claim['job']['profile']
            intent = self.engine.orchestration.transport_context(claim['attempt']['id'])
            profile['_launch_context'] = {'launch_id': intent['id'], 'intent_nonce': intent['nonce']}
            if claim['attempt'].get('review_request'):
                review_intent = self.engine.orchestration.transport_context(claim['attempt']['review_request']['report_id'])
                profile['_review_launch_context'] = {'launch_id': review_intent['id'], 'intent_nonce': review_intent['nonce']}
            profile['_receipt_sink'] = self._record_receipt
            profile['_not_launched_sink'] = self._record_not_launched
        result = Bridge().execute(claim)
        if claim['stage'] == 'build' and result.get('outcome') == 'SUCCEEDED':
            result = self.import_artifact(claim, result)
        return result

    def _record_receipt(self, receipt):
        with self.engine.store.connection() as c:
            row = c.execute('SELECT owner_id FROM launch_receipts WHERE id=?', (receipt.get('launch_id'),)).fetchone()
        if not row:
            raise Conflict('Process callback has no matching durable intent.', 'RECEIPT_MISMATCH')
        self.engine.orchestration.record_transport(row['owner_id'], receipt)

    def _record_not_launched(self, proof):
        with self.engine.store.connection() as c:
            row = c.execute('SELECT owner_id FROM launch_receipts WHERE id=?', (proof.get('launch_id'),)).fetchone()
        if not row:
            raise Conflict('No-launch callback has no matching allocation.', 'RECEIPT_MISMATCH')
        self.engine.orchestration.record_not_launched(row['owner_id'], proof)

    @staticmethod
    def _failed_envelope(message='Execution adapter failed.'):
        return {'envelope_version': 1, 'wire_result': None, 'related_reports': [], 'observations': {}, 'transport': {'status': 'FAILED', 'error_class': 'ENVIRONMENT', 'error': message}}

    @staticmethod
    def _legacy_control_result(result):
        from backend.contracts import ContractError, validate_legacy_result
        try:
            return validate_legacy_result(result)
        except ContractError as exc:
            return {'outcome': 'FAILED', 'evidence': exc.safe_message, 'error_class': 'CONTRACT'}

    def execute_orchestration(self, run):
        result = self._execute_orchestration(run)
        self.engine.orchestration.record_result(run['id'], result)
        return result

    def _execute_orchestration(self, run):
        if run['job']['execution'] == 'demo':
            request = run['request']
            wire = {key: request[key] for key in ['job_id', 'orchestration_run_id', 'session_id', 'trigger_ids', 'base_state_version', 'plan_version', 'fingerprint', 'result_refs']}
            wire.update(schema_version=1, message_type='orchestration_result', outcome='SUCCEEDED', summary='Simulation coordinator fixture; no model invoked.', proposals=[], error_class='')
            return {'envelope_version': 1, 'wire_result': wire, 'transport': {'status': 'COMPLETED', 'simulation': True}}
        profile = dict(run['job']['profile'])
        intent = self.engine.orchestration.transport_context(run['id'])
        profile['_launch_context'] = {'launch_id': intent['id'], 'intent_nonce': intent['nonce']}
        profile['_receipt_sink'] = self._record_receipt
        return Bridge().invoke(profile, 'claude', run['request'], profile['orchestration'].get('timeout_seconds', 120))

    def _drain(self):
        for future, (kind, identifier, payload) in list(self.control_pending.items()):
            if future.done():
                try:
                    result = future.result()
                except Exception:
                    result = self._failed_envelope('Coordinator control adapter failed.')
                if kind == 'orchestrate':
                    self.engine.orchestration.finish(payload['id'], result)
                    for proposal in self.engine.orchestration.pending_proposals(payload['id']):
                        if proposal:
                            current = self.engine.store.snapshot(identifier)
                            try:
                                self.engine.orchestration.apply(identifier, proposal['id'], proposal['command_id'] + ':auto', current['version'], 'orchestrator')
                            except Conflict:
                                pass
                del self.control_pending[future]
        for future in list(self.jira_pending):
            if future.done():
                try:
                    future.result()
                except Exception:
                    pass  # Durable SENDING intent is reconciled on restart; no blind create.
                del self.jira_pending[future]

    def import_artifact(self, claim, result):
        import shutil
        raw = result.get('artifact', {})
        workspace = Path(claim['job']['profile']['workspace']).resolve()
        path = (workspace / str(raw.get('path', ''))).resolve()
        if not path.is_relative_to(workspace) or not path.is_file():
            return {'outcome': 'FAILED', 'evidence': '빌드 산출물이 허용된 작업 폴더에 없습니다.', 'error_class': 'ARTIFACT'}
        folder = self.engine.artifacts / claim['job']['id']; folder.mkdir(exist_ok=True)
        identifier = uid() + '.bin'
        target = folder / identifier
        shutil.copyfile(path, target)
        with target.open('rb') as f:
            digest = hashlib.file_digest(f, 'sha256').hexdigest()
        if digest != raw.get('sha256'):
            target.unlink()
            return {'outcome': 'FAILED', 'evidence': '산출물 해시 불일치', 'error_class': 'ARTIFACT'}
        result['artifact'] = {'id': identifier, 'name': path.name, 'bytes': target.stat().st_size, 'sha256': digest, 'source_revision': result.get('source_revision', claim['job']['source_revision'])}
        return result

    def tick(self):
        self._drain()
        for future, claim in list(self.pending.items()):
            if future.done():
                try:
                    result = future.result()
                except Exception:
                    result = self._failed_envelope() if claim['attempt'].get('request') else {'outcome': 'FAILED', 'evidence': '실행 어댑터 오류', 'error_class': 'ENVIRONMENT'}
                self.engine.finish_integration(claim, result) if claim['stage'] == 'integration' else self.engine.finish(claim['job']['id'], claim['module']['id'], claim['stage'], claim['attempt']['id'], claim['attempt']['token'], result)
                del self.pending[future]
        if self.closed:
            return
        for job in self.engine.store.all():
            busy = {(kind, identifier) for kind, identifier, _ in self.control_pending.values()}
            # Session initialization and questions share the same durable coordinator lane.
            if len(self.control_pending) < 3 and not any(identifier == job['id'] for _, identifier in busy):
                needs_initialize = job['execution'] == 'bridge' and job['session']['status'] in {'NOT_CONNECTED', 'NEEDS_RECONCILIATION'}
                if job['profile'].get('runner') == 'native' and job['session']['status'] == 'NEEDS_RECONCILIATION':
                    needs_initialize = False
                if needs_initialize:
                    self.control_pending[self.control_pool.submit(self.initialize_session, job)] = ('initialize', job['id'], job)
                elif any(p['status'] == 'PENDING' for p in job['prompts']):
                    self.control_pending[self.control_pool.submit(self.answer_question, job)] = ('question', job['id'], job)
                else:
                    run = self.engine.orchestration.claim(job['id'], self.owner)
                    if run:
                        self.control_pending[self.control_pool.submit(self.execute_orchestration, run)] = ('orchestrate', job['id'], run)
            if len(self.jira_pending) < 2 and job['id'] not in self.jira_pending.values():
                self.jira_pending[self.jira_pool.submit(self.sync_decisions, job)] = job['id']
            running_analysis = sum(1 for c in self.pending.values() if c['job']['id'] == job['id'] and c['stage'] == 'analysis')
            for m in job['modules']:
                for name in STAGES:
                    if len(self.pending) >= 8 or (name == 'analysis' and running_analysis >= job['profile']['max_analysis']):
                        continue
                    try:
                        claim = self.engine.claim(job['id'], m['id'], name, self.owner)
                    except Conflict:
                        continue
                    if claim and name != 'device_test':
                        self.pending[self.pool.submit(self.execute, claim)] = claim
                        running_analysis += name == 'analysis'
                    if claim:
                        break
            if len(self.pending) < 8:
                integrated = self.engine.claim_integration(job['id'], self.owner)
                if integrated:
                    self.pending[self.pool.submit(self.execute, integrated)] = integrated

    def initialize_session(self, job):
        if job['execution'] != 'bridge' or job['session']['status'] not in {'NOT_CONNECTED', 'NEEDS_RECONCILIATION'}:
            return
        if job['profile'].get('runner') == 'native' and job['session']['status'] == 'NEEDS_RECONCILIATION':
            return
        with self.engine.store.transaction() as c:
            latest = self.engine.store.get(c, job['id'])
            if latest['session']['status'] not in {'NOT_CONNECTED', 'NEEDS_RECONCILIATION'}:
                return
            lane_id = 'initialize:' + latest['session']['id']
            if not self.engine.orchestration.acquire_lane(c, job['id'], lane_id, 'initialize'):
                return
            intent = self.engine.orchestration.launch_intent(c, job['id'], lane_id, 'initialize')
            latest['session']['status'] = 'CONNECTING'
            persist = self.engine.store.audit if self.engine.orchestration.enabled(latest) else self.engine.store.save
            persist(c, latest, 'COORDINATOR_CONNECTING')
        profile = dict(job['profile'], _launch_context={'launch_id': intent['id'], 'intent_nonce': intent['nonce']}, _receipt_sink=self._record_receipt)
        from backend.domain.orchestration import public_snapshot
        try:
            result = Bridge().invoke(profile, 'claude',
                              {'schema_version':1,'stage':'coordinate','job_id':job['id'],
                               'session_id':job['session']['id'],'resume_external_id':job['session'].get('external_id'),
                               'modules':public_snapshot(job['modules']),'source_revision':job['source_revision'],'analysis_only':True},
                              60)
        except Exception:
            result = {'outcome': 'UNKNOWN', 'evidence': 'Coordinator transport interrupted; reconcile the stored process receipt.'}
        result = self._legacy_control_result(result)
        self.engine.orchestration.record_result(lane_id, {'legacy_control_result': result})
        with self.engine.store.transaction() as c:
            latest = self.engine.store.get(c, job['id'])
            if result.get('outcome') == 'SUCCEEDED' and result.get('external_session_id') and result.get('evidence'):
                latest['session'].update(status='READY',external_id=str(result['external_session_id']),evidence=result['evidence'])
            elif result.get('outcome') == 'UNKNOWN':
                latest['session'].update(status='NEEDS_RECONCILIATION', evidence=result.get('evidence'))
            else:
                latest['session'].update(status='FAILED',evidence=result.get('evidence') or '조정 세션 연결/복구 증거를 확인할 수 없습니다.')
            self.engine.orchestration.release_lane(c, job['id'], lane_id, result.get('outcome') == 'UNKNOWN')
            persist = self.engine.store.audit if self.engine.orchestration.enabled(latest) else self.engine.store.save
            persist(c, latest, 'COORDINATOR_RESULT')

    def answer_question(self, job):
        request = next((p for p in job['prompts'] if p['status'] == 'PENDING'), None)
        if not request:
            return
        with self.engine.store.transaction() as c:
            latest = self.engine.store.get(c, job['id'])
            p = next(p for p in latest['prompts'] if p['id'] == request['id'])
            if p['status'] != 'PENDING':
                return
            if not self.engine.orchestration.acquire_lane(c, job['id'], request['id'], 'question'):
                return
            intent = self.engine.orchestration.launch_intent(c, job['id'], request['id'], 'question')
            p['status'] = 'RUNNING'
            persist = self.engine.store.audit if self.engine.orchestration.enabled(latest) else self.engine.store.save
            persist(c, latest, 'QUESTION_STARTED')
        if job['execution'] == 'demo':
            answer = '모의 응답: 현재 상태와 실패 단계의 근거를 확인하세요. 분석은 병렬로 가능하며 수정·빌드는 선행 조건을 충족해야 합니다. 실제 AI 진단을 수행한 결과가 아닙니다.'
            status = 'SUCCEEDED'
        else:
            from backend.domain.orchestration import public_snapshot
            payload = {'schema_version':1, 'stage':'question', 'read_only':True, 'job_id':job['id'], 'target':request['target'], 'prompt':request['text'], 'snapshot':public_snapshot({'modules': job['modules'], 'decisions': job['decisions'], 'source_revision': job['source_revision']})}
            profile = dict(job['profile'], _launch_context={'launch_id': intent['id'], 'intent_nonce': intent['nonce']}, _receipt_sink=self._record_receipt)
            try:
                result = Bridge().invoke(profile, 'claude', payload, 60)
            except Exception:
                result = {'outcome': 'UNKNOWN', 'evidence': 'Question transport interrupted; reconcile stored process identity.'}
            result = self._legacy_control_result(result)
            answer = str(result.get('evidence', '질문 브리지의 응답을 확인할 수 없습니다.'))[:8000]
            status = result['outcome'] if result.get('outcome') in {'SUCCEEDED', 'UNKNOWN'} else 'FAILED'
            self.engine.orchestration.record_result(request['id'], {'legacy_control_result': result})
        with self.engine.store.transaction() as c:
            latest = self.engine.store.get(c, job['id'])
            p = next(p for p in latest['prompts'] if p['id'] == request['id'])
            p.update(status=status, response=answer)
            if job['execution'] == 'bridge':
                p['external_session_id'] = result.get('external_session_id')
            self.engine.orchestration.release_lane(c, job['id'], request['id'], status == 'UNKNOWN')
            persist = self.engine.store.audit if self.engine.orchestration.enabled(latest) else self.engine.store.save
            persist(c, latest, 'QUESTION_FINISHED')

    def sync_decisions(self, job):
        if job['execution'] != 'bridge':
            return
        from backend.adapters.jira import Jira
        for decision in job['decisions']:
            prior = decision['sync_status']
            if prior not in {'QUEUED', 'UNKNOWN'}:
                continue
            checked = decision.get('checked_at')
            if checked and (datetime.now(timezone.utc) - datetime.fromisoformat(checked)).total_seconds() < 30:
                continue
            with self.engine.store.transaction() as c:
                latest = self.engine.store.get(c, job['id'])
                d = next(d for d in latest['decisions'] if d['id'] == decision['id'])
                if d['sync_status'] != prior:
                    continue
                d['sync_status'] = 'SENDING'
                d['checked_at'] = now()
                self.engine.store.audit(c, latest, 'JIRA_INTENT_STARTED', {'decision_id': d['id']})
            try:
                result = Jira(job['profile']).ensure_link(decision, prior)
            except Exception:
                result = {'sync_status': 'UNKNOWN'}
            with self.engine.store.transaction() as c:
                latest = self.engine.store.get(c, job['id'])
                d = next(d for d in latest['decisions'] if d['id'] == decision['id'])
                if d['sync_status'] == 'SENDING':
                    d.update(result)
                    self.engine.store.audit(c, latest, 'JIRA_SYNC_RESULT', {'decision_id': d['id'], 'status': d['sync_status']})

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=True)
        self.control_pool.shutdown(wait=True)
        self.jira_pool.shutdown(wait=True)
        self.tick()


def main():
    import fcntl
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', default='.runtime')
    args = parser.parse_args()
    root = Path(args.runtime).resolve(); root.mkdir(exist_ok=True, parents=True)
    lock = (root / 'worker.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('이미 작업 관리자가 실행 중입니다.')
    engine = Engine(Store(root / 'dashboard.db'), root / 'artifacts')
    engine.recover()
    worker = Worker(engine)
    from backend.worker.hardware import HardwareWorker
    hardware_worker = HardwareWorker(engine, root)
    from backend.services.gui_test_host import make_dashboard_manager
    from backend.gui_test.core.worker import Worker as GuiWorker
    gui_manager = make_dashboard_manager(root, engine=engine)
    from backend.gui_test.standalone.server import ProcessLock
    gui_lock = ProcessLock(gui_manager.store.path.with_suffix('.lock'))
    gui_lock.__enter__()  # Same OS lock as the optional GUI-only integration host.
    gui_manager.recover()
    gui_worker = GuiWorker(gui_manager)
    gui_failed = False
    try:
        while True:
            worker.tick()
            hardware_worker.tick()
            if not gui_failed:
                try:
                    gui_worker.tick()
                except Exception:
                    # A GUI storage/adapter failure must not stop the existing BSP worker.
                    # Persisted active attempts are reconciled after an explicit restart.
                    gui_failed = True
                    print('GUI Test worker stopped scheduling after an internal error; restart to reconcile. BSP worker remains active.', flush=True)
            time.sleep(0.4)
    except KeyboardInterrupt:
        hardware_worker.close()
        gui_worker.close()
        worker.close()
        gui_lock.__exit__(None, None, None)


if __name__ == '__main__':
    main()
