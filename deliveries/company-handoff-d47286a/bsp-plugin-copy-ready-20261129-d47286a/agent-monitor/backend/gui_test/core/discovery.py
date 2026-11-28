"""Read-only folder/Git discovery. No imports of test code, checkout, or shell."""
from collections import Counter
import os
from pathlib import Path, PurePosixPath
import subprocess
from .models import TestError, digest, DEFAULT_TC_TIMEOUT_SECONDS
from .module_selection import valid_memberships


def classify(path):
    return 'Dual' if any('dual' in p.casefold() for p in PurePosixPath(path).parts[:-1]) else 'Single'


def script_paths(root, *, include_linux_shell=False):
    for directory, folders, names in os.walk(root, followlinks=False):
        folders[:] = [name for name in folders if not name.startswith('.') and name != '__pycache__']
        for name in names:
            shell_tc = include_linux_shell and name.endswith('.sh') and 'linux' in Path(directory).relative_to(root).parts
            if name.startswith('.') or not (name.endswith('.py') or shell_tc):
                continue
            file = Path(directory) / name
            if not file.is_symlink() and file.is_file() and file.resolve().is_relative_to(root):
                yield file.relative_to(root).as_posix()


def discover(root, metadata=None, revision=None, *, include_linux_shell=False):
    root = Path(root).resolve()
    metadata = metadata or {}
    files = {}
    if revision:
        def git(*args):
            return subprocess.check_output(['git', '-C', str(root), *args], timeout=15).decode('utf-8')
        if revision.startswith('-'):
            raise TestError('Invalid revision', status=422)
        commit = git('rev-parse', '--verify', revision + '^{commit}').strip()
        for path in git('ls-tree', '-r', '--name-only', commit).splitlines():
            if path.endswith('.py') and not any(p.startswith('.') for p in PurePosixPath(path).parts):
                files[path] = git('show', f'{commit}:{path}')
    else:
        for path in sorted(script_paths(root, include_linux_shell=include_linux_shell)):
            files[path] = (root / path).read_text(encoding='utf-8')
        commit = 'content-' + digest(files)
    return discover_contents(files, metadata, commit)


def discover_contents(files, metadata=None, revision=None):
    """Catalog already acquired UTF-8 script text without importing any script."""
    metadata = metadata or {}
    commit = revision or 'content-' + digest(files)
    tests = []
    for path, content in files.items():
        if PurePosixPath(path).name == '__init__.py':
            continue
        meta = metadata.get(path, {})
        kind = classify(path)
        reason = 'Folder/metadata connection type conflict' if meta.get('kind', kind) != kind else ''
        timeout = meta.get('timeout', DEFAULT_TC_TIMEOUT_SECONDS)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 86400:
            reason = 'Explicit valid TC timeout is required'
        if 'modules' in meta and not valid_memberships(meta['modules']):
            reason = 'Explicit valid module membership metadata is required'
        tests.append({'id': meta.get('id', path), 'path': path, 'name': PurePosixPath(path).stem,
                      'module': str(PurePosixPath(path).parent), 'kind': kind,
                      'timeout': timeout, 'timeout_explicit': 'timeout' in meta, 'after': meta.get('after', []),
                      'parser': meta.get('parser', {}), 'content_hash': digest(content), 'disabled_reason': reason,
                      **({'modules': meta['modules']} if 'modules' in meta else {})})
    ids = Counter(t['id'] for t in tests)
    for test in tests:
        if ids[test['id']] > 1:
            test['disabled_reason'] = 'Duplicate TC identity'
    return {'revision': commit, 'metadata_revision': digest(metadata), 'tests': sorted(tests, key=lambda t: (t['module'], t['name']))}


def select(catalog, ids):
    if len(ids) != len(set(ids)):
        raise TestError('Duplicate TC selection', status=422)
    available = {t['id']: t for t in catalog['tests']}
    if not ids or any(i not in available for i in ids):
        raise TestError('Missing TC: refresh and explicitly update the suite', status=422)
    tests = [available[i] for i in ids]
    for index, test in enumerate(tests):
        if test['disabled_reason']:
            raise TestError(test['disabled_reason'], status=422)
        if any(dep not in ids[:index] for dep in test['after']):
            raise TestError('Required predecessor/order missing for ' + test['id'], status=422)
    return tests
