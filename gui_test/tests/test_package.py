"""Standalone packaging must not need or accidentally ship a Dashboard/runtime."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest
from gui_test.standalone import package as packaging


@pytest.fixture
def source(tmp_path):
    module = tmp_path / 'source with spaces' / 'gui_test'
    files = {
        'README.md': '# Install', 'static/index.html': '<html>Mock</html>',
        'static/assets/app.js': 'console.log("demo")', 'core/manager.py': '# source',
        'web/package-lock.json': '{}', 'web/vite.config.ts': 'export default {}',
        'standalone/build.cmd': '@echo off', 'standalone/build.ps1': '# build',
        'config/production.example.json': '{"token":null}',
        'config/secrets.json': '{"token":"must not ship"}',
        'config/production.local.json': '{"token":"must not ship"}',
        'runtime/private.json': '{}', '.build/venv/private.py': '# secret',
        'web/node_modules/dependency/index.js': '// dependency',
        'core/__pycache__/x.py': '# stale', 'dist/previous.json': '{}',
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
        assert 'gui_test/web/vite.config.ts' in files
        assert 'gui_test/web/package-lock.json' in files
        assert 'gui_test/standalone/build.cmd' in files
        assert 'gui_test/config/production.example.json' in files
        assert not any('/backend/' in p or 'secrets' in p or '.local.json' in p or '/runtime/' in p or 'node_modules' in p or '/.build/' in p or '/dist/' in p for p in files)
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
    assert calls[0][1]['cwd'] == source.parent
    with zipfile.ZipFile(output) as archive:
        assert archive.read('dashboard-integration.patch').startswith(b'diff --git')


def test_package_rejects_missing_ui_and_empty_wheelhouse(source, tmp_path):
    output = tmp_path / 'bundle.zip'
    output.write_bytes(b'old successful artifact')
    with pytest.raises(ValueError, match='wheelhouse'):
        packaging.build_archive(source, output, standalone=True, wheelhouse=tmp_path / 'empty')
    assert output.read_bytes() == b'old successful artifact'
    (source / 'static/index.html').unlink()
    with pytest.raises(ValueError, match='Build standalone UI'):
        packaging.build_archive(source, output, standalone=True)
    assert output.read_bytes() == b'old successful artifact'


@pytest.mark.parametrize('options', [{}, {'standalone': True, 'base': 'main'}])
def test_package_requires_one_mode(source, tmp_path, options):
    with pytest.raises(ValueError, match='exactly one'):
        packaging.build_archive(source, tmp_path / 'bundle.zip', **options)
