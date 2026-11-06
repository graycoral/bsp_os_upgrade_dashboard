"""Source ZIP transport and immutable execution copies; no network or device calls."""
import json
import hashlib
import stat
import zipfile

import pytest

from backend.gui_test.core.models import TestError, digest
from backend.gui_test.execution import source_snapshots as snapshots


@pytest.fixture
def prepared(tmp_path):
    files = {'case.py': b"print('Test Result: PASS')\n", 'data/input.bin': b'\x00\xff\r\n'}
    value = snapshots.manifest(files, {'kind': 'server-folder', 'location': '/fixture/tc', 'generation': 1})
    directory = tmp_path / 'prepared'
    snapshots.publish(files, value, directory)
    return directory, value, files


def archive(tmp_path, value, files, extra=None):
    target = tmp_path / 'incoming.zip'
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED) as bundle:
        bundle.writestr(snapshots.MANIFEST, json.dumps(value))
        for name, content in files.items():
            bundle.writestr(name, content)
        if extra:
            extra(bundle)
    return target


def test_archive_round_trip_is_idempotent_and_attempt_copies_do_not_mutate_prepared_source(prepared, tmp_path):
    """T-178: transfer all auxiliary bytes and isolate each execution's writable copy."""
    directory, value, files = prepared
    incoming = tmp_path / 'incoming.zip'
    with snapshots.create_archive(directory, value) as stream:
        incoming.write_bytes(stream.read())
    destination = tmp_path / 'received'
    first = snapshots.receive_archive(incoming, value['snapshot_id'], destination)
    assert snapshots.receive_archive(incoming, value['snapshot_id'], destination) == first
    accepted = destination / value['snapshot_id']
    for name, content in files.items():
        assert (accepted / name).read_bytes() == content
    attempt = tmp_path / 'attempt-one'
    catalog = snapshots.copy_snapshot(accepted, attempt, value['source_revision'])
    assert catalog['revision'] == value['source_revision']
    (attempt / 'data/input.bin').write_bytes(b'TC modified its own data')
    second = tmp_path / 'attempt-two'
    snapshots.copy_snapshot(accepted, second, value['source_revision'])
    assert (second / 'data/input.bin').read_bytes() == files['data/input.bin']
    assert (accepted / 'data/input.bin').read_bytes() == files['data/input.bin']


@pytest.mark.parametrize('unsafe', ['../escape.py', '/absolute.py', 'C:/drive.py', 'case.py:stream',
    'folder\\case.py', 'folder/../case.py', 'NUL.py', 'folder/CON', 'trailing./case.py'])
def test_unsafe_windows_paths_are_rejected_before_publication(prepared, tmp_path, unsafe):
    """T-178: malicious ZIP members never create files outside the snapshot root."""
    _, value, files = prepared
    incoming = archive(tmp_path, value, files, lambda bundle: bundle.writestr(unsafe, b'unsafe'))
    destination = tmp_path / 'accepted'
    with pytest.raises(TestError):
        snapshots.receive_archive(incoming, value['snapshot_id'], destination)
    assert not destination.exists()
    assert not (tmp_path / 'escape.py').exists()


@pytest.mark.parametrize('mutation', ['bytes', 'missing', 'extra', 'case-collision', 'symlink', 'manifest', 'identity'])
def test_tampered_archives_and_identity_mismatch_leave_no_partial_snapshot(prepared, tmp_path, mutation):
    """T-178: successful decompression alone never proves source identity."""
    _, value, original = prepared
    files = dict(original)
    extra = None
    identity = value['snapshot_id']
    if mutation == 'bytes': files['case.py'] = b"print('Test Result: FAIL')\n"
    if mutation == 'missing': files.pop('case.py')
    if mutation == 'extra': files['unlisted.py'] = b'extra'
    if mutation == 'case-collision': files['CASE.py'] = files['case.py']
    if mutation == 'manifest': value = {**value, 'source_revision': 'source-' + '0' * 64}
    if mutation == 'identity': identity = '0' * 64
    if mutation == 'symlink':
        files.pop('case.py')
        def extra(bundle):
            member = zipfile.ZipInfo('case.py')
            member.create_system = 3
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            bundle.writestr(member, 'outside.py')
    incoming = archive(tmp_path, value, files, extra)
    destination = tmp_path / 'accepted'
    with pytest.raises(TestError):
        snapshots.receive_archive(incoming, identity, destination)
    assert not destination.exists()


def test_modified_prepared_bytes_rejected_for_upload_and_attempt_copy(prepared, tmp_path):
    """T-178: disk mutation after successful receipt is detected before execution."""
    directory, value, _ = prepared
    (directory / 'data/input.bin').write_bytes(b'tampered dependency')
    with pytest.raises(TestError): snapshots.create_archive(directory, value)
    destination = tmp_path / 'attempt'
    with pytest.raises(TestError): snapshots.copy_snapshot(directory, destination, value['source_revision'])
    assert not destination.exists()


def test_manifest_enforces_file_and_total_bounds_without_large_allocations(monkeypatch):
    """T-178: bounded fixtures exercise file/total limits before persistence."""
    monkeypatch.setattr(snapshots, 'MAX_FILE', 4)
    monkeypatch.setattr(snapshots, 'MAX_TOTAL', 6)
    for files in ({'case.py': b'12345'}, {'a.py': b'1234', 'b.txt': b'5678'}):
        with pytest.raises(TestError): snapshots.manifest(files, {'kind': 'server-folder'})
    for files in ({'case.py': b'a', 'CASE.py': b'b'}, {'data': b'a', 'DATA/case.py': b'b'}):
        with pytest.raises(TestError): snapshots.manifest(files, {'kind': 'server-folder'})


@pytest.mark.parametrize('names', [
    ('Foo/a.py', 'foo/b.py'),
    ('root/Foo/a.py', 'root/foo/b.py'),
    ('a', 'a/b.py'),
    ('A', 'a/b.py'),
])
def test_windows_prefix_aliases_rejected_by_generator_and_independent_receiver(tmp_path, names):
    """T-178 / REG0062: Linux trees must not merge or change type on Windows."""
    files = {name: b"print('Test Result: PASS')\n" for name in names}
    with pytest.raises(TestError) as generated:
        snapshots.manifest(files, {'kind': 'server-folder'})
    assert generated.value.code == 'SOURCE_UNSAFE'
    assert generated.value.status == 422

    # Construct a correctly hashed wire manifest independently. Calling the
    # sender's manifest() here would reject the fixture before the receiver is
    # tested, hiding a missing trust-boundary check on uploaded archives.
    value = {'format': 'source_snapshot_v1', 'source': {'kind': 'server-folder'}, 'metadata': {},
             'files': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                       for name, data in files.items()}}
    value['source_revision'] = 'source-' + digest(value)
    value['snapshot_id'] = digest(value)
    incoming = archive(tmp_path, value, files)
    destination = tmp_path / 'accepted'
    with pytest.raises(TestError) as received:
        snapshots.receive_archive(incoming, value['snapshot_id'], destination)
    assert received.value.code == 'SOURCE_UNSAFE'
    assert received.value.status == 422
    assert not destination.exists()


def test_consistent_directory_prefix_allows_distinct_sibling_files(tmp_path):
    """T-178 / REG0062: sharing the same directory spelling is valid."""
    files = {'Foo/a.py': b'first case', 'Foo/b.py': b'second case'}
    value = snapshots.manifest(files, {'kind': 'server-folder'})
    incoming = archive(tmp_path, value, files)
    destination = tmp_path / 'accepted'
    snapshots.receive_archive(incoming, value['snapshot_id'], destination)
    for name, data in files.items():
        assert (destination / value['snapshot_id'] / name).read_bytes() == data
