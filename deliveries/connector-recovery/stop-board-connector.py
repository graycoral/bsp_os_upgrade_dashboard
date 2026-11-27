#!/usr/bin/env python3
"""Stop this Windows board connector. Run with Python 3.11+; optional --home PATH.

Standalone copy of the connector's emergency stop implementation. Requires
only the Python standard library. It does not use the network or install
packages. It force-stops owned processes, including active tests or flashing.
"""
import argparse
from contextlib import ExitStack
import ctypes
import hashlib
import ntpath
import re
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import uuid

WINDOWS = os.name == 'nt'


# Process identity and locking (backend/gui_test/execution/launch.py).
def _plain_path(path):
    path = Path(path).absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise ValueError('Launch paths must not contain symbolic links')
    return path


class LaunchLock:
    """Same byte-zero/flock protocol as the host's existing ProcessLock."""
    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        path = _plain_path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if os.fstat(self.file.fileno()).st_size == 0:
                    self.file.write(b'0')
                    self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise RuntimeError('Runner or launcher already running') from exc
        return self

    def __exit__(self, *args):
        self.file.close()


def _lock_held(path):
    if not _plain_path(path).exists():
        return False
    try:
        with LaunchLock(path):
            return False
    except RuntimeError:
        return True


def process_identity(pid):
    """Return a live PID plus OS creation time, preventing PID reuse matches."""
    if type(pid) is not int or pid <= 0:
        raise ValueError('Invalid process id')
    if os.name == 'nt':
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # Process no longer exists.
                return None
            raise ctypes.WinError(error)
        try:
            status = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(status)):
                raise ctypes.WinError(ctypes.get_last_error())
            if status.value != 259:
                return None
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
                raise ctypes.WinError(ctypes.get_last_error())
            created = times[0].dwLowDateTime | times[0].dwHighDateTime << 32
            return {'pid': pid, 'creation_time': str(created)}
        finally:
            kernel.CloseHandle(handle)
    # Linux /proc starttime is monotonic within this boot, unlike wall-clock time.
    try:
        data = Path(f'/proc/{pid}/stat').read_text(encoding='ascii')
        fields = data[data.rindex(')') + 2:].split()
        if fields[0] == 'Z':
            return None
        boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
        return {'pid': pid, 'creation_time': boot + ':' + fields[19]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def _windows_process_snapshot():
    """Return pid -> (parent pid, image name) from one complete Toolhelp snapshot."""
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        function.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)  # TH32CS_SNAPPROCESS
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        entries = {}
        more = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while more:
            entries[entry.th32ProcessID] = (entry.th32ParentProcessID, entry.szExeFile)
            more = kernel.Process32NextW(handle, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise ctypes.WinError(ctypes.get_last_error())
        return entries
    finally:
        kernel.CloseHandle(handle)


def _process_parents():
    """Read OS parent PIDs; identities are checked separately around traversal."""
    if os.name == 'nt':
        return {pid: row[0] for pid, row in _windows_process_snapshot().items()}
    parents = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            data = path.read_text(encoding='ascii')
            fields = data[data.rindex(')') + 2:].split()
            parents[int(path.parent.name)] = int(fields[1])
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return parents


def _created_before(parent, child):
    try:
        left, right = parent['creation_time'], child['creation_time']
        if os.name == 'nt':
            return int(left) <= int(right)
        parent_boot, parent_ticks = left.rsplit(':', 1)
        child_boot, child_ticks = right.rsplit(':', 1)
        return parent_boot == child_boot and int(parent_ticks) <= int(child_ticks)
    except (ValueError, TypeError):
        return False


def _identity(value):
    if (not isinstance(value, dict) or set(value) != {'pid', 'creation_time'} or
            type(value['pid']) is not int or value['pid'] <= 0 or
            not isinstance(value['creation_time'], str) or not value['creation_time'] or
            len(value['creation_time']) > 256):
        raise ValueError('Invalid receipt process identity')
    return value

# Pinned termination (backend/gui_test/execution/force_stop.py).
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


def stop_console_message(message, stream):
    """Windows console uses Unicode. Pipes shared by CMD/PowerShell use ASCII JSON."""
    if stream.isatty():
        return message
    return json.dumps({'status':message.split(':', 1)[0] if message.startswith('FORCE_STOP_') else 'CONNECTOR_ERROR',
                       'message':'Check process IDs, locks and verification details in the connector profile.',
                       'detail':message}, ensure_ascii=True)


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


def _discovery_parents():
    # Windows can reject a Toolhelp snapshot while the process table changes.
    for delay in (0.05, 0.1, None):
        try:
            return _process_parents()
        except OSError as exc:
            if not WINDOWS or delay is None or getattr(exc, 'winerror', None) not in (5, 24, 299):
                raise
            time.sleep(delay)


def _inspect_denied_child(pid, parent):
    # The dead parent's pinned handle protects its PID throughout this retry.
    for delay in (0.05, 0.1):
        time.sleep(delay)
        try:
            child = process_identity(pid)
        except PermissionError:
            continue
        if child is None:
            raise RuntimeError(f'FORCE_STOP_PENDING: PID {pid}가 자식 조회 중 사라져 하위 프로세스를 확인할 수 없습니다.')
        return child
    try:
        _, births = _windows_recovery_times()
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError):
        births = {}
    born = births.get(pid)
    # CIM can exclude an older orphan. Only a pinned native process may be killed.
    if born and born + 10 < int(parent.identity['creation_time']):
        return None
    raise _permission_error(pid, '자식 프로세스 조회')


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
                if _discovery_parents().get(identity['pid']) != expected_parent.identity['pid']:
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

        exited = set()

        def discover():
            count = len(pinned)
            for pid, parent_pid in _discovery_parents().items():
                parent = pinned.get(parent_pid)
                if parent is None or pid in pinned:
                    continue
                if not WINDOWS and not parent.alive():
                    continue
                retry = False
                try:
                    child = process_identity(pid)
                except PermissionError as exc:
                    if not WINDOWS:
                        raise
                    if parent_pid not in exited:
                        raise _permission_error(pid, '자식 프로세스 조회') from exc
                    retry = True
                    child = _inspect_denied_child(pid, parent)
                if child and _created_before(parent.identity, child):
                    capture(child, parent)
                    if retry and pid not in pinned:
                        raise RuntimeError(f'FORCE_STOP_PENDING: PID {pid}의 자식 세대를 재확인할 수 없습니다.')
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
                exited.add(handle.identity['pid'])
                # All parent handles remain pinned until the entire traversal ends.
                try:
                    while discover():
                        pass
                    checkpoint([value.identity for value in pinned.values()])
                    phase(None)
                except (OSError, ValueError, RuntimeError) as exc:
                    detail = str(exc)
                    if not detail.startswith('FORCE_STOP_PENDING:'):
                        code = getattr(exc, 'winerror', None) or type(exc).__name__
                        detail = f"FORCE_STOP_PENDING: 부모 PID {handle.identity['pid']} 종료 후 자식 목록을 확인하지 못했습니다 ({code})."
                    raise DiscoveryIncomplete(detail) from exc
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


class StopResidue(RuntimeError):
    def __init__(self, processes=(), locks=()):
        unique = {}
        for p in processes:
            unique.setdefault((p['pid'], p.get('creation_time')), p)
        self.processes = list(unique.values())
        self.locks = list(dict.fromkeys(locks))
        items = [f"{p['role']} PID {p['pid']}" for p in self.processes] + self.locks
        super().__init__('FORCE_STOP_PENDING: 현재 프로필에 남은 대상: ' + ', '.join(items)
                         + '. 소유 프로세스 또는 잠금이 해제된 뒤 시작할 수 있습니다.')


def _unique_generations(values):
    return list({(v['pid'], v['creation_time']): v for v in values}.values())


def _verify_previous_windows_tree(roots, previous_write_ns):
    """Only a parent PID from this profile links an orphan to the old stop."""
    if not roots:
        return
    parents = _discovery_parents()
    if not parents:
        raise RuntimeError('FORCE_STOP_PENDING: Windows 프로세스 목록을 읽지 못했습니다.')
    oldest = {}
    for owner in roots:
        pid = owner['pid']
        born = int(owner['creation_time'])
        oldest[pid] = min(oldest.get(pid, born), born)
    supplemental = None
    def windows_times():
        nonlocal supplemental
        if supplemental is None:
            try:
                supplemental = _windows_recovery_times()
            except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError):
                supplemental = (0, {})
        return supplemental

    remaining = []
    for pid, parent in parents.items():
        if parent not in oldest:
            continue
        try:
            child = process_identity(pid)
            if child is None or int(child['creation_time']) < oldest[parent]:
                continue
            current = process_identity(parent) if parent in parents else None
            if current and int(current['creation_time']) < int(child['creation_time']) and current not in roots:
                continue  # Different live parent generation, older than this child.
        except OSError:
            child = None
            born = windows_times()[1].get(pid)
            if born and born + 10 < oldest[parent]:
                continue
        remaining.append({'role':'possible_child', 'pid':pid, 'parent_pid':parent,
                          'creation_time':child['creation_time'] if child else None})
    if remaining:
        boot, _ = windows_times()
        epoch = 116444736000000000
        if previous_write_ns and previous_write_ns // 100 + epoch + 10 < boot <= time.time_ns() // 100 + epoch:
            return
        raise StopResidue(remaining)


def stop_recorded(path, owners, *, verify_stopped=None, inspect_only=False):
    """Durable pending evidence allows retry after a partial emergency stop."""
    path = Path(path)
    previous = json.loads(path.read_bytes()) if path.exists() else None
    if previous is not None and (not isinstance(previous, dict) or previous.get('version') != 1 or
                                 not isinstance(previous.get('targets'), list)):
        raise ValueError('Invalid force-stop retry record')
    if previous and previous.get('state') == 'FORCE_STOPPED':
        previous = None
    previous_write_ns = path.stat().st_mtime_ns if previous else None
    if previous:
        owners = _unique_generations([_identity(v) for v in [*owners, *previous['targets'],
                                                             *previous.get('tree_roots', [])]])
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
    if WINDOWS or inspect_only:
        history = previous or {}
        past = [*history.get('tree_roots', []), *record['completed']]
        if history.get('post_exit_scan_pending'):
            past.append(history['post_exit_scan_pending'])
        record['tree_roots'] = _unique_generations([_identity(v) for v in [*owners, *past]])
        record['tree_candidates'] = (previous or {}).get('tree_candidates', [])
        if record['tree_unverified'] and previous:
            record['tree_gap_recorded_ns'] = history.get('tree_gap_recorded_ns') or previous_write_ns
    if not inspect_only:
        atomic_record(path, record)
    def checkpoint(targets):
        if WINDOWS:
            record['tree_roots'] = _unique_generations([*record['tree_roots'], *targets])
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
        stopped = force_owned(owners, checkpoint, phase) if owners and not inspect_only else []
        remaining, locks = [], []
        if verify_stopped:
            try:
                verify_stopped(stopped)
            except StopResidue as exc:
                remaining.extend(exc.processes)
                locks.extend(exc.locks)
        if inspect_only:
            remaining.extend(dict(v, role='recorded') for v in record['tree_roots'] if recorded_process_alive(v))
        if record['tree_unverified']:
            if not WINDOWS or verify_stopped is None:
                raise RuntimeError('FORCE_STOP_PENDING: 이전 종료의 하위 프로세스 확인이 필요합니다.')
            try:
                _verify_previous_windows_tree([*record['tree_roots'], *record['tree_candidates']], record['tree_gap_recorded_ns'])
            except StopResidue as exc:
                remaining.extend(exc.processes)
        if remaining or locks:
            raise StopResidue(remaining, locks)
        if record['tree_unverified']:
            record['previous_tree_unverified'] = True
            record['tree_unverified'] = False
        record.update(state='FORCE_STOPPED', targets=stopped, remaining_processes=[], remaining_locks=[])
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
        if inspect_only and previous:
            # A read-only startup check must retain interrupted kill checkpoints.
            record = dict(previous, tree_roots=record['tree_roots'], tree_candidates=record['tree_candidates'],
                          tree_unverified=record['tree_unverified'])
        if WINDOWS and isinstance(exc, StopResidue):
            # Possible children are evidence for future inspections only. They
            # never enter the list of process generations authorized to be killed.
            candidates = [{'pid':p['pid'], 'creation_time':p['creation_time']} for p in exc.processes
                          if p['role'] == 'possible_child' and p.get('creation_time')]
            record['tree_candidates'] = _unique_generations([*record.get('tree_candidates', []), *candidates])
        if not detail:
            detail = f'FORCE_STOP_PENDING: 로컬 종료 확인을 완료하지 못했습니다 ({type(exc).__name__}). 프로필 기록과 프로세스 조회 상태를 확인하세요.'
        record.update(state='FORCE_STOP_PENDING', error=type(exc).__name__, detail=detail,
                      remaining_processes=getattr(exc, 'processes', None), remaining_locks=getattr(exc, 'locks', None))
        atomic_record(path, record)
        if str(exc) == detail:
            raise
        raise RuntimeError(detail) from exc


# Read-only post-stop discovery for a recovery file outside the source checkout.
def _profile_option(home):
    path = os.path.normcase(os.path.abspath(home))
    digest = hashlib.sha256(path.encode('utf-8')).hexdigest()
    # A negative SendEnv pattern removes this private name; no server config is required.
    return 'SendEnv=-BSP_CONNECTOR_PROFILE_' + digest


_PYTHON_IMAGE = re.compile(r'pythonw?(?:[23](?:\.\d+)?)?\.exe')


def _option_path(args, flag):
    values = []
    for index, arg in enumerate(args):
        if arg == flag and index + 1 < len(args):
            values.append(args[index + 1])
        elif arg.startswith(flag + '='):
            values.append(arg[len(flag) + 1:])
    if len(values) == 1 and ntpath.isabs(values[0]):
        return ntpath.normcase(ntpath.normpath(values[0]))
    return None


def _profile_python(executable, profile):
    if not executable:
        return False
    try:
        relative = ntpath.relpath(ntpath.normcase(executable), profile).split(ntpath.sep)
    except ValueError:  # Different drive.
        return False
    if relative[-2:] not in (['scripts', 'python.exe'], ['scripts', 'pythonw.exe']):
        return False
    return (relative[:-2] == ['venv'] or
            len(relative) == 4 and relative[0] == 'connector-environments'
            and bool(re.fullmatch('env-[0-9a-f]{32}', relative[1])))


def process_role(image, argv, home, executable=None):
    args = argv[1:]
    if image == 'ssh.exe':
        if (args[:2] == ['-o', _profile_option(home)] and ('-N' in args or '-NT' in args)
                and ('-R' in args or '-L' in args)):
            return 'ssh'
        return None
    if not _PYTHON_IMAGE.fullmatch(image):
        return None
    # Consume only interpreter switches used by our launchers. An argument to
    # a different Python script (or -c) cannot impersonate a connector module.
    while args[:1] == ['-B'] or args[:2] == ['-X', 'utf8']:
        args = args[1:] if args[0] == '-B' else args[2:]
    profile = ntpath.normcase(ntpath.normpath(str(home)))
    if args[:2] == ['-m', 'backend.gui_test.execution.host']:
        if (_option_path(args[2:], '--runtime') == ntpath.join(profile, 'runtime')
                and _option_path(args[2:], '--config') == ntpath.join(profile, 'windows-runner.json')):
            return 'host'
        return None
    roles = {'backend.gui_test.connector.supervisor': 'manager', 'backend.gui_test.connector': 'ui'}
    if args[:1] == ['-m'] and len(args) >= 2 and args[1] in roles:
        if _option_path(args[2:], '--home') == profile and '--preview' not in args:
            return roles.get(args[1])
        return None
    if '--force-stop' in args:
        return None
    if _profile_python(executable, profile):
        if any(a == '--home' or a.startswith('--home=') for a in args) and _option_path(args, '--home') != profile:
            return None
        return 'profile_python'
    if not args:
        return None
    script = ntpath.normcase(ntpath.normpath(args[0]))
    if args[:2] == ['-m', 'scripts.setup_runtime'] and executable:
        # The editable Windows CLI runs this module from its bundled interpreter.
        python = Path(executable)
        bundle = python.parent.parent
        if (python != bundle / 'runtime/python.exe' or not (bundle / 'bundle.json').is_file()
                or not (bundle / 'src/scripts/setup_runtime.py').is_file()):
            return None
    elif not (ntpath.isabs(script) and Path(script).parent.name == 'scripts'
              and Path(script).name in ('board_connector.py', 'setup_runtime.py')):
        return None
    if any(arg in args for arg in ('--force-stop', '--diagnose', '--install-only', '--import-only', 'doctor', 'ports')):
        return None
    selected = _option_path(args[1:], '--home')
    if selected is None and not any(a == '--home' or a.startswith('--home=') for a in args):
        selected = ntpath.normcase(str(Path.home() / '.bsp-dashboard' / 'windows'))
    return 'launcher' if selected == profile else None


def _split_command(command):
    count = ctypes.c_int()
    split = ctypes.windll.shell32.CommandLineToArgvW
    split.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    split.restype = ctypes.POINTER(ctypes.c_wchar_p)
    args = split(command, ctypes.byref(count))
    if not args:
        raise ctypes.WinError()
    try:
        return args[:count.value]
    finally:
        release = ctypes.windll.kernel32.LocalFree
        release.argtypes = [ctypes.c_void_p]
        release.restype = ctypes.c_void_p
        release(args)


def _command_rows():
    # No user data is interpolated into PowerShell. Command lines stay in memory.
    query = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rows = @(Get-CimInstance Win32_Process -Filter "Name='ssh.exe' OR Name LIKE 'python%.exe'" |
    Where-Object { $_.CommandLine -and (Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid -ErrorAction SilentlyContinue).Sid -eq $sid } |
    Select-Object ProcessId,Name,ExecutablePath,CommandLine)
ConvertTo-Json -InputObject $rows -Compress
"""
    binary = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    proc = subprocess.run([str(binary), '-NoProfile', '-NonInteractive', '-Command', query],
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          timeout=15, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    rows = json.loads(proc.stdout.decode('utf-8-sig'))
    if not isinstance(rows, list):
        raise ValueError('Invalid Windows process list')
    return rows


def discover_windows_processes(home):
    if sys.platform != 'win32':
        return {}
    before = {}
    snapshot = _windows_process_snapshot()
    if not snapshot:
        raise RuntimeError('FORCE_STOP_PENDING: Windows 프로세스 목록을 읽지 못했습니다.')
    callers = set()
    pid = os.getpid()
    while pid and pid not in callers:
        callers.add(pid)
        pid = snapshot.get(pid, (0, ''))[0]
    for pid, (_, image) in snapshot.items():
        if pid not in callers and (image.casefold() == 'ssh.exe' or _PYTHON_IMAGE.fullmatch(image.casefold())):
            try:
                before[pid] = process_identity(pid)
            except OSError as exc:
                if exc.errno != 5 and getattr(exc, 'winerror', None) != 5:
                    raise
                # If CIM later identifies this as ours, the scan must stay pending.
                before[pid] = 'inaccessible'
    if not any(before.values()):
        return {}
    roles = {}
    try:
        rows = _command_rows()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError('FORCE_STOP_PENDING: Windows CIM에서 후보 프로세스의 소유권을 조회하지 못했습니다.') from exc
    for row in rows:
        pid = row['ProcessId']
        if not before.get(pid):
            continue
        role = process_role(row['Name'].casefold(), _split_command(row['CommandLine']), home, row.get('ExecutablePath'))
        if role and before[pid] == 'inaccessible':
            raise RuntimeError(f'FORCE_STOP_PENDING: PID {pid}의 커넥터 프로세스 조회 권한이 없습니다. '
                               '커넥터를 실행한 Windows 계정과 권한 수준에서 확인하세요.')
        if role and process_identity(pid) == before[pid]:
            roles.setdefault(role, []).append(before[pid])
    return roles


def _verify_legacy_ssh(active, stopped):
    """An old launcher starts OpenSSH directly, but may omit its process generation."""
    if active.get('phase') not in {'ssh_starting', 'ssh_running'} or active.get('transport'):
        return
    owner = active.get('owner')
    if owner is None or owner in stopped:
        # Without a recorded parent, only profile-specific discovery can identify SSH.
        return
    _identity(owner)
    try:
        processes = _windows_process_snapshot()
        for pid, (parent, image) in processes.items():
            if parent != owner['pid']:
                continue
            if image and image.casefold() != 'ssh.exe':
                continue
            child = process_identity(pid)
            if child is None:
                continue
            if int(child['creation_time']) < int(owner['creation_time']):
                continue
            current_parent = process_identity(owner['pid'])
            if current_parent and current_parent != owner and int(child['creation_time']) > int(current_parent['creation_time']):
                # Child belongs to a later generation that reused the parent's PID.
                continue
            raise RuntimeError(f'FORCE_STOP_PENDING: 구형 SSH 후보(PID {pid})의 소유권을 확인할 수 없습니다. '
                               '식별한 프로세스는 정리했습니다. 이 SSH가 종료되면 같은 명령으로 확인하세요.')
    except OSError as exc:
        raise RuntimeError('FORCE_STOP_PENDING: Windows SSH 프로세스 조회를 완료하지 못했습니다. '
                           '같은 계정에서 다시 실행하세요.') from exc


def force_stop(home):
    home = _plain_path(home)
    runtime = home / 'runtime'
    with LaunchLock(runtime / 'connector-start.lock'):
        def read(name):
            path = _plain_path(runtime / name)
            value = json.loads(path.read_bytes()) if path.exists() else {}
            if not isinstance(value, dict):
                raise ValueError('Invalid connector process receipt')
            return value
        manager = read('connector-manager.json')
        active = read('active-endpoints.json')
        host_active = read('host-active.json')
        ssh_tunnel = read('ssh-tunnel.json')
        targets = [value for value in [
            manager.get('owner'),
            active.get('owner'), active.get('runner'), active.get('transport'),
            host_active.get('owner'), host_active.get('runner'),
            ssh_tunnel.get('transport'), ssh_tunnel.get('dashboard_transport'),
        ] if value is not None]
        if _lock_held(runtime / 'connector-manager.lock') and not manager.get('owner'):
            raise RuntimeError('FORCE_STOP_BLOCKED: Manager 소유권 기록을 확인할 수 없습니다.')
        if _lock_held(runtime / 'runner.lock') and not (active.get('runner') or host_active.get('runner')):
            raise RuntimeError('FORCE_STOP_BLOCKED: Host 소유권 기록을 확인할 수 없습니다.')
        if _lock_held(runtime / 'ssh-tunnel.lock') and not (ssh_tunnel.get('transport') or ssh_tunnel.get('dashboard_transport') or active.get('transport')):
            mgr_owner = manager.get('owner')
            idle_manager_tunnel = bool(
                ssh_tunnel
                and ssh_tunnel.get('ssh_state') in {'NOT_CONFIGURED', 'CONNECTING', 'RECONNECTING', 'AUTH_OR_CONFIG_ERROR', 'DISCONNECTED', 'STOPPED'}
                and isinstance(mgr_owner, dict)
                and mgr_owner.get('pid')
                and process_identity(mgr_owner['pid']) == mgr_owner
            )
            if not idle_manager_tunnel:
                raise RuntimeError('FORCE_STOP_BLOCKED: SSH 터널 소유권 기록을 확인할 수 없습니다.')
        def verify(stopped):
            found = discover_windows_processes(home)
            remaining = [dict(p, role=role) for role, group in found.items() for p in group]
            locks = [name for name in ('connector-manager.lock', 'runner.lock', 'ssh-tunnel.lock')
                     if _lock_held(runtime / name)]
            if remaining or locks:
                raise StopResidue(remaining, locks)
            _verify_legacy_ssh(active, stopped)

        path = runtime / 'force-stop.json'
        try:
            return stop_recorded(path, targets, verify_stopped=verify)
        except (DiscoveryIncomplete, StopResidue):
            return stop_recorded(path, targets, verify_stopped=verify, inspect_only=True)

def main():
    parser = argparse.ArgumentParser(description="현재 설치본의 Windows 보드 커넥터를 강제 종료합니다.", allow_abbrev=False)
    parser.add_argument('--home', type=Path, default=Path.home() / '.bsp-dashboard' / 'windows',
                        help='사용자 지정 Profile home')
    args = parser.parse_args()
    if not WINDOWS:
        parser.exit(2, 'Windows PC에서 실행하세요.\n')
    home = args.home.expanduser().absolute()
    print('Profile home:', str(home) if sys.stdout.isatty() else json.dumps(str(home)), flush=True)
    if not (home / 'runtime').is_dir():
        parser.exit(1, '커넥터 실행 기록 폴더가 없습니다. 사용자 지정 설치라면 --home을 지정하세요.\n')
    try:
        result = force_stop(home)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, stop_console_message(str(error), sys.stderr) + '\n')
    print(result['state'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
