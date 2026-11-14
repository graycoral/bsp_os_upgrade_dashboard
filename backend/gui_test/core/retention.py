"""Collect only managed snapshot caches; run records and logs are never deleted.

Snapshot publication and reference acceptance share this lock with collection.
The byte limit is a target: active references and failure evidence take priority.
"""
from contextlib import contextmanager
from functools import wraps
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
import uuid
from typing import Literal

from pydantic import Field, StrictBool, StrictInt
from .models import StrictModel, TestError, digest
from ..execution.launch import LaunchLock


class StoragePolicy(StrictModel):
    enabled: StrictBool = True
    max_age_seconds: StrictInt = Field(default=7 * 86400, ge=3600, le=3650 * 86400)
    max_bytes: StrictInt = Field(default=20 * 1024**3, ge=1, le=1024**5)


class StorageUpdate(StoragePolicy):
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')


class StorageFile(StorageUpdate):
    format: Literal['snapshot-storage-policy-v1'] = 'snapshot-storage-policy-v1'


class CleanupRequest(StrictModel):
    dry_run: StrictBool = True


class StorageSettings:
    def __init__(self, store): self.store = store

    def read(self, connection=None):
        if connection is None:
            with self.store.connection() as c: return self.read(c)
        row = connection.execute("SELECT data FROM documents WHERE kind='storage-policy' AND name='current'").fetchone()
        value = StoragePolicy.model_validate(json.loads(row[0]) if row else {}).model_dump()
        return value | {'revision': digest(value)}

    def save(self, payload):
        update = StorageUpdate.model_validate(payload)
        value = update.model_dump(exclude={'expected_revision'})
        with self.store.transaction() as c:
            if self.read(c)['revision'] != update.expected_revision:
                raise TestError('Storage policy changed; reload settings', 'STORAGE_POLICY_CHANGED')
            c.execute("INSERT INTO documents VALUES('storage-policy','current',?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data", (json.dumps(value),))
            c.execute("INSERT INTO documents VALUES('storage-sync','connector',?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data",
                      (json.dumps({'state': 'SYNC_PENDING', 'origin': 'plugin', 'desired_revision': digest(value)}),))
        return value | {'revision': digest(value)}

    def report(self):
        with self.store.connection() as c:
            row = c.execute("SELECT data FROM documents WHERE kind='storage-cleanup' AND name='last'").fetchone()
        return json.loads(row[0]) if row else None


_locks = {}
_locks_guard = threading.Lock()
_local = threading.local()


@contextmanager
def snapshot_lock(root, *, blocking=True):
    key = str(Path(root).absolute())
    with _locks_guard: mutex = _locks.setdefault(key, threading.RLock())
    if not mutex.acquire(blocking=blocking):
        raise BlockingIOError('Snapshot operation in progress')
    depths = getattr(_local, 'depths', {})
    _local.depths = depths
    held = None
    acquired = False
    try:
        if depths.get(key, 0) == 0:
            held = LaunchLock(Path(key) / 'snapshot-retention.lock')
            deadline = time.monotonic() + 60
            while True:
                try:
                    held.__enter__()
                    acquired = True
                    break
                except RuntimeError:
                    if not blocking or time.monotonic() >= deadline:
                        held = None
                        raise BlockingIOError('Snapshot operation in progress')
                    time.sleep(.05)
        depths[key] = depths.get(key, 0) + 1
        try: yield
        finally: depths[key] -= 1
    finally:
        if acquired: held.__exit__(None, None, None)
        mutex.release()


def snapshot_operation(function):
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        store = getattr(self, 'store', None) or self.manager.store
        with snapshot_lock(store.path.parent): return function(self, *args, **kwargs)
    return wrapped


def references(value):
    """Conservatively recognize embedded cache IDs, including old receipt shapes."""
    found = set()
    if isinstance(value, dict):
        for child in value.values(): found.update(references(child))
    elif isinstance(value, list):
        for child in value: found.update(references(child))
    elif isinstance(value, str):
        candidate = value.replace('\\', '/').rstrip('/').rsplit('/', 1)[-1]
        if re.fullmatch('[a-f0-9]{64}', candidate): found.add(candidate)
    return found


def has_failure(value):
    if isinstance(value, dict): return any(has_failure(v) for v in value.values())
    if isinstance(value, list): return any(has_failure(v) for v in value)
    return isinstance(value, str) and value in {'FAIL', 'FAILED', 'ERROR', 'TIMEOUT', 'UNKNOWN'}


def _plain(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Linked snapshot path')
    return info


def _measure(path):
    for parent in path.parents:
        _plain(parent)
    root_info = _plain(path)
    if not stat.S_ISDIR(root_info.st_mode): raise ValueError('Snapshot is not a directory')
    size, newest = 0, root_info.st_mtime
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            info = _plain(Path(root) / name)
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise ValueError('Special file in snapshot')
            if stat.S_ISREG(info.st_mode): size += info.st_size
            newest = max(newest, info.st_mtime)
    return size, newest


def scan_trees(roots):
    """Slow filesystem work stays outside all producer/DB/control locks."""
    items, skipped = [], []
    for root, pattern in roots:
        root = Path(root)
        if not root.exists(): continue
        try:
            for parent in (root, *root.parents): _plain(parent)
            children = list(root.iterdir())
        except (OSError, ValueError) as exc:
            skipped.append({'path': str(root), 'reason': type(exc).__name__})
            continue
        for path in children:
            if not re.fullmatch(pattern, path.name) and not re.fullmatch(r'\.retention-[a-f0-9]{32}', path.name):
                skipped.append({'path': str(path), 'reason': 'UNMANAGED_NAME'})
                continue
            try:
                before = _plain(path)
                size, newest = _measure(path)
                after = _plain(path)
                stamp = lambda info: (info.st_dev, info.st_ino, info.st_mtime_ns)
                if stamp(before) != stamp(after): raise ValueError('Snapshot changed during scan')
            except (OSError, ValueError) as exc:
                skipped.append({'path': str(path), 'reason': type(exc).__name__})
                continue
            items.append({'path': path, 'size': size, 'newest': newest, 'stamp': stamp(after)})
    return items, skipped


def quarantine_trees(scan, protected, policy, *, dry_run, clock=None, minimum_age=3600):
    """Caller holds the producer lock and a fresh reference transaction.

    Only cheap root validation and atomic renames occur here, never recursive I/O.
    A changed candidate is skipped and can be reconsidered by a later sweep.
    """
    now = time.time() if clock is None else clock
    value = StoragePolicy.model_validate(policy).model_dump()
    items, skipped = scan
    report = {'dry_run': dry_run, 'enabled': value['enabled'], 'checked_at': now,
              'bytes_before': 0, 'bytes_after': 0, 'protected_bytes': 0,
              'eligible_bytes': 0, 'deleted_bytes': 0, 'planned_bytes': 0,
              'deleted': [], 'candidates': [], 'skipped': list(skipped), 'over_budget': False, 'batch_limited': False}
    eligible, quarantined = [], []
    for item in items:
        path, size, newest = item['path'], item['size'], item['newest']
        report['bytes_before'] += size
        keep = str(path) in protected or path.name in protected or now - newest < minimum_age
        if keep: report['protected_bytes'] += size
        else:
            report['eligible_bytes'] += size
            eligible.append(item)
    remaining = report['bytes_before']
    for item in sorted(eligible, key=lambda item: (item['newest'], str(item['path']))):
        path, size = item['path'], item['size']
        if not value['enabled'] or (now - item['newest'] < value['max_age_seconds'] and remaining <= value['max_bytes']): continue
        if len(report['candidates']) >= 32:
            report['batch_limited'] = True
            break
        try:
            for parent in (path, *path.parents): _plain(parent)
            info = path.lstat()
            if (info.st_dev, info.st_ino, info.st_mtime_ns) != item['stamp'] or not stat.S_ISDIR(info.st_mode):
                raise ValueError('Snapshot changed since scan')
            trash = path.with_name('.retention-' + uuid.uuid4().hex)
            if not dry_run:
                if trash.exists(): raise FileExistsError('Quarantine collision')
                path.rename(trash)
                os.utime(trash, None)  # Other collectors leave fresh quarantine alone.
                quarantined.append((path, trash, size))
            report['candidates'].append(str(path))
            report['planned_bytes'] += size
            remaining -= size
        except (OSError, ValueError) as exc:
            report['skipped'].append({'path': str(path), 'reason': type(exc).__name__})
    report['bytes_after'] = remaining if dry_run else report['bytes_before']
    report['over_budget'] = report['bytes_after'] > value['max_bytes']
    report['measurement_complete'] = not report['skipped']
    return report, quarantined, value['max_bytes']


def delete_quarantined(plan):
    """No DB/control lock held. Interrupted quarantines age into the next sweep."""
    report, quarantined, budget = plan
    for path, trash, size in quarantined:
        try:
            _measure(trash)
            shutil.rmtree(trash)
            report['deleted'].append(str(path))
            report['deleted_bytes'] += size
            report['bytes_after'] -= size
        except (OSError, ValueError) as exc:
            report['skipped'].append({'path': str(trash), 'reason': type(exc).__name__})
    report['over_budget'] = report['bytes_after'] > budget
    report['measurement_complete'] = not report['skipped']
    return report


def collect_trees(roots, protected, policy, *, dry_run, clock=None, minimum_age=3600):
    """Standalone test/helper; service callers lock only quarantine_trees."""
    return delete_quarantined(quarantine_trees(scan_trees(roots), protected, policy,
                             dry_run=dry_run, clock=clock, minimum_age=minimum_age))


def collect(manager, *, dry_run=True, blocking=False, clock=None):
    store = manager.store
    now = time.time() if clock is None else clock
    roots = [(manager.sources.snapshots, '[a-f0-9]{64}'),
             (store.path.parent / 'integration-inputs' / 'tc', '[a-f0-9]{64}'),
             (store.path.parent / 'integration-inputs' / 'installers', '[a-f0-9]{64}')]
    scan = scan_trees(roots)
    try:
        with snapshot_lock(store.path.parent, blocking=blocking), store.transaction() as c:
            policy = StorageSettings(store).read(c)
            protected = set()
            for row in c.execute('SELECT data FROM runs'):
                run = json.loads(row[0])
                if run.get('state') != 'COMPLETED' or run.get('overall_result') != 'PASS' or has_failure(run):
                    protected.update(references(run))
            for kind, raw in c.execute('SELECT kind,data FROM documents'):
                doc = json.loads(raw)
                if (kind == 'source-state' or
                    kind == 'integration-preparation' and (doc.get('state') == 'PREPARING' or
                        doc.get('state') == 'READY' and doc.get('expires_at', 0) > now)):
                    protected.update(references(doc))
            plan = quarantine_trees(scan, protected, {k:v for k,v in policy.items() if k != 'revision'}, dry_run=dry_run, clock=now)
        report = delete_quarantined(plan)
        if not dry_run:
            with store.transaction() as c:
                c.execute("INSERT INTO documents VALUES('storage-cleanup','last',?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data", (json.dumps(report),))
        return report
    except BlockingIOError:
        return {'dry_run': dry_run, 'skipped_reason': 'SNAPSHOT_BUSY'}


_last = {}


def maybe_collect(manager):
    key = str(manager.store.path)
    now = time.monotonic()
    if now - _last.get(key, -300) < 300: return None
    _last[key] = now
    try:
        report = collect(manager, dry_run=False)
        connector_sync(manager)
        return report
    except (OSError, ValueError, RuntimeError) as exc:
        return {'skipped_reason': 'STORAGE_CLEANUP_FAILED', 'error_type': type(exc).__name__}


def connector_sync(manager, *, retry=True):
    """Apply only an explicitly saved central policy, pinning the fresh identity.

    Defaults never overwrite standalone connector choices. Failed transport leaves
    a durable pending receipt; the normal worker retries it without blocking TCs.
    """
    store = manager.store
    with store.connection() as c:
        row = c.execute("SELECT data FROM documents WHERE kind='storage-sync' AND name='connector'").fetchone()
    if not row: return {'state': 'LOCAL_DEFAULT', 'origin': 'connector'}
    receipt = json.loads(row[0])
    if not retry: return receipt
    desired = StorageSettings(store).read()
    try:
        runner = manager.runner
        target = getattr(type(runner), 'target', None)
        remote = runner.target(fresh=True) if target else runner
        identity = remote.request('/identity')
        runner_id = identity.get('runner_id')
        if not runner_id or identity.get('storage_retention_v1') is not True:
            raise TestError('Connector storage retention unsupported', 'STORAGE_UNSUPPORTED')
        current = remote.request('/storage-policy')
        if remote.request('/identity').get('runner_id') != runner_id:
            raise TestError('Connector identity changed', 'RUNNER_CHANGED')
        values = {k: desired[k] for k in StoragePolicy.model_fields}
        if current['revision'] != desired['revision'] or current.get('origin') != 'plugin':
            applied = remote.request('/storage-policy', 'PUT', values | {'expected_revision': current['revision'], 'expected_runner_id': runner_id})
        else: applied = current
        if applied['revision'] != desired['revision'] or remote.request('/identity').get('runner_id') != runner_id:
            raise TestError('Connector policy application not verified', 'STORAGE_SYNC_UNVERIFIED')
        receipt = {'state': 'APPLIED', 'origin': 'plugin', 'runner_id': runner_id,
                   'desired_revision': desired['revision'], 'applied_revision': applied['revision'], 'checked_at': time.time()}
    except Exception as exc:
        receipt = {'state': 'SYNC_PENDING', 'origin': 'plugin', 'desired_revision': desired['revision'],
                   'reason': getattr(exc, 'code', type(exc).__name__), 'checked_at': time.time()}
    with store.transaction() as c:
        # An older in-flight response may not mark a newer policy as applied.
        if StorageSettings(store).read(c)['revision'] == desired['revision']:
            c.execute("INSERT INTO documents VALUES('storage-sync','connector',?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data", (json.dumps(receipt),))
    return receipt


def connector_cleanup(manager, *, dry_run=True):
    try:
        runner = manager.runner
        remote = runner.target(fresh=True) if getattr(type(runner), 'target', None) else runner
        identity = remote.request('/identity')
        runner_id = identity.get('runner_id')
        if not runner_id or identity.get('storage_retention_v1') is not True:
            raise TestError('Connector storage retention unsupported', 'STORAGE_UNSUPPORTED')
        report = remote.request('/storage-cleanup', 'POST',
                                {'dry_run': dry_run, 'expected_runner_id': runner_id})
        return {'state': 'CHECKED', 'runner_id': runner_id, 'report': report}
    except Exception as exc:
        return {'state': 'UNAVAILABLE', 'reason': getattr(exc, 'code', type(exc).__name__)}


def main(argv=None):
    """Offline settings only; maintenance remains owned by the normal services."""
    import argparse
    from .store import Store
    parser = argparse.ArgumentParser(description='Export or apply snapshot cache retention settings')
    parser.add_argument('--database', required=True)
    parser.add_argument('action', choices=['export', 'apply'])
    parser.add_argument('file')
    args = parser.parse_args(argv)
    database = Path(args.database)
    if not database.is_file(): parser.error('Use an existing GUI Test database')
    settings = StorageSettings(Store(database))
    if args.action == 'export':
        current = settings.read()
        value = StorageFile(**{k:v for k,v in current.items() if k != 'revision'}, expected_revision=current['revision'])
        Path(args.file).write_text(value.model_dump_json(indent=2) + '\n', encoding='utf-8')
    else:
        value = StorageFile.model_validate_json(Path(args.file).read_text(encoding='utf-8'))
        settings.save(value.model_dump(exclude={'format'}))


if __name__ == '__main__': main()
