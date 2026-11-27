#!/usr/bin/env python3
"""Stop this Windows board connector. Run with Python 3.11+; optional --home PATH.

Standalone copy of the connector's emergency stop implementation. Requires
only the Python standard library. It does not use the network or install
packages. It force-stops owned processes, including active tests or flashing.
"""
import argparse
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
            raise OSError(error, 'Cannot inspect launch process')
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
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


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
    if any(value['pid'] in ancestors and process_identity(value['pid']) == value for value in owners):
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


def _windows_recovery_times():
    """Supplement Toolhelp with read-only creation times for protected processes."""
    import subprocess
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
    import subprocess
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
        interrupted_tree = any(value not in completed and process_identity(value['pid']) != value
                               for value in previous['targets'])
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
        record.update(state='FORCE_STOP_PENDING', error=type(exc).__name__, detail=detail)
        atomic_record(path, record)
        if isinstance(exc, RuntimeError) and str(exc).startswith('FORCE_STOP_PENDING:'):
            raise
        raise RuntimeError('FORCE_STOP_PENDING: 로컬 종료 확인 실패. 같은 명령으로 재시도하세요. '+type(exc).__name__) from exc


def _verify_legacy_ssh(active, stopped):
    """An old launcher starts OpenSSH directly, but may omit its process generation."""
    if active.get('phase') not in {'ssh_starting', 'ssh_running'} or active.get('transport'):
        return
    owner = active.get('owner')
    if owner in stopped:
        # The pinned launcher already passed the post-exit scan of all its children.
        return
    if owner is not None:
        _identity(owner)
    try:
        processes = _windows_process_snapshot()
        current_parent = process_identity(owner['pid']) if owner else None
        for pid, (parent, image) in processes.items():
            if owner and parent != owner['pid']:
                continue
            if image and image.casefold() != 'ssh.exe':
                continue
            child = process_identity(pid)
            if child is None:
                continue
            if owner and int(child['creation_time']) < int(owner['creation_time']):
                continue
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
            value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
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
        if (manager or _lock_held(runtime / 'connector-manager.lock')) and not manager.get('owner'):
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
            _verify_legacy_ssh(active, stopped)
            if any(_lock_held(runtime / name) for name in ('connector-manager.lock', 'runner.lock', 'ssh-tunnel.lock')):
                raise RuntimeError('FORCE_STOP_PENDING: Manager/Host/SSH 잠금 종료를 확인할 수 없습니다.')

        return stop_recorded(runtime / 'force-stop.json', targets, verify_stopped=verify)

def main():
    parser = argparse.ArgumentParser(description="현재 설치본의 Windows 보드 커넥터를 강제 종료합니다.", allow_abbrev=False)
    parser.add_argument('--home', type=Path, default=Path.home() / '.bsp-dashboard' / 'windows',
                        help='사용자 지정 Profile home')
    args = parser.parse_args()
    if not WINDOWS:
        parser.exit(2, 'Windows PC에서 실행하세요.\n')
    home = args.home.expanduser().absolute()
    print('Profile home:', home, flush=True)
    if not (home / 'runtime').is_dir():
        parser.exit(1, '커넥터 실행 기록 폴더가 없습니다. 사용자 지정 설치라면 --home을 지정하세요.\n')
    try:
        result = force_stop(home)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f'{error}\n')
    print(result['state'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
