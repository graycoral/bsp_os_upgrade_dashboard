"""Standard-library launch locks, owned sockets and ephemeral endpoint receipts.

Receipts discover a running launcher; they are neither configuration nor evidence
that a hardware operation completed. No credentials are stored here.
"""
import ctypes
import json
import os
from pathlib import Path
import re
import socket
import tempfile
import warnings


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


def _process_parents():
    """Read OS parent PIDs; identities are checked separately around traversal."""
    if os.name == 'nt':
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
            parents = {}
            more = kernel.Process32FirstW(handle, ctypes.byref(entry))
            while more:
                parents[entry.th32ProcessID] = entry.th32ParentProcessID
                more = kernel.Process32NextW(handle, ctypes.byref(entry))
            if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                raise ctypes.WinError(ctypes.get_last_error())
            return parents
        finally:
            kernel.CloseHandle(handle)
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


def _owned_descendant(child, ancestor, *, inspect_process=None):
    """Accept only a live, generation-stable OS chain to the expected ancestor.

    Windows venv python.exe is a redirector: Popen owns that root process while
    the Python code runs in its child. A live unrelated PID is never sufficient.
    """
    inspect = inspect_process or process_identity
    if inspect(child['pid']) != child or inspect(ancestor['pid']) != ancestor:
        return False
    if child == ancestor:
        return True
    parents = _process_parents()
    current = child
    visited = {child['pid']}
    chain = [child]
    for _ in range(32):
        parent_pid = parents.get(current['pid'])
        if not parent_pid or parent_pid in visited:
            return False
        parent = inspect(parent_pid)
        if parent is None or not _created_before(parent, current):
            return False
        chain.append(parent)
        if parent == ancestor:
            # Recheck every generation after traversal, not merely numeric PIDs
            # from a snapshot that may have raced an exit and PID reuse.
            return all(inspect(item['pid']) == item for item in chain)
        visited.add(parent_pid)
        current = parent
    return False


def _port(value):
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError('Invalid receipt port')
    return value


def bind_loopback(port, *, allow_fallback=False):
    _port(port)
    def bind(selected):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if os.name == 'nt':
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(('127.0.0.1', selected))
            listener.listen(socket.SOMAXCONN)
            return listener
        except BaseException:
            listener.close()
            raise
    try:
        return bind(port)
    except OSError:
        if not allow_fallback:
            raise
        return bind(0)


def _identity(value):
    if (not isinstance(value, dict) or set(value) != {'pid', 'creation_time'} or
            type(value['pid']) is not int or value['pid'] <= 0 or
            not isinstance(value['creation_time'], str) or not value['creation_time'] or
            len(value['creation_time']) > 256):
        raise ValueError('Invalid receipt process identity')
    return value


def _nonce(value):
    if not isinstance(value, str) or not re.fullmatch('[a-f0-9]{32}', value):
        raise ValueError('Invalid launch nonce')
    return value


_STARTUP = {'version', 'launch_id', 'owner', 'runner', 'runner_id', 'runner_port'}
_ACTIVE = _STARTUP | {'dashboard_port', 'remote_runner_port', 'remote_dashboard_port',
                      'ssh_port', 'phase', 'runner_url', 'dashboard_url'}
_MISSING = object()


def _startup(value, *, active=False):
    if (not isinstance(value, dict) or set(value) != (_ACTIVE if active else _STARTUP) or
            type(value['version']) is not int or value['version'] != 1):
        raise ValueError('Invalid launch receipt schema')
    _nonce(value['launch_id'])
    _identity(value['owner'])
    _identity(value['runner'])
    _nonce(value['runner_id'])
    _port(value['runner_port'])
    if active:
        for name in ('dashboard_port', 'remote_runner_port', 'remote_dashboard_port', 'ssh_port'):
            _port(value[name])
        if (value['dashboard_port'] == value['runner_port'] or
                value['remote_runner_port'] == value['remote_dashboard_port'] or
                value['phase'] not in {'runner_ready', 'ssh_starting', 'ssh_running'} or
                value['runner_url'] != f"http://127.0.0.1:{value['runner_port']}" or
                value['dashboard_url'] != f"http://127.0.0.1:{value['dashboard_port']}"):
            raise ValueError('Invalid active endpoint values')
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate launch receipt field')
        result[key] = value
    return result


def _read(path):
    path = _plain_path(path)
    try:
        with path.open('rb') as stream:
            data = stream.read(16385)
    except FileNotFoundError:
        return _MISSING
    if len(data) > 16384:
        raise ValueError('Launch receipt too large')
    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=_unique)


def read_startup(path, *, launch_id, owner, runner):
    _nonce(launch_id)
    _identity(owner)
    _identity(runner)
    value = _read(path)
    if value is _MISSING:
        return None
    _startup(value)
    if (value['launch_id'] != launch_id or value['owner'] != owner or
            (value['runner'] != runner and not _owned_descendant(value['runner'], runner))):
        raise ValueError('Startup receipt belongs to another launch/process')
    return value


def read_active(runtime, *, inspect_process=None):
    runtime = _plain_path(runtime)
    inspect = inspect_process or process_identity
    # An unlocked file is stale, even when its JSON is damaged. Never delete here.
    value = _read(runtime / 'active-endpoints.json') if _lock_held(runtime / 'setup-launch.lock') else _MISSING
    if value is _MISSING:
        if (runtime / 'active-endpoints.json').exists():
            warnings.warn('Stale active endpoint receipt; using desired ports', RuntimeWarning)
        return None
    _startup(value, active=True)
    if inspect(value['owner']['pid']) != value['owner'] or inspect(value['runner']['pid']) != value['runner']:
        warnings.warn('Stale endpoint process identity; using desired ports', RuntimeWarning)
        return None
    if not _owned_descendant(value['runner'], value['owner'], inspect_process=inspect):
        raise ValueError('Active Runner is not owned by the launch process')
    if not _lock_held(runtime / 'runner.lock'):
        raise ValueError('Active Runner does not hold its host lock')
    startup = read_startup(runtime / f"launch-{value['launch_id']}.json",
                           launch_id=value['launch_id'], owner=value['owner'], runner=value['runner'])
    if startup is None or any(startup[key] != value[key] for key in _STARTUP):
        raise ValueError('Active receipt does not match current Runner startup')
    return value


def write_receipt(path, value):
    path = _plain_path(path)
    _startup(value, active='phase' in value)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        _plain_path(path)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def remove_owned_receipts(runtime, launch_id):
    _nonce(launch_id)
    runtime = _plain_path(runtime)
    for path in (runtime / 'active-endpoints.json', runtime / f'launch-{launch_id}.json'):
        value = _read(path)
        if isinstance(value, dict) and value.get('launch_id') == launch_id:
            path.unlink(missing_ok=True)
