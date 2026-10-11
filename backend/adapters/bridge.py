"""Explicit stdin/stdout JSON protocol. Vendor-specific CLI flags belong in configured wrappers."""
import json
import subprocess
import tempfile
from backend.domain.policy import uid


class Bridge:
    def run(self, argv, payload, cwd, timeout):
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=out, stderr=err, cwd=cwd, start_new_session=True)
                try:
                    p.communicate(json.dumps(payload).encode(), timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Kill and reap the entire POSIX group before a lease can be released.
                    import os, signal
                    os.killpg(p.pid, signal.SIGKILL)
                    p.communicate()
                    return {'outcome': 'FAILED', 'evidence': '브리지 실행 시간 초과', 'error_class': 'ENVIRONMENT'}
                if p.returncode != 0:
                    return {'outcome': 'FAILED', 'evidence': f'브리지 종료 코드 {p.returncode}; 민감 원문 로그는 반환하지 않음', 'error_class': 'ENVIRONMENT'}
                out.seek(0)
                raw = out.read(1_048_577)
                if len(raw) > 1_048_576:
                    raise ValueError('oversized')
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError('object required')
                return data
            except (OSError, ValueError):
                return {'outcome': 'FAILED', 'evidence': '브리지 실행/JSON 결과 검증 실패', 'error_class': 'CONTRACT'}

    def execute(self, claim):
        job, m, stage, a = claim['job'], claim['module'], claim['stage'], claim['attempt']
        p = job['profile']
        argv = p['build_argv'] if stage in {'build', 'integration'} else p['agents'].get(a['tool'], [])
        if not argv:
            return {'outcome': 'FAILED', 'evidence': '역할 브리지 미설정', 'error_class': 'ENVIRONMENT'}
        payload = {'schema_version': 1, 'job_id': job['id'], 'module_id': m['id'], 'stage': stage,
                   'attempt_id': a['id'], 'session_id': a['session_id'], 'fingerprint': a['fingerprint'],
                   'source_revision': m.get('stages', {}).get('code', {}).get('result', {}).get('source_revision', job['source_revision']) if m.get('stages', {}).get('code', {}).get('result') else job['source_revision'], 'module': m, 'model_policy': a['model'],
                   'source_paths': {k: p[k] for k in ['old_base', 'vendor_tree', 'new_base']}}
        result = self.run(argv, payload, p['workspace'], p['timeout_seconds'])
        if result.get('outcome') == 'SUCCEEDED' and (result.get('attempt_id') != a['id'] or result.get('fingerprint') != a['fingerprint']):
            return {'outcome': 'FAILED', 'evidence': '브리지 결과의 실행/입력 기준 불일치', 'error_class': 'CONTRACT'}
        if stage == 'code' and result.get('outcome') == 'SUCCEEDED':
            from backend.domain.policy import reviewer
            tool = reviewer([a['tool']], {k: bool(v) for k, v in p['agents'].items()})
            session = uid()
            review = self.run(p['agents'][tool], payload | {'stage': 'review', 'session_id': session, 'implementation': result}, p['workspace'], p['timeout_seconds'])
            result['review'] = {'tool': tool, 'session_id': session, 'revision': result.get('source_revision', job['source_revision']),
                                'outcome': 'PASS' if review.get('outcome') == 'SUCCEEDED' else 'FAIL', 'evidence': review.get('evidence')}
        return result
