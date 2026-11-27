"""Discover a Windows connector's process generations when runtime receipts are missing."""
import ctypes
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys

from ..execution import launch


def _profile_option(home):
    path = os.path.normcase(os.path.abspath(home))
    digest = hashlib.sha256(path.encode('utf-8')).hexdigest()
    # A negative SendEnv pattern removes this private name; no server config is required.
    return 'SendEnv=-BSP_CONNECTOR_PROFILE_' + digest


def tag_transport(argv, home):
    return [argv[0], '-o', _profile_option(home), *argv[1:]]


_PYTHON_IMAGE = re.compile(r'pythonw?(?:[23](?:\.\d+)?)?\.exe')
_ROOT = Path(__file__).resolve().parents[3]


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
    if args[:2] == ['-X', 'utf8']:
        args = args[2:]
    if args[:1] == ['-B']:
        args = args[1:]
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
    scripts = _ROOT / 'scripts'
    if script not in {ntpath.normcase(str(scripts / name)) for name in ('board_connector.py', 'setup_runtime.py')}:
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
    snapshot = launch._windows_process_snapshot()
    callers = set()
    pid = os.getpid()
    while pid and pid not in callers:
        callers.add(pid)
        pid = snapshot.get(pid, (0, ''))[0]
    for pid, (_, image) in snapshot.items():
        if pid not in callers and (image.casefold() == 'ssh.exe' or _PYTHON_IMAGE.fullmatch(image.casefold())):
            try:
                before[pid] = launch.process_identity(pid)
            except OSError as exc:
                if exc.errno != 5 and getattr(exc, 'winerror', None) != 5:
                    raise
                # If CIM later identifies this as ours, the scan must stay pending.
                before[pid] = 'inaccessible'
    roles = {}
    try:
        rows = _command_rows()
    except subprocess.SubprocessError as exc:
        raise RuntimeError('Windows CIM 프로세스 조회 실패') from exc
    for row in rows:
        pid = row['ProcessId']
        if not before.get(pid):
            continue
        role = process_role(row['Name'].casefold(), _split_command(row['CommandLine']), home, row.get('ExecutablePath'))
        if role and before[pid] == 'inaccessible':
            raise PermissionError('Cannot inspect connector process generation')
        if role and launch.process_identity(pid) == before[pid]:
            roles.setdefault(role, []).append(before[pid])
    return roles
