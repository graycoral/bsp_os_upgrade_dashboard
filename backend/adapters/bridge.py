"""Route frozen job profiles through built-in adapters or legacy JSON wrappers."""
import json
import subprocess
import tempfile
from copy import deepcopy
from backend.domain.policy import Conflict, uid
from backend.contracts import validate_legacy_result


class Bridge:
    def run(self, argv, payload, cwd, timeout, *, launch_context=None, receipt_sink=None):
        if launch_context is not None or receipt_sink is not None:
            from backend.adapters.process import run_process
            process = run_process(argv, cwd=cwd, timeout=timeout, stdin=json.dumps(payload).encode(),
                                  limit=1_048_576, launch_context=launch_context, receipt_sink=receipt_sink)
            if process.unknown:
                return {'outcome': 'UNKNOWN', 'evidence': '브리지 프로세스 종료 상태를 확인할 수 없습니다.', 'error_class': 'ENVIRONMENT'}
            if process.error or process.code != 0:
                return {'outcome': 'FAILED', 'evidence': '브리지 실행 실패; 민감 원문 로그는 반환하지 않음', 'error_class': 'ENVIRONMENT'}
            try:
                data = json.loads(process.stdout)
                if not isinstance(data, dict):
                    raise ValueError('object required')
                return validate_legacy_result(data)
            except (ValueError, UnicodeError):
                return {'outcome': 'FAILED', 'evidence': '브리지 실행/JSON 결과 검증 실패', 'error_class': 'CONTRACT'}
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
                return validate_legacy_result(data)
            except (OSError, ValueError):
                return {'outcome': 'FAILED', 'evidence': '브리지 실행/JSON 결과 검증 실패', 'error_class': 'CONTRACT'}

    def invoke(self, profile, tool, payload, timeout=None):
        if profile.get('runner', 'bridge') == 'native':
            from backend.adapters.native import Native
            return Native().invoke(profile, tool, payload, timeout)
        if payload.get('message_type') in {'module_request', 'orchestration_request'}:
            return self._invoke_v2(profile, tool, payload, timeout)
        from backend.adapters.native import _process_options
        return self.run(profile['agents'].get(tool, []), payload, profile['workspace'], timeout or profile['timeout_seconds'],
                        **_process_options(profile, optional=True))

    def _invoke_v2(self, profile, tool, payload, timeout=None):
        from backend.adapters.capabilities import validate_tool_capability
        from backend.adapters.process import run_process
        from backend.adapters.native import adapter_envelope, _file_observations, _observations, _validate_files, _process_options, workspace_revision, verify_source_identity, _workspace_bound
        from backend.contracts import canonical_json, parse_json, ContractError, validate_module_result, validate_orchestration_result
        process, wire = None, None
        try:
            validate_tool_capability(profile, tool, payload)
            argv = profile.get('build_argv', []) if tool == 'build' else profile.get('agents', {}).get(tool, [])
            orchestration = payload.get('message_type') == 'orchestration_request'
            if not argv:
                raise ContractError('CAPABILITY_UNSUPPORTED', '$', 'Requested wrapper contract is unsupported.')
            before = _file_observations(profile) if orchestration or _workspace_bound(payload) else {}
            if not orchestration:
                verify_source_identity(profile, payload, before)
            process = run_process(argv, cwd=profile['workspace'], timeout=timeout or profile['timeout_seconds'],
                                  stdin=canonical_json(payload), limit=1_048_576, **_process_options(profile))
            if process.stdout:
                wire = parse_json(process.stdout)
            if process.unknown:
                return adapter_envelope(wire, status='UNKNOWN', error_class='ENVIRONMENT', error=process.error, process_receipt=process.process_receipt)
            if process.error or process.code != 0:
                return adapter_envelope(wire, status='FAILED', error_class='ENVIRONMENT', error=process.error or 'Wrapper exited unsuccessfully.', process_receipt=process.process_receipt)
            if wire is None:
                raise ContractError(safe_message='Wrapper did not return structured JSON.')
            validated = (validate_orchestration_result if orchestration else validate_module_result)(wire, payload)
            if orchestration:
                if before != _file_observations(profile):
                    raise ContractError('DEPENDENCY', '$', 'Orchestration modified source files.')
                observations = {'source_revision': profile.get('source_revision'), 'diff_sha256': None, 'files': []}
            else:
                _validate_files(profile, validated)
                observations = _observations(profile, payload, before, validated)
            return adapter_envelope(validated, process_receipt=process.process_receipt, observations=observations)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return adapter_envelope(status='UNKNOWN' if process and process.unknown else 'FAILED', error_class=exc.code if isinstance(exc, ContractError) else 'CONTRACT',
                                    error='Wrapper transport, contract, source, or evidence validation failed.',
                                    process_receipt=process.process_receipt if process else None, raw_result=wire)

    def execute(self, claim):
        job, m, stage, a = claim['job'], claim['module'], claim['stage'], claim['attempt']
        p = job['profile']
        if p.get('module_report_version', 1) == 2:
            return self._execute_v2(claim)
        payload = {'schema_version': 1, 'job_id': job['id'], 'module_id': m['id'], 'stage': stage,
                   'attempt_id': a['id'], 'session_id': a['session_id'], 'fingerprint': a['fingerprint'],
                   'source_revision': m.get('stages', {}).get('code', {}).get('result', {}).get('source_revision', job['source_revision']) if m.get('stages', {}).get('code', {}).get('result') else job['source_revision'], 'module': m, 'model_policy': a['model'],
                   'source_paths': {k: p[k] for k in ['old_base', 'vendor_tree', 'new_base']}}
        if p.get('runner', 'bridge') == 'native' and stage in {'build', 'verification', 'integration'}:
            from backend.adapters.native import Native
            result = Native().command(p, payload)
        elif stage in {'build', 'integration'}:
            result = self.run(p['build_argv'], payload, p['workspace'], p['timeout_seconds'])
        else:
            result = self.invoke(p, a['tool'], payload)
        try:
            validate_legacy_result(result)
        except ValueError:
            return {'outcome': 'FAILED', 'evidence': '결과 버전이 고정된 v1 계약과 다릅니다.', 'error_class': 'CONTRACT'}
        if result.get('outcome') == 'SUCCEEDED' and (result.get('attempt_id') != a['id'] or result.get('fingerprint') != a['fingerprint']):
            return {'outcome': 'FAILED', 'evidence': '브리지 결과의 실행/입력 기준 불일치', 'error_class': 'CONTRACT'}
        if stage == 'code' and result.get('outcome') == 'SUCCEEDED':
            from backend.domain.policy import reviewer
            tool = reviewer([a['tool']], {k: bool(v) for k, v in p['agents'].items()})
            session = uid()
            review = self.invoke(p, tool, payload | {'stage': 'review', 'session_id': session, 'model_policy': 'configured', 'implementation': result})
            try:
                validate_legacy_result(review)
            except ValueError:
                return {'outcome': 'FAILED', 'evidence': '별도 리뷰 결과 버전이 고정된 v1 계약과 다릅니다.', 'error_class': 'CONTRACT'}
            if review.get('outcome') == 'UNKNOWN':
                return review
            if p.get('runner') == 'native':
                from backend.adapters.native import workspace_revision
                try:
                    unchanged = workspace_revision(p) == result['source_revision']
                except (OSError, ValueError):
                    unchanged = False
                if not unchanged:
                    review = {'outcome': 'FAILED', 'evidence': '리뷰 도중 작업 소스가 바뀌었습니다.'}
            result['review'] = {'tool': tool, 'session_id': session, 'revision': result.get('source_revision', job['source_revision']),
                                'outcome': 'PASS' if review.get('outcome') == 'SUCCEEDED' else 'FAIL', 'evidence': review.get('evidence'),
                                'external_session_id': review.get('external_session_id')}
        return result

    def _execute_v2(self, claim):
        from backend.adapters.native import Native, adapter_envelope, workspace_revision
        from backend.adapters.capabilities import validate_tool_capability
        from backend.domain.policy import reviewer
        from backend.contracts import report_hash
        job, attempt, stage = claim['job'], claim['attempt'], claim['stage']
        profile = job['profile']
        def review_not_launched(reason):
            allocated = attempt.get('review_request') or claim.get('review_request') or {}
            callback = profile.get('_not_launched_sink')
            if callback and allocated.get('report_id'):
                context = profile.get('_review_launch_context') or {}
                callback({'launch_id': context.get('launch_id') or allocated['report_id'],
                          'intent_nonce': context.get('intent_nonce'), 'owner_id': allocated['report_id'], 'reason': reason})
        request = attempt.get('request') or claim.get('request')
        if not isinstance(request, dict):
            if stage == 'code':
                review_not_launched('Frozen code request is missing; independent review was never invoked.')
            return adapter_envelope(status='FAILED', error_class='CONTRACT', error='Frozen v2 request is missing.')
        if stage in {'build', 'verification', 'integration'}:
            if profile.get('runner', 'bridge') == 'native':
                result = Native().command(profile, request)
            else:
                result = self._invoke_v2(profile, 'build', request)
        else:
            result = self.invoke(profile, attempt['tool'], request)
        code_wire = result.get('wire_result')
        if stage != 'code' or result['transport']['status'] != 'COMPLETED' or not code_wire or code_wire.get('outcome') != 'SUCCEEDED':
            if stage == 'code':
                review_not_launched('Code transport or authored report did not succeed; independent review was never invoked.')
            return result
        review_request = deepcopy(attempt.get('review_request') or claim.get('review_request'))
        if not isinstance(review_request, dict):
            result['transport'].update(status='FAILED', error_class='REVIEW', error='Preallocated independent review request is missing.')
            return result
        if review_request.get('session_id') == request['session_id'] or review_request.get('report_id') == request['report_id']:
            review_not_launched('Allocated review identifiers failed validation before invocation.')
            result['transport'].update(status='FAILED', error_class='REVIEW', error='Independent review IDs were not allocated.')
            return result
        revision = result['observations']['source_revision']
        diff = result['observations']['diff_sha256']
        review_request['source_revision'] = revision
        review_request['implementation'] = code_wire
        review_request['input_result_refs'] = request['input_result_refs'] + [{'report_id': code_wire['report_id'], 'sha256': report_hash(code_wire)}]
        review_request.setdefault('report_expectations', {}).update(reviewed_source_revision=revision, reviewed_diff_sha256=diff,
            source_identity={'kind': 'workspace-content-sha256-v1', 'sha256': revision}, diff_format='bsp-workspace-diff-v1')
        review_profile = dict(profile)
        review_profile['_author_tools'] = [attempt['tool']]
        if profile.get('_review_launch_context') is not None:
            review_profile['_launch_context'] = profile['_review_launch_context']
        else:
            context = dict(profile.get('_launch_context') or {})
            context['launch_id'] = review_request['report_id']
            context.pop('receipt_dir', None)
            review_profile['_launch_context'] = context
        review_invoked = False
        try:
            tool = attempt.get('review_tool') or reviewer([attempt['tool']], {key: bool(value) for key, value in profile['agents'].items()}, profile=profile)
            validate_tool_capability(review_profile, tool, review_request, author_tools=[attempt['tool']])
            review_invoked = True
            review = self.invoke(review_profile, tool, review_request)
            # Include the exact finalized request with private adapter metadata so the
            # intake can validate its IDs/source/input refs without rewriting the wire.
            review['transport']['request'] = review_request
            review['transport']['tool'] = tool
            result['related_reports'].append(review)
            if workspace_revision(profile) != revision:
                result['transport'].update(status='FAILED', error_class='DEPENDENCY', error='Source changed during independent review.')
            elif review['transport']['status'] != 'COMPLETED':
                result['transport'].update(status=review['transport']['status'], error_class=review['transport'].get('error_class') or 'REVIEW', error='Independent review did not complete.')
            elif not review.get('wire_result') or review['wire_result'].get('outcome') != 'SUCCEEDED':
                result['transport'].update(status='FAILED', error_class='REVIEW', error='Independent review requested changes.')
        except (OSError, ValueError, KeyError, TypeError, Conflict) as exc:
            if not review_invoked:
                review_not_launched('Independent review tool selection failed before invocation.')
            result['transport'].update(status='FAILED', error_class=getattr(exc, 'code', 'REVIEW'), error='Independent review could not be validated.')
        return result
