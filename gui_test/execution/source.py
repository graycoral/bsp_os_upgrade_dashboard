"""Freeze shared files on the Windows host before executing any TC."""
import hashlib
from pathlib import Path
from gui_test.core.discovery import discover
from gui_test.core.models import TestError, digest

EXCLUDED = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', '.runtime'}


def read_source(root):
    root = Path(root).resolve(strict=True)
    files, total = {}, 0
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if any(part in EXCLUDED or part.startswith('.') for part in relative.parts):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise TestError('Source links outside the TC snapshot are not supported', 'SOURCE_UNSAFE')
        if not path.is_file(): continue
        if path.stat().st_size > 16 * 1024 * 1024:
            raise TestError('A TC source file exceeds 16 MiB', 'SOURCE_LIMIT')
        data = path.read_bytes(); total += len(data)
        if len(files) >= 10000 or total > 128 * 1024 * 1024:
            raise TestError('TC source snapshot exceeds 10000 files / 128 MiB', 'SOURCE_LIMIT')
        files[relative.as_posix()] = data
    return files


def revision(files, metadata):
    return 'shared-' + digest({'files': {p: hashlib.sha256(b).hexdigest() for p, b in files.items()}, 'metadata': metadata})


def snapshot(root, destination, metadata, expected=None):
    files = read_source(root)
    version = revision(files, metadata)
    if expected and expected != version:
        raise TestError('Shared TC files changed; refresh and repeat Preflight', 'SOURCE_CHANGED')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    catalog = discover(destination, metadata)
    catalog.update(revision=version, branch='shared')
    return catalog
