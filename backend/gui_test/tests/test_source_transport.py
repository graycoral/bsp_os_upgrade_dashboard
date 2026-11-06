"""Registered Linux snapshots sent to a local fake Windows runner; no board I/O."""
from pathlib import Path
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.core.manager import Manager
from backend.gui_test.core.models import TestError, digest, uid
from backend.gui_test.core.sources import SourceService
from backend.gui_test.core.store import Store
from backend.gui_test.execution.host import Host, create_app
from .test_windows_runner import TOKEN, BOARD, TEMPLATE, done


def prepared(tmp_path):
    root = tmp_path / 'registered source'
    (root / 'support').mkdir(parents=True)
    (root / 'support' / 'payload.bin').write_bytes(b'\x00\xfffrozen auxiliary data')
    (root / 'case.py').write_text(
        "from pathlib import Path\n"
        "assert (Path(__file__).parent / 'support/payload.bin').read_bytes() == b'\\x00\\xfffrozen auxiliary data'\n"
        "print('FROZEN AUXILIARY OK', flush=True)\nprint('Test Result: PASS', flush=True)\n", encoding='utf-8')
    service = SourceService(Store(tmp_path / 'manager' / 'runs.db'))
    inspection = service.inspect('server-folder', str(root))
    service.apply(inspection['inspection_id'], None, 0)
    return root, service


def test_selected_source_transfers_and_executes_exact_auxiliary_bytes_without_retargeting_host(tmp_path):
    """T-179: harmless Python consumes the registered snapshot, not Host.root or edited originals."""
    root, service = prepared(tmp_path)
    legacy = tmp_path / 'legacy runner source'
    legacy.mkdir()
    (legacy / 'legacy.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
    original = (root / 'case.py').read_bytes()
    (root / 'case.py').write_text("raise RuntimeError('must not execute original')\n", encoding='utf-8')
    (root / 'support' / 'payload.bin').write_bytes(b'modified after registration')
    host = Host({'source_root': str(legacy), 'python': sys.executable, 'boards': [BOARD]},
                tmp_path / 'runner', ports=lambda: {BOARD['com']})
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1', 50000)) as client:
        remote = WindowsRemote('http://localhost', TOKEN, client=client)
        descriptor = service.descriptor()
        directory = service.directory(descriptor)
        remote.prepare_source(directory, descriptor)
        # A repeated upload acknowledges the same immutable snapshot.
        remote.prepare_source(directory, descriptor)
        identity = uid()
        logs = []
        result = remote.execute({'id': 'case.py', 'path': 'case.py', 'kind': 'Single'}, {'a': BOARD, 'b': None}, 10,
            {'process_ref': 'windows:' + identity, 'source_revision': descriptor['source_revision'],
             'command_template': TEMPLATE, 'source_snapshot': descriptor, 'source_directory': str(directory)},
            lambda stream, text: logs.append((stream, text)), lambda: False)
        assert result['terminated'] is True and result['exit_code'] == 0
        assert 'FROZEN AUXILIARY OK' in ''.join(text for _, text in logs)
        assert 'Test Result: PASS' in ''.join(text for _, text in logs)
        attempt = Path(result['executed_command_argv'][1]).parent
        assert attempt.is_relative_to(host.runtime / 'snapshots')
        assert (attempt / 'case.py').read_bytes() == original
        assert (attempt / 'support/payload.bin').read_bytes() == b'\x00\xfffrozen auxiliary data'
        assert host.root == legacy.resolve()
        assert {item['path'] for item in remote.catalog()['tests']} == {'legacy.py'}
        assert (root / 'support/payload.bin').read_bytes() == b'modified after registration'
        assert (legacy / 'legacy.py').read_text(encoding='utf-8') == "print('Test Result: PASS')\n"


def test_old_runner_explicitly_rejects_registered_sources_but_legacy_remains_ready(tmp_path):
    """T-179: absence of snapshot capability never falls back to unrelated shared files."""
    _, service = prepared(tmp_path)
    requests = []
    def respond(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={'runner_id': 'old-runner'})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        remote = WindowsRemote('http://localhost', TOKEN, client=client)
        manager = Manager(Store(tmp_path / 'other' / 'runs.db'), mode='dashboard', adapter=remote)
        assert manager.source_state()['execution']['ready'] is True
        manager.sources = service
        assert manager.source_state()['execution']['code'] == 'SOURCE_SNAPSHOT_UNSUPPORTED'
        with pytest.raises(TestError) as unsupported:
            remote.prepare_source(service.directory(service.descriptor()), service.descriptor())
        assert unsupported.value.code == 'SOURCE_SNAPSHOT_UNSUPPORTED'
    assert requests == ['/v1/identity'] * 3


def test_mismatched_upload_acknowledgement_is_rejected_without_execution(tmp_path):
    """T-179: a successful HTTP response must acknowledge the exact frozen identity."""
    _, service = prepared(tmp_path)
    paths = []
    def respond(request):
        paths.append(request.url.path)
        if request.url.path == '/v1/identity': return httpx.Response(200, json={'source_snapshot_v1': True})
        return httpx.Response(200, json={'snapshot_id': '0' * 64, 'source_revision': service.descriptor()['source_revision']})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        remote = WindowsRemote('http://localhost', TOKEN, client=client)
        with pytest.raises(TestError) as rejected:
            remote.prepare_source(service.directory(service.descriptor()), service.descriptor())
        assert rejected.value.code == 'SOURCE_CHANGED'
    assert paths == ['/v1/identity', '/v1/source-snapshots/' + service.descriptor()['snapshot_id']]


def test_legacy_execution_hash_omits_optional_snapshot_id(tmp_path):
    """T-179: existing clients keep their request identity when the new field is absent."""
    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    (legacy / 'case.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
    host = Host({'source_root': str(legacy), 'python': sys.executable, 'boards': [BOARD]},
                tmp_path / 'runner', ports=lambda: {BOARD['com']})
    try:
        payload = {'id': uid(), 'tc_id': 'case.py', 'source_revision': host.catalog()['revision'],
                   'connection': {'a': BOARD, 'b': None}, 'template': TEMPLATE}
        started = host.start(payload)
        assert started['request_hash'] == digest(payload)
        finished = done(host, payload['id'])
        assert finished['exit_code'] == 0 and finished['terminated'] is True
        assert host.start(payload)['request_hash'] == digest(payload)
    finally:
        host.close()


def test_authenticated_upload_supports_long_host_runtime_staging(tmp_path):
    """T-179 / REG0064: HTTP upload staging must support long runtime paths too."""
    from backend.gui_test.execution import source_snapshots as snapshots
    _, service = prepared(tmp_path)
    legacy = tmp_path / 'legacy'
    legacy.mkdir()
    (legacy / 'legacy.py').write_bytes(b"print('Test Result: PASS')\n")
    runtime = tmp_path / 'long-host-runtime'
    # Keep executions.db below the old Windows limit, while the upload's
    # temporary staging child and final 64-character snapshot exceed it.
    while len(str(runtime.resolve())) < 235:
        room = 235 - len(str(runtime.resolve())) - 1
        runtime /= 'r' * max(1, min(22, room))
    host = Host({'source_root': str(legacy), 'python': sys.executable, 'boards': [BOARD]},
                runtime, ports=lambda: {BOARD['com']})
    descriptor = service.descriptor()
    with snapshots.create_archive(service.directory(descriptor), descriptor) as stream:
        payload = stream.read()
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1', 50000)) as client:
        reply = client.put('/v1/source-snapshots/' + descriptor['snapshot_id'], content=payload,
                           headers={'Authorization': 'Bearer ' + TOKEN, 'Content-Type': 'application/zip'})
        assert reply.status_code == 200
        assert reply.json() == {'snapshot_id': descriptor['snapshot_id'], 'source_revision': descriptor['source_revision']}
        uploaded = host.runtime / 'source-snapshots' / descriptor['snapshot_id']
        assert len(str(uploaded / snapshots.MANIFEST)) >= 300
        assert snapshots.load_manifest(uploaded)['source_revision'] == descriptor['source_revision']
        attempt = tmp_path / 'uploaded-attempt'
        catalog = snapshots.copy_snapshot(uploaded, attempt, descriptor['source_revision'])
        assert [tc['path'] for tc in catalog['tests']] == ['case.py']
        assert (attempt / 'support/payload.bin').read_bytes() == b'\x00\xfffrozen auxiliary data'
        assert host.root == legacy.resolve()
