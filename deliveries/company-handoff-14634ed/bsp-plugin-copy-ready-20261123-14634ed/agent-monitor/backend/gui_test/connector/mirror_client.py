"""Windows mirror adapter. The existing Manager remains the hardware owner.

The heartbeat publishes observations and claims one bounded UI command. Claimed
commands are never replayed. Terminal receipts survive a lost SSH response.
"""
import copy
import json
from pathlib import Path
import threading
import time
import uuid

from ..core.models import TestError, digest
from .logs import redact
from .mirror import public_profile

PREFIX = '/api/v1/gui-test/live/connector/mirror/'


class MirrorClient:
    def __init__(self, manager):
        self.manager = manager
        self.session_id = uuid.uuid4().hex
        self.directory = Path(manager.home) / 'runtime' / 'mirror-receipts'
        self.thread = None
        self.flush_lock = threading.Lock()

    def request(self, suffix, body):
        from .shared_control import request
        return request(self.manager.home, suffix, 'POST', body, prefix=PREFIX)

    def _write(self, value):
        from scripts.setup_runtime import atomic_write
        self.directory.mkdir(parents=True, exist_ok=True)
        atomic_write(self.directory / (value['command']['command_id'] + '.json'),
                     json.dumps(value, ensure_ascii=False).encode())

    def flush(self):
        # A DONE receipt is retried with its original token, never its action.
        with self.flush_lock:
            for path in sorted(self.directory.glob('*.json')):
                value = json.loads(path.read_text(encoding='utf-8'))
                if value.get('phase') != 'DONE':
                    continue
                command = value['command']
                self.request('commands/' + command['command_id'] + '/receipt', value['receipt'])
                path.unlink()

    def tick(self, status):
        if status.get('state') != 'CONNECTED' or not status.get('fresh'):
            return
        registration = status.get('mirror_registration')
        if not registration:
            return
        manager = self.manager
        with manager.control_lock:
            profile = public_profile(manager.settings.read())
        from ..adapters.windows_ports import enumerate_ports
        payload = {key: copy.deepcopy(status.get(key)) for key in
                   ('state', 'error', 'executions', 'execution_paths', 'server_paths')}
        payload.update(runner_id=registration['runner_id'], session_id=self.session_id,
                       revision=digest(profile), profile=profile, ports=enumerate_ports()['ports'])
        self.request('state', bounded_state(payload, registration))
        self.flush()
        if self.thread and self.thread.is_alive():
            return
        claimed = self.request('claim', {'runner_id': registration['runner_id'],
                                        'session_id': self.session_id}).get('command')
        if not claimed:
            return
        record = {'command': claimed, 'phase': 'CLAIMED'}
        self._write(record)  # Failure here leaves an uncertain claim, never executes it.
        self.thread = threading.Thread(target=self._execute, args=(record,),
                                       name='connector-mirror-command', daemon=True)
        self.thread.start()

    def _execute(self, record):
        command = record['command']
        try:
            if command['action'] == 'restart':
                result = self._restart(command)
            elif command['action'] == 'apply-settings':
                result = self._apply(command['body']['desired_revision'], command['revision'])
            else:
                result = self._control(command)
            state = 'APPLIED'
        except Exception as exc:
            state = 'UNKNOWN' if getattr(exc, 'code', None) == 'CONNECTOR_RESTART_UNCONFIRMED' else 'FAILED'
            result = {'code': getattr(exc, 'code', 'CONNECTOR_COMMAND_FAILED'),
                      'message': redact(str(exc))[:1000]}
        receipt = {key: command[key] for key in ('runner_id', 'session_id', 'claim_token')}
        receipt.update(state=state, result=result)
        record.update(phase='DONE', receipt=receipt)
        self._write(record)
        try:
            self.flush()
        except Exception:
            # The next successful heartbeat sends this same receipt.
            pass

    def _restart(self, command):
        """Restart Host/SSH under the same Manager; never force-stop or replay."""
        from ..execution.launch import read_active
        manager = self.manager
        with manager.control_lock:
            if manager.mirror_applying or digest(public_profile(manager.settings.read())) != command['revision']:
                raise TestError('설정 또는 다른 보드 커넥터 작업을 확인하세요.', 'CONNECTOR_BUSY', 409)
            before = read_active(manager.home / 'runtime')
            if not before or before['runner_id'] != command['runner_id']:
                raise TestError('연결된 보드 커넥터를 확인하세요.', 'RUNNER_CHANGED', 409)
            previous_console = manager.probe().get('console') or {}
            previous_epoch = previous_console.get('epoch')
            if previous_console.get('runner_id') != command['runner_id'] or not previous_epoch:
                raise TestError('기존 콘솔 연결을 확인하세요.', 'CONNECTOR_BUSY', 409)
            manager.mirror_applying = True
        disconnected = False
        stop_confirmed = False
        try:
            with manager.control_lock:
                disconnected = True  # Stop may take effect even if its HTTP response is lost.
                manager._disconnect()  # Existing central/local Run/COM/UNKNOWN guard.
                stop_confirmed = True
            owner = manager.thread
            if owner: owner.join(timeout=45)
            if owner and owner.is_alive() or read_active(manager.home / 'runtime'):
                raise TestError('보드 커넥터 종료 확인 중입니다.', 'CONNECTOR_RESTART_UNCONFIRMED', 409)
            with manager.control_lock:
                # A restart must not implicitly apply somebody's pending settings.
                manager._connect(apply_settings=False)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline and not manager.shutdown.is_set():
                try:
                    actual = read_active(manager.home / 'runtime')
                    status = manager.probe(); manager.cached = status
                    console = status.get('console') or {}
                    if (actual and actual['runner_id'] == command['runner_id'] and
                            actual['launch_id'] != before['launch_id'] and status.get('state') == 'CONNECTED' and
                            status.get('fresh') is True and console.get('runner_id') == command['runner_id'] and
                            console.get('epoch') and console['epoch'] != previous_epoch):
                        from .shared_control import request
                        received = request(manager.home, 'console', prefix='/api/v1/gui-test/live/connector/')
                        if (received.get('fresh') is not True or received.get('runner_id') != command['runner_id'] or
                                received.get('epoch') != console['epoch']):
                            manager.shutdown.wait(1)
                            continue
                        return {'scope': 'connection-host', 'previous_launch_id': before['launch_id'],
                                'launch_id': actual['launch_id'], 'message': '보드 커넥터 Host·SSH 재시작과 재연결을 확인했습니다.'}
                except Exception:
                    pass
                manager.shutdown.wait(1)
            raise TestError('보드 커넥터 재연결을 확인하지 못했습니다.', 'CONNECTOR_RESTART_UNCONFIRMED', 409)
        except Exception as exc:
            if disconnected and (stop_confirmed or not isinstance(exc, TestError) or exc.code != 'CONNECTOR_BUSY'):
                raise TestError('보드 커넥터 재시작 결과를 확인하세요. 자동으로 반복하지 않습니다.',
                                'CONNECTOR_RESTART_UNCONFIRMED', 409) from exc
            raise
        finally:
            with manager.control_lock: manager.mirror_applying = False

    def _control(self, command):
        with self.manager.control_lock:
            if digest(public_profile(self.manager.settings.read())) != command['revision']:
                raise TestError('Windows 설정이 변경됐습니다. 다시 불러오세요.', 'SETTINGS_CHANGED', 409)
            from .web_actions import ManagerActions
            actual = ManagerActions(self.manager).action(command['action'], command['body'])
            # No lease, secret, process command or arbitrary result travels back.
            result = {key: actual[key] for key in ('opened', 'manual', 'board_id') if key in actual}
            return result | {'message': '보드 커넥터에서 처리했습니다.'}

    def _apply(self, revision, profile_revision):
        manager = self.manager
        with manager.control_lock:
            if digest(public_profile(manager.settings.read())) != profile_revision or manager.mirror_applying:
                raise TestError('Windows 설정이 변경됐습니다. 다시 불러오세요.', 'SETTINGS_CHANGED', 409)
            manager.mirror_applying = True
        try:
            return self._reconnect(revision)
        finally:
            with manager.control_lock:
                manager.mirror_applying = False

    def _reconnect(self, revision):
        """Safe reconnect; a saved JSON file alone is never an APPLIED receipt."""
        from .shared_control import request, remember_desired
        from ..execution.launch import read_active
        manager = self.manager
        application = request(manager.home, 'settings')['connector_application']
        if application.get('desired_revision') != revision:
            raise TestError('적용 요청 이후 공통 설정이 변경됐습니다.', 'SETTINGS_CHANGED', 409)
        if application.get('expected_profile_revision') and application['expected_profile_revision'] != digest(public_profile(manager.settings.read())):
            raise TestError('Windows 설정이 변경됐습니다. 공통 설정을 다시 불러오세요.', 'SETTINGS_CHANGED', 409)
        manager.settings.validate(application['settings'])
        receipt = read_active(manager.home / 'runtime')
        if not receipt or receipt['runner_id'] != application['runner_id']:
            raise TestError('연결된 보드 커넥터가 변경됐습니다.', 'RUNNER_CHANGED', 409)
        remember_desired(manager.home, application, receipt['runner_id'], force=True)
        with manager.control_lock:
            manager._disconnect()  # Existing Run, UART, reservation and UNKNOWN guards.
        owner = manager.thread
        if owner:
            owner.join(timeout=45)
        if (owner and owner.is_alive()) or read_active(manager.home / 'runtime'):
            raise TestError('연결 종료를 확인하지 못했습니다. 설정을 적용하지 않았습니다.', 'CONNECTOR_BUSY', 409)
        with manager.control_lock:
            manager._connect(desired_revision=revision)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and not manager.shutdown.is_set():
            try:
                status = manager.probe()
                manager.cached = status
                actual = request(manager.home, 'settings')['connector_application']
                if actual.get('desired_revision') != revision:
                    raise TestError('재연결 중 공통 설정이 변경됐습니다.', 'SETTINGS_CHANGED', 409)
                if status.get('state') == 'CONNECTED' and actual.get('state') == 'APPLIED':
                    return {'applied': True, 'desired_revision': revision,
                            'message': 'Windows 재연결과 실제 설정 적용을 확인했습니다.'}
            except TestError as exc:
                if exc.code == 'SETTINGS_CHANGED':
                    raise
            except Exception:
                pass
            manager.shutdown.wait(1)
        raise TestError('재연결 후 실제 적용을 확인하지 못했습니다. Windows 로그를 확인하세요.',
                        'CONNECTOR_APPLY_UNCONFIRMED', 409)


def bounded_state(payload, registration):
    """Bound encoded traffic before httpx (standalone accepts at most 64 KiB).

    Actual output is a tail window. Never silently truncate a configuration that
    could later be edited; omit older log/path observations first instead.
    """
    from .mirror import public_executions
    value = copy.deepcopy(payload)
    value['executions'] = public_executions(value.get('executions'))
    for record in value['executions']:
        for key in ('stdout', 'stderr'):
            if key in record:
                raw = record[key].encode('utf-8')
                record[key] = raw[-2048:].decode('utf-8', errors='ignore')
    value['logs_truncated'] = value.get('executions') != payload.get('executions')
    result = {'projection': value, 'registration': registration}
    def size():
        # Budget both ASCII-escaped requests clients and httpx's UTF-8 encoding.
        return len(json.dumps(result, ensure_ascii=True).encode('utf-8'))
    for key in ('executions', 'execution_paths', 'ports'):
        while size() > 60000 and value.get(key):
            value[key].pop()
            value['logs_truncated'] = True
    if size() > 60000:
        value['server_paths'] = None
        value['logs_truncated'] = True
    if size() > 60000:
        raise TestError('미러 설정이 전송 한도를 초과했습니다. Windows 설정을 확인하세요.', 'MIRROR_TOO_LARGE', 422)
    return result
