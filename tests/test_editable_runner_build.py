"""RQ-61 packaging trust boundaries; synthetic bundles never execute TC code."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import time
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def put(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return digest(data)


@pytest.fixture
def manifest():
    from scripts.build_connector_bundle import load_input_lock
    return load_input_lock(ROOT / 'packaging/editable-windows-runner-inputs.lock.json')


@pytest.mark.parametrize('mutation', [
    lambda m: m.update(python_version='3.13.0'),
    lambda m: m.update(platform='win32'),
    lambda m: m['runtime'].update(filename='../python.zip'),
    lambda m: m['runtime'].update(url='http://example.invalid/python.zip'),
    lambda m: m['pip'].update(sha256='g' * 64),
    lambda m: m['pip'].update(size=True),
    lambda m: m['wheels'].append(copy.deepcopy(m['wheels'][0])),
])
def test_input_lock_rejects_unpinned_or_ambiguous_inputs(tmp_path, manifest, mutation):
    from scripts.build_connector_bundle import load_input_lock
    mutation(manifest)
    path = tmp_path / 'inputs.lock.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(ValueError):
        load_input_lock(path)


def test_missing_offline_cache_never_contacts_network_or_replaces_old_zip(tmp_path, manifest, monkeypatch):
    from scripts import build_connector_bundle as builder
    import urllib.request
    monkeypatch.setattr(builder, 'urlopen', lambda *a, **k: pytest.fail('offline contacted network'))
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('offline contacted network'))
    monkeypatch.setattr(urllib.request, 'urlretrieve', lambda *a, **k: pytest.fail('offline contacted network'))
    output = tmp_path / 'existing-approved.zip'
    output.write_bytes(b'previous-approved-artifact')
    with pytest.raises((ValueError, OSError, RuntimeError)):
        builder.build(ROOT, tmp_path / 'empty-cache', output, offline=True)
    assert output.read_bytes() == b'previous-approved-artifact'


def test_cache_lock_mismatch_is_readonly_failure(tmp_path, manifest):
    from scripts.build_connector_bundle import verify_cache
    cache = tmp_path / 'cache'
    cache.mkdir()
    altered = copy.deepcopy(manifest)
    altered['requirements_sha256'] = '0' * 64
    lock = cache / 'inputs.lock.json'
    lock.write_text(json.dumps(altered), encoding='utf-8')
    before = lock.read_bytes()
    with pytest.raises((ValueError, OSError)):
        verify_cache(cache, manifest)
    assert lock.read_bytes() == before
    assert sorted(p.name for p in cache.iterdir()) == ['inputs.lock.json']


@pytest.mark.parametrize('bom,newline', [(False, '\n'), (True, '\r\n'), (True, '\r')])
def test_requirements_bom_and_line_endings_share_canonical_hash(tmp_path, manifest, monkeypatch, bom, newline):
    from scripts import build_connector_bundle as builder
    root = tmp_path / 'source'
    raw = (ROOT / 'apps/gui-test/requirements.lock').read_text(encoding='utf-8-sig')
    canonical = raw.replace('\r\n', '\n').replace('\r', '\n')
    put(root, 'packaging/editable-windows-runner-inputs.lock.json', json.dumps(manifest).encode())
    put(root, 'apps/gui-test/requirements.lock',
        (b'\xef\xbb\xbf' if bom else b'') + canonical.replace('\n', newline).encode())
    reached = []
    def after_inputs(*args, **kwargs):
        reached.append(True)
        raise ValueError('fixture stops after validated requirement pins')
    monkeypatch.setattr(builder, '_prepare', after_inputs)
    with pytest.raises(RuntimeError, match='fixture stops after validated requirement pins'):
        builder.build(root, tmp_path / 'cache', tmp_path / 'out.zip', offline=True)
    assert reached == [True]


@pytest.mark.skipif(os.name == 'nt', reason='POSIX whole-file flock ownership')
def test_posix_lock_excludes_same_process_open_and_releases_after_failure(tmp_path):
    from scripts.build_connector_bundle import _lock
    path = tmp_path / 'build.lock'
    with pytest.raises(ValueError, match='fixture body failure'):
        with _lock(path, byte=0):
            # A second open must not silently replace/release this lock, even
            # within one process. This guards against switching to lockf.
            with pytest.raises(RuntimeError, match='already locked'):
                with _lock(path, byte=1):
                    pytest.fail('second open acquired a held whole-file lock')
            raise ValueError('fixture body failure')
    with _lock(path, byte=1):
        pass


@pytest.mark.skipif(os.name == 'nt', reason='POSIX does not use bootstrap byte ranges')
@pytest.mark.parametrize('held_byte', [0, 1])
def test_posix_build_does_not_bypass_other_owner_with_bootstrap_marker(
        tmp_path, manifest, monkeypatch, held_byte):
    from scripts import build_connector_bundle as builder
    root, cache = tmp_path / 'source', tmp_path / 'cache'
    put(root, 'packaging/editable-windows-runner-inputs.lock.json', json.dumps(manifest).encode())
    put(root, 'apps/gui-test/requirements.lock', (ROOT / 'apps/gui-test/requirements.lock').read_bytes())
    monkeypatch.setenv('BSP_EDITABLE_BOOTSTRAP_OWNER', str(os.getppid()))
    monkeypatch.setattr(builder, '_prepare', lambda *a, **k: pytest.fail('held lock reached preparation'))
    # flock locks belong to open descriptions, so this independent open is an
    # owner even in this process. The existing orphan test covers another PID.
    with builder._lock(cache / 'build.lock', byte=held_byte):
        with pytest.raises(RuntimeError, match='already locked'):
            builder.build(root, cache, tmp_path / 'out.zip', offline=True)
    assert not (tmp_path / 'out.zip').exists()


def test_requirements_exact_pin_set_checked_even_if_digest_matches(tmp_path, manifest, monkeypatch):
    from scripts import build_connector_bundle as builder
    root = tmp_path / 'source'
    raw = (ROOT / 'apps/gui-test/requirements.lock').read_text(encoding='utf-8-sig')
    canonical = raw.replace('\r\n', '\n').replace('\r', '\n') + 'unapproved-extra==1.0\n'
    manifest['requirements_sha256'] = digest(canonical.encode())
    put(root, 'packaging/editable-windows-runner-inputs.lock.json', json.dumps(manifest).encode())
    put(root, 'apps/gui-test/requirements.lock', canonical.encode())
    monkeypatch.setattr(builder, '_prepare', lambda *a, **kw: pytest.fail('invalid pins reached cache preparation'))
    with pytest.raises((ValueError, RuntimeError), match='pin'):
        builder.build(root, tmp_path / 'cache', tmp_path / 'out.zip', offline=True)


def test_orphan_builder_lock_blocks_direct_build_and_new_bootstrap_before_cache_mutation(tmp_path, manifest, monkeypatch):
    """Byte zero becomes free after parent death; live child byte one still excludes builders."""
    from scripts import build_connector_bundle as builder
    root, cache = tmp_path / 'source', tmp_path / 'cache'
    cache.mkdir()
    put(root, 'packaging/editable-windows-runner-inputs.lock.json', json.dumps(manifest).encode())
    put(root, 'apps/gui-test/requirements.lock', (ROOT / 'apps/gui-test/requirements.lock').read_bytes())
    ready, stop = tmp_path / 'ready', tmp_path / 'stop'
    code = '''
import sys,time
from pathlib import Path
from scripts.build_connector_bundle import _lock
with _lock(Path(sys.argv[1]),byte=1):
    Path(sys.argv[2]).touch()
    while not Path(sys.argv[3]).exists(): time.sleep(.02)
'''
    child = subprocess.Popen([sys.executable, '-B', '-c', code, str(cache / 'build.lock'), str(ready), str(stop)], cwd=ROOT)
    try:
        deadline = time.monotonic() + 8
        while not ready.exists():
            assert child.poll() is None, 'fixture lock child exited'
            assert time.monotonic() < deadline, 'fixture lock child did not become ready'
            time.sleep(.02)
        monkeypatch.delenv('BSP_EDITABLE_BOOTSTRAP_OWNER', raising=False)
        monkeypatch.setattr(builder, '_prepare', lambda *a, **kw: pytest.fail('orphan child allowed concurrent cache mutation'))
        with pytest.raises(RuntimeError, match='locked'):
            builder.build(root, cache, tmp_path / 'out.zip', offline=True)
        assert sorted(p.name for p in cache.iterdir()) == ['build.lock']
        if os.name == 'nt':
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                     '-File', str(ROOT / 'scripts/build-connector-bundle.ps1'),
                                     '-Offline', '-CachePath', str(cache), '-OutputPath', str(tmp_path / 'ps.zip')],
                                    capture_output=True, timeout=30)
            assert result.returncode != 0, result.stdout.decode(errors='replace')
            assert sorted(p.name for p in cache.iterdir()) == ['build.lock']
        assert child.poll() is None
    finally:
        stop.touch()
        child.wait(timeout=8)


@pytest.mark.skipif(os.name != 'nt', reason='PowerShell native process creation regression')
def test_bootstrap_native_launch_failure_is_nonzero_and_preserves_old_artifact(tmp_path, manifest):
    """Exercise the full bootstrap with a deliberately pinned invalid-PE fixture.

    Substitute only the approved hash in a temporary script copy; this is an
    injection seam to reach native spawn failure, not a valid distribution input.
    """
    root, cache = tmp_path / 'fixture-source', tmp_path / 'cache'
    runtime = cache / 'runtime' / manifest['runtime']['filename']
    runtime.parent.mkdir(parents=True)
    with zipfile.ZipFile(runtime, 'w') as archive:
        archive.writestr('python.exe', b'fixture-invalid-Windows-executable')
    original_sha = manifest['runtime']['sha256']
    manifest['runtime'].update(size=runtime.stat().st_size, sha256=digest(runtime.read_bytes()))
    put(root, 'packaging/editable-windows-runner-inputs.lock.json', json.dumps(manifest).encode())
    (cache / 'inputs.lock.json').write_text(json.dumps(manifest))
    wrapper = (ROOT / 'scripts/build-connector-bundle.ps1').read_text(encoding='utf-8-sig')
    script = root / 'scripts/build-connector-bundle.ps1'
    put(root, 'scripts/build-connector-bundle.ps1', wrapper.replace(original_sha, manifest['runtime']['sha256']).encode('utf-8-sig'))
    output = tmp_path / 'approved.zip'
    output.write_bytes(b'approved-prior-artifact')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                             '-Offline', '-CachePath', str(cache), '-OutputPath', str(output)],
                            capture_output=True, timeout=30)
    assert result.returncode != 0, result.stdout.decode(errors='replace')
    assert b'Build failed in builder' in result.stdout
    assert b'Built:' not in result.stdout
    assert output.read_bytes() == b'approved-prior-artifact'
    logs = list((root / '.local-reports').glob('*/bootstrap.log'))
    assert len(logs) == 1
    logged = logs[0].read_text(encoding='utf-8-sig')
    assert 'Builder exit code: 1' in logged or 'FAIL phase=builder' in logged


@pytest.fixture
def synthetic_cache(tmp_path, manifest):
    """Verified bytes/metadata boundary without downloading or executing artifacts."""
    cache = tmp_path / 'cache'
    manifest = copy.deepcopy(manifest)
    manifest['wheels'] = [manifest['wheels'][0]]
    for folder, artifact in [('runtime', manifest['runtime']), ('bootstrap', manifest['pip']),
                             ('wheels', manifest['wheels'][0])]:
        path = cache / folder / artifact['filename']
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as z:
            if folder == 'runtime':
                blob = bytearray(128)
                blob[:2] = b'MZ'
                struct.pack_into('<I', blob, 60, 64)
                blob[64:70] = b'PE\0\0d\x86'
                for name, data in [('python.exe', blob), ('python312.dll', b'dll'),
                                   ('python312.zip', b'stdlib'), ('python312._pth', b'.'),
                                   ('LICENSE.txt', b'license')]:
                    z.writestr(name, data)
            else:
                name, version, tags = ('pip', '25.0.1', ['py3-none-any']) if folder == 'bootstrap' else (
                    artifact['name'], artifact['version'], artifact['tags'])
                prefix = name.replace('-', '_') + '-' + version + '.dist-info/'
                z.writestr(prefix + 'METADATA', f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n')
                z.writestr(prefix + 'WHEEL', 'Wheel-Version: 1.0\n' + ''.join('Tag: ' + t + '\n' for t in tags))
        artifact.update(size=path.stat().st_size, sha256=digest(path.read_bytes()))
    (cache / 'inputs.lock.json').write_text(json.dumps(manifest), encoding='utf-8')
    return cache, manifest


def test_verified_cache_returns_only_exact_artifacts_and_detects_byte_tampering(synthetic_cache):
    from scripts.build_connector_bundle import verify_cache
    cache, manifest = synthetic_cache
    verified = verify_cache(cache, manifest)
    assert set(verified) == {manifest['runtime']['filename'], manifest['pip']['filename'], manifest['wheels'][0]['filename']}
    assert all(isinstance(p, Path) and p.is_file() for p in verified.values())
    target = verified[manifest['wheels'][0]['filename']]
    data = target.read_bytes()
    target.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(ValueError):
        verify_cache(cache, manifest)


@pytest.mark.parametrize('member', ['../escape.py', '/absolute.py', 'C:/drive.py',
                                    'nested\\..\\escape.py', 'Case.py', 'link.py'])
def test_cache_rejects_unsafe_zip_members_even_with_matching_outer_hash(synthetic_cache, member):
    from scripts.build_connector_bundle import verify_cache
    cache, manifest = synthetic_cache
    artifact = manifest['wheels'][0]
    path = cache / 'wheels' / artifact['filename']
    with zipfile.ZipFile(path, 'a') as z:
        if member == 'Case.py':
            z.writestr('case.py', 'first')
        item = zipfile.ZipInfo(member)
        # ZipInfo normalizes os.sep on Windows; preserve deliberately hostile bytes.
        item.filename = member
        if member == 'link.py':
            item.create_system = 3
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(item, 'untrusted')
    artifact.update(size=path.stat().st_size, sha256=digest(path.read_bytes()))
    (cache / 'inputs.lock.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_cache(cache, manifest)
    assert not (cache.parent / 'escape.py').exists()


@pytest.fixture
def bundle_tree(tmp_path):
    root = tmp_path / 'bundle space 한글'
    root.mkdir()
    marker = {'version': 1, 'mode': 'editable', 'python': 'runtime/python.exe',
              'source': 'src', 'dependencies': 'deps', 'python_version': '3.12.10', 'platform': 'win_amd64'}
    immutable = {
        'bundle.json': put(root, 'bundle.json', json.dumps(marker).encode()),
        'runtime/python.exe': put(root, 'runtime/python.exe', b'fixture-interpreter-never-executed'),
        'runtime/python312._pth': put(root, 'runtime/python312._pth', b'python312.zip\n.\n../deps\n../src\n'),
        'deps/fixture/__init__.py': put(root, 'deps/fixture/__init__.py', b'VALUE=1\n')}
    source = {'src/scripts/setup_ports.py': put(root, 'src/scripts/setup_ports.py', b'VALUE=1\n')}
    info = {'version': 1, 'bundle_id': '11111111-1111-4111-8111-111111111111',
            'parent_bundle_id': None, 'source_revision': None, 'source_dirty': None,
            'modified': False, 'built_at': '2026-11-07T00:00:00Z', 'inputs_lock_sha256': 'a' * 64,
            'original_source_hashes': source.copy(), 'source_hashes': source.copy(),
            'immutable_hashes': immutable}
    put(root, 'build-info.json', json.dumps(info).encode())
    hashes = {name: digest(path.read_bytes()) for name, path in
              ((p.relative_to(root).as_posix(), p) for p in root.rglob('*') if p.is_file())}
    put(root, 'SHA256SUMS', ''.join(f'{sha}  {name}\n' for name, sha in sorted(hashes.items())).encode())
    return root, info


def test_repack_allows_source_edits_additions_and_preserves_original_baseline(bundle_tree, tmp_path, monkeypatch):
    from scripts import build_connector_bundle as builder
    import urllib.request
    root, before = bundle_tree
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('repack contacted network'))
    put(root, 'src/scripts/setup_ports.py', b'VALUE=2\n')
    put(root, 'src/backend/gui_test/new_fixture.py', b'VALUE=3\n')
    output = tmp_path / 'new.zip'
    assert builder.repack(root, output) == output
    with zipfile.ZipFile(output) as archive:
        info = json.loads(archive.read('build-info.json'))
        assert archive.read('src/scripts/setup_ports.py') == b'VALUE=2\n'
        assert archive.read('src/backend/gui_test/new_fixture.py') == b'VALUE=3\n'
    assert info['original_source_hashes'] == before['original_source_hashes']
    assert info['immutable_hashes'] == before['immutable_hashes']
    assert info['source_hashes'] != before['source_hashes']
    assert info['modified'] is True and info['parent_bundle_id'] == before['bundle_id']
    assert info['bundle_id'] != before['bundle_id']
    assert json.loads((root / 'build-info.json').read_text()) == before


@pytest.mark.parametrize('mutation', ['change', 'remove', 'add'])
def test_repack_rejects_changed_missing_or_added_immutable_files(bundle_tree, tmp_path, mutation):
    from scripts.build_connector_bundle import repack
    root, _ = bundle_tree
    target = root / 'deps/fixture/__init__.py'
    if mutation == 'change':
        target.write_bytes(b'altered dependency')
    elif mutation == 'remove':
        target.unlink()
    else:
        put(root, 'runtime/unexpected.dll', b'added immutable')
    output = tmp_path / 'new.zip'
    with pytest.raises(ValueError):
        repack(root, output)
    assert not output.exists()


def test_repack_excludes_local_user_secrets_logs_and_bytecode(bundle_tree, tmp_path):
    from scripts.build_connector_bundle import repack
    root, _ = bundle_tree
    excluded = ['windows-runner.json', 'runtime-user/token', 'private-home/runner.db',
                '.git/config', '.vscode/settings.json', 'src/scripts/__pycache__/cached.pyc',
                'src/scripts/not-shipped.log', 'device-test.example.json']
    for name in excluded:
        put(root, name, b'private-fixture-sentinel')
    output = tmp_path / 'safe.zip'
    # An unexpected user file is actionable contamination, never silently shipped.
    with pytest.raises(ValueError):
        repack(root, output)
    assert not output.exists()


def test_repack_refuses_overwrite_of_existing_artifact(bundle_tree, tmp_path):
    from scripts.build_connector_bundle import repack
    output = tmp_path / 'approved.zip'
    output.write_bytes(b'approved-zip')
    with pytest.raises((ValueError, OSError)):
        repack(bundle_tree[0], output)
    assert output.read_bytes() == b'approved-zip'


@pytest.mark.parametrize('filename', ['edited-runner.zip', '새 전달 repacked.zip'])
@pytest.mark.parametrize('operation', ['publish', 'cacheless-repack'])
def test_zip_checksum_supports_unicode_filename_and_exact_archive_hash(bundle_tree, tmp_path, monkeypatch, filename, operation):
    """The checksum records the actual ZIP basename, including non-ASCII text."""
    from scripts import build_connector_bundle as builder
    root, info = bundle_tree
    output = tmp_path / '한글 delivery directory' / filename
    monkeypatch.setattr(builder, 'urlopen', lambda *a, **kw: pytest.fail('local packaging contacted network'))
    monkeypatch.setattr(builder, '_run', lambda *a, **kw: pytest.fail('cacheless repack invoked a dependency installer'))
    if operation == 'publish':
        result = builder._publish(root, output, info, overwrite=True)
    else:
        put(root, 'src/scripts/setup_ports.py', b'VALUE=2\n')
        result = builder.repack(root, output)
    assert result == output
    assert output.is_file()
    sidecar = output.with_name(output.name + '.sha256')
    assert sidecar.read_bytes().decode('utf-8').splitlines() == [digest(output.read_bytes()) + '  ' + filename]
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        if operation == 'cacheless-repack':
            assert archive.read('src/scripts/setup_ports.py') == b'VALUE=2\n'


@pytest.mark.parametrize('rollback_blocked', [False, True])
def test_publish_sidecar_failure_restores_or_retains_recoverable_previous_zip(bundle_tree, tmp_path, monkeypatch, rollback_blocked):
    from scripts import build_connector_bundle as builder
    root, info = bundle_tree
    output = tmp_path / 'approved.zip'
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('approved-marker.txt', 'previous-validated-bundle')
    original = output.read_bytes()
    sidecar = output.with_name(output.name + '.sha256')
    sidecar.write_text(digest(original) + '  ' + output.name + '\n')
    original_sidecar = sidecar.read_bytes()
    actual_replace = builder.os.replace
    def replace(source, destination):
        if Path(source).name.endswith('.sha256.pending'):
            raise PermissionError('fixture sidecar publish blocked')
        if rollback_blocked and Path(source).name.endswith('.previous-zip'):
            raise PermissionError('fixture rollback also blocked')
        return actual_replace(source, destination)
    monkeypatch.setattr(builder.os, 'replace', replace)
    with pytest.raises(OSError) as failure:
        builder._publish(root, output, info, overwrite=True)
    assert sidecar.read_bytes() == original_sidecar
    backups = list(tmp_path.glob('*.previous-zip'))
    if rollback_blocked:
        assert len(backups) == 1 and backups[0].read_bytes() == original
        assert str(backups[0]) in str(failure.value)
        assert 'recovery' in str(failure.value).lower()
        with zipfile.ZipFile(backups[0]) as archive:
            assert archive.read('approved-marker.txt') == b'previous-validated-bundle'
    else:
        assert output.read_bytes() == original
        assert not backups
