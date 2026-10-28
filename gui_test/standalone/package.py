"""Build an allowlisted GUI Test ZIP, optionally with the legacy Dashboard patch."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ['backend/api/main.py', 'backend/domain/engine.py', 'backend/worker/main.py',
         'apps/web/src/main.tsx', 'apps/web/package.json', 'apps/web/tsconfig.json',
         'apps/web/vite.config.ts', 'pyproject.toml']
SOURCE_DIRS = {'core', 'adapters', 'api', 'standalone', 'demo', 'web', 'config', 'static', 'tests'}
SOURCE_FILES = {'__init__.py', 'runtime.py', 'pyproject.toml', 'requirements.lock', 'README.md', 'VALIDATION.md'}
SUFFIXES = {'.py', '.md', '.toml', '.json', '.ps1', '.cmd', '.ts', '.tsx', '.css', '.html', '.js', '.lock'}


def package_files(package):
    """Exclude caches, local settings, dependencies and arbitrary runtime folders."""
    names = {}
    for path in package.rglob('*'):
        rel = path.relative_to(package)
        if not path.is_file() or any((package.joinpath(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts) + 1)):
            continue
        if len(rel.parts) == 1:
            if rel.name not in SOURCE_FILES:
                continue
        elif rel.parts[0] not in SOURCE_DIRS:
            continue
        if any(part.startswith('.') or part in {'__pycache__', 'node_modules', 'build', 'dist'} or part.endswith('.egg-info') for part in rel.parts):
            continue
        if path.suffix not in SUFFIXES or path.name.endswith('.local.json'):
            continue
        if rel.parts[0] == 'config' and not path.name.endswith('.example.json'):
            continue
        names['gui_test/' + rel.as_posix()] = path.read_bytes()
    return names


def build_archive(package, output, *, base=None, standalone=False, wheelhouse=None, wheels=None):
    if standalone == bool(base):
        raise ValueError('Choose exactly one of --standalone or --base')
    if not (package / 'static/index.html').is_file():
        raise ValueError('Build standalone UI before packaging: cd gui_test/web && npm ci && npm run build')
    names = package_files(package)
    if base:
        names['dashboard-integration.patch'] = subprocess.check_output(
            ['git', 'diff', '--binary', base, '--', *HOOKS], cwd=package.parent)
    names['INSTALL.md'] = (package / 'README.md').read_bytes()
    for folder, label in [(wheelhouse, 'wheelhouse'), (wheels, 'wheels')]:
        if folder is not None:
            found = sorted(Path(folder).glob('*.whl'))
            if not found or any(w.is_symlink() or not w.is_file() for w in found):
                raise ValueError(f'{label} must contain regular .whl files: {folder}')
            for wheel in found:
                names[label + '/' + wheel.name] = wheel.read_bytes()
    manifest = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(names.items())}
    names['SHA256SUMS.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Replace the previous artifact only after the new ZIP is completely written.
    temporary = output.with_suffix(output.suffix + '.tmp')
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


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--base', help='Legacy company bundle: include Dashboard integration patch against this Git ref')
    mode.add_argument('--standalone', action='store_true', help='GUI Test only; no Git or Dashboard source required')
    parser.add_argument('--wheelhouse')
    parser.add_argument('--wheels')
    parser.add_argument('--output', default='.local-reports/gui-test-company.zip')
    args = parser.parse_args()
    try:
        result = build_archive(ROOT / 'gui_test', args.output, base=args.base,
                               standalone=args.standalone, wheelhouse=args.wheelhouse, wheels=args.wheels)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
