"""Linux-side adapter for a Windows host reached over an SSH reverse tunnel."""
import time
import hashlib
from urllib.parse import urlsplit
import httpx
from ..core.models import TestError, Connection, digest
from ..execution.source_snapshots import create_archive
from ..catalog_settings import DEFAULT_CATALOG_TIMEOUT_SECONDS, validate_catalog_timeout_seconds


class WindowsRemote:
    simulation = False
    branches = ['shared']

    def __init__(self, url, token, client=None, *, catalog_timeout_provider=None, diagnostics=None):
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
            raise ValueError('TEST BOARD CONNECTOR URL must be an HTTP loopback SSH tunnel endpoint')
        if len(token) < 32: raise ValueError('Set GUI_TEST_RUNNER_TOKEN in both Dashboard API and worker environments')
        self.url = url.rstrip('/')
        self.token = token
        self.client = client or httpx.Client(timeout=5, follow_redirects=False, trust_env=False)
        self.catalog_timeout_provider = catalog_timeout_provider or (lambda: DEFAULT_CATALOG_TIMEOUT_SECONDS)
        from ..core.diagnostics import DiagnosticRecorder
        self.diagnostics = diagnostics or DiagnosticRecorder()

    def connection_error(self, message, code, started, *, phase='runner-request', cause='Runner transport failed', attempt=1, status=503):
        error = TestError(message, code, status)
        error.diagnostic = self.diagnostics.record(phase, self.url, code, cause,
            'Check the TEST BOARD CONNECTOR service, reverse SSH tunnel, matching token and pinned runner identity.',
            attempt=attempt, duration_ms=int((time.monotonic() - started) * 1000))
        return error

    def request(self, path, method='GET', data=None, *, catalog_timeout=None, operation_timeout=None):
        started = time.monotonic()
        phase = ('runner-catalog' if path == '/catalog' else 'runner-health' if path == '/identity' else
                 'installer-transfer' if path.startswith('/installer-snapshots') else
                 'runner-batch' if path.startswith('/batches') else 'runner-tc')
        try:
            response = self.client.request(method, self.url + '/v1' + path,
                headers={'Authorization': 'Bearer ' + self.token}, **({'json': data} if data is not None else {}),
                **({'timeout': catalog_timeout if catalog_timeout is not None else operation_timeout}
                   if catalog_timeout is not None or operation_timeout is not None else {}))
            if response.status_code >= 400:
                code = 'RUNNER_AUTH_REQUIRED' if response.status_code in {401, 403} else 'RUNNER_REJECTED'
                raise self.connection_error('TEST BOARD CONNECTOR rejected the request; check source, COM mapping, command and active executions',
                    code, started, phase=phase, cause='Runner HTTP status ' + str(response.status_code), status=response.status_code)
            limit = 5 * 1024 * 1024 if path.startswith('/installer-snapshots/') else 2 * 1024 * 1024
            if response.status_code != 200 or len(response.content) > limit:
                raise ValueError('Invalid runner response')
            return response.json()
        except httpx.TimeoutException as exc:
            if operation_timeout is not None:
                raise self.connection_error('커넥터의 세션 삭제 완료를 기다리는 중 시간 초과입니다. 연결 복구 후 삭제를 다시 시도하세요.',
                    'SESSION_DELETE_PENDING', started, phase=phase, cause='Session deletion response timeout', status=504) from exc
            if catalog_timeout is not None:
                raise self.connection_error(f'TC 목록 읽기가 제한시간 {catalog_timeout}초를 초과했습니다. TC 공유 폴더와 실행기 연결을 확인하거나 목록 읽기 제한시간을 조정하세요.',
                    'TC_CATALOG_TIMEOUT', started, phase=phase, cause='Runner catalog timeout', status=504) from exc
            raise self.connection_error('TEST BOARD CONNECTOR is unavailable; check the runner and SSH tunnel', 'RUNNER_UNAVAILABLE', started, phase=phase, cause='Runner request timeout') from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise self.connection_error('TEST BOARD CONNECTOR is unavailable; check the runner and SSH tunnel', 'RUNNER_UNAVAILABLE', started,
                phase=phase, cause='Runner connection or response validation failed') from exc

    def catalog(self, branch='shared'):
        if branch not in {'shared', 'demo/main'}: raise TestError('Use the configured shared TC source')
        seconds = validate_catalog_timeout_seconds(self.catalog_timeout_provider())
        return self.request('/catalog', catalog_timeout=seconds)

    def readiness(self):
        try:
            identity = self.request('/identity')
            if not isinstance(identity, dict):
                raise TestError('Invalid TEST BOARD CONNECTOR identity', 'RUNNER_UNAVAILABLE')
        except TestError as exc:
            return {'ready': False, 'code': 'RUNNER_UNAVAILABLE',
                    'message': 'TEST BOARD CONNECTOR에 연결할 수 없습니다. 실행기와 SSH 터널을 확인하세요.',
                    'capabilities': {'source_snapshot_v1': False}, 'diagnostic': getattr(exc, 'diagnostic', None)}
        return {'ready': True, 'execution_ready': identity.get('tc_python_configured_v1') is not False, 'code': 'READY',
                'message': 'TEST BOARD CONNECTOR 응답을 확인했습니다. 보드와 TC는 Preflight에서 검사합니다.',
                'runner_id': identity.get('runner_id'),
                'capabilities': {key: identity.get(key) is True for key in
                                 ('source_snapshot_v1', 'installer_stream_v1', 'batch_reservation_v1', 'bsp_upgrade_integration_v1')}}

    def integration_identity(self, expected=None):
        value = self.request('/identity')
        if not all(value.get(key) is True for key in ('source_snapshot_v1', 'installer_stream_v1', 'batch_reservation_v1', 'bsp_upgrade_integration_v1')):
            raise self.connection_error('TEST BOARD CONNECTOR integration capabilities are unavailable', 'RUNNER_CAPABILITY', time.monotonic(),
                phase='runner-capability', cause='Runner integration capability/version mismatch')
        if value.get('tc_python_configured_v1') is False:
            raise TestError('커넥터에서 외부 TC Python을 설정하세요.','TC_PYTHON_NOT_CONFIGURED',409)
        if expected is not None and value.get('runner_id') != expected:
            raise self.connection_error('TEST BOARD CONNECTOR identity changed', 'RUNNER_CHANGED', time.monotonic(),
                phase='runner-identity', cause='Runner identity differs from pinned configuration')
        return value

    def require_timeout_support(self):
        if self.request('/identity').get('tc_timeout_v1') is not True:
            raise TestError('대시보드 TC 제한시간을 적용하려면 TEST BOARD CONNECTOR를 tc_timeout_v1 지원 버전으로 업데이트하세요.',
                            'TC_TIMEOUT_UNSUPPORTED')

    def delete_session(self, run):
        integration = run.get('integration', {})
        batch = integration.get('batch') or {}
        attempts = [a for a in run['attempts'] if str(a.get('process_ref', '')).startswith('windows:')]
        if not attempts and not batch:
            return {'deleted': True}
        identity = self.request('/identity')
        if identity.get('session_delete_v1') is not True:
            raise TestError('영구 삭제를 지원하는 TEST BOARD CONNECTOR로 업데이트하세요.', 'SESSION_DELETE_UNSUPPORTED')
        expected = run.get('runner_id_snapshot') or integration.get('config', {}).get('runner_id')
        if expected and identity.get('runner_id') != expected:
            raise TestError('원래 시험을 실행한 커넥터 저장소에 연결해야 합니다.', 'RUNNER_CHANGED')
        ids = []
        for attempt in attempts:
            execution_id = attempt['process_ref'].split(':', 1)[1]
            payload = {'id': execution_id, 'tc_id': attempt['tc_id'], 'source_revision': run['source_revision'],
                       'connection': Connection.model_validate(run['connection_snapshot']).model_dump(),
                       'template': run['command_snapshot']['template']}
            snapshot = run.get('source_snapshot') or integration.get('receipt', {}).get('source_snapshot')
            if snapshot: payload['snapshot_id'] = snapshot['snapshot_id']
            if batch: payload.update(batch_id=batch['batch_id'], batch_token=batch['token'], batch_epoch=batch['epoch'])
            if run.get('timeout_override'):
                payload['timeout_seconds'] = next(t['timeout'] for t in run['tests'] if t['id'] == attempt['tc_id'])
            try:
                job = self.request('/executions/' + execution_id)
            except TestError as exc:
                if exc.status != 404 or not expected:
                    raise TestError('원래 실행 기록을 확인하지 못했습니다. 연결 복구 후 삭제를 다시 시도하세요.', 'SESSION_DELETE_UNVERIFIED') from exc
            else:
                if job.get('request_hash') != digest(payload):
                    raise TestError('삭제 대상이 원래 실행 요청과 다릅니다.', 'SESSION_DELETE_UNVERIFIED')
            ids.append(execution_id)
        if batch.get('prepare_id'): ids.append(batch['prepare_id'])
        ids = list(dict.fromkeys(ids))
        groups = [ids[index:index + 128] for index in range(0, len(ids), 128)] or [[]]
        for index, group in enumerate(groups):
            payload = {'runner_id': identity['runner_id'], 'execution_ids': group}
            if batch: payload['batch_id'] = batch['batch_id']
            result = self.request('/session-deletions', 'POST', payload, operation_timeout=120)
            if result.get('deleted') is not True or result.get('runner_id') != identity['runner_id']:
                raise TestError('커넥터의 영구 삭제 완료를 확인하지 못했습니다.', 'SESSION_DELETE_UNVERIFIED')
        return {'deleted': True}

    def prepare_installer(self, directory, descriptor):
        from ..execution.installer_snapshots import create_archive as installer_archive
        self.integration_identity()
        with installer_archive(directory, descriptor) as archive:
            h = hashlib.sha256(); size = 0
            for chunk in iter(lambda: archive.read(1024 * 1024), b''):
                size += len(chunk); h.update(chunk)
            archive_sha = h.hexdigest()
            last_error = None
            for attempt in range(3):
                started = time.monotonic()
                try:
                    previous = self.request('/installer-snapshots/' + descriptor['snapshot_id'])
                    if previous.get('snapshot_id') != descriptor['snapshot_id']:
                        raise TestError('Installer receipt identity mismatch', 'IMAGE_CHANGED')
                    if previous.get('archive_sha256') not in {None, archive_sha}:
                        raise TestError('Installer transport hash changed', 'IMAGE_CHANGED')
                    if previous.get('state') == 'READY':
                        if previous.get('manifest') != descriptor:
                            raise TestError('Installer publication acknowledgement mismatch', 'IMAGE_CHANGED')
                        return previous
                    offset = previous.get('offset', 0)
                    if type(offset) is not int or not 0 <= offset <= size:
                        raise TestError('Invalid installer resume offset', 'IMAGE_OFFSET')
                    archive.seek(offset)
                    response = self.client.request('PUT', self.url + '/v1/installer-snapshots/' + descriptor['snapshot_id'],
                        headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/zip',
                                 'Content-Length': str(size - offset), 'Content-Range': f'bytes {offset}-{size - 1}/{size}',
                                 'X-Archive-SHA256': archive_sha},
                        content=iter(lambda: archive.read(1024 * 1024), b''), timeout=600)
                    if response.status_code != 200 or len(response.content) > 5 * 1024**2:
                        raise self.connection_error('Windows installer stream rejected', 'IMAGE_TRANSPORT', started,
                            phase='installer-transfer', cause='Installer HTTP status or response limit rejected', attempt=attempt + 1)
                    value = response.json()
                    if value.get('snapshot_id') != descriptor['snapshot_id'] or value.get('state') != 'READY' or value.get('manifest') != descriptor:
                        raise TestError('Installer acknowledgement mismatch', 'IMAGE_CHANGED')
                    return value
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    self.connection_error('Installer transfer interrupted; receipt retained', 'RUNNER_UNAVAILABLE', started,
                        phase='installer-transfer', cause='Installer stream connection or response failed', attempt=attempt + 1)
                    if attempt < 2: time.sleep(2 ** (attempt + 1))
                except TestError as exc:
                    if exc.code != 'RUNNER_UNAVAILABLE': raise
                    last_error = exc
                    if attempt < 2: time.sleep(2 ** (attempt + 1))
            raise self.connection_error('Installer transfer interrupted; receipt retained', 'RUNNER_UNAVAILABLE', started,
                phase='installer-transfer', cause='Installer transfer retries exhausted', attempt=3) from last_error

    def reserve_batch(self, payload):
        self.integration_identity(payload.get('runner_id'))
        return self.request('/batches', 'POST', payload)

    def integration_profile(self, name):
        identity = self.integration_identity()
        if not isinstance(name, str) or not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-' for c in name):
            raise TestError('Invalid registered flash profile', 'FLASH_NOT_CONFIGURED')
        value = self.request('/flash-profiles/' + name)
        if (value.get('profile') != name or value.get('runner_id') != identity['runner_id'] or
                not isinstance(value.get('revision'), str) or len(value['revision']) != 64 or
                any(c not in '0123456789abcdef' for c in value['revision'])):
            raise TestError('Registered profile receipt identity mismatch', 'RUNNER_MISMATCH')
        return value

    def prepare_batch(self, batch_id, payload):
        return self.request('/batches/' + batch_id + '/prepare', 'POST', payload)

    def batch_status(self, identity): return self.request('/batches/' + identity)

    def cancel_batch(self, receipt):
        return self.request('/batches/' + receipt['batch_id'] + '/cancel', 'POST', {key: receipt[key] for key in ('token', 'epoch')})

    def release_batch(self, receipt):
        return self.request('/batches/' + receipt['batch_id'] + '/release', 'POST', {key: receipt[key] for key in ('token', 'epoch')})

    def reconcile_batch(self, receipt):
        return self.request('/batches/' + receipt['batch_id'] + '/reconcile', 'POST',
                            {key: receipt[key] for key in ('token', 'epoch', 'prepare_id') if key in receipt})

    def begin_integration(self, receipt, context):
        if context.get('timeout_override'):
            self.require_timeout_support()
        identity = self.integration_identity(context['config']['runner_id'])
        self.prepare_source(receipt['source_directory'], receipt['source_snapshot'])
        self.prepare_installer(receipt['installer_directory'], receipt['installer_snapshot'])
        batch = self.reserve_batch({'id': context['run_id'], 'request_id': context['run_id'],
                                    'runner_id': identity['runner_id'], 'connection': context['connection']})
        value = {key: batch[key] for key in ('batch_id', 'token', 'epoch', 'runner_id')}
        value.update(prepare_id=digest({'run_id': context['run_id'], 'kind': 'prepare'})[:32], state='RUNNING')
        # The backend persists ownership before this method can issue a hardware preparation request.
        context['save_batch'](value)
        try:
            self.prepare_batch(batch['batch_id'], {'id': value['prepare_id'], 'token': batch['token'], 'epoch': batch['epoch'],
                'profile': context['config']['flash_profile'], 'snapshot_id': receipt['installer_snapshot']['snapshot_id'],
                'profile_revision': context['config']['flash_profile_revision'],
                'connection': context['connection'],
                'source_revision': receipt['source_snapshot']['source_revision']})
        except TestError:
            return value | {'state': 'UNKNOWN', 'reason': 'Preparation submission requires receipt reconciliation'}
        return value

    def reconcile_integration(self, run_id, batch_receipt):
        self.integration_identity(batch_receipt['runner_id'])
        batch = self.reconcile_batch(batch_receipt)
        if batch.get('runner_id') != batch_receipt['runner_id'] or batch.get('epoch') != batch_receipt['epoch']:
            raise TestError('Batch recovery identity mismatch', 'RUNNER_CHANGED')
        value = dict(batch_receipt)
        if batch['state'] in {'UNKNOWN', 'RELEASED'}:
            return value | {'state': 'UNKNOWN', 'reason': batch.get('reason', 'Reservation no longer permits execution')}
        try:
            job = self.request('/executions/' + batch_receipt['prepare_id'])
        except TestError:
            return value | {'state': 'UNKNOWN', 'reason': 'Preparation receipt not established; no resubmission'}
        if job.get('batch_id') != batch_receipt['batch_id'] or job.get('runner_id') != batch_receipt['runner_id']:
            return value | {'state': 'UNKNOWN', 'reason': 'Preparation receipt identity mismatch'}
        if job['state'] == 'UNKNOWN': state = 'UNKNOWN'
        elif job['state'] == 'DONE': state = 'READY' if job.get('phase') == 'READY' and batch['state'] == 'READY' else 'FAILED'
        else: state = 'RUNNING'
        return value | {'state': state, 'phase': job.get('phase'), 'reason': job.get('reason', ''), 'console': job.get('console'),
                        'terminated': job.get('terminated') is True, 'not_started': job.get('not_started') is True}

    def finish_integration(self, batch_receipt):
        return self.release_batch(batch_receipt)

    def boards(self): return self.request('/boards')['boards']

    def verify(self, connection, dual):
        value = dict(connection)
        if not dual: value['b'] = None
        self.request('/verify', 'POST', value)

    def probe(self, process_ref):
        if not process_ref.startswith('windows:'): return 'UNKNOWN'
        try:
            value = self.request('/executions/' + process_ref.split(':', 1)[1] + '/reconcile', 'POST')
            return 'STOPPED' if value.get('terminated') is True else 'UNKNOWN'
        except TestError: return 'UNKNOWN'

    def prepare_source(self, directory, descriptor):
        status = self.readiness()
        if not status['ready']:
            raise TestError(status['message'], status['code'], 503)
        if status['capabilities'].get('source_snapshot_v1') is not True:
            raise TestError('TEST BOARD CONNECTOR does not support source snapshots', 'SOURCE_SNAPSHOT_UNSUPPORTED')
        with create_archive(directory, descriptor) as archive:
            archive.seek(0, 2)
            size = archive.tell()
            archive.seek(0)
            started = time.monotonic()
            try:
                response = self.client.request('PUT', self.url + '/v1/source-snapshots/' + descriptor['snapshot_id'],
                    headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/zip', 'Content-Length': str(size)},
                    content=iter(lambda: archive.read(65536), b''), timeout=120)
                if response.status_code != 200 or len(response.content) > 65536:
                    raise self.connection_error('TEST BOARD CONNECTOR rejected the source snapshot', 'SOURCE_SNAPSHOT_REJECTED', started,
                        phase='tc-source-transfer', cause='TC source HTTP status or acknowledgement limit rejected')
                value = response.json()
                if value.get('snapshot_id') != descriptor['snapshot_id'] or value.get('source_revision') != descriptor['source_revision']:
                    raise TestError('Windows source snapshot acknowledgement mismatch', 'SOURCE_CHANGED')
            except (httpx.HTTPError, ValueError) as exc:
                raise self.connection_error('Windows source snapshot transfer failed', 'RUNNER_UNAVAILABLE', started,
                    phase='tc-source-transfer', cause='TC source stream connection or response failed') from exc

    def execute(self, tc, connections, timeout, context, emit, cancelled):
        identity = context['process_ref'].split(':', 1)[1]
        path = '/executions/' + identity
        payload = {'id': identity, 'tc_id': tc['id'], 'source_revision': context['source_revision'],
                   'connection': Connection.model_validate(connections).model_dump(), 'template': context['command_template']}
        if context.get('timeout_override'):
            self.require_timeout_support()
            payload['timeout_seconds'] = timeout
        if context.get('integration_batch'):
            batch = context['integration_batch']
            payload.update(batch_id=batch['batch_id'], batch_token=batch['token'], batch_epoch=batch['epoch'])
        if context.get('source_snapshot'):
            # Upload has no execution side effects; a failure here proves this attempt was not submitted.
            try:
                self.prepare_source(context['source_directory'], context['source_snapshot'])
            except (TestError, OSError, ValueError):
                return {'exit_code': None, 'terminated': True, 'forced_state': 'ERROR'}
            payload['snapshot_id'] = context['source_snapshot']['snapshot_id']
        offsets = {'stdout': 0, 'stderr': 0}
        auth = ({key: context['integration_batch'][key] for key in ('token', 'epoch')}
                if context.get('integration_batch') else None)
        try:
            try: self.request('/executions', 'POST', payload)
            except TestError:
                # An HTTP failure is not evidence that the TC did not start. Never resubmit.
                self.request(path)
            deadline = time.monotonic() + timeout + 20
            while time.monotonic() < deadline:
                value = self.request(path + ('/cancel' if cancelled() else '/poll'), 'POST', auth)
                if value.get('id') != identity or value.get('source_revision') != context['source_revision'] or value.get('request_hash') != digest(payload):
                    raise TestError('Runner response does not match this attempt', 'RUNNER_MISMATCH')
                for stream in offsets:
                    text = value.get(stream, '')
                    if not isinstance(text, str) or len(text) < offsets[stream] or len(text.encode()) > 262144:
                        raise TestError('Invalid runner log snapshot')
                    emit(stream, text[offsets[stream]:]); offsets[stream] = len(text)
                if value.get('state') in {'DONE', 'UNKNOWN'}:
                    # Configured COM mapping is not proof of physical board/image identity.
                    result = {key: value[key] for key in ('exit_code', 'terminated', 'forced_state') if key in value}
                    result['executed_command_argv'] = value.get('argv')
                    if context.get('integration_batch') or isinstance(value.get('console'), dict):
                        evidence = value.get('console')
                        if isinstance(evidence, dict):
                            result['console'] = {key: evidence[key] for key in ('unsafe', 'panic', 'console_failure', 'fenced') if key in evidence}
                            result['console']['observers'] = [{key: row[key] for key in
                                ('offset', 'boot_epoch', 'phase_epoch', 'phase', 'start_offset', 'end_offset', 'panic',
                                 'unexpected_boot', 'events', 'gaps', 'complete', 'evidence_overflow', 'log_directory', 'rotations', 'retained_from')
                                if key in row} for row in evidence.get('observers', []) if isinstance(row, dict)]
                        rows = evidence.get('observers', []) if isinstance(evidence, dict) else []
                        result['panic'] = value.get('panic') is True or (isinstance(evidence, dict) and evidence.get('panic') is True) or any(row.get('panic') is True for row in rows if isinstance(row, dict))
                        result['console_failure'] = (value.get('console_failure') is True or
                            (isinstance(evidence, dict) and evidence.get('unsafe') is True) or
                            any(row.get('complete') is False or row.get('gaps') or row.get('unexpected_boot') is True
                                for row in rows if isinstance(row, dict)))
                        if result['panic'] or result['console_failure']:
                            result.update(forced_state='ERROR', reason='CONSOLE_UNSAFE')
                    return result
                time.sleep(.1)
            self.request(path + '/cancel', 'POST', auth)
        except TestError:
            pass
        return {'exit_code': None, 'terminated': False}
