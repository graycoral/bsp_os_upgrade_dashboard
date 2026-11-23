"""Disk-backed, immutable installer transport. TC snapshot limits remain separate."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import zipfile

from ..core.models import TestError, digest
from .source_snapshots import safe_name, validate_paths

MAX_TOTAL = 64 * 1024**3
MANIFEST = '.installer-manifest.json'
MAX_MANIFEST = 4 * 1024**2
MAX_FILES = 10000
RESERVE = 1024**3


def regular(path, directory=False):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400 or
            not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise TestError('Installer links and special files are forbidden', 'IMAGE_PATH', 422)
    return info


def file_hash(path):
    regular(path)
    result = hashlib.sha256()
    with path.open('rb') as stream:
        regular(path)
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def validate_manifest(value, identity=None, max_total=MAX_TOTAL):
    if not isinstance(value, dict) or set(value) != {'format', 'batch', 'files', 'snapshot_id'}:
        raise TestError('Invalid installer manifest', 'IMAGE_MANIFEST', 422)
    if value['format'] != 'installer_snapshot_v1' or not isinstance(value['files'], dict) or not 2 <= len(value['files']) <= MAX_FILES:
        raise TestError('Invalid installer manifest', 'IMAGE_MANIFEST', 422)
    validate_paths(value['files'])
    total = 0
    for name, row in value['files'].items():
        safe_name(name)
        if name.casefold() == MANIFEST.casefold() or not isinstance(row, dict) or set(row) != {'size', 'sha256'}:
            raise TestError('Invalid installer file', 'IMAGE_MANIFEST', 422)
        if type(row['size']) is not int or row['size'] < 0 or not isinstance(row['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', row['sha256']):
            raise TestError('Invalid installer size/hash', 'IMAGE_MANIFEST', 422)
        total += row['size']
    if total > max_total:
        raise TestError('Installer exceeds configured byte limit', 'IMAGE_SPACE', 413)
    if value['batch'] not in value['files'] or Path(value['batch']).suffix.lower() != '.bat':
        raise TestError('Installer BAT is missing', 'IMAGE_MANIFEST', 422)
    base = {key: value[key] for key in ('format', 'batch', 'files')}
    if value['snapshot_id'] != digest(base) or (identity is not None and identity != value['snapshot_id']):
        raise TestError('Installer manifest hash mismatch', 'IMAGE_CHANGED', 422)
    if len(json.dumps(value).encode()) > MAX_MANIFEST:
        raise TestError('Installer manifest too large', 'IMAGE_MANIFEST', 413)
    return value


def inventory(root):
    regular(root, directory=True)
    files = {}
    for directory, folders, names in os.walk(root, followlinks=False):
        for name in folders:
            regular(Path(directory) / name, directory=True)
        for name in names:
            path = Path(directory) / name
            info = regular(path)
            relative = path.relative_to(root).as_posix()
            safe_name(relative)
            if relative.casefold() == MANIFEST.casefold():
                raise TestError('Reserved installer filename', 'IMAGE_PATH', 422)
            files[relative] = (info.st_size, info.st_mtime_ns, info.st_ino)
            if len(files) > MAX_FILES:
                raise TestError('Too many installer files', 'IMAGE_MANIFEST', 413)
    validate_paths(files)
    return files


def freeze_installer(installer_path, allowed_roots, destination, max_total=MAX_TOTAL):
    original = Path(installer_path)
    if not original.is_absolute():
        raise TestError('Installer must be an absolute Linux path', 'IMAGE_PATH', 422)
    roots = [Path(root).resolve(strict=True) for root in allowed_roots]
    # Inspect the original components before resolve, including links to an allowed root.
    for ancestor in [original, *original.parents]:
        if ancestor.exists() and (ancestor.is_symlink() or getattr(ancestor.lstat(), 'st_file_attributes', 0) & 0x400):
            raise TestError('Installer links are forbidden', 'IMAGE_PATH', 422)
    path = original.resolve(strict=True)
    if not any(path.is_relative_to(root) for root in roots) or path.suffix.lower() != '.bat':
        raise TestError('Installer is outside allowed roots', 'IMAGE_PATH', 422)
    root = path.parent
    before = inventory(root)
    total = sum(row[0] for row in before.values())
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if total > max_total or shutil.disk_usage(destination).free < total + RESERVE:
        raise TestError('Insufficient installer staging space', 'IMAGE_SPACE', 413)
    with tempfile.TemporaryDirectory(dir=destination, prefix='freeze-') as temp:
        target = Path(temp) / 'files'; target.mkdir()
        rows = {}
        for name, expected in sorted(before.items()):
            src, out = root / name, target / name
            out.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256(); size = 0
            with src.open('rb') as inp, out.open('xb') as stream:
                for chunk in iter(lambda: inp.read(1024 * 1024), b''):
                    size += len(chunk)
                    if size > expected[0] or shutil.disk_usage(destination).free < RESERVE:
                        raise TestError('Installer changed or staging space exhausted', 'SOURCE_CHANGED')
                    h.update(chunk); stream.write(chunk)
            if size != expected[0]:
                raise TestError('Installer changed during preparation', 'SOURCE_CHANGED')
            rows[name] = {'size': size, 'sha256': h.hexdigest()}
        if (inventory(root) != before or any(file_hash(root / name) != row['sha256'] for name, row in rows.items()) or
                inventory(root) != before):
            raise TestError('Installer changed during preparation', 'SOURCE_CHANGED')
        base = {'format': 'installer_snapshot_v1', 'batch': path.name, 'files': rows}
        value = validate_manifest(base | {'snapshot_id': digest(base)}, max_total=max_total)
        (target / MANIFEST).write_text(json.dumps(value, sort_keys=True), encoding='utf-8')
        final = destination / value['snapshot_id']
        publish(target, final, value, max_total)
        return value


def load_manifest(directory, identity=None, max_total=MAX_TOTAL, verify=True):
    directory = Path(directory)
    regular(directory, directory=True)
    path = directory / MANIFEST
    if regular(path).st_size > MAX_MANIFEST:
        raise TestError('Installer manifest too large', 'IMAGE_MANIFEST')
    try:
        value = validate_manifest(json.loads(path.read_text(encoding='utf-8')), identity, max_total)
    except (ValueError, OSError) as exc:
        raise TestError('Installer manifest unreadable', 'IMAGE_MANIFEST') from exc
    if verify:
        for name, row in value['files'].items():
            current = directory
            for part in safe_name(name).parts[:-1]:
                current /= part; regular(current, directory=True)
            path = directory / name
            if regular(path).st_size != row['size'] or file_hash(path) != row['sha256']:
                raise TestError('Published installer bytes changed', 'IMAGE_CHANGED')
        actual = set()
        for path in directory.rglob('*'):
            info = path.lstat()
            regular(path, directory=stat.S_ISDIR(info.st_mode))
            if stat.S_ISREG(info.st_mode): actual.add(path.relative_to(directory).as_posix())
        if actual != set(value['files']) | {MANIFEST}:
            raise TestError('Unexpected installer files', 'IMAGE_CHANGED')
    return value


def publish(staged, final, value, max_total=MAX_TOTAL):
    if final.exists():
        if load_manifest(final, value['snapshot_id'], max_total) != value:
            raise TestError('Conflicting installer publication', 'IMAGE_CHANGED')
        return
    try:
        os.rename(staged, final)
    except OSError:
        if not final.is_dir(): raise
    if load_manifest(final, value['snapshot_id'], max_total) != value:
        raise TestError('Installer publication verification failed', 'IMAGE_CHANGED')


def create_archive(directory, descriptor):
    directory = Path(directory)
    value = load_manifest(directory, descriptor['snapshot_id'])
    if value != descriptor:
        raise TestError('Installer descriptor changed', 'IMAGE_CHANGED')
    archive = tempfile.TemporaryFile()
    try:
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:
            bundle.write(directory / MANIFEST, MANIFEST)
            for name in value['files']:
                bundle.write(directory / name, name)
        archive.seek(0)
        return archive
    except BaseException:
        archive.close(); raise


def receive_archive(path, identity, destination, max_total=MAX_TOTAL):
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(path) as bundle, tempfile.TemporaryDirectory(dir=destination, prefix='unpack-') as temp:
            members = bundle.infolist()
            names = [m.filename for m in members]
            if len(members) > MAX_FILES + 1 or len(set(n.casefold() for n in names)) != len(names) or names.count(MANIFEST) != 1:
                raise TestError('Duplicate or missing installer entries', 'IMAGE_MANIFEST', 422)
            for member in members:
                safe_name(member.filename)
                mode = member.external_attr >> 16
                if member.compress_type != zipfile.ZIP_STORED or member.flag_bits & 1 or member.is_dir() or stat.S_IFMT(mode) not in {0, stat.S_IFREG} or member.external_attr & 0x400:
                    raise TestError('Unsafe installer archive member', 'IMAGE_PATH', 422)
            entry = bundle.getinfo(MANIFEST)
            if entry.file_size > MAX_MANIFEST:
                raise TestError('Installer manifest too large', 'IMAGE_MANIFEST', 413)
            value = validate_manifest(json.loads(bundle.read(MANIFEST)), identity, max_total)
            if set(names) != set(value['files']) | {MANIFEST}:
                raise TestError('Unexpected installer entries', 'IMAGE_MANIFEST', 422)
            total = sum(row['size'] for row in value['files'].values())
            if shutil.disk_usage(destination).free < 2 * total + RESERVE:
                raise TestError('Insufficient Windows installer capacity', 'IMAGE_SPACE', 413)
            target = Path(temp) / 'files'; target.mkdir()
            for name, row in value['files'].items():
                if bundle.getinfo(name).file_size != row['size']:
                    raise TestError('Installer size mismatch', 'IMAGE_CHANGED', 422)
                output = target / name; output.parent.mkdir(parents=True, exist_ok=True)
                h = hashlib.sha256(); size = 0
                with bundle.open(name) as inp, output.open('xb') as out:
                    for chunk in iter(lambda: inp.read(1024 * 1024), b''):
                        size += len(chunk)
                        if size > row['size'] or shutil.disk_usage(destination).free < RESERVE:
                            raise TestError('Installer stream exceeds space or size', 'IMAGE_SPACE', 413)
                        h.update(chunk); out.write(chunk)
                if size != row['size'] or h.hexdigest() != row['sha256']:
                    raise TestError('Installer file hash mismatch', 'IMAGE_CHANGED', 422)
            (target / MANIFEST).write_text(json.dumps(value, sort_keys=True), encoding='utf-8')
            publish(target, destination / identity, value, max_total)
            return {'snapshot_id': identity, 'state': 'READY', 'manifest': value}
    except (zipfile.BadZipFile, ValueError, KeyError, OSError) as exc:
        raise TestError('Invalid installer archive', 'IMAGE_MANIFEST', 422) from exc
