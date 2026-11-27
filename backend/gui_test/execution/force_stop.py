"""Explicit local emergency stop, pinned to OS process generations.

Only standard-library imports: this path must not install packages or start a
service. It does not establish board/BSP completion or release reservations.
"""
from contextlib import ExitStack
import ctypes
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import uuid

from .launch import _identity, _process_parents, _created_before, process_identity

WINDOWS = os.name == 'nt'


class DiscoveryIncomplete(RuntimeError):
    """A parent exited before its complete final child scan was saved."""


def atomic_record(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
        for delay in (0.05, 0.1, 0.2, None):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                if not WINDOWS or getattr(exc, 'winerror', None) not in (5, 32, 33):
                    raise
                if delay is None:
                    raise RuntimeError(f'FORCE_STOP_PENDING: 종료 기록 {path}을 갱신할 수 없습니다. '
                                       '파일 사용 여부와 프로필 폴더의 쓰기 권한을 확인하세요.') from exc
                time.sleep(delay)
    finally:
        temporary.unlink(missing_ok=True)


def require_force_complete(path):
    path = Path(path)
    if path.exists():
        record = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(record, dict):
            raise ValueError('Invalid force-stop record')
        if record.get('state') != 'FORCE_STOPPED':
            if record.get('detail'):
                raise RuntimeError(str(record['detail']))
            raise RuntimeError('FORCE_STOP_PENDING: 강제 종료 명령을 다시 실행해 로컬 종료를 확인하세요.')


class PinnedProcess:
    """Signal an open process object, never a PID looked up again at kill time."""
    def __init__(self, identity):
        self.identity = dict(_identity(identity))
        self.handle = None
        self.paused = False
        try:
            if WINDOWS:
                from ctypes import wintypes
                self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                self.kernel.OpenProcess.restype = wintypes.HANDLE
                self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
                self.kernel.GetProcessTimes.restype = wintypes.BOOL
                self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                self.kernel.TerminateProcess.restype = wintypes.BOOL
                self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                self.kernel.WaitForSingleObject.restype = wintypes.DWORD
                self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                self.handle = self.kernel.OpenProcess(0x1000 | 0x100000 | 1, False, identity['pid'])
                if not self.handle:
                    raise ctypes.WinError(ctypes.get_last_error())
                times = [wintypes.FILETIME() for _ in range(4)]
                if not self.kernel.GetProcessTimes(self.handle, *(ctypes.byref(v) for v in times)):
                    raise ctypes.WinError(ctypes.get_last_error())
                created = str(times[0].dwLowDateTime | times[0].dwHighDateTime << 32)
                if created != identity['creation_time']:
                    raise ProcessLookupError('Stored process generation has exited')
            else:
                if not sys.platform.startswith('linux') or not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
                    raise RuntimeError('FORCE_STOP_UNSUPPORTED: Linux pidfd 또는 Windows process handle이 필요합니다.')
                self.handle = os.pidfd_open(identity['pid'])
                if process_identity(identity['pid']) != identity:
                    raise ProcessLookupError('Stored process generation has exited')
        except BaseException:
            self.close()
            raise

    def alive(self):
        if WINDOWS:
            result = self.kernel.WaitForSingleObject(self.handle, 0)
            if result == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
            return result == 258
        return not select.select([self.handle], [], [], 0)[0]

    def pause(self):
        if WINDOWS or not self.alive():
            return
        signal.pidfd_send_signal(self.handle, signal.SIGSTOP)
        self.paused = True
        deadline = time.monotonic() + 2
        while self.alive():
            try:
                raw = Path(f"/proc/{self.identity['pid']}/stat").read_text(encoding='ascii')
            except FileNotFoundError:
                return
            if raw[raw.rindex(')') + 2:].split()[0] in {'T', 't'}:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError('FORCE_STOP_PENDING: 프로세스 정지 확인 시간 초과')
            time.sleep(.01)

    def kill(self):
        if not self.alive():
            return
        if WINDOWS:
            if not self.kernel.TerminateProcess(self.handle, 1) and self.alive():
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            signal.pidfd_send_signal(self.handle, signal.SIGKILL)

    def close(self):
        if self.handle is not None:
            try:
                # A failed discovery must not leave healthy processes SIGSTOPed.
                if self.paused and self.alive():
                    signal.pidfd_send_signal(self.handle, signal.SIGCONT)
            finally:
                if WINDOWS:
                    self.kernel.CloseHandle(self.handle)
                else:
                    os.close(self.handle)
                self.handle = None


def _permission_error(pid, operation):
    return RuntimeError(f'FORCE_STOP_PENDING: PID {pid}의 {operation} 권한이 없습니다. '
                        '커넥터를 실행한 Windows 계정과 권한 수준에서 확인하세요.')


def recorded_process_alive(identity):
    """Only a native match authorizes pinning. CIM may disprove an old receipt."""
    pid = identity['pid']
    try:
        return process_identity(pid) == identity
    except PermissionError as exc:
        if not WINDOWS:
            raise
        try:
            parents = _process_parents()
            if parents and pid not in parents:
                return False
            _, births = _windows_recovery_times()
        except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError):
            births = {}
        # CIM truncates FILETIME to microseconds. A strictly newer process
        # cannot be the saved owner. Fail closed on missing/ambiguous evidence.
        stamp = identity['creation_time']
        if stamp.isdecimal() and births.get(pid, 0) > int(stamp) + 10:
            return False
        raise _permission_error(pid, '프로세스 생성 시각 조회') from exc


def force_owned(owners, checkpoint, phase=None):
    """Freeze Linux trees; pin Windows handles through post-termination scans.

    Windows preserves PPID after exit; keeping every process handle open also
    prevents PID reuse. A second child scan after the pinned parent exits catches
    children born between the first scan and termination. Creation time rejects
    old orphans carrying a recycled parent's numeric PID.
    """
    owners = [dict(_identity(value)) for value in owners]
    phase = phase or (lambda value: None)
    parents = _process_parents()
    ancestors = {os.getpid()}
    parent = os.getpid()
    while parents.get(parent) and parents[parent] not in ancestors:
        parent = parents[parent]
        ancestors.add(parent)
    if any(value['pid'] in ancestors and recorded_process_alive(value) for value in owners):
        raise ValueError('FORCE_STOP_BLOCKED: 호출자 또는 그 상위 프로세스는 종료할 수 없습니다.')
    pinned = {}
    deadline = time.monotonic() + 15
    with ExitStack() as stack:
        def capture(identity, expected_parent=None):
            if not recorded_process_alive(identity):
                return  # Already exited or a reused PID: never signal the replacement.
            if identity['pid'] in pinned:
                if pinned[identity['pid']].identity != identity:
                    raise RuntimeError('FORCE_STOP_PENDING: 프로세스 세대가 바뀌었습니다.')
                return
            if len(pinned) >= 4096 or time.monotonic() >= deadline:
                raise RuntimeError('FORCE_STOP_PENDING: 하위 프로세스 탐색 한도 초과')
            try:
                handle = PinnedProcess(identity)
            except ProcessLookupError:
                return
            except PermissionError as exc:
                if not WINDOWS:
                    raise
                raise _permission_error(identity['pid'], '종료') from exc
            stack.callback(handle.close)
            if expected_parent is not None:
                # A child PID from the discovery snapshot may have exited and
                # been reused before it was pinned. Re-read PPID only after the
                # new handle is open; a newer unrelated process is not our child.
                if _process_parents().get(identity['pid']) != expected_parent.identity['pid']:
                    return
                if not WINDOWS and not expected_parent.alive():
                    return
            pinned[identity['pid']] = handle
            # Persist each newly pinned generation immediately. In particular,
            # a later Windows post-kill discovery error must not lose this child.
            checkpoint([*owners, *(value.identity for value in pinned.values())])
            handle.pause()

        for owner in owners:
            capture(owner)

        def discover():
            count = len(pinned)
            for pid, parent_pid in _process_parents().items():
                parent = pinned.get(parent_pid)
                if parent is None or pid in pinned:
                    continue
                if not WINDOWS and not parent.alive():
                    continue
                try:
                    child = process_identity(pid)
                except PermissionError as exc:
                    if not WINDOWS:
                        raise
                    raise _permission_error(pid, '자식 프로세스 조회') from exc
                if child and _created_before(parent.identity, child):
                    capture(child, parent)
            return len(pinned) != count

        while discover():
            pass
        checkpoint([value.identity for value in pinned.values()])
        index = 0
        while index < len(pinned):
            handle = list(pinned.values())[index]
            if WINDOWS:
                # Persist before TerminateProcess: even interruption of this
                # command must leave evidence that the final scan is outstanding.
                phase(handle.identity)
            try:
                handle.kill()
            except PermissionError as exc:
                if not WINDOWS:
                    raise
                raise _permission_error(handle.identity['pid'], '종료') from exc
            until = time.monotonic() + 5
            while handle.alive():
                if time.monotonic() >= until:
                    raise RuntimeError('FORCE_STOP_PENDING: 프로세스 종료 확인 시간 초과')
                time.sleep(.02)
            if WINDOWS:
                # All parent handles remain pinned until the entire traversal ends.
                try:
                    while discover():
                        pass
                    checkpoint([value.identity for value in pinned.values()])
                    phase(None)
                except (OSError, ValueError, RuntimeError) as exc:
                    raise DiscoveryIncomplete(str(exc) if str(exc).startswith('FORCE_STOP_PENDING:') else
                                              'FORCE_STOP_PENDING: 부모 종료 후 자식 프로세스를 확인하지 못했습니다.') from exc
            index += 1
        return [value.identity for value in pinned.values()]


def _windows_recovery_times():
    """Supplement Toolhelp with read-only creation times for protected processes."""
    query = """
$ErrorActionPreference = 'Stop'
$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToFileTimeUtc()
$rows = @(Get-CimInstance Win32_Process -Property ProcessId,CreationDate | ForEach-Object {
    if ($_.CreationDate) { [pscustomobject]@{pid=$_.ProcessId; born=$_.CreationDate.ToFileTimeUtc()} }
})
ConvertTo-Json -Compress -Depth 3 -InputObject @{boot=$boot; rows=$rows}
"""
    exe = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    response = subprocess.run([str(exe), '-NoProfile', '-NonInteractive', '-Command', query],
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              check=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    data = json.loads(response.stdout.decode('utf-8-sig'))
    return int(data['boot']), {int(row['pid']): int(row['born']) for row in data['rows']}


def _verify_previous_windows_tree(earliest, previous_write_ns):
    """Prove no surviving process can descend from the lost generation. Never signal candidates."""
    filetime_epoch = 116444736000000000
    before = time.time_ns() // 100 + filetime_epoch
    parents = _process_parents()
    if not parents:
        raise RuntimeError('FORCE_STOP_PENDING: Windows 프로세스 목록이 비어 있어 종료를 확인할 수 없습니다.')
    times = {}
    supplementary = None

    def supplement():
        nonlocal supplementary
        if supplementary is None:
            try:
                supplementary = _windows_recovery_times()
            except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError):
                supplementary = (0, {})
        return supplementary

    def birth(pid):
        if pid not in times:
            try:
                value = process_identity(pid)
                ticks = int(value['creation_time']) if value else 0
            except OSError:
                ticks = supplement()[1].get(pid, 0)
            # Reject a replacement created after the Toolhelp snapshot began.
            times[pid] = ticks if 0 < ticks < before - 10 else 0
        return times[pid]

    # Every surviving orphan chain has an edge to an absent/recycled parent.
    # Such an edge predating all possible owners cannot belong to the lost tree.
    # 0 and 4 are Windows kernel PIDs. CIM times have microsecond precision.
    for pid, parent in parents.items():
        if pid in (0, 4) or parent == 4:
            continue
        child_time = birth(pid)
        if child_time and child_time + 10 < earliest:
            continue
        parent_time = birth(parent) if parent and parent in parents else 0
        if parent_time and parent_time + 10 < child_time:
            continue
        boot, _ = supplement()
        if previous_write_ns and previous_write_ns // 100 + filetime_epoch + 10 < boot <= before:
            return  # No descendant from the previous Windows boot can survive.
        raise RuntimeError(f'FORCE_STOP_PENDING: Windows PID {pid} (부모 {parent})의 이전 소유 트리와의 '
                           '관계를 확인할 수 없습니다. 이 PID와 부모의 생성 시각을 확인하세요.')


def stop_recorded(path, owners, *, verify_stopped=None):
    """Durable pending evidence allows retry after a partial emergency stop."""
    path = Path(path)
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    if previous is not None and (not isinstance(previous, dict) or previous.get('version') != 1 or
                                 not isinstance(previous.get('targets'), list)):
        raise ValueError('Invalid force-stop retry record')
    if previous and previous.get('state') == 'FORCE_STOPPED':
        previous = None
    previous_write_ns = path.stat().st_mtime_ns if previous else None
    if previous:
        owners = [*owners, *previous['targets']]
    interrupted_tree = False
    if previous and previous.get('termination_started'):
        completed = previous.get('completed', [])
        try:
            interrupted_tree = any(value not in completed and not recorded_process_alive(value)
                                   for value in previous['targets'])
        except RuntimeError as exc:
            atomic_record(path, dict(previous, state='FORCE_STOP_PENDING', detail=str(exc)))
            raise
    record = {'version': 1, 'state': 'FORCE_STOPPING', 'targets': owners,
              'execution_state': 'UNKNOWN', 'records_preserved': True,
              'tree_unverified': bool(interrupted_tree or previous and previous.get('tree_unverified')),
              'termination_started': False, 'post_exit_scan_pending': None,
              'completed': previous.get('completed', []) if previous else []}
    if WINDOWS:
        # Older retries sometimes discarded all prior targets. In that case the
        # verifier must examine every orphan, without an inferred lower bound.
        births = [int(stamp) if stamp.isdecimal() else 0 for stamp in (_identity(v)['creation_time'] for v in owners)]
        if previous and 'tree_earliest_creation' in previous:
            births.append(previous['tree_earliest_creation'])
        elif previous and previous.get('tree_unverified'):
            births.append(0)
        record['tree_earliest_creation'] = min(births, default=0)
        if record['tree_unverified'] and previous:
            # Keep the original evidence across retries, unless another kill was
            # interrupted since then. This permits proof of an intervening boot.
            saved_at = None if previous.get('post_exit_scan_pending') else previous.get('tree_gap_recorded_ns')
            record['tree_gap_recorded_ns'] = saved_at or previous_write_ns
    atomic_record(path, record)
    def checkpoint(targets):
        record['targets'] = targets
        atomic_record(path, record)
    def phase(value):
        if value is None:
            completed = record['post_exit_scan_pending']
            if completed is not None and completed not in record['completed']:
                record['completed'].append(completed)
        else:
            record['termination_started'] = True
        record['post_exit_scan_pending'] = value
        atomic_record(path, record)
    try:
        stopped = force_owned(owners, checkpoint, phase)
        if verify_stopped:
            verify_stopped(stopped)
        if record['tree_unverified']:
            if not WINDOWS or verify_stopped is None:
                raise RuntimeError('FORCE_STOP_PENDING: 이전 종료의 하위 프로세스 확인이 필요합니다.')
            _verify_previous_windows_tree(record['tree_earliest_creation'], record['tree_gap_recorded_ns'])
            record['tree_unverified'] = False
        record.update(state='FORCE_STOPPED', targets=stopped)
        atomic_record(path, record)
        return record
    except (OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, DiscoveryIncomplete):
            record['tree_unverified'] = True
            record['tree_gap_recorded_ns'] = time.time_ns()
        detail = str(exc) if isinstance(exc, RuntimeError) and str(exc).startswith('FORCE_STOP_PENDING:') else ''
        if WINDOWS and isinstance(exc, PermissionError):
            target = getattr(exc, 'filename', None)
            detail = (f'FORCE_STOP_PENDING: {target} 파일의 접근 권한과 사용 여부를 확인하세요.' if target else
                      'FORCE_STOP_PENDING: 로컬 종료 확인 중 접근이 거부됐습니다. 커넥터를 실행한 계정과 권한 수준을 확인하세요.')
        record.update(state='FORCE_STOP_PENDING', error=type(exc).__name__, detail=detail)
        atomic_record(path, record)
        if detail:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(detail) from exc
        raise RuntimeError('FORCE_STOP_PENDING: 로컬 종료 확인 실패. 같은 명령으로 재시도하세요. '+type(exc).__name__) from exc
