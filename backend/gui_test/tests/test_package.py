"""Standalone packaging must not need or accidentally ship a Dashboard/runtime."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile

import pytest
spec = importlib.util.spec_from_file_location(
    'gui_test_packaging', Path(__file__).resolve().parents[3] / 'apps/gui-test/package.py')
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


@pytest.fixture
def source(tmp_path):
    module = tmp_path / 'source with spaces'
    files = {
        'apps/gui-test/README.md': '# Install', 'apps/gui-test/static/index.html': '<html>Mock</html>',
        'apps/gui-test/static/assets/app.js': 'console.log("demo")', 'backend/gui_test/core/manager.py': '# source',
        'apps/gui-test/package-lock.json': '{}', 'apps/gui-test/vite.config.ts': 'export default {}',
        'apps/gui-test/build.cmd': '@echo off', 'apps/gui-test/build.ps1': '# build',
        'apps/gui-test/config/production.example.json': '{"token":null}',
        'apps/gui-test/config/secrets.json': '{"token":"must not ship"}',
        'apps/gui-test/config/production.local.json': '{"token":"must not ship"}',
        'apps/gui-test/runtime/private.json': '{}', 'apps/gui-test/.build/venv/private.py': '# secret',
        'apps/gui-test/node_modules/dependency/index.js': '// dependency',
        'backend/gui_test/core/__pycache__/x.py': '# stale', 'apps/gui-test/dist/previous.json': '{}',
        'runs.db': 'private', '.env': 'private',
    }
    for name, content in files.items():
        target = module / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    return module


def test_standalone_archive_without_git_or_dashboard(source, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Standalone package must not call Git')
    monkeypatch.setattr(packaging.subprocess, 'check_output', forbidden)
    wheels = tmp_path / 'wheels'; wheels.mkdir()
    (wheels / 'bsp_gui_test-0.1.0-py3-none-any.whl').write_bytes(b'wheel fixture')
    output = tmp_path / 'output with spaces' / 'gui-test.zip'
    result = packaging.build_archive(source, output, standalone=True, wheels=wheels)
    assert result['mode'] == 'standalone'
    assert result['sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as archive:
        files = set(archive.namelist())
        assert 'dashboard-integration.patch' not in files
        assert 'apps/gui-test/vite.config.ts' in files
        assert 'apps/gui-test/package-lock.json' in files
        assert 'apps/gui-test/build.cmd' in files
        assert 'apps/gui-test/config/production.example.json' in files
        assert not any(p.startswith(('backend/api/', 'backend/domain/')) or 'secrets' in p or '.local.json' in p or '/runtime/' in p or 'node_modules' in p or '/.build/' in p or '/dist/' in p for p in files)
        hashes = json.loads(archive.read('SHA256SUMS.json'))
        assert set(hashes) == files - {'SHA256SUMS.json'}
        for name, checksum in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum


def test_legacy_integration_archive_keeps_patch(source, tmp_path, monkeypatch):
    calls = []
    def fake_git(argv, **kwargs):
        calls.append((argv, kwargs))
        return b'diff --git a/backend/api/main.py b/backend/api/main.py\n'
    monkeypatch.setattr(packaging.subprocess, 'check_output', fake_git)
    output = tmp_path / 'legacy.zip'
    packaging.build_archive(source, output, base='reviewed-base')
    assert calls[0][0][:5] == ['git', 'diff', '--binary', 'reviewed-base', '--']
    assert calls[0][1]['cwd'] == source
    with zipfile.ZipFile(output) as archive:
        assert archive.read('dashboard-integration.patch').startswith(b'diff --git')


def test_package_rejects_missing_ui_and_empty_wheelhouse(source, tmp_path):
    output = tmp_path / 'bundle.zip'
    output.write_bytes(b'old successful artifact')
    with pytest.raises(ValueError, match='wheelhouse'):
        packaging.build_archive(source, output, standalone=True, wheelhouse=tmp_path / 'empty')
    assert output.read_bytes() == b'old successful artifact'
    (source / 'apps/gui-test/static/index.html').unlink()
    with pytest.raises(ValueError, match='Build standalone UI'):
        packaging.build_archive(source, output, standalone=True)
    assert output.read_bytes() == b'old successful artifact'


def test_integration_patch_contains_dashboard_import_dependencies(source, tmp_path):
    """The actual emitted patch must carry newly imported Dashboard modules."""
    repo = source
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=repo)
    git('init', '--quiet')
    git('-c', 'user.name=Package Test', '-c', 'user.email=package@example.invalid',
        'commit', '--quiet', '--allow-empty', '-m', 'Synthetic integration base')
    base = git('rev-parse', 'HEAD').decode().strip()
    changed = {
        'apps/web/src/main.tsx': "import './audit.css';\nimport {Bar} from './ProgressBar';\n",
        'apps/web/src/audit.css': '.audit-sr-only { position: absolute; }\n',
        'apps/web/src/ProgressBar.tsx': 'export function Bar() { return null; }\n',
    }
    for name, content in changed.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    git('add', '--', *changed)
    output = tmp_path / 'integration-with-dependencies.zip'
    packaging.build_archive(source, output, base=base)
    with zipfile.ZipFile(output) as archive:
        patch = archive.read('dashboard-integration.patch').decode('utf-8')
    for name, content in changed.items():
        assert f'diff --git a/{name} b/{name}' in patch
        assert all('+' + line in patch for line in content.splitlines())


@pytest.mark.parametrize('options', [{}, {'standalone': True, 'base': 'main'}])
def test_package_requires_one_mode(source, tmp_path, options):
    with pytest.raises(ValueError, match='exactly one'):
        packaging.build_archive(source, tmp_path / 'bundle.zip', **options)
