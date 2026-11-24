"""Upgrade managed profiles while the caller holds both connector launch locks."""
import json
from contextlib import contextmanager
import sqlite3
from pathlib import Path

from ..core.models import TestError


def automatic_transport(value):
    if value not in {'native', 'proxy'}:
        raise TestError('Invalid serial transport', 'CONNECTOR_CONFIG')
    return 'proxy'


def prepare_locked(home):
    """Called under setup-launch.lock and runner.lock, before opening any COM.

    Preserve inactive RX settings for rollback. Never migrate a profile with
    unresolved execution ownership, including after an interrupted Host.
    """
    from scripts.setup_runtime import save_json
    from .settings import Settings
    home = Path(home)
    profile = Settings(home).read()
    mode = automatic_transport(profile.get('serial_transport', 'native'))
    if profile.get('serial_transport') == mode:
        return
    with idle_records(home):
        profile['serial_transport'] = mode
        save_json(home / 'windows-runner.json', profile)


@contextmanager
def idle_records(home):
    """Caller holds both launch locks; keep durable ownership stable until save."""
    db = Path(home).resolve() / 'runtime' / 'executions.db'
    if not db.exists():
        yield
        return
    # Existing but unreadable/incomplete records must not be treated as idle.
    with sqlite3.connect(db.as_uri() + '?mode=rw', uri=True) as connection:
        connection.execute('BEGIN IMMEDIATE')
        jobs = [json.loads(row[0]) for row in connection.execute('SELECT data FROM jobs')]
        batches = [json.loads(row[0]) for row in connection.execute('SELECT data FROM batches')]
        if any(job.get('state') in {'RUNNING', 'UNKNOWN'} for job in jobs) or any(
                batch.get('state') != 'RELEASED' for batch in batches):
            raise TestError('진행·예약·종료 불명 작업을 확인한 뒤 다시 연결하세요.', 'CONNECTOR_BUSY', 409)
        yield
