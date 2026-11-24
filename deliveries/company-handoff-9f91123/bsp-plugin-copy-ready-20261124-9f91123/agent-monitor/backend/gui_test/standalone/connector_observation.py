"""Versioned JSON lines and single-owner connection watches for the portable CLI."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import sys


ACTIVE_PHASES = {'QUEUED', 'FLASHING', 'RUNNING', 'PAUSE_REQUESTED', 'CANCEL_REQUESTED', 'FINALIZING'}
OUTCOME_CODES = {'PASSED': 0, 'FAILED': 5, 'CANCELLED': 5, 'ABORTED': 5, 'SUPERSEDED_BY_REPREPARE': 5}


def emit_json_line(value):
    line = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    sys.stdout.buffer.write(line.encode('utf-8'))
    sys.stdout.buffer.flush()


def connection_status(diagnostics):
    code = diagnostics.get('code')
    if code == 'RUNNER_CHANGED':
        state = 'runner_changed'
    else:
        state = 'connected' if diagnostics['reachable'] else 'disconnected'
    return {'schema_version': 1, 'type': 'connection', 'state': state,
            'runner_id': diagnostics.get('runner_id'), 'code': code}


def observe_run(direct, run_id, *, watch, emit):
    previous = None
    while True:
        run = direct.get_run(run_id)
        phase, outcome = run['state'], run['outcome']
        if phase == 'COMPLETED' and outcome in OUTCOME_CODES:
            state, code = outcome.lower(), OUTCOME_CODES[outcome]
        elif phase == 'PAUSED':
            state, code = ('hold' if run['analysis_latched'] else 'paused'), 4
        elif phase == 'UNKNOWN':
            state, code = 'unknown', 3
        elif phase in ACTIVE_PHASES:
            state, code = phase.lower(), 0
        else:
            raise ValueError('Connector returned an unsupported Run phase or outcome')
        if type(run['version']) is not int or not run['runner_id'] or not run['run_id']:
            raise ValueError('Connector returned an invalid Run identity or version')
        if (run_id and run_id != run['run_id']) or (previous and previous['runner_id'] != run['runner_id']):
            raise ValueError('Run identity changed during observation')
        run_id = run['run_id']
        record = {'schema_version': 1, 'type': 'run', 'runner_id': run['runner_id'], 'run_id': run_id,
                  'state': state, 'phase': phase, 'outcome': outcome, 'version': run['version']}
        if record != previous:
            emit(record)
            previous = record
        if not watch or phase not in ACTIVE_PHASES:
            return code
        direct.sleep(0.25)


@contextmanager
def connection_watch_lock(port):
    """One local user and loopback endpoint share one stable inode across projects."""
    if os.name == 'nt':
        # Keep the legacy client callable there. The activation hook targets POSIX.
        yield True
        return
    import fcntl

    directory = Path('/tmp') / f'bsp-connector-watch-{os.getuid()}'
    directory.mkdir(mode=0o700, exist_ok=True)
    metadata = directory.lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077):
        raise ValueError('Connector watch lock directory must be private to the current user')
    lock_file = directory / f'127.0.0.1-{port}.lock'
    fd = os.open(lock_file, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            yield True
    finally:
        os.close(fd)
