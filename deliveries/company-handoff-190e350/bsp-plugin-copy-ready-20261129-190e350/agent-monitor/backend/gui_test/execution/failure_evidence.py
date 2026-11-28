"""Bounded evidence from the failed TC attempt and its selected boards."""
from __future__ import annotations

import re
import subprocess

from ..connector.logs import redact

TC_LOG_BYTES = 48 * 1024
KERNEL_BYTES = 16 * 1024
# Preserve dmesg's exit status (in particular EPERM) and cap USB traffic even
# when one kernel line is very long. The first line gives the unclipped size.
KERNEL_COMMAND = (
    'output=$(dmesg) || exit $?; '
    'recent=$(printf "%s\\n" "$output" | tail -n 50) || exit $?; '
    'printf "%s\\n" "$recent" | wc -c && printf "%s\\n" "$recent" | tail -c 65537'
)


def log_tails(directory):
    streams = {}
    for name in ('stdout', 'stderr'):
        path = directory / (name + '.log')
        try:
            with path.open('rb') as source:
                size = source.seek(0, 2)
                source.seek(max(0, size - TC_LOG_BYTES))
                data = source.read(TC_LOG_BYTES)
            streams[name] = (size, data, 'READY')
        except FileNotFoundError:
            streams[name] = (0, b'', 'EMPTY')
        except OSError:
            streams[name] = (0, b'', 'UNAVAILABLE')
    result = {}
    for name, (size, data, status) in streams.items():
        other = 'stderr' if name == 'stdout' else 'stdout'
        limit = TC_LOG_BYTES - min(len(streams[other][1]), TC_LOG_BYTES // 2)
        # TC log files are already redacted, including complete-line handling.
        result[name] = {'text': data[-limit:].decode('utf-8', errors='ignore'),
                        'total_bytes': size, 'truncated': size > limit, 'status': status}
    return result


def kernel_tail(adb, serial):
    try:
        result = subprocess.run([adb, '-s', serial, 'shell', KERNEL_COMMAND],
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=3)
    except subprocess.TimeoutExpired:
        return {'status': 'TIMEOUT'}
    except OSError:
        return {'status': 'ADB_UNAVAILABLE'}
    if result.returncode:
        diagnostic = result.stderr.lower()
        if b'permission denied' in diagnostic or b'operation not permitted' in diagnostic:
            return {'status': 'PERMISSION_DENIED'}
        if re.search(rb"(?:device '[^'\r\n]+' not found|no devices/emulators found)", diagnostic):
            return {'status': 'ADB_DEVICE_NOT_FOUND'}
        if re.search(rb'(?:^|: )device (offline|unauthorized)\b', diagnostic):
            return {'status': 'ADB_UNAVAILABLE'}
        return {'status': 'ADB_ERROR', 'exit_code': result.returncode}
    header, newline, data = result.stdout.partition(b'\n')
    if not newline or not re.fullmatch(rb'[0-9]{1,12}', header.strip()):
        return {'status': 'INVALID_RESPONSE'}
    size = int(header)
    if len(data) != min(size, 65537):
        return {'status': 'INVALID_RESPONSE'}
    if size > len(data):
        # A cut through a credential-bearing line would hide its key from redact().
        data = data.partition(b'\n')[2]
    safe = redact(data.decode('utf-8', errors='replace'))
    raw = '\n'.join(safe.splitlines()[-50:]).encode('utf-8')
    return {'status': 'READY', 'text': raw[-KERNEL_BYTES:].decode('utf-8', errors='ignore'),
            'total_bytes': size, 'truncated': size > 65537 or len(raw) > KERNEL_BYTES}
