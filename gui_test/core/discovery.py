"""Read-only folder/Git discovery. No imports of test code, checkout, or shell."""
from pathlib import Path, PurePosixPath
import subprocess
from gui_test.core.models import TestError, digest


def classify(path):
    return 'Dual' if any('dual' in p.casefold() for p in PurePosixPath(path).parts[:-1]) else 'Single'


def discover(root, metadata=None, revision=None):
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
        for file in sorted(root.rglob('*.py')):
            if file.is_symlink() or not file.resolve().is_relative_to(root):
                continue
            path = file.relative_to(root).as_posix()
            if not any(p.startswith('.') or p == '__pycache__' for p in PurePosixPath(path).parts):
                files[path] = file.read_text(encoding='utf-8')
        commit = 'content-' + digest(files)
    tests = []
    for path, content in files.items():
        if PurePosixPath(path).name == '__init__.py':
            continue
        meta = metadata.get(path, {})
        kind = classify(path)
        reason = 'Folder/metadata connection type conflict' if meta.get('kind', kind) != kind else ''
        timeout = meta.get('timeout', 10)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= 86400:
            reason = 'Explicit valid TC timeout is required'
        tests.append({'id': meta.get('id', path), 'path': path, 'name': PurePosixPath(path).stem,
                      'module': str(PurePosixPath(path).parent), 'kind': kind,
                      'timeout': timeout, 'after': meta.get('after', []),
                      'parser': meta.get('parser', {}), 'content_hash': digest(content), 'disabled_reason': reason})
    ids = [t['id'] for t in tests]
    for test in tests:
        if ids.count(test['id']) > 1:
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
