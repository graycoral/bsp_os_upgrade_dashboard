"""Process identity verification. Ambiguity is UNKNOWN, never permission to relaunch."""
import ctypes
import hashlib
import json
import os
import platform
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessVerification:
    state: str
    evidence: dict


def host_identity():
    return hashlib.sha256(platform.node().encode()).hexdigest()


def boot_identity():
    if os.name == 'posix':
        return Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()
    if os.name == 'nt':
        class TimeOfDay(ctypes.Structure):
            _fields_ = [('boot_time', ctypes.c_longlong), ('current_time', ctypes.c_longlong),
                        ('timezone_bias', ctypes.c_longlong), ('timezone_id', ctypes.c_ulong),
                        ('reserved', ctypes.c_ulong), ('boot_bias', ctypes.c_ulonglong),
                        ('sleep_bias', ctypes.c_ulonglong)]
        item = TimeOfDay()
        status = ctypes.windll.ntdll.NtQuerySystemInformation(3, ctypes.byref(item), ctypes.sizeof(item), None)
        if status != 0 or item.boot_time <= 0:
            raise OSError('Windows boot identity is unavailable.')
        return str(item.boot_time)
    raise OSError('Boot identity is unavailable.')


def _linux(pid):
    text = Path(f'/proc/{pid}/stat').read_text(encoding='ascii')
    fields = text[text.rfind(')') + 2:].split()
    return {'pid': int(pid), 'state': fields[0], 'group_id': int(fields[2]), 'session_id': int(fields[3]), 'start_id': fields[19]}


def _windows(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        if ctypes.get_last_error() == 87:
            return None
        raise OSError('Cannot inspect process.')
    try:
        creation, exit_time, kernel_time, user_time = (ctypes.c_ulonglong() for _ in range(4))
        if not kernel.GetProcessTimes(ctypes.c_void_p(handle), ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel_time), ctypes.byref(user_time)):
            raise OSError('Cannot inspect process creation time.')
        code = ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)):
            raise OSError('Cannot inspect process state.')
        return {'pid': pid, 'start_id': str(creation.value), 'state': 'RUNNING' if code.value == 259 else 'EXITED'}
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def launch_receipt(pid, context):
    identity = _linux(pid) if os.name == 'posix' else _windows(pid)
    if not identity:
        raise OSError('Process exited before identity capture.')
    return {'receipt_version': 1, 'phase': 'LAUNCHED', 'host_id': host_identity(), 'boot_id': boot_identity(),
            'platform': os.name, 'launch_id': context['launch_id'], 'intent_nonce': context.get('intent_nonce'),
            'pid': pid, 'start_id': identity['start_id'], 'group_id': identity.get('group_id'),
            'session_id': identity.get('session_id'), 'launched_at': time.time(), 'members': [identity]}


def verify_receipt(receipt):
    try:
        if not isinstance(receipt, dict) or receipt.get('receipt_version') != 1:
            return ProcessVerification('UNKNOWN', {'reason': 'Missing process identity receipt.'})
        if receipt.get('host_id') != host_identity():
            return ProcessVerification('UNKNOWN', {'reason': 'Receipt belongs to another host.'})
        if receipt.get('boot_id') != boot_identity():
            return ProcessVerification('TERMINATED', {'reason': 'Host has rebooted since launch.'})
        pid, start = receipt['pid'], receipt['start_id']
        if receipt.get('platform') == 'posix' and os.name == 'posix':
            group, session = receipt.get('group_id'), receipt.get('session_id')
            if not isinstance(group, int) or not isinstance(session, int) or group != pid or session != pid:
                return ProcessVerification('UNKNOWN', {'reason': 'Missing exclusive group/session identity.'})
            members, ambiguous = [], False
            for item in Path('/proc').iterdir():
                if not item.name.isdigit():
                    continue
                try:
                    identity = _linux(int(item.name))
                except FileNotFoundError:
                    continue
                except (PermissionError, OSError, ValueError, IndexError):
                    ambiguous = True
                    continue
                if identity['group_id'] == group or identity['session_id'] == session:
                    if int(identity['start_id']) < int(start) or (identity['pid'] == pid and identity['start_id'] != start):
                        return ProcessVerification('UNKNOWN', {'reason': 'Group identity was reused.'})
                    if identity['state'] != 'Z':
                        members.append(identity)
            if members:
                return ProcessVerification('ALIVE', {'members': members, 'host_id': receipt['host_id'], 'boot_id': receipt['boot_id']})
            return ProcessVerification('UNKNOWN' if ambiguous else 'TERMINATED', {'reason': 'Process group scan incomplete.' if ambiguous else 'No live process in recorded group/session.'})
        if receipt.get('platform') == 'nt' and os.name == 'nt':
            identity = _windows(pid)
            if identity and identity['start_id'] == start and identity['state'] == 'RUNNING':
                return ProcessVerification('ALIVE', {'process': identity})
            # A leader exit does not establish that its descendants stopped. Windows
            # launch does not yet own a job object with durable descendant identities.
            return ProcessVerification('UNKNOWN', {'reason': 'Leader ended; descendant termination cannot be proven.'})
        return ProcessVerification('UNKNOWN', {'reason': 'Unsupported process inspection platform.'})
    except (OSError, KeyError, TypeError, ValueError, IndexError):
        return ProcessVerification('UNKNOWN', {'reason': 'Process identity is unreadable or incomplete.'})


def durable_receipt(path, value):
    """Atomic replace plus file/directory fsync; caller chooses a scoped local path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name == 'posix':
        handle = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
    return hashlib.sha256(raw).hexdigest()
