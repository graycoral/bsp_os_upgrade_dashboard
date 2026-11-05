"""Server-owned opt-in device-test dispatch and reconciliation.

The Windows host executes one reserved flash/boot/TC pipeline. Linux owns the
current BSP attempt and only accepts results matching its frozen inputs.
"""
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from backend.domain.policy import gate, file_hash, now
from backend.gui_test.core.models import TestError, digest
from backend.gui_test.execution.flashing import FlashRequest, validate_manifest
from backend.gui_test.core.results import parse_result
from backend.gui_test.core.discovery import select


def baseline(job, module):
    stages = module['stages']
    return {'job_id': job['id'], 'module_id': module['id'], 'fingerprint': job['fingerprint'],
            'plan_version': job['plan_version'], 'source_revision': job['source_revision'],
            'artifact': (stages['build']['result'] or {}).get('artifact'),
            'verification_attempt': stages['verification']['attempts'][-1]['id'],
            'attempt_id': stages['device_test']['attempts'][-1]['id'],
            'required_cases': stages['device_test']['required_cases']}


def verify_result(value, payload):
    if value.get('runner_id') != payload['runner_id'] or value.get('id') != payload['id'] or value.get('request_hash') != digest(payload):
        raise TestError('Pipeline response identity mismatch', 'PIPELINE_MISMATCH')
    if value.get('state') != 'DONE' or value.get('terminated') is not True:
        return None
    # Failures never become a successful device_test, regardless of console text.
    if value.get('outcome') != 'SUCCEEDED':
        return {'outcome': 'FAILED', 'evidence': value.get('reason') or '퓨징 또는 TC 실패', 'cases': value.get('cases', {})}
    selected = [payload['connection']['a']] + ([payload['connection']['b']] if payload['connection'].get('b') else [])
    flashes = value.get('flashes', [])
    if len(flashes) != len(selected) or any(f.get('board') != b or f.get('manifest_hash') != digest(payload['manifest']) or
            f.get('success') is not True or f.get('boot_ready') is not True or f.get('result', {}).get('terminated') is not True or f['result'].get('exit_code') != 0
            for f, b in zip(flashes, selected)):
        raise TestError('Missing flash identity evidence', 'PIPELINE_MISMATCH')
    ids = list(dict.fromkeys(t for group in payload['cases'].values() for t in group))
    tests = value.get('tests', [])
    if [t.get('tc_id') for t in tests] != ids:
        raise TestError('Incomplete mapped TC evidence', 'PIPELINE_MISMATCH')
    states = {}
    for t, spec in zip(tests, payload['tests']):
        if spec['id'] != t['tc_id'] or spec.get('parser', {}) != t.get('parser', {}):
            raise TestError('Pinned TC parser mismatch', 'PIPELINE_MISMATCH')
        state, _, _ = parse_result(t['stdout'], t['stderr'], t['exit_code'], terminated=t['terminated'], **spec.get('parser', {}))
        if state not in {'PASS', 'FAIL'} or state != t.get('state'):
            raise TestError('TC verdict does not match process evidence', 'PIPELINE_MISMATCH')
        states[t['tc_id']] = state
    cases = {case: 'PASS' if all(states[t] == 'PASS' for t in ids) else 'FAIL' for case, ids in payload['cases'].items()}
    if cases != value.get('cases') or any(v != 'PASS' for v in cases.values()) or value.get('phase') != 'COMPLETED':
        raise TestError('Pipeline success is inconsistent', 'PIPELINE_MISMATCH')
    return {'outcome': 'SUCCEEDED', 'cases': cases, 'evidence': '이미지 퓨징·부팅 준비·필수 TC 완료'}


class HardwareCoordinator:
    def __init__(self, engine, remote, modules):
        self.engine, self.remote, self.modules = engine, remote, modules
        self.resource = 'hardware:' + remote.url

    def prepare(self, job, module, config):
        artifact = (module['stages']['build']['result'] or {}).get('artifact', {})
        path = (self.engine.artifacts / job['id'] / str(artifact.get('id', ''))).resolve()
        if path.parent != (self.engine.artifacts / job['id']).resolve() or not path.is_file() or path.stat().st_size > 60000 or file_hash(path) != artifact.get('sha256'):
            raise TestError('검증된 빌드 manifest 산출물이 필요합니다.', 'IMAGE_MANIFEST')
        manifest = json.loads(path.read_text(encoding='utf-8-sig'))
        validate_manifest(manifest)
        if set(config['cases']) != set(module['stages']['device_test']['required_cases']):
            raise TestError('모든 필수 사례의 TC 매핑이 필요합니다.', 'CASE_MAPPING')
        catalog = self.remote.catalog()
        ids = list(dict.fromkeys(t for group in config['cases'].values() for t in group))
        tests = select(catalog, ids)
        payload = FlashRequest.model_validate({
            'id': module['stages']['device_test']['attempts'][-1]['id'],
            'runner_id': self.remote.request('/identity')['runner_id'],
            'profile': config['profile'], 'bundle': config['bundle'], 'manifest': manifest,
            'source_revision': catalog['revision'], 'connection': config['connection'],
            'template': config['template'], 'cases': config['cases'], 'tests': tests, 'baseline': baseline(job, module)}).model_dump()
        if len(json.dumps(payload).encode()) > 65000:
            raise TestError('Image manifest/request exceeds transport limit', 'IMAGE_MANIFEST')
        return payload

    def record_blocked(self, job_id, module_id, reason):
        with self.engine.store.transaction() as c:
            job = self.engine.store.get(c, job_id)
            s = self.engine.module(job, module_id)['stages']['device_test']
            if s['status'] == 'WAITING_INPUT' and s.get('automation_blocked') != reason:
                s['automation_blocked'] = reason
                self.engine.store.save(c, job, 'HARDWARE_CONFIGURATION_REQUIRED', {'module_id': module_id})

    def dispatch(self, job, module, config):
        if gate(job, module, 'device_test'): return
        try:
            payload = self.prepare(job, module, config)
        except Exception as exc:
            self.record_blocked(job['id'], module['id'], exc.message if isinstance(exc, TestError) else '자동 퓨징 설정 또는 manifest를 확인하세요.')
            return
        with self.engine.store.transaction() as c:
            current = self.engine.store.get(c, job['id'])
            m = self.engine.module(current, module['id']); s = m['stages']['device_test']
            if (s['status'] != 'WAITING_INPUT' or gate(current, m, 'device_test') or baseline(current, m) != payload['baseline'] or
                    c.execute('SELECT 1 FROM leases WHERE resource=?', (self.resource,)).fetchone()):
                return
            a = s['attempts'][-1]
            s.pop('automation_blocked', None)
            s.update(status='RUNNING', automation={'payload': payload, 'request_hash': digest(payload), 'phase': 'DISPATCHING', 'resource': self.resource})
            a.update(status='RUNNING', tool='windows-flash-test')
            c.execute('INSERT INTO leases VALUES(?,?,?)', (self.resource, a['id'], a['token']))
            self.engine.store.save(c, current, 'HARDWARE_DISPATCHED', {'attempt_id': a['id']})
        # Never resubmit after this point, including when the POST response is lost.
        try: self.remote.request('/flash-tests', 'POST', payload)
        except TestError: pass

    def reconcile(self, job, module):
        auto = module['stages']['device_test']['automation']; payload = auto['payload']
        try:
            if auto['resource'] != self.resource:
                raise TestError('Active pipeline endpoint changed; restore original configuration', 'ENDPOINT_CHANGED')
            if self.remote.request('/identity').get('runner_id') != payload['runner_id']:
                raise TestError('Windows runner runtime changed; restore original runtime', 'RUNNER_CHANGED')
            value = self.remote.request('/executions/' + payload['id'] + '/reconcile', 'POST')
            if value.get('runner_id') == payload['runner_id'] and value.get('id') == payload['id'] and value.get('not_started') is True and value.get('terminated') is True:
                result = {'outcome': 'FAILED', 'evidence': 'Windows 실행이 시작되지 않았습니다. 설정/예약을 확인하고 재시도하세요.'}
            else:
                result = verify_result(value, payload)
        except TestError as exc:
            value = {'state': 'UNKNOWN', 'phase': 'UNKNOWN', 'reason': exc.code}
            result = None
        except Exception:
            value = {'state': 'UNKNOWN', 'phase': 'UNKNOWN', 'reason': 'PIPELINE_CONTRACT'}
            result = None
        with self.engine.store.transaction() as c:
            current = self.engine.store.get(c, job['id'])
            m = self.engine.module(current, module['id']); s = m['stages']['device_test']; a = s['attempts'][-1]
            if a['id'] != payload['id'] or s['status'] not in {'RUNNING', 'UNKNOWN', 'CANCEL_REQUESTED'}: return
            previous_status = s['status']
            if not c.execute('SELECT 1 FROM leases WHERE resource=? AND attempt=? AND token=?', (auto['resource'], a['id'], a['token'])).fetchone():
                result = None
                value = {'state': 'UNKNOWN', 'phase': 'UNKNOWN', 'reason': 'LEASE_MISMATCH'}
            if result and not value.get('phase'):
                value['phase'] = 'FAILED' if result['outcome'] == 'FAILED' else 'COMPLETED'
            summary = {k: value.get(k) for k in ('state', 'phase', 'reason', 'events', 'tests', 'flashes', 'cases')}
            old_summary = s['automation'].get('report')
            if result:
                # A restarted coordinator session is not evidence that this independent
                # Windows operation failed. Still recheck plan, stages and decisions.
                if baseline(current, m) != payload['baseline'] or gate(current | {'paused': False, 'session': {'status': 'READY'}}, m, 'device_test'):
                    result = {'outcome': 'FAILED', 'evidence': '작업·이미지·계획·의존 조건이 변경되어 자동 결과를 적용하지 않았습니다.'}
                result.update(pipeline_id=payload['id'], simulation=False, artifact_id=payload['baseline']['artifact']['id'],
                              sha256=payload['baseline']['artifact']['sha256'], source_revision=payload['baseline']['source_revision'],
                              test_plan_version=payload['baseline']['plan_version'], request_hash=digest(payload),
                              evidence_kind='host-flash-process-and-boot-readiness')
                outcome = 'CANCELLED' if s['status'] == 'CANCEL_REQUESTED' else result['outcome']
                a.update(status=outcome, ended_at=now(), result=result)
                s.update(status=outcome, validity='CURRENT' if outcome == 'SUCCEEDED' else 'UNVERIFIED', result=result)
                c.execute('DELETE FROM leases WHERE attempt=? AND token=?', (a['id'], a['token']))
            else:
                state = 'UNKNOWN' if value.get('state') == 'UNKNOWN' else 'RUNNING'
                if s['status'] != 'CANCEL_REQUESTED': s['status'] = state
                a['status'] = s['status']
            s['automation'].update(phase=value.get('phase', 'UNKNOWN'), report=summary)
            if result or old_summary != summary or previous_status != s['status']:
                self.engine.store.save(c, current, 'HARDWARE_RESULT' if result else 'HARDWARE_PROGRESS', {'attempt_id': a['id']})

    def tick(self):
        for job in self.engine.store.all():
            if job['execution'] != 'bridge': continue
            for module in job['modules']:
                s = module['stages']['device_test']
                if s.get('automation') and s['status'] in {'RUNNING', 'UNKNOWN', 'CANCEL_REQUESTED'}:
                    self.reconcile(job, module)
                elif s['status'] == 'WAITING_INPUT':
                    config = self.modules.get(module['name'])
                    if config and config.get('enabled') is True:
                        self.dispatch(job, module, config)


class HardwareWorker:
    def __init__(self, engine, runtime):
        self.coordinator = None
        self.future = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hardware-dispatch')
        path = Path(runtime) / 'device-test.json'
        if path.exists():
            from backend.gui_test.adapters.windows_remote import WindowsRemote
            config = json.loads(path.read_text(encoding='utf-8-sig'))
            if config.get('enabled') is True:
                remote = WindowsRemote(config['url'], os.environ.get('GUI_TEST_RUNNER_TOKEN', ''))
                self.coordinator = HardwareCoordinator(engine, remote, config['modules'])

    def tick(self):
        if not self.coordinator: return
        if self.future:
            if not self.future.done(): return
            try: self.future.result()
            except Exception:
                print('Hardware dispatcher error; persisted work will be reconciled without re-dispatch.', flush=True)
        self.future = self.pool.submit(self.coordinator.tick)

    def close(self):
        self.pool.shutdown(wait=True)
