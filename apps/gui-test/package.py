"""Export the independent three-root source bundle or stage an installed wheel.

Only backend/gui_test is canonical Python source. The gui_test wheel namespace
is synthesized into a fresh staging directory, never maintained as a second tree.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ['backend/api/main.py', 'backend/domain/engine.py', 'backend/worker/main.py',
         'backend/worker/hardware.py', 'backend/services/module_test_selection.py',
         'apps/web/src/main.tsx', 'apps/web/src/ProgressBar.tsx', 'apps/web/src/audit.css',
         'apps/web/package.json', 'apps/web/tsconfig.json',
         'apps/web/vite.config.ts', 'pyproject.toml']
PYTHON_DIRS = {'core', 'adapters', 'api', 'standalone', 'demo', 'execution', 'tests'}
APP_FILES = {'launch.py', 'package.py', 'build.cmd', 'build.ps1', 'start.ps1',
             'package.json', 'package-lock.json', 'vite.config.ts', 'tsconfig.json',
             'index.html', 'pyproject.toml', 'requirements.lock', 'README.md', 'VALIDATION.md'}
IGNORED = {'__pycache__', 'node_modules', 'build', 'dist', 'runtime', 'logs'}
UI_SUFFIXES = {'.ts', '.tsx', '.css', '.json', '.svg'}


def regular_files(folder):
    """Return regular files without traversing hidden/runtime/symlink trees."""
    if folder.is_symlink() or not folder.is_dir():
        return
    for current, directories, files in os.walk(folder, followlinks=False):
        directories[:] = sorted(name for name in directories
                                 if not name.startswith('.') and name not in IGNORED
                                 and not name.endswith('.egg-info')
                                 and not (Path(current) / name).is_symlink())
        for name in sorted(files):
            path = Path(current) / name
            if (not name.startswith('.') and not name.endswith(('.local.json', '.db', '.db-wal', '.db-shm'))
                    and not path.is_symlink() and path.is_file()):
                yield path, path.relative_to(folder)


def package_files(source_root):
    """Read bounded app/backend/shared-UI roots; no Dashboard or Git needed."""
    source_root = Path(source_root).resolve()
    names = {'backend/__init__.py': b'"""Portable GUI Test source namespace."""\n'}
    backend = source_root / 'backend/gui_test'
    app = source_root / 'apps/gui-test'
    ui = source_root / 'packages/gui-test-ui/src'
    for folder in (backend, app, ui):
        relative = folder.relative_to(source_root)
        if any(source_root.joinpath(*relative.parts[:i]).is_symlink()
               for i in range(1, len(relative.parts) + 1)):
            raise ValueError(f'Source root must not be a symlink: {folder}')
    for path, rel in regular_files(backend):
        if (len(rel.parts) == 1 and rel.name in {'__init__.py', 'runtime.py'}
                or len(rel.parts) > 1 and rel.parts[0] in PYTHON_DIRS) and path.suffix == '.py':
            names['backend/gui_test/' + rel.as_posix()] = path.read_bytes()
    for path, rel in regular_files(app):
        allowed = (len(rel.parts) == 1 and rel.name in APP_FILES
                   or len(rel.parts) > 1 and rel.parts[0] == 'src' and path.suffix in UI_SUFFIXES
                   or len(rel.parts) > 1 and rel.parts[0] == 'config' and path.name.endswith('.example.json')
                   or len(rel.parts) > 1 and rel.parts[0] == 'static')
        if allowed:
            names['apps/gui-test/' + rel.as_posix()] = path.read_bytes()
    for path, rel in regular_files(ui):
        if path.suffix in UI_SUFFIXES:
            names['packages/gui-test-ui/src/' + rel.as_posix()] = path.read_bytes()
    return names


def stage_wheel(source_root, destination):
    """Stage canonical code/resources into the legacy installed gui_test namespace."""
    names = package_files(source_root)
    if 'apps/gui-test/static/index.html' not in names:
        raise ValueError('Build standalone UI before staging: npm ci --prefix apps/gui-test && npm run build --prefix apps/gui-test')
    staged = {}
    for name, content in names.items():
        if name.startswith('backend/gui_test/'):
            relative = name.removeprefix('backend/gui_test/')
            if relative.split('/')[0] != 'tests':
                staged['gui_test/' + relative] = content
        elif name.startswith(('apps/gui-test/static/', 'apps/gui-test/config/')):
            staged['gui_test/' + name.removeprefix('apps/gui-test/')] = content
    for name in ('pyproject.toml', 'requirements.lock', 'README.md'):
        key = 'apps/gui-test/' + name
        if key not in names:
            raise ValueError(f'Missing wheel input: {key}')
        staged[name if name != 'README.md' else 'gui_test/README.md'] = names[key]
    staged['gui_test/requirements.lock'] = names['apps/gui-test/requirements.lock']
    destination = Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError('Wheel staging destination must be a fresh or empty directory')
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in staged.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return destination


def build_archive(source_root, output, *, base=None, standalone=False, wheelhouse=None, wheels=None):
    if standalone == bool(base):
        raise ValueError('Choose exactly one of --standalone or --base')
    source_root = Path(source_root).resolve()
    names = package_files(source_root)
    if 'apps/gui-test/static/index.html' not in names:
        raise ValueError('Build standalone UI before packaging: npm ci --prefix apps/gui-test && npm run build --prefix apps/gui-test')
    if base:
        names['dashboard-integration.patch'] = subprocess.check_output(
            ['git', 'diff', '--binary', base, '--', *HOOKS], cwd=source_root)
    names['INSTALL.md'] = names['apps/gui-test/README.md']
    for folder, label in [(wheelhouse, 'wheelhouse'), (wheels, 'wheels')]:
        if folder is not None:
            folder = Path(folder)
            found = sorted(folder.glob('*.whl'))
            if folder.is_symlink() or not found or any(w.is_symlink() or not w.is_file() for w in found):
                raise ValueError(f'{label} must contain regular .whl files: {folder}')
            for wheel in found:
                names[label + '/' + wheel.name] = wheel.read_bytes()
    manifest = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(names.items())}
    names['SHA256SUMS.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=output.name + '.', suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(names.items()):
                archive.writestr(name, content)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {'file': str(output), 'files': len(names), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'mode': 'standalone' if standalone else 'dashboard-integration'}


def main(argv=None):
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--base', help='Include the allowlisted Dashboard integration patch against this Git ref')
    mode.add_argument('--standalone', action='store_true', help='Independent source bundle; never calls Git')
    mode.add_argument('--stage-wheel', type=Path, help='Stage an installed wheel namespace into this fresh directory')
    parser.add_argument('--wheelhouse')
    parser.add_argument('--wheels')
    parser.add_argument('--output', default='.local-reports/gui-test-company.zip')
    args = parser.parse_args(argv)
    try:
        if args.stage_wheel is not None:
            result = {'stage': str(stage_wheel(ROOT, args.stage_wheel))}
        else:
            result = build_archive(ROOT, args.output, base=args.base,
                                   standalone=args.standalone, wheelhouse=args.wheelhouse, wheels=args.wheels)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
