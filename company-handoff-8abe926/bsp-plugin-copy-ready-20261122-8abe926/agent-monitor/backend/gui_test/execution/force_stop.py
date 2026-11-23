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
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def require_force_complete(path):
    path = Path(path)
    if path.exists():
        record = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(record, dict):
            raise ValueError('Invalid force-stop record')
        if record.get('state') != 'FORCE_STOPPED':
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
    if any(value['pid'] in ancestors for value in owners):
        raise ValueError('FORCE_STOP_BLOCKED: 호출자 또는 그 상위 프로세스는 종료할 수 없습니다.')
    pinned = {}
    deadline = time.monotonic() + 15
    with ExitStack() as stack:
        def capture(identity, expected_parent=None):
            if process_identity(identity['pid']) != identity:
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
                child = process_identity(pid)
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
            handle.kill()
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
                    raise DiscoveryIncomplete('Post-exit child discovery is unverified') from exc
            index += 1
        return [value.identity for value in pinned.values()]


def stop_recorded(path, owners):
    """Durable pending evidence allows retry after a partial emergency stop."""
    path = Path(path)
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    if previous is not None and (not isinstance(previous, dict) or previous.get('version') != 1 or
                                 not isinstance(previous.get('targets'), list)):
        raise ValueError('Invalid force-stop retry record')
    if previous and previous.get('state') != 'FORCE_STOPPED':
        owners = [*owners, *previous['targets']]
    interrupted_tree = False
    if previous and previous.get('state') != 'FORCE_STOPPED' and previous.get('termination_started'):
        completed = previous.get('completed', [])
        interrupted_tree = any(value not in completed and process_identity(value['pid']) != value
                               for value in previous['targets'])
    record = {'version': 1, 'state': 'FORCE_STOPPING', 'targets': owners,
              'execution_state': 'UNKNOWN', 'records_preserved': True,
              'tree_unverified': bool(interrupted_tree or previous and previous.get('tree_unverified')),
              'termination_started': False, 'post_exit_scan_pending': None,
              'completed': previous.get('completed', []) if previous and previous.get('state') != 'FORCE_STOPPED' else []}
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
        if record['tree_unverified']:
            raise RuntimeError('이전 탐색 실패의 누락 가능성이 남아 있습니다. OS에서 소유 트리를 확인해야 합니다.')
        record.update(state='FORCE_STOPPED', targets=stopped)
        atomic_record(path, record)
        return record
    except (OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, DiscoveryIncomplete):
            record['tree_unverified'] = True
        record.update(state='FORCE_STOP_PENDING', error=type(exc).__name__)
        atomic_record(path, record)
        raise RuntimeError('FORCE_STOP_PENDING: 로컬 종료 확인 실패. 같은 명령으로 재시도하세요. '+type(exc).__name__) from exc
