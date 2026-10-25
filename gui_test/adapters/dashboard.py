"""Automatic result receiver, using the existing Dashboard transaction/attempt history.

No public endpoint accepts client-supplied PASS. The worker submits its persisted
run. DemoDashboard owns a separate database and never receives the production DB.
"""
import copy
from pathlib import Path
from gui_test.core.models import TestError, digest
from gui_test.core.results import module_results, aggregate, parse_result


def baseline(job, mapping):
    from backend.domain.policy import gate
    modules = {}
    for spec in mapping['modules']:
        m = next((m for m in job['modules'] if m['id'] == spec['module_key']), None)
        if not m or gate(job, m, 'device_test'):
            raise TestError('Job module is not ready for device_test', 'JOB_NOT_READY')
        stage = m['stages']['device_test']
        artifact = (m['stages']['build']['result'] or {}).get('artifact', {})
        if not artifact.get('id') or not artifact.get('sha256') or not stage['attempts'] or stage['status'] not in {'WAITING_INPUT', 'SUCCEEDED', 'FAILED'}:
            raise TestError('Current image and device_test attempt required', 'JOB_NOT_READY')
        if set(stage['required_cases']) != set(spec['required_cases']):
            raise TestError('Required-case mapping mismatch', 'MAPPING_MISMATCH')
        modules[m['id']] = {'attempt_id': stage['attempts'][-1]['id'], 'artifact_id': artifact['id'],
                            'sha256': artifact['sha256'], 'required_cases': stage['required_cases']}
    return {'job_id': job['id'], 'job_version': job['version'], 'plan_version': job['plan_version'],
            'fingerprint': job['fingerprint'], 'source_revision': job['source_revision'], 'modules': modules}


def automatic_result(engine, run):
    """Internal trusted receiver. Public APIs must load runs from their own store."""
    from backend.domain.policy import Conflict, now, uid
    link = run['link']
    results, reason = module_results(run, link['mapping'])
    if not results:
        raise TestError(reason)
    if aggregate([run['results'].get(t['id'], 'PENDING') for t in run['tests']]) != run['overall_result']:
        raise TestError('Run aggregate does not match the selected TC evidence')
    if link['mapping_hash'] != digest(link['mapping']):
        raise TestError('Mapping snapshot changed')
    # The payload excludes transport attempts/sync metadata so retries remain identical.
    payload = {'run_id': run['id'], 'results': results, 'baseline': link['baseline'],
               'mapping_hash': link['mapping_hash'], 'attempts_hash': digest(run['attempts'])}

    def operation(c, job):
        if run['simulation'] and job['execution'] != 'demo':
            raise Conflict('Mock results cannot modify an operational Dashboard job', 'DEMO_ISOLATION')
        if not run['simulation']:
            # Real board image attestations/API are deliberately not fabricated.
            raise Conflict('Production board attestation adapter not configured', 'ATTESTATION_REQUIRED')
        if baseline(job, link['mapping']) != link['baseline']:
            raise Conflict('Job/image/plan/current attempt changed', 'BASELINE_CHANGED')
        if not link.get('board_evidence') or link['board_evidence']['connection_hash'] != digest(run['connection_snapshot']):
            raise Conflict('Board image identity evidence missing', 'ATTESTATION_REQUIRED')
        selected_ids = {t['id'] for t in run['tests']}
        for tc_id, state in run['results'].items():
            attempts = [a for a in run['attempts'] if a['tc_id'] == tc_id]
            if tc_id not in selected_ids or not attempts or not attempts[-1]['terminated'] or attempts[-1]['state'] != state:
                raise Conflict('Run evidence does not match the final result')
            a = attempts[-1]
            tc = next(t for t in run['tests'] if t['id'] == tc_id)
            parsed, _, _ = parse_result(a['stdout'], a['stderr'], a['exit_code'], terminated=a['terminated'], **tc.get('parser', {}))
            if parsed != state:
                raise Conflict('Stored result does not match raw process evidence')
        was_completed = job['final_review'] is not None
        affected = []
        for module_id, cases in results.items():
            m = engine.module(job, module_id)
            stage = m['stages']['device_test']
            previous = stage['attempts'][-1]
            if previous['status'] == 'WAITING_INPUT':
                previous.update(status='SUPERSEDED', ended_at=now(), superseded_by_run=run['id'])
            outcome = 'SUCCEEDED' if all(v == 'PASS' for v in cases.values()) else 'FAILED'
            a = {'id': uid(), 'ordinal': len(stage['attempts']) + 1, 'status': outcome, 'tool': 'gui-test',
                 'fingerprint': job['fingerprint'], 'started_at': run['started_at'], 'ended_at': run['ended_at'],
                 'execution': job['execution'], 'session_id': uid(), 'owner': 'gui-test-worker', 'token': uid()}
            result = {'run_id': run['id'], 'cases': cases, 'simulation': run['simulation'],
                      'attempt_id': a['id'], 'previous_attempt_id': previous['id'],
                      'source_revision': run['source_revision'], 'mapping_hash': link['mapping_hash'],
                      'test_plan_version': job['plan_version'], 'fingerprint': job['fingerprint'],
                      **link['baseline']['modules'][module_id],
                      'evidence_refs': [x['id'] for x in run['attempts']], 'submitted_at': now()}
            result['attempt_id'] = a['id']
            a['result'] = result
            stage['attempts'].append(a)
            stage.update(status=outcome, validity='CURRENT' if outcome == 'SUCCEEDED' else 'UNVERIFIED', result=result)
            affected.append(module_id)
        # The existing graph has a boot-group gate and final integration dependency.
        invalidated = []
        if any(m['id'] in affected and m['group'] == 'boot' and m['stages']['device_test']['status'] == 'FAILED' for m in job['modules']):
            for m in job['modules']:
                if m['group'] == 'main' and m['id'] not in affected:
                    s = m['stages']['device_test']
                    s.update(status='PENDING', validity='INVALIDATED', invalidation_reason='Boot prerequisite automatic test failed')
                    invalidated.append(m['id'])
        old_integration = copy.deepcopy(job['integration'])
        job['integration'] = {'status': 'PENDING', 'evidence': None, 'history': [old_integration]}
        if job['final_review']:
            job.setdefault('final_review_history', []).append(job['final_review'])
            job['final_review'] = None
        if was_completed or invalidated:
            job['paused'] = True
            job['gui_revalidation'] = {'status': 'AWAITING_APPROVAL', 'run_id': run['id'],
                                       'modules': invalidated, 'steps': ['device_test for affected modules', 'integration', 'human final review']}
        engine.store.save(c, job, 'AUTOMATIC_DEVICE_TEST', {'run_id': run['id'], 'modules': affected, 'invalidated': invalidated})
        return {'job_id': job['id'], 'version': job['version'], 'modules': results, 'simulation': run['simulation']}
    try:
        return engine.command('gui-test:' + run['id'], payload, operation, link['baseline']['job_id'], link['baseline']['job_version'])
    except Conflict as exc:
        raise TestError(exc.message, exc.code, exc.status) from exc


class DemoDashboard:
    def __init__(self, root):
        from backend.domain.engine import Engine
        from backend.storage.store import Store
        root = Path(root)
        self.engine = Engine(Store(root / 'demo-dashboard.db'), root / 'demo-artifacts')

    def jobs(self):
        return [{'id': j['id'], 'title': j['title']} for j in self.engine.store.all()]

    def create(self, key):
        from backend.settings import Profile
        from backend.domain.policy import STAGES, uid
        from backend.worker.main import demo_result
        existing = self.jobs()
        if existing:
            return self.engine.snapshot(existing[0]['id'])
        e = self.engine
        job_id = e.create(key, Profile().model_dump(), 'GUI Test isolated demo job', 'linux',
                          modules=[{'name': 'Demo Boot', 'group': 'boot'}, {'name': 'Demo Network', 'group': 'boot'}])['job_id']
        for m in e.snapshot(job_id)['modules']:
            claim = e.claim(job_id, m['id'], 'analysis', 'fixture')
            e.finish(job_id, m['id'], 'analysis', claim['attempt']['id'], claim['attempt']['token'], demo_result(claim, e.artifacts))
        e.act(job_id, uid(), e.snapshot(job_id)['version'], 'confirm', {'plan_version': 1})
        for m in e.snapshot(job_id)['modules']:
            for stage in STAGES[1:]:
                claim = e.claim(job_id, m['id'], stage, 'fixture')
                if stage != 'device_test':
                    e.finish(job_id, m['id'], stage, claim['attempt']['id'], claim['attempt']['token'], demo_result(claim, e.artifacts))
        return e.snapshot(job_id)

    def pin(self, job_id, connection):
        try:
            job = self.engine.store.snapshot(job_id)
        except Exception as exc:
            raise TestError('Only an isolated GUI demo job can be linked while using Mock adapters') from exc
        mapping = {'schema_version': 1, 'mapping_revision': 'demo-v1', 'modules': [
            {'module_key': job['modules'][0]['id'], 'required_cases': {'boot': ['boot/01_boot.py'], 'functional': ['boot/02_smoke.py']}},
            {'module_key': job['modules'][1]['id'], 'required_cases': {'boot': ['network/03_link.py'], 'functional': ['network/dual/04_pair.py']}}]}
        return {'baseline': baseline(job, mapping), 'mapping': mapping, 'mapping_hash': digest(mapping),
                'board_evidence': {'simulation': True, 'connection_hash': digest(connection), 'method': 'mock-image-attestation'}}

    def validate(self, link):
        job = self.engine.store.snapshot(link['baseline']['job_id'])
        try:
            current = baseline(job, link['mapping'])
        except TestError as exc:
            raise TestError('Job baseline changed; start a new run', 'BASELINE_CHANGED') from exc
        if current != link['baseline']:
            raise TestError('Job/image/plan/attempt baseline changed; start a new run', 'BASELINE_CHANGED')

    def submit(self, run):
        return self.engine.automatic_device_test(run)
