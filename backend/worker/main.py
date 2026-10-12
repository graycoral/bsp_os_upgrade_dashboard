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

    def execute(self, claim):
        if claim['job']['execution'] == 'demo':
            time.sleep(self.delay)
            return demo_result(claim, self.engine.artifacts)
        result = Bridge().execute(claim)
        if claim['stage'] == 'build' and result.get('outcome') == 'SUCCEEDED':
            result = self.import_artifact(claim, result)
        return result

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
        for future, claim in list(self.pending.items()):
            if future.done():
                try:
                    result = future.result()
                except Exception:
                    result = {'outcome': 'FAILED', 'evidence': '실행 어댑터 오류', 'error_class': 'ENVIRONMENT'}
                self.engine.finish_integration(claim, result) if claim['stage'] == 'integration' else self.engine.finish(claim['job']['id'], claim['module']['id'], claim['stage'], claim['attempt']['id'], claim['attempt']['token'], result)
                del self.pending[future]
        for job in self.engine.store.all():
            self.initialize_session(job)
            self.sync_decisions(job)
            self.answer_question(job)
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
            latest['session']['status'] = 'CONNECTING'
            self.engine.store.save(c, latest, 'COORDINATOR_CONNECTING')
        result = Bridge().invoke(job['profile'], 'claude',
                              {'schema_version':1,'stage':'coordinate','job_id':job['id'],
                               'session_id':job['session']['id'],'resume_external_id':job['session'].get('external_id'),
                               'modules':job['modules'],'source_revision':job['source_revision'],'analysis_only':True},
                              60)
        with self.engine.store.transaction() as c:
            latest = self.engine.store.get(c, job['id'])
            if result.get('outcome') == 'SUCCEEDED' and result.get('external_session_id') and result.get('evidence'):
                latest['session'].update(status='READY',external_id=str(result['external_session_id']),evidence=result['evidence'])
            elif result.get('outcome') == 'UNKNOWN':
                latest['session'].update(status='NEEDS_RECONCILIATION', evidence=result.get('evidence'))
            else:
                latest['session'].update(status='FAILED',evidence=result.get('evidence') or '조정 세션 연결/복구 증거를 확인할 수 없습니다.')
            self.engine.store.save(c, latest, 'COORDINATOR_RESULT')

    def answer_question(self, job):
        request = next((p for p in job['prompts'] if p['status'] == 'PENDING'), None)
        if not request:
            return
        with self.engine.store.transaction() as c:
            latest = self.engine.store.get(c, job['id'])
            p = next(p for p in latest['prompts'] if p['id'] == request['id'])
            if p['status'] != 'PENDING':
                return
            p['status'] = 'RUNNING'
            self.engine.store.save(c, latest, 'QUESTION_STARTED')
        if job['execution'] == 'demo':
            answer = '모의 응답: 현재 상태와 실패 단계의 근거를 확인하세요. 분석은 병렬로 가능하며 수정·빌드는 선행 조건을 충족해야 합니다. 실제 AI 진단을 수행한 결과가 아닙니다.'
            status = 'SUCCEEDED'
        else:
            payload = {'schema_version':1, 'stage':'question', 'read_only':True, 'job_id':job['id'], 'target':request['target'], 'prompt':request['text'], 'snapshot':{'modules': job['modules'], 'decisions': job['decisions'], 'source_revision': job['source_revision']}}
            result = Bridge().invoke(job['profile'], 'claude', payload, 60)
            answer = str(result.get('evidence', '질문 브리지의 응답을 확인할 수 없습니다.'))[:8000]
            status = result['outcome'] if result.get('outcome') in {'SUCCEEDED', 'UNKNOWN'} else 'FAILED'
        with self.engine.store.transaction() as c:
            latest = self.engine.store.get(c, job['id'])
            p = next(p for p in latest['prompts'] if p['id'] == request['id'])
            p.update(status=status, response=answer)
            if job['execution'] == 'bridge':
                p['external_session_id'] = result.get('external_session_id')
            self.engine.store.save(c, latest, 'QUESTION_FINISHED')

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
                self.engine.store.save(c, latest, 'JIRA_INTENT_STARTED', {'decision_id': d['id']})
            result = Jira(job['profile']).ensure_link(decision, prior)
            with self.engine.store.transaction() as c:
                latest = self.engine.store.get(c, job['id'])
                d = next(d for d in latest['decisions'] if d['id'] == decision['id'])
                if d['sync_status'] == 'SENDING':
                    d.update(result)
                    self.engine.store.save(c, latest, 'JIRA_SYNC_RESULT', {'decision_id': d['id'], 'status': d['sync_status']})

    def close(self):
        self.pool.shutdown(wait=True)
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
    try:
        while True:
            worker.tick()
            time.sleep(0.4)
    except KeyboardInterrupt:
        worker.pool.shutdown(wait=True)
        for future, claim in list(worker.pending.items()):
            engine.finish_integration(claim, future.result()) if claim['stage'] == 'integration' else engine.finish(claim['job']['id'], claim['module']['id'], claim['stage'], claim['attempt']['id'], claim['attempt']['token'], future.result())


if __name__ == '__main__':
    main()
