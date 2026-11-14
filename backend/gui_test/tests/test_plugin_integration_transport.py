"""T-203: authenticated installer streaming resumes the same immutable receipt."""
import hashlib
import os
import time

from fastapi.testclient import TestClient

from backend.gui_test.execution.host import create_app
from backend.gui_test.execution import installer_snapshots as snapshots
from backend.gui_test.tests.test_plugin_integration_batches import rig as runner_rig
from backend.gui_test.tests.test_plugin_integration_snapshots import installer


TOKEN = 'fixture-runner-stream-token-0123456789abcdef'


def archive_bytes(installer, tmp_path):
    root, release, _ = installer
    storage = tmp_path / 'frozen'
    manifest = snapshots.freeze_installer(str(release / 'install.bat'), [str(root)], storage)
    with snapshots.create_archive(storage / manifest['snapshot_id'], manifest) as stream:
        return manifest, stream.read()


def test_partial_transfer_resumes_by_offset_then_replay_does_not_republish_or_touch_hardware(runner_rig, installer, tmp_path):
    host, _, _ = runner_rig
    manifest, data = archive_bytes(installer, tmp_path)
    identity = manifest['snapshot_id']
    path = '/v1/installer-snapshots/' + identity
    sha = hashlib.sha256(data).hexdigest()
    headers = {'Content-Type': 'application/zip', 'X-Archive-SHA256': sha,
               'Content-Range': f'bytes 0-{len(data)-1}/{len(data)}', 'Content-Length': str(len(data))}
    half = len(data) // 2
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1', 1000), headers={'Authorization': 'Bearer ' + TOKEN}) as client:
        partial = client.put(path, content=data[:half], headers=headers)
        assert partial.status_code == 409 and partial.json()['code'] == 'IMAGE_INCOMPLETE'
        receipt = client.get(path).json()
        assert receipt['state'] == 'PARTIAL' and receipt['offset'] == half
        assert not (host.runtime / 'installer-snapshots' / identity).exists()
        resumed_headers = headers | {'Content-Range': f'bytes {half}-{len(data)-1}/{len(data)}',
                                     'Content-Length': str(len(data) - half)}
        resumed = client.put(path, content=data[half:], headers=resumed_headers)
        assert resumed.status_code == 200 and resumed.json()['state'] == 'READY'
        assert client.put(path, content=data, headers=headers).json() == resumed.json()
        directory = host.runtime / 'installer-snapshots' / identity
        old = time.time() - 30 * 86400
        for entry in [*directory.rglob('*'), directory]: os.utime(entry, (old, old))
        assert client.get(path).json()['state'] == 'READY'
        from backend.gui_test.execution.retention import collect
        assert str(directory) not in collect(host, dry_run=True)['candidates']
        assert snapshots.load_manifest(host.runtime / 'installer-snapshots' / identity, identity) == manifest
        assert host.threads == [] and host.flashing.supervised == {}


def test_changed_hash_or_wrong_resume_offset_cannot_replace_partial_receipt(runner_rig, installer, tmp_path):
    host, _, _ = runner_rig
    manifest, data = archive_bytes(installer, tmp_path)
    path = '/v1/installer-snapshots/' + manifest['snapshot_id']
    half = len(data) // 2
    headers = {'Content-Type': 'application/zip', 'X-Archive-SHA256': hashlib.sha256(data).hexdigest(),
               'Content-Range': f'bytes 0-{len(data)-1}/{len(data)}', 'Content-Length': str(len(data))}
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1', 1000), headers={'Authorization': 'Bearer ' + TOKEN}) as client:
        client.put(path, content=data[:half], headers=headers)
        mismatch = client.put(path, content=data, headers=headers | {'X-Archive-SHA256': '0' * 64})
        assert mismatch.status_code == 409 and mismatch.json()['code'] == 'IMAGE_CHANGED'
        offset = client.put(path, content=data, headers=headers)
        assert offset.status_code == 409 and offset.json()['code'] == 'IMAGE_OFFSET'
        assert client.get(path).json()['offset'] == half
        assert not (host.runtime / 'installer-snapshots' / manifest['snapshot_id']).exists()
