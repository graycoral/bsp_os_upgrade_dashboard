"""Windows cache retention under the execution host's producer/reference lock."""
import json
import os
from pathlib import Path
import sqlite3
import time
import threading
from functools import wraps

from pydantic import Field
from ..core.models import TestError, digest
from ..core.retention import StoragePolicy, StorageUpdate, CleanupRequest, scan_trees, quarantine_trees, delete_quarantined, references, has_failure
from ..core.results import parse_result


_cache_guard = threading.Lock()


def cache_lock(host):
    with _cache_guard:
        if not hasattr(host, 'snapshot_cache_lock'):
            host.snapshot_cache_lock = threading.RLock()
        return host.snapshot_cache_lock


def snapshot_operation(function):
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        host = self if hasattr(self, 'runtime') else self.host
        with cache_lock(host): return function(self, *args, **kwargs)
    return wrapped


class ConnectorStorageUpdate(StorageUpdate):
    expected_runner_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


class ConnectorCleanupRequest(CleanupRequest):
    expected_runner_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


def require_identity(host, expected):
    if expected is not None and host.identity != expected:
        raise TestError('Connector identity changed', 'RUNNER_CHANGED')


def read_policy(host, c=None):
    if c is None:
        with host.lock, sqlite3.connect(host.db) as connection: return read_policy(host, connection)
    row = c.execute("SELECT value FROM runner_meta WHERE key='storage-policy'").fetchone()
    value = StoragePolicy.model_validate(json.loads(row[0]) if row else {}).model_dump()
    report = c.execute("SELECT value FROM runner_meta WHERE key='storage-cleanup'").fetchone()
    origin = c.execute("SELECT value FROM runner_meta WHERE key='storage-policy-origin'").fetchone()
    return value | {'revision': digest(value), 'report': json.loads(report[0]) if report else None,
                    'origin': origin[0] if origin else 'connector-default'}


def save_policy(host, payload):
    update = ConnectorStorageUpdate.model_validate(payload)
    value = update.model_dump(exclude={'expected_revision', 'expected_runner_id'})
    with host.lock, sqlite3.connect(host.db) as c:
        c.execute('BEGIN IMMEDIATE')
        require_identity(host, update.expected_runner_id)
        if read_policy(host, c)['revision'] != update.expected_revision:
            raise TestError('Storage policy changed; reload settings', 'STORAGE_POLICY_CHANGED')
        c.execute("INSERT INTO runner_meta VALUES('storage-policy',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(value),))
        c.execute("INSERT INTO runner_meta VALUES('storage-policy-origin',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  ('plugin' if update.expected_runner_id else 'connector',))
    return read_policy(host)


def successful(job):
    if job.get('state') != 'DONE' or job.get('terminated') is not True or has_failure(job): return False
    if job.get('forced_state') or job.get('console', {}).get('unsafe'): return False
    if job.get('kind') in {'batch-prepare', 'flash-test'}: return job.get('outcome') == 'SUCCEEDED'
    return parse_result(job.get('stdout', ''), job.get('stderr', ''), job.get('exit_code'))[0] == 'PASS'


def collect(host, *, dry_run=True, clock=None, expected_runner_id=None):
    roots = [(host.runtime / name, '[a-f0-9]{64}') for name in ('source-snapshots', 'installer-snapshots')]
    roots += [(host.runtime / name, '[a-f0-9]{32}') for name in ('snapshots', 'flash-snapshots', 'batch-snapshots')]
    scan = scan_trees(roots)
    with cache_lock(host), host.lock, sqlite3.connect(host.db) as c:
        c.execute('BEGIN IMMEDIATE')
        require_identity(host, expected_runner_id)
        policy = read_policy(host, c)
        jobs = [json.loads(r[0]) for r in c.execute('SELECT data FROM jobs')]
        batches = [json.loads(r[0]) for r in c.execute('SELECT data FROM batches')]
        protected, keep_sources, keep_installers = set(), False, False
        held_batches = {b['id'] for b in batches if b.get('state') != 'RELEASED'}
        for batch in batches:
            if batch['id'] in held_batches:
                protected.add(batch['id'])
                protected.update(references(batch))
                # Older reservations do not carry the future TC snapshot identity.
                keep_sources = True
        for job in jobs:
            if job.get('state') == 'DELETED': continue
            if not successful(job) or job.get('batch_id') in held_batches:
                protected.add(job['id'])
                protected.update(references(job))
                if job.get('batch_id'): protected.add(job['batch_id'])
                if not job.get('source_snapshot_id'): keep_sources = True
                if job.get('kind') in {'batch-prepare', 'flash-test'} and not references(job): keep_installers = True
        for item in scan[0]:
            path = item['path']
            if (path.parent.name == 'source-snapshots' and keep_sources or
                    path.parent.name == 'installer-snapshots' and keep_installers):
                protected.add(str(path))
        plan = quarantine_trees(scan, protected, {k: policy[k] for k in StoragePolicy.model_fields}, dry_run=dry_run, clock=clock)
        # Invalidate only receipts for successfully quarantined installers, before
        # releasing the publication lock. A future upload may then safely recreate it.
        for path, trash, size in plan[1]:
            if path.parent == host.runtime / 'installer-snapshots':
                receipt = host.runtime / 'installer-transfers' / (path.name + '.json')
                if receipt.is_file() and not receipt.is_symlink():
                    try: receipt.unlink()
                    except OSError: pass
    report = delete_quarantined(plan)
    report['excluded'] = ['installer-transfers (resumable uploads)', 'logs', 'execution records']
    if not dry_run:
        with host.lock, sqlite3.connect(host.db) as c:
            c.execute("INSERT INTO runner_meta VALUES('storage-cleanup',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(report),))
    return report


def publish(host, function, *args):
    """Serialize publication with collection; refresh the remote acceptance grace."""
    with cache_lock(host):
        result = function(*args)
        identity = result.get('snapshot_id')
        for name in ('source-snapshots', 'installer-snapshots'):
            path = host.runtime / name / str(identity)
            if path.is_dir() and not path.is_symlink(): os.utime(path, None)
        return result


async def maintain(host):
    import asyncio
    while True:
        task = asyncio.create_task(asyncio.to_thread(collect, host, dry_run=False))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # Keep the process ownership lock until the in-flight collector exits.
            try: await task
            except Exception: pass
            raise
        except Exception:
            # Cleanup is optional maintenance and never terminates hardware work.
            import logging
            logging.getLogger(__name__).exception('Snapshot retention failed')
        await asyncio.sleep(300)
