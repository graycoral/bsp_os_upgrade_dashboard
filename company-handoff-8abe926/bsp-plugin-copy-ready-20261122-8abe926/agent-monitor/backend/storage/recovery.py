"""Offline BSP runtime bundles. Does not migrate or restart a restored runtime."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path


class RecoveryError(ValueError):
    pass


def _hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _database_check(path):
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or c.execute('PRAGMA foreign_key_check').fetchall():
            raise RecoveryError('Database integrity or foreign-key verification failed.')
        version = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if not version or version[0] not in {'1', '2'}:
            raise RecoveryError('Unsupported BSP database schema.')
        return version[0]


def _references(database):
    refs = {}
    def add(job_id, identifier, sha=None, size=None):
        if not isinstance(identifier, str) or not identifier:
            return
        if Path(identifier).name != identifier or '/' in identifier or '\\' in identifier or job_id in {'.', '..'} or Path(job_id).name != job_id:
            raise RecoveryError('Unsafe artifact reference.')
        relative = job_id + '/' + identifier
        old = refs.get(relative)
        if old and sha and old.get('sha256') and old['sha256'] != sha:
            raise RecoveryError('Conflicting artifact hashes in database.')
        refs[relative] = {'path': relative, 'sha256': sha or (old or {}).get('sha256'), 'bytes': size if size is not None else (old or {}).get('bytes')}
    def walk(value, job_id):
        if isinstance(value, list):
            for item in value:
                walk(item, job_id)
        elif isinstance(value, dict):
            # Stored runtime IDs, never agent workspace paths.
            if value.get('id') and value.get('sha256') and ('bytes' in value or 'name' in value) and 'path' not in value:
                add(job_id, value['id'], value.get('sha256'), value.get('bytes'))
            if value.get('evidence_id'):
                add(job_id, value['evidence_id'])
            for item in value.values():
                walk(item, job_id)
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as c:
        for identifier, raw in c.execute('SELECT id,data FROM jobs'):
            walk(json.loads(raw), identifier)
        tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'agent_reports' in tables:
            for job_id, raw in c.execute('SELECT job_id,data FROM agent_reports'):
                data = json.loads(raw)
                for item in data.get('files', []):
                    add(job_id, item['id'], item['sha256'], item['bytes'])
    return refs


def _fresh_destination(destination, sources):
    destination = Path(destination).resolve()
    for source in sources:
        source = Path(source).resolve()
        if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
            raise RecoveryError('Destination must be outside and separate from the source runtime.')
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise RecoveryError('Destination must be empty.')
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def backup_runtime(store, artifact_root, destination):
    """Accept a Store or a DB path; the path form never initializes or migrates Store."""
    source_database = Path(store.path if hasattr(store, 'path') else store).resolve()
    artifacts = Path(artifact_root).resolve()
    root = _fresh_destination(destination, [source_database.parent, artifacts])
    database = root / 'dashboard.db'
    with sqlite3.connect(source_database.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(database) as target:
        source.backup(target)
    schema = _database_check(database)
    references = _references(database)
    copied = []
    for item in references.values():
        source = (artifacts / item['path']).resolve()
        if not source.is_relative_to(artifacts) or not source.is_file():
            raise RecoveryError('Referenced artifact is missing: ' + item['path'])
        digest, size = _hash(source), source.stat().st_size
        if item['sha256'] and digest != item['sha256'] or item['bytes'] is not None and size != item['bytes']:
            raise RecoveryError('Referenced artifact hash or size mismatch: ' + item['path'])
        target = root / 'artifacts' / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        if _hash(target) != digest or target.stat().st_size != size:
            raise RecoveryError('Artifact changed during backup: ' + item['path'])
        copied.append({'path': item['path'], 'sha256': digest, 'bytes': size})
    manifest = {'bundle_version': 1, 'kind': 'bsp-runtime', 'schema_version': int(schema), 'database': {'path': 'dashboard.db', 'sha256': _hash(database), 'bytes': database.stat().st_size}, 'artifacts': sorted(copied, key=lambda item: item['path']), 'automatic_start': False}
    (root / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    verify_backup(root)
    return manifest


def verify_backup(root):
    root = Path(root).resolve()
    try:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        if manifest.get('bundle_version') != 1 or manifest.get('kind') != 'bsp-runtime':
            raise RecoveryError('Unsupported backup manifest.')
        database = root / 'dashboard.db'
        expected = manifest['database']
        if expected['path'] != 'dashboard.db' or _hash(database) != expected['sha256'] or database.stat().st_size != expected['bytes']:
            raise RecoveryError('Database hash or size mismatch.')
        schema = _database_check(database)
        references = _references(database)
        entries = {item['path']: item for item in manifest['artifacts']}
        if len(entries) != len(manifest['artifacts']) or set(entries) != set(references):
            raise RecoveryError('Backup artifact references do not match database references.')
        artifact_root = root / 'artifacts'
        for path, entry in entries.items():
            file = (artifact_root / path).resolve()
            if not file.is_relative_to(artifact_root) or not file.is_file() or _hash(file) != entry['sha256'] or file.stat().st_size != entry['bytes']:
                raise RecoveryError('Backup artifact is missing or tampered: ' + path)
            expected_ref = references[path]
            if expected_ref['sha256'] and expected_ref['sha256'] != entry['sha256'] or expected_ref['bytes'] is not None and expected_ref['bytes'] != entry['bytes']:
                raise RecoveryError('Backup artifact differs from database evidence: ' + path)
        return {'valid': True, 'status': 'VERIFIED', 'schema_version': int(schema), 'artifact_count': len(entries), 'database_sha256': expected['sha256'], 'automatic_start': False}
    except (OSError, KeyError, TypeError, sqlite3.Error, json.JSONDecodeError) as exc:
        raise RecoveryError('Backup verification failed: ' + type(exc).__name__) from exc


def restore_runtime(root, empty_destination):
    root = Path(root).resolve()
    verification = verify_backup(root)
    destination = _fresh_destination(empty_destination, [root])
    shutil.copyfile(root / 'dashboard.db', destination / 'dashboard.db')
    if (root / 'artifacts').exists():
        shutil.copytree(root / 'artifacts', destination / 'artifacts')
    shutil.copyfile(root / 'manifest.json', destination / 'manifest.json')
    restored = verify_backup(destination)
    return {'status': 'RESTORED', 'destination': str(destination), 'verification': restored, 'automatic_start': False, 'leases_preserved': True, 'database_sha256': verification['database_sha256']}
