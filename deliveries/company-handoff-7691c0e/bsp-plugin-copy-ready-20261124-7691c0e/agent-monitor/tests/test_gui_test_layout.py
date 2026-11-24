"""RQ-54/T-164..168: portable artifacts and CWD-independent app boundaries.

These tests use a deliberately small independent source tree. Real npm builds,
wheel construction/installation and process lifecycle checks belong to the
separate layout acceptance run, not the default unit suite.
"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tomllib
from types import SimpleNamespace
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def packaging():
    spec = importlib.util.spec_from_file_location(
        'gui_test_layout_packaging', ROOT / 'apps/gui-test/package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def portable_source(tmp_path):
    root = tmp_path / 'source tree with spaces'
    files = {
        'backend/__init__.py': 'raise RuntimeError("Dashboard initializer must not ship")\n',
        'backend/gui_test/__init__.py': '"""Portable GUI Test."""\n',
        'backend/gui_test/runtime.py': '# portable runtime\n',
        'backend/gui_test/connector/__init__.py': '',
        'backend/gui_test/connector/__main__.py': 'def main(): pass\n',
        'backend/gui_test/connector/gui.py': '# desktop UI\n',
        'backend/gui_test/core/__init__.py': '',
        'backend/gui_test/core/manager.py': '# shared manager\n',
        'backend/gui_test/standalone/__init__.py': '',
        'backend/gui_test/standalone/cli.py': 'def main(): pass\n',
        'backend/gui_test/execution/__init__.py': '',
        'backend/gui_test/execution/host.py': 'def main(): pass\n',
        'backend/gui_test/demo/tc/sample/test_example.py': 'print("Test Result: PASS")\n',
        'backend/gui_test/tests/test_smoke.py': 'def test_smoke(): pass\n',
        'apps/gui-test/launch.py': '# app launcher\n',
        'apps/gui-test/package.py': '# app exporter\n',
        'apps/gui-test/build-windows-package.ps1': '# Windows build\n',
        'apps/gui-test/build-windows-package.cmd': '@echo off\n',
        'apps/gui-test/package.json': '{"scripts":{"build":"vite build"}}',
        'apps/gui-test/package-lock.json': '{"lockfileVersion":3}',
        'apps/gui-test/vite.config.ts': 'export default {};\n',
        'apps/gui-test/tsconfig.json': '{}',
        'apps/gui-test/index.html': '<div id="root"></div>',
        'apps/gui-test/src/main.tsx': 'export {};\n',
        'apps/gui-test/README.md': '# Independent GUI Test\n',
        'apps/gui-test/requirements.lock': 'example==1.0\n',
        'apps/gui-test/config/production.example.json': '{"token":null}',
        'apps/gui-test/static/index.html': '<html>independent app</html>',
        'apps/gui-test/static/assets/app.js': 'console.log("portable");',
        'packages/gui-test-ui/src/GuiTestApp.tsx': 'export function GuiTestApp() {}\n',
        'packages/gui-test-ui/src/components/Panel.tsx': 'export {};\n',
    }
    # Use the real release metadata; source content and paths remain independent.
    files['apps/gui-test/pyproject.toml'] = (ROOT / 'apps/gui-test/pyproject.toml').read_text(encoding='utf-8')
    forbidden = [
        'backend/api/main.py', 'backend/domain/engine.py', 'apps/web/src/main.tsx',
        'apps/web/package.json', 'pyproject.toml', '.git/config', '.env',
        'backend/gui_test/runtime/private.json', 'backend/gui_test/runs.db',
        'backend/gui_test/core/__pycache__/old.py',
        'apps/gui-test/config/secrets.json', 'apps/gui-test/config/production.local.json',
        'apps/gui-test/.build/venv/private.py', 'apps/gui-test/node_modules/pkg/index.js',
        'apps/gui-test/runtime/private.json', 'apps/gui-test/private.json',
        'packages/gui-test-ui/src/node_modules/pkg/index.ts',
        'packages/gui-test-ui/src/.private/token.json',
    ]
    for name in forbidden:
        files[name] = 'DO_NOT_SHIP_PRIVATE_CONTENT'
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
    return root


def test_standalone_source_bundle_is_complete_without_dashboard_or_git(
        packaging, portable_source, tmp_path, monkeypatch):
    def no_git(*args, **kwargs):
        pytest.fail('standalone export consulted Git')
    monkeypatch.setattr(packaging.subprocess, 'check_output', no_git)
    output = tmp_path / 'delivery with spaces' / 'standalone.zip'
    packaging.build_archive(portable_source, output, standalone=True)
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        required = {
            'backend/__init__.py', 'backend/gui_test/runtime.py',
            'backend/gui_test/connector/__init__.py',
            'backend/gui_test/connector/__main__.py', 'backend/gui_test/connector/gui.py',
            'backend/gui_test/core/manager.py', 'backend/gui_test/execution/host.py',
            'backend/gui_test/demo/tc/sample/test_example.py',
            'apps/gui-test/launch.py', 'apps/gui-test/package.py',
            'apps/gui-test/build-windows-package.cmd', 'apps/gui-test/build-windows-package.ps1',
            'apps/gui-test/package.json', 'apps/gui-test/package-lock.json',
            'apps/gui-test/vite.config.ts', 'apps/gui-test/pyproject.toml',
            'apps/gui-test/requirements.lock', 'apps/gui-test/config/production.example.json',
            'apps/gui-test/static/index.html', 'apps/gui-test/static/assets/app.js',
            'packages/gui-test-ui/src/GuiTestApp.tsx',
            'packages/gui-test-ui/src/components/Panel.tsx',
        }
        assert required <= names
        assert {'INSTALL.md', 'RELEASE_SUMMARY.md', 'docs/HOST_CONTRACT.md'} <= names
        assert 'dashboard-integration.patch' not in names
        assert all(name.startswith(('backend/gui_test/', 'apps/gui-test/',
                                    'packages/gui-test-ui/src/'))
                   or name in {'backend/__init__.py', 'INSTALL.md', 'RELEASE_SUMMARY.md',
                               'docs/HOST_CONTRACT.md', 'SHA256SUMS.json'}
                   for name in names)
        assert all(b'DO_NOT_SHIP_PRIVATE_CONTENT' not in archive.read(name) for name in names)
        assert b'Dashboard initializer' not in archive.read('backend/__init__.py')
        checksums = json.loads(archive.read('SHA256SUMS.json'))
        assert set(checksums) == names - {'SHA256SUMS.json'}
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == value
                   for name, value in checksums.items())


def test_wheel_stage_has_installed_namespace_resources_and_entry_points(
        packaging, portable_source, tmp_path):
    stage = tmp_path / 'wheel stage'
    packaging.stage_wheel(portable_source, stage)
    expected_resources = {
        'gui_test/__init__.py', 'gui_test/runtime.py', 'gui_test/core/manager.py',
        'gui_test/standalone/cli.py', 'gui_test/execution/host.py',
        'gui_test/connector/__init__.py', 'gui_test/connector/__main__.py',
        'gui_test/connector/gui.py',
        'gui_test/static/index.html', 'gui_test/static/assets/app.js',
        'gui_test/config/production.example.json', 'gui_test/README.md',
        'gui_test/requirements.lock', 'gui_test/demo/tc/sample/test_example.py',
        'pyproject.toml',
    }
    assert all((stage / name).is_file() for name in expected_resources)
    assert not any((stage / name).exists() for name in ('backend', 'apps', 'packages'))
    assert all(b'DO_NOT_SHIP_PRIVATE_CONTENT' not in path.read_bytes()
               for path in stage.rglob('*') if path.is_file())
    metadata = tomllib.loads((stage / 'pyproject.toml').read_text(encoding='utf-8'))
    assert metadata['project']['name'] == 'bsp-gui-test'
    assert metadata['project']['scripts'] == {
        'gui-test': 'gui_test.standalone.cli:main',
        'gui-test-runner': 'gui_test.execution.host:main',
        'gui-test-integration': 'gui_test.standalone.integration:main',
        'gui-test-connector': 'gui_test.connector.__main__:main',
    }
    assert (stage / 'gui_test/static/index.html').read_bytes() == (
        portable_source / 'apps/gui-test/static/index.html').read_bytes()


@pytest.mark.parametrize('operation', ['archive', 'wheel'])
def test_portable_artifacts_do_not_follow_file_or_directory_symlinks(
        operation, packaging, portable_source, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'secret.py').write_text('SYMLINK_TARGET_MUST_NOT_SHIP', encoding='utf-8')
    try:
        (portable_source / 'backend/gui_test/core/link.py').symlink_to(outside / 'secret.py')
        (portable_source / 'apps/gui-test/static/linked').symlink_to(outside, target_is_directory=True)
        (portable_source / 'packages/gui-test-ui/src/linked').symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f'symlink creation unavailable: {exc}')
    if operation == 'archive':
        target = tmp_path / 'bundle.zip'
        packaging.build_archive(portable_source, target, standalone=True)
        with zipfile.ZipFile(target) as archive:
            assert not any('link' in Path(name).parts or Path(name).name == 'link.py'
                           or 'linked' in Path(name).parts for name in archive.namelist())
            assert all(b'SYMLINK_TARGET_MUST_NOT_SHIP' not in archive.read(name)
                       for name in archive.namelist())
    else:
        target = tmp_path / 'stage'
        packaging.stage_wheel(portable_source, target)
        assert not any(path.is_symlink() or path.name in {'link.py', 'linked'}
                       for path in target.rglob('*'))


def test_source_cli_detaches_with_resolved_paths_and_import_root(tmp_path, monkeypatch):
    from backend.gui_test.core.models import digest
    from backend.gui_test.standalone import cli

    working = tmp_path / 'unrelated current directory'
    working.mkdir()
    static = working / 'my static'
    static.mkdir()
    (static / 'index.html').write_text('<html>custom</html>', encoding='utf-8')
    monkeypatch.chdir(working)
    calls = []

    def popen(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(poll=lambda: None)

    def health(*args, **kwargs):
        if not calls:
            raise OSError('not started')
        return io.BytesIO(json.dumps({
            'mode': 'standalone', 'runtime_id': digest(str(working / 'my runtime')),
        }).encode())

    monkeypatch.setattr(cli.subprocess, 'Popen', popen)
    monkeypatch.setattr(cli.urllib.request, 'urlopen', health)
    monkeypatch.setattr(cli.time, 'sleep', lambda seconds: None)
    cli.main(['start', '--runtime', 'my runtime', '--static-dir', 'my static', '--port', '18767'])
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[1:4] == ['-m', 'backend.gui_test.standalone.cli', 'serve']
    assert Path(argv[argv.index('--runtime') + 1]) == working / 'my runtime'
    assert Path(argv[argv.index('--static-dir') + 1]) == static
    assert Path(kwargs['cwd']).resolve() == ROOT
    assert argv[argv.index('--port') + 1] == '18767'


def test_static_override_serves_app_assets_and_preserves_existing_run_history(tmp_path):
    from fastapi.testclient import TestClient
    from backend.gui_test.core.models import uid
    from backend.gui_test.runtime import make_manager
    from backend.gui_test.standalone.server import create_app

    runtime = tmp_path / 'existing runtime'
    manager = make_manager(runtime, 'standalone')
    catalog = manager.catalog()
    boards = manager.boards.boards()
    run = manager.start(uid(), 'owner', {
        'tc_ids': [catalog['tests'][0]['id']], 'source_revision': catalog['revision'],
        'connection': {'a': boards[0], 'b': boards[1]}, 'speed': 20,
    })
    snapshot = manager.get(run['id'])
    events = manager.store.events(run['id'])
    static = tmp_path / 'app owned static'
    static.mkdir()
    (static / 'index.html').write_text('<html>app owned assets</html>', encoding='utf-8')
    app = create_app(runtime, start_worker=False, static_dir=static)
    with TestClient(app, client=('127.0.0.1', 1000)) as client:
        assert 'app owned assets' in client.get('/').text
        response = client.get('/api/v1/gui-test/runs/' + run['id'])
        assert response.status_code == 200
        assert response.json() == snapshot
        assert client.get('/api/v1/health').json()['mode'] == 'standalone'
    assert app.state.manager.store.path == manager.store.path
    assert app.state.manager.store.events(run['id']) == events
