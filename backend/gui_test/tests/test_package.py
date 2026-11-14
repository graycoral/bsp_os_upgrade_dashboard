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
        'apps/gui-test/build-windows-package.cmd': '@echo off', 'apps/gui-test/build-windows-package.ps1': '# build',
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
        assert 'apps/gui-test/build-windows-package.cmd' in files
        assert 'apps/gui-test/config/production.example.json' in files
        assert not any(p.startswith(('backend/api/', 'backend/domain/')) or 'secrets' in p or '.local.json' in p or '/runtime/' in p or 'node_modules' in p or '/.build/' in p or '/dist/' in p for p in files)
        hashes = json.loads(archive.read('SHA256SUMS.json'))
        assert set(hashes) == files - {'SHA256SUMS.json'}
        for name, checksum in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum


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


@pytest.mark.parametrize('options', [{}, {'standalone': True, 'host_integration': True},
                                    {'host_integration': True},
                                    {'host_integration': True, 'target': 'unknown'},
                                    {'standalone': True, 'target': 'bsp-dashboard-host-v1'}])
def test_package_rejects_invalid_mode_before_source_or_output_access(tmp_path, monkeypatch, options):
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid mode must fail before collecting sources')
    monkeypatch.setattr(packaging, 'package_files', forbidden)
    output = tmp_path / 'bundle.zip'; output.write_bytes(b'previous artifact')
    with pytest.raises(ValueError):
        packaging.build_archive(tmp_path / 'missing source', output, **options)
    assert output.read_bytes() == b'previous artifact'


@pytest.mark.parametrize('standalone', [False, True])
def test_retired_base_fails_before_source_or_output_access(tmp_path, monkeypatch, standalone):
    def forbidden(*args, **kwargs):
        pytest.fail('Retired base must not inspect source or invoke Git')
    monkeypatch.setattr(packaging, 'package_files', forbidden)
    monkeypatch.setattr(packaging.subprocess, 'check_output', forbidden)
    output = tmp_path / 'bundle.zip'; output.write_bytes(b'previous artifact')
    with pytest.raises(ValueError, match='retired'):
        packaging.build_archive(tmp_path / 'missing', output, base='old-base', standalone=standalone)
    assert output.read_bytes() == b'previous artifact'


def test_cli_retired_base_does_not_collect_or_replace(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('Retired CLI must not collect sources')
    monkeypatch.setattr(packaging, 'package_files', forbidden)
    output = tmp_path / 'bundle.zip'; output.write_bytes(b'previous artifact')
    with pytest.raises(SystemExit) as failure:
        packaging.main(['--base', 'old-base', '--output', str(output)])
    assert failure.value.code == 2
    assert 'retired' in capsys.readouterr().err
    assert output.read_bytes() == b'previous artifact'


def test_actual_host_archive_is_self_contained_and_hashes_every_entry(tmp_path):
    root = Path(__file__).resolve().parents[3]
    output = tmp_path / 'host source.zip'
    result = packaging.build_archive(root, output, host_integration=True, target='bsp-dashboard-host-v1')
    assert result['mode'] == 'host-integration'
    assert result['sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()
    extracted = tmp_path / 'extracted'; extracted.mkdir()
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert 'dashboard-integration.patch' not in names
        assert not any(name.startswith(('backend/domain/', 'backend/api/', 'apps/gui-test/static/')) for name in names)
        assert {'INSTALL.md', 'RELEASE_SUMMARY.md', 'docs/HOST_CONTRACT.md', 'HOST_INTEGRATION.json',
                'packages/gui-test-ui/src/index.ts', 'packages/gui-test-ui/src/host.ts',
                'backend/gui_test/core/sources.py', 'backend/gui_test/core/ports.py',
                'host-reference/backend/services/gui_test_host.py'} <= names
        hashes = json.loads(archive.read('SHA256SUMS.json'))
        assert set(hashes) == names - {'SHA256SUMS.json'}
        for name, checksum in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum
        manifest = json.loads(archive.read('HOST_INTEGRATION.json'))
        assert manifest['target'] == 'bsp-dashboard-host-v1'
        assert manifest['actual_validation']['company_acceptance'] == 'NOT_RUN'
        verification = manifest['ui_verification']
        canonical = (root / verification['canonical_source']).read_bytes()
        exported = archive.read(verification['exported_fixture'])
        assert verification['canonical_source'] == 'workflow_diagram/tests/portable-ui-host.tsx'
        assert verification['exported_fixture'] == 'ui-verification/portable-ui-host.tsx'
        old = b"from '../../packages/gui-test-ui/src'"
        new = b"from '../packages/gui-test-ui/src'"
        assert canonical.count(old) == 1
        assert exported == canonical.replace(old, new, 1)
        assert verification['import_rewrite'] == {'from': old.decode(), 'to': new.decode()}
        assert verification['canonical_sha256'] == hashlib.sha256(canonical).hexdigest()
        assert verification['exported_sha256'] == hashlib.sha256(exported).hexdigest()
        assert set(verification['files']) == {
            'ui-verification/portable-ui-host.tsx', 'ui-verification/index.html',
            'ui-verification/vite.config.mjs', 'ui-verification/README.md'}
        assert set(verification['files']) <= names
        assert b'./portable-ui-host.tsx' in archive.read('ui-verification/index.html')
        assert 'packages/gui-test-ui/src/index.ts' in names
        config = archive.read('ui-verification/vite.config.mjs')
        assert b'../apps/gui-test/package.json' in config
        assert b'apps/web' not in config and b'apps/web' not in exported
        assert all(command in archive.read('ui-verification/README.md').decode()
                   for command in verification['commands'])
        assert 'NOT_RUN' in verification['actual_validation']
        for name, checksum in manifest['provenance']['file_sha256'].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum
        # Exported relative Markdown links must resolve inside the actual bundle.
        import posixpath, re
        for name in [verification['exported_fixture'],
                     *sorted(n for n in names if n.startswith('packages/gui-test-ui/src/')
                             and n.endswith(('.ts', '.tsx')))]:
            for relative in re.findall(r"(?:\bfrom\s*|\bimport\s*)['\"](\.[^'\"]+)['\"]",
                                       archive.read(name).decode('utf-8-sig')):
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), relative))
                candidates = {resolved, *(resolved + ext for ext in ('.ts', '.tsx', '.css')),
                              resolved + '/index.ts', resolved + '/index.tsx'}
                assert candidates & names, (name, relative)
        for name in ('INSTALL.md', 'RELEASE_SUMMARY.md', 'apps/gui-test/README.md', 'apps/gui-test/VALIDATION.md'):
            for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', archive.read(name).decode()):
                if ':' not in target and not target.startswith('#'):
                    assert posixpath.normpath(posixpath.join(posixpath.dirname(name), target.split('#')[0])) in names
        archive.extractall(extracted)
    # Isolated interpreter imports only extracted source; host modules must remain unused.
    import sys
    code = """import sys
sys.path.insert(0, sys.argv[1])
from backend.gui_test.runtime import make_manager
from backend.gui_test.api.router import router
manager = make_manager(sys.argv[2], 'standalone')
assert manager.simulation and manager.dashboard is None
assert manager.catalog()['tests']
router(manager)
assert not any(name == 'backend.services' or name.startswith(('backend.services.', 'backend.domain.', 'backend.storage.', 'backend.worker.')) for name in sys.modules)
"""
    completed = subprocess.run([sys.executable, '-I', '-c', code, str(extracted), str(tmp_path / 'runtime')],
                               cwd=extracted, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr


def test_host_missing_reference_keeps_existing_artifact(source, tmp_path):
    output = tmp_path / 'bundle.zip'; output.write_bytes(b'previous artifact')
    with pytest.raises(ValueError, match='host reference'):
        packaging.build_archive(source, output, host_integration=True, target='bsp-dashboard-host-v1')
    assert output.read_bytes() == b'previous artifact'


@pytest.mark.parametrize('fixture', [None, b"import './unsupported';\n",
                                    b"import {} from '../../packages/gui-test-ui/src';\n" * 2])
def test_host_rejects_missing_or_changed_verification_fixture_without_replacing_artifact(
        source, tmp_path, fixture):
    reference = source / 'backend/services/gui_test_host.py'
    reference.parent.mkdir(parents=True)
    reference.write_text('# synthetic host reference\n', encoding='utf-8')
    if fixture is not None:
        canonical = source / 'workflow_diagram/tests/portable-ui-host.tsx'
        canonical.parent.mkdir(parents=True)
        canonical.write_bytes(fixture)
    output = tmp_path / 'bundle.zip'
    output.write_bytes(b'previous artifact')
    with pytest.raises(ValueError, match='fixture'):
        packaging.build_archive(source, output, host_integration=True, target='bsp-dashboard-host-v1')
    assert output.read_bytes() == b'previous artifact'


def test_actual_connector_sources_are_exported_for_declared_wheel_package():
    """A new declared package must not vanish through the source allowlist."""
    root = Path(__file__).resolve().parents[3]
    names = packaging.package_files(root)
    connector = root / 'backend/gui_test/connector'
    expected = {path.relative_to(root).as_posix() for path in connector.glob('*.py')}
    assert 'backend/gui_test/connector/__init__.py' in expected
    assert 'backend/gui_test/connector/__main__.py' in expected
    assert expected <= names.keys()
    for name in expected:
        assert names[name] == (root / name).read_bytes()
