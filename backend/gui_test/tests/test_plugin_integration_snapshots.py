"""T-203: installer staging transports the entire directory without executing BAT."""
import hashlib
import stat
import zipfile
import pytest

from backend.gui_test.core.models import TestError
from backend.gui_test.execution import installer_snapshots as snapshots


@pytest.fixture
def installer(tmp_path):
    root = tmp_path / 'published-builds'
    release = root / 'release'; release.mkdir(parents=True)
    files = {'install.bat': b'@echo off\r\n', 'images/system.bin': b'\x00\xff\x01',
             'tools/flash-helper.cmd': b'@exit /b 0', 'notes.txt': b'also part of installer'}
    for name, data in files.items():
        path = release / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    return root, release, files


def test_installer_freeze_includes_auxiliary_files_and_isolates_later_source_edits(installer, tmp_path):
    root, release, files = installer
    frozen = tmp_path / 'frozen'
    descriptor = snapshots.freeze_installer(str(release / 'install.bat'), [str(root)], frozen)
    frozen = frozen / descriptor['snapshot_id']
    assert set(descriptor['files']) == set(files)
    for name, data in files.items():
        assert descriptor['files'][name] == {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        assert (frozen / name).read_bytes() == data
    (release / 'images/system.bin').write_bytes(b'new producer revision')
    assert (frozen / 'images/system.bin').read_bytes() == files['images/system.bin']


def test_installer_archive_round_trip_checks_all_bytes_and_identity(installer, tmp_path):
    root, release, files = installer
    frozen = tmp_path / 'frozen'
    descriptor = snapshots.freeze_installer(str(release / 'install.bat'), [str(root)], frozen)
    frozen = frozen / descriptor['snapshot_id']
    incoming = tmp_path / 'incoming.zip'
    with snapshots.create_archive(frozen, descriptor) as stream:
        with incoming.open('wb') as output:
            while block := stream.read(7):
                output.write(block)
    destination = tmp_path / 'received'
    first = snapshots.receive_archive(incoming, descriptor['snapshot_id'], destination)
    assert snapshots.receive_archive(incoming, descriptor['snapshot_id'], destination) == first
    for name, data in files.items():
        assert (destination / descriptor['snapshot_id'] / name).read_bytes() == data
    with pytest.raises(TestError):
        snapshots.receive_archive(incoming, '0' * 64, tmp_path / 'wrong-identity')


def test_changed_frozen_auxiliary_file_cannot_be_transferred(installer, tmp_path):
    root, release, _ = installer
    frozen = tmp_path / 'frozen'
    descriptor = snapshots.freeze_installer(str(release / 'install.bat'), [str(root)], frozen)
    frozen = frozen / descriptor['snapshot_id']
    (frozen / 'tools/flash-helper.cmd').write_bytes(b'changed helper, same registered BAT')
    with pytest.raises(TestError):
        snapshots.create_archive(frozen, descriptor)


def test_size_limit_counts_whole_bundle_and_never_publishes_partial_success(installer, tmp_path):
    root, release, files = installer
    destination = tmp_path / 'too-large'
    with pytest.raises(TestError):
        snapshots.freeze_installer(str(release / 'install.bat'), [str(root)], destination,
                                   max_total=sum(map(len, files.values())) - 1)
    assert not destination.exists() or list(destination.iterdir()) == []


@pytest.mark.parametrize('path', ['outside', 'directory', 'not-bat'])
def test_installer_must_be_an_allowed_bat_file(installer, tmp_path, path):
    root, release, _ = installer
    value = {'outside': tmp_path / 'outside/install.bat', 'directory': release,
             'not-bat': release / 'notes.txt'}[path]
    if path == 'outside':
        value.parent.mkdir(); value.write_bytes(b'@echo off')
    with pytest.raises(TestError):
        snapshots.freeze_installer(str(value), [str(root)], tmp_path / 'invalid')


@pytest.mark.parametrize('damage', ['changed-bytes', 'missing-helper', 'extra-file', 'traversal',
                                   'windows-case-alias', 'symlink', 'truncated'])
def test_receiver_rejects_tampered_transport_without_publishing(installer, tmp_path, damage):
    root, release, _ = installer
    storage = tmp_path / 'frozen'
    descriptor = snapshots.freeze_installer(str(release / 'install.bat'), [str(root)], storage)
    with snapshots.create_archive(storage / descriptor['snapshot_id'], descriptor) as source:
        with zipfile.ZipFile(source) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
    if damage == 'changed-bytes': entries['images/system.bin'] = b'\x03\x02\x01'
    if damage == 'missing-helper': entries.pop('tools/flash-helper.cmd')
    if damage == 'extra-file': entries['unlisted.exe'] = b'unreviewed'
    if damage == 'traversal': entries['../escaped.bin'] = b'unsafe'
    if damage == 'windows-case-alias': entries['IMAGES/SYSTEM.bin'] = b'alias'
    if damage == 'symlink': entries.pop('images/system.bin')
    incoming = tmp_path / 'tampered.zip'
    with zipfile.ZipFile(incoming, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in entries.items(): archive.writestr(name, data)
        if damage == 'symlink':
            member = zipfile.ZipInfo('images/system.bin')
            member.create_system = 3
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(member, '../../outside')
    if damage == 'truncated': incoming.write_bytes(incoming.read_bytes()[:-22])
    destination = tmp_path / 'rejected'
    with pytest.raises(TestError):
        snapshots.receive_archive(incoming, descriptor['snapshot_id'], destination)
    assert not (destination / descriptor['snapshot_id']).exists()
    assert not (tmp_path / 'escaped.bin').exists()
