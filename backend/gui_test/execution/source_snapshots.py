"""Content-addressed source transport. Shared by the Linux sender and Windows host."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile

from ..core.models import TestError, digest
from .source import read_source, source_path

MAX_ARCHIVE = 160 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_FILE = 16 * 1024 * 1024
MANIFEST = '.source-manifest.json'


def safe_name(name):
    if not isinstance(name, str) or not name or len(name) > 1024 or '\\' in name or ':' in name or '\x00' in name:
        raise TestError('Unsafe source path', 'SOURCE_UNSAFE', 422)
    parts = name.split('/')
    if any(not p or p in {'.', '..'} or p.endswith((' ', '.')) or
           any(ord(c) < 32 or c in '<>"|?*' for c in p) or
           re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[0-9¹²³]|LPT[0-9¹²³])(?:\..*)?', p) for p in parts):
        raise TestError('Unsafe Windows source path', 'SOURCE_UNSAFE', 422)
    return PurePosixPath(name)


def validate_paths(names):
    # NTFS merges directory names by case too: Foo/a.py and foo/b.py must
    # not become a different tree on Windows than the one cataloged on Linux.
    nodes = {}
    for name in names:
        safe_name(name)
        parts = name.split('/')
        for index in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:index])
            node = (prefix, 'file' if index == len(parts) else 'directory')
            previous = nodes.get(prefix.casefold())
            if previous is not None and previous != node:
                raise TestError('Conflicting Windows source paths', 'SOURCE_UNSAFE', 422)
            nodes[prefix.casefold()] = node


def file_manifest(files):
    if len(files) > 10000 or sum(map(len, files.values())) > MAX_TOTAL:
        raise TestError('Source snapshot limit exceeded', 'SOURCE_LIMIT', 422)
    seen = set()
    rows = {}
    for name, data in sorted(files.items()):
        safe_name(name)
        if name.casefold() == MANIFEST.casefold() or name.casefold() in seen or len(data) > MAX_FILE:
            raise TestError('Duplicate/reserved source path or oversized file', 'SOURCE_UNSAFE', 422)
        seen.add(name.casefold())
        rows[name] = {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    validate_paths(rows)
    return rows


def manifest(files, source, metadata=None):
    value = {'format': 'source_snapshot_v1', 'source': source, 'metadata': metadata or {}, 'files': file_manifest(files)}
    value['source_revision'] = 'source-' + digest(value)
    value['snapshot_id'] = digest(value)
    if len(json.dumps(value, sort_keys=True).encode()) > 4 * 1024 * 1024:
        raise TestError('Source manifest exceeds 4 MiB', 'SOURCE_LIMIT', 422)
    return value


def validate_manifest(value, identity):
    if not isinstance(value, dict) or set(value) != {'format', 'source', 'metadata', 'files', 'source_revision', 'snapshot_id'}:
        raise TestError('Invalid source manifest', 'SOURCE_UNSAFE', 422)
    if value['format'] != 'source_snapshot_v1' or not isinstance(value['source'], dict) or value['metadata'] != {} or not isinstance(value['files'], dict):
        raise TestError('Invalid source manifest', 'SOURCE_UNSAFE', 422)
    base = {k: value[k] for k in ('format', 'source', 'metadata', 'files')}
    if value['source_revision'] != 'source-' + digest(base) or value['snapshot_id'] != identity or digest(base | {'source_revision': value['source_revision']}) != identity:
        raise TestError('Source manifest digest mismatch', 'SOURCE_CHANGED', 422)
    if len(value['files']) > 10000:
        raise TestError('Source file limit exceeded', 'SOURCE_LIMIT', 422)
    total, seen = 0, set()
    for name, row in value['files'].items():
        safe_name(name)
        if name.casefold() == MANIFEST.casefold() or name.casefold() in seen or not isinstance(row, dict) or set(row) != {'size', 'sha256'}:
            raise TestError('Invalid source manifest file', 'SOURCE_UNSAFE', 422)
        seen.add(name.casefold())
        if type(row['size']) is not int or not 0 <= row['size'] <= MAX_FILE or not isinstance(row['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', row['sha256']):
            raise TestError('Invalid source manifest file', 'SOURCE_UNSAFE', 422)
        total += row['size']
    if total > MAX_TOTAL:
        raise TestError('Source snapshot limit exceeded', 'SOURCE_LIMIT', 422)
    validate_paths(value['files'])
    return value


def load_manifest(directory, identity=None):
    try:
        path = source_path(directory) / MANIFEST
        if path.is_symlink() or path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError()
        value = json.loads(path.read_text(encoding='utf-8'))
        return validate_manifest(value, identity or value['snapshot_id'])
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        raise TestError('Source snapshot is missing or invalid', 'SOURCE_CHANGED') from exc


def checked_files(directory, value):
    files = read_source(directory)
    if file_manifest(files) != value['files']:
        raise TestError('Prepared source bytes changed', 'SOURCE_CHANGED')
    return files


def publish(files, value, destination):
    destination = source_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix='prepare-') as temp:
        directory = Path(temp) / 'source'
        directory.mkdir()
        for name, data in files.items():
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (directory / MANIFEST).write_text(json.dumps(value, sort_keys=True), encoding='utf-8')
        try:
            os.rename(directory, destination)
        except OSError:
            if not destination.is_dir() or load_manifest(destination) != value:
                raise TestError('Conflicting prepared snapshot', 'SOURCE_CHANGED')
            checked_files(destination, value)
        # A successful directory rename is not sufficient publication evidence
        # on Windows: verify the final child paths and bytes before acknowledging.
        if load_manifest(destination, value['snapshot_id']) != value:
            raise TestError('Published source manifest mismatch', 'SOURCE_CHANGED')
        checked_files(destination, value)


def create_archive(directory, descriptor):
    value = load_manifest(directory, descriptor['snapshot_id'])
    if value['source_revision'] != descriptor['source_revision']:
        raise TestError('Frozen snapshot revision mismatch', 'SOURCE_CHANGED')
    files = checked_files(directory, value)
    archive = tempfile.TemporaryFile()
    try:
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as bundle:
            bundle.writestr(MANIFEST, json.dumps(value, sort_keys=True))
            for name, data in files.items():
                bundle.writestr(name, data)
        if archive.tell() > MAX_ARCHIVE:
            raise TestError('Source transport limit exceeded', 'SOURCE_LIMIT')
        archive.seek(0)
        return archive
    except BaseException:
        archive.close()
        raise


def receive_archive(path, identity, destination):
    if not re.fullmatch('[a-f0-9]{64}', identity):
        raise TestError('Invalid snapshot ID', status=422)
    try:
        path = source_path(path)
        if path.stat().st_size > MAX_ARCHIVE:
            raise TestError('Source transport limit exceeded', 'SOURCE_LIMIT', 413)
        with zipfile.ZipFile(path) as bundle:
            members = bundle.infolist()
            if len(members) > 10001 or sum(m.file_size for m in members) > MAX_TOTAL + 4 * 1024 * 1024:
                raise TestError('Source transport limit exceeded', 'SOURCE_LIMIT', 413)
            names = [m.filename for m in members]
            if len(set(n.casefold() for n in names)) != len(names) or names.count(MANIFEST) != 1:
                raise TestError('Duplicate/missing source manifest', 'SOURCE_UNSAFE', 422)
            for member in members:
                if member.filename != MANIFEST:
                    safe_name(member.filename)
                mode = member.external_attr >> 16
                if member.compress_type != zipfile.ZIP_STORED or member.flag_bits & 1 or member.is_dir() or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
                    raise TestError('Unsupported source archive member', 'SOURCE_UNSAFE', 422)
                if member.file_size > (4 * 1024 * 1024 if member.filename == MANIFEST else MAX_FILE):
                    raise TestError('Oversized archive member', 'SOURCE_LIMIT', 413)
            value = validate_manifest(json.loads(bundle.read(MANIFEST)), identity)
            if set(names) != set(value['files']) | {MANIFEST}:
                raise TestError('Unexpected source archive members', 'SOURCE_UNSAFE', 422)
            files = {name: bundle.read(name) for name in value['files']}
            if file_manifest(files) != value['files']:
                raise TestError('Source archive bytes mismatch', 'SOURCE_CHANGED', 422)
        publish(files, value, Path(destination) / identity)
        return {'snapshot_id': identity, 'source_revision': value['source_revision']}
    except (OSError, ValueError, KeyError, TypeError, RecursionError, zipfile.BadZipFile, NotImplementedError) as exc:
        raise TestError('Invalid source archive', 'SOURCE_UNSAFE', 422) from exc


def copy_snapshot(prepared, destination, expected_revision):
    value = load_manifest(prepared)
    if value['source_revision'] != expected_revision:
        raise TestError('Prepared snapshot revision mismatch', 'SOURCE_CHANGED')
    files = checked_files(prepared, value)
    destination = source_path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if file_manifest(read_source(destination)) != value['files']:
        raise TestError('Attempt snapshot bytes mismatch', 'SOURCE_CHANGED')
    from ..core.discovery import discover
    return discover(destination, value['metadata']) | {'revision': expected_revision, 'branch': value['source'].get('ref') or 'folder'}
