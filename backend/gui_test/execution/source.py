"""Freeze shared files on the Windows host before executing any TC."""
import hashlib
import os
import stat
from pathlib import Path
from ..core.discovery import discover
from ..core.models import TestError, digest

EXCLUDED = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', '.runtime'}


def excluded_source_path(relative):
    """Apply the same exclusions before validating folder or Git entry types."""
    name = relative.as_posix() if isinstance(relative, Path) else str(relative)
    return any(part.startswith('.') or part in EXCLUDED for part in name.replace('\\', '/').split('/'))


def source_path(value):
    """Use Win32 extended paths for private snapshot I/O, including UNC roots.

    Renaming a short staging tree can make a child exceed MAX_PATH even when
    the rename succeeds. Prefix the whole absolute tree before creating or
    reading children rather than relying on the machine's long-path policy.
    """
    path = Path(os.path.abspath(value))
    if os.name != 'nt':
        return path
    text = str(path)
    if text.startswith('\\\\?\\'):
        return path
    if text.startswith('\\\\'):
        return Path('\\\\?\\UNC\\' + text[2:])
    return Path('\\\\?\\' + text)


def read_source(root):
    root = source_path(root).resolve(strict=True)
    files, total = {}, 0
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if excluded_source_path(relative):
            continue
        if path.is_symlink() or (getattr(path.lstat(), 'st_file_attributes', 0) & 0x400) or not path.resolve().is_relative_to(root):
            raise TestError('Source links outside the TC snapshot are not supported', 'SOURCE_UNSAFE')
        if not path.is_file(): continue
        if path.stat().st_size > 16 * 1024 * 1024:
            raise TestError('A TC source file exceeds 16 MiB', 'SOURCE_LIMIT')
        # Bound the actual read too: a file growing between stat/read must not
        # defeat the memory limit, and Unix links swapped in after stat fail closed.
        handle = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(handle, 'rb') as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise TestError('Only regular source files are supported', 'SOURCE_UNSAFE')
            data = source.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024:
            raise TestError('A TC source file exceeds 16 MiB', 'SOURCE_LIMIT')
        total += len(data)
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
    destination = source_path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    catalog = discover(destination, metadata)
    catalog.update(revision=version, branch='shared')
    return catalog
