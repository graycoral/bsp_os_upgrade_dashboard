"""T-82: populated v1 migration and recovery, including evidence and UNKNOWN writers."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from backend.storage.store import Store


@pytest.fixture
def legacy_runtime(tmp_path):
    root = tmp_path / 'original'
    root.mkdir()
    artifacts = root / 'artifacts'
    folder = artifacts / 'legacy-job'
    folder.mkdir(parents=True)
    image = b'fixture image\x00\xff\n'
    (folder / 'retained.bin').write_bytes(image)
    digest = hashlib.sha256(image).hexdigest()
    failed = {'id': 'failed-attempt', 'status': 'FAILED', 'error_class': 'FIX', 'cause_key': 'old-api',
              'evidence': 'Retained failed implementation.', 'token': 'expired-fixture-token'}
    passed = {'id': 'passed-attempt', 'status': 'SUCCEEDED', 'evidence': 'Retained successful build.'}
    artifact = {'id': 'retained.bin', 'name': 'board.bin', 'sha256': digest, 'bytes': len(image)}
    stages = {'code': {'status': 'UNKNOWN', 'validity': 'UNVERIFIED',
                      'attempts': [failed, {'id': 'writer-unknown', 'status': 'UNKNOWN', 'token': 'unknown-token'}], 'result': None},
              'build': {'status': 'SUCCEEDED', 'validity': 'CURRENT', 'attempts': [passed],
                        'result': {'outcome': 'SUCCEEDED', 'artifact': artifact, 'evidence': 'Build log.'}},
              'device_test': {'status': 'SUCCEEDED', 'validity': 'CURRENT', 'attempts': [],
                              'result': {'outcome': 'SUCCEEDED', 'cases': {'boot': 'PASS', 'network': 'PASS'}}}}
    job = {'id': 'legacy-job', 'version': 9, 'plan_version': 1, 'confirmed_plan': 1,
           'source_revision': 'frozen-revision', 'execution': 'bridge', 'profile': {'runner': 'bridge'},
           'session': {'id': 'old-session', 'status': 'NEEDS_RECONCILIATION'},
           'modules': [{'id': 'legacy-module', 'name': 'BSP', 'group': 'boot', 'stages': stages}],
           'decisions': [{'id': 'prior-decision', 'status': 'RESOLVED', 'resolution': 'Keep upstream behavior.'}],
           'prompts': [], 'integration': {'status': 'PENDING'}, 'final_review': None}
    # Whitespace and ordering deliberately differ from current serialization.
    raw_job = json.dumps(job, ensure_ascii=False, indent=2)
    raw_command = '{ "job_id" : "legacy-job", "version" : 9, "accepted" : true }'
    db = root / 'db.sqlite'
    with sqlite3.connect(db) as c:
        c.executescript('''
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            INSERT INTO meta VALUES('schema_version','1');
            CREATE TABLE jobs(id TEXT PRIMARY KEY,version INTEGER NOT NULL,data TEXT NOT NULL);
            CREATE TABLE commands(key TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE events(seq INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL,type TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE leases(resource TEXT PRIMARY KEY,attempt TEXT NOT NULL,token TEXT NOT NULL);
            CREATE TABLE config(id INTEGER PRIMARY KEY CHECK(id=1),version INTEGER NOT NULL,data TEXT NOT NULL);
        ''')
        c.execute('INSERT INTO jobs VALUES(?,?,?)', ('legacy-job', 9, raw_job))
        c.execute('INSERT INTO commands VALUES(?,?,?,?)', ('retained-command', 'hash', raw_command, '2026-10-01'))
        c.execute('INSERT INTO events VALUES(?,?,?,?,?)', (7, 'legacy-job', 'ATTEMPT_FAILED', '{"attempt":"failed-attempt"}', '2026-10-01'))
        c.execute('INSERT INTO leases VALUES(?,?,?)', ('linux-write-build', 'writer-unknown', 'unknown-token'))
        c.execute('INSERT INTO config VALUES(1,1,?)', ('{"execution":"bridge","runner":"bridge"}',))
    return {'root': root, 'db': db, 'artifacts': artifacts, 'job': raw_job,
            'command': raw_command, 'image': image}


def retained_rows(store):
    with store.connection() as c:
        return {table: [tuple(r) for r in c.execute('SELECT * FROM ' + table + ' ORDER BY 1')]
                for table in ('jobs', 'commands', 'events', 'leases', 'config')}


def test_t82_v1_migration_is_additive_repeatable_and_preserves_raw_history(legacy_runtime):
    store = Store(legacy_runtime['db'])
    before = retained_rows(store)
    with store.connection() as c:
        assert c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == '2'
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'agent_reports', 'orchestration_runs', 'orchestration_triggers', 'orchestration_proposals',
            'decision_candidates', 'scope_holds', 'launch_receipts', 'coordinator_lanes'} <= names
    assert before['jobs'][0][2] == legacy_runtime['job']
    assert before['commands'][0][2] == legacy_runtime['command']
    assert retained_rows(Store(legacy_runtime['db'])) == before
    assert store.snapshot('legacy-job')['modules'][0]['stages']['code']['status'] == 'UNKNOWN'


def test_t82_pre_migration_path_backup_never_initializes_or_changes_v1_source(legacy_runtime, tmp_path, monkeypatch):
    from backend.storage.recovery import backup_runtime, verify_backup
    database = legacy_runtime['db']
    source_bytes = database.read_bytes()
    artifact = legacy_runtime['artifacts'] / 'legacy-job' / 'retained.bin'
    artifact_bytes = artifact.read_bytes()
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as c:
        source_tables = c.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        source_rows = {name: c.execute('SELECT * FROM ' + name + ' ORDER BY 1').fetchall()
                       for name in ('meta', 'jobs', 'commands', 'events', 'leases', 'config')}
    def forbidden_init(*_args, **_kwargs):
        pytest.fail('Read-only pre-migration backup attempted Store initialization/migration.')
    monkeypatch.setattr(Store, '__init__', forbidden_init)
    bundle = tmp_path / 'pre-migration-backup'
    manifest = backup_runtime(database, legacy_runtime['artifacts'], bundle)
    assert manifest['schema_version'] == 1
    assert verify_backup(bundle)['schema_version'] == 1
    assert database.read_bytes() == source_bytes
    assert artifact.read_bytes() == artifact_bytes
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as c:
        assert c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == '1'
        assert c.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall() == source_tables
        for name, rows in source_rows.items():
            assert c.execute('SELECT * FROM ' + name + ' ORDER BY 1').fetchall() == rows
    with sqlite3.connect(bundle / 'dashboard.db') as c:
        assert c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == '1'
        assert c.execute('SELECT result FROM commands').fetchone()[0] == legacy_runtime['command']
        assert c.execute('SELECT attempt FROM leases').fetchone()[0] == 'writer-unknown'
    assert (bundle / 'artifacts' / 'legacy-job' / 'retained.bin').read_bytes() == artifact_bytes


def test_t82_unknown_schema_is_rejected_without_migration(legacy_runtime):
    with sqlite3.connect(legacy_runtime['db']) as c:
        c.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
    with pytest.raises(RuntimeError):
        Store(legacy_runtime['db'])
    with sqlite3.connect(legacy_runtime['db']) as c:
        assert c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] == '999'
        assert c.execute('SELECT data FROM jobs').fetchone()[0] == legacy_runtime['job']
        assert c.execute("SELECT name FROM sqlite_master WHERE name='agent_reports'").fetchone() is None


def test_t82_backup_restore_preserves_artifacts_history_commands_and_unknown_lease(legacy_runtime, tmp_path):
    from backend.storage.recovery import backup_runtime, verify_backup, restore_runtime
    store = Store(legacy_runtime['db'])
    expected = retained_rows(store)
    bundle = tmp_path / 'backup'
    manifest = backup_runtime(store, legacy_runtime['artifacts'], bundle)
    assert isinstance(manifest, dict)
    assert isinstance(verify_backup(bundle), dict)
    destination = tmp_path / 'restored'
    restore_runtime(bundle, destination)
    restored_db = destination / 'dashboard.db'
    assert restored_db.is_file()
    restored = Store(restored_db)
    assert retained_rows(restored) == expected
    assert (destination / 'artifacts' / 'legacy-job' / 'retained.bin').read_bytes() == legacy_runtime['image']
    assert restored.snapshot('legacy-job')['modules'][0]['stages']['code']['status'] == 'UNKNOWN'
    with restored.connection() as c:
        assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert c.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('damage', ['missing', 'tampered'])
def test_t82_corrupt_evidence_is_rejected_before_restoring_active_data(legacy_runtime, tmp_path, damage):
    from backend.storage.recovery import backup_runtime, verify_backup, restore_runtime
    bundle = tmp_path / 'backup'
    backup_runtime(Store(legacy_runtime['db']), legacy_runtime['artifacts'], bundle)
    copied = next(bundle.rglob('retained.bin'))
    if damage == 'missing':
        copied.unlink()
    else:
        copied.write_bytes(b'tampered evidence')
    destination = tmp_path / 'restored'
    with pytest.raises((ValueError, RuntimeError)):
        verify_backup(bundle)
    with pytest.raises((ValueError, RuntimeError)):
        restore_runtime(bundle, destination)
    assert not destination.exists() or not list(destination.iterdir())


def test_t82_restore_refuses_existing_destination_and_backup_inside_source(legacy_runtime, tmp_path):
    from backend.storage.recovery import backup_runtime, restore_runtime
    store = Store(legacy_runtime['db'])
    bundle = tmp_path / 'backup'
    backup_runtime(store, legacy_runtime['artifacts'], bundle)
    target = tmp_path / 'occupied'
    target.mkdir()
    sentinel = target / 'user.txt'
    sentinel.write_text('preserve me')
    with pytest.raises((ValueError, RuntimeError)):
        restore_runtime(bundle, target)
    assert sentinel.read_text() == 'preserve me'
    with pytest.raises((ValueError, RuntimeError)):
        backup_runtime(store, legacy_runtime['artifacts'], legacy_runtime['artifacts'] / 'nested-backup')
