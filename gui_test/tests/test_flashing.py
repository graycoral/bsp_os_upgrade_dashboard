"""Flash pipeline contract tests. Every device operation is an injected fake."""
import hashlib
import threading
import time

import pytest
from fastapi.testclient import TestClient

from gui_test.core.models import TestError, uid
from gui_test.execution.host import Host, create_app
from gui_test.execution import flashing as flashing_module
from gui_test.execution.flashing import UnknownHardware


TOKEN = 'local-test-token-only-0123456789abcdef'
A = {'host': 'fixture-pc', 'board_id': 'a', 'com': 'COM31'}
B = {'host': 'fixture-pc', 'board_id': 'b', 'com': 'COM32'}
TEMPLATE = {'single': ['python', '{tc_path}', '-p', '{com_a}'],
            'dual': ['python', '{tc_path}', '-n', '{node_a}', '-n2', '{node_b}']}


class Console:
    def __init__(self, io, cfg):
        self.io, self.cfg = io, cfg
        self.closed = False
        io.events.append(('open', cfg['serial']))

    def command(self, value):
        assert value in {'reboot lkshell', 'fast'}
        self.io.events.append((value, self.cfg['serial']))

    def wait(self, marker, timeout):
        assert marker in {self.cfg['lkshell_prompt'], self.cfg['boot_marker']}
        self.io.events.append(('wait:' + marker, self.cfg['serial']))
        if self.io.fail == 'boot' and marker == self.cfg['boot_marker']:
            raise TestError('No boot marker', 'CONSOLE_TIMEOUT')

    def close(self):
        self.closed = True
        self.io.events.append(('close', self.cfg['serial']))


class FakeIO:
    def __init__(self):
        self.events = []
        self.fail = None
        self.tc_results = []

    def console(self, cfg):
        return Console(self, cfg)

    def devices(self, profile):
        serial = self.events[-1][1]
        self.events.append(('devices', serial))
        return ['intruder'] if self.fail == 'serial' else [serial]

    def flash(self, profile, cfg, directory, batch):
        assert (directory / batch).is_file()
        self.events.append(('flash', cfg['serial']))
        return {'stdout': '' if self.fail == 'no-marker' else 'FLASH COMPLETE',
                'stderr': 'FAILED' if self.fail == 'batch-error' else '',
                'exit_code': 1 if self.fail == 'batch-exit' else 0,
                'terminated': True}

    def run(self, argv, cwd, timeout):
        assert not any(event[0] == 'open' for event in self.events[-1:])
        self.events.append(('tc', argv[1]))
        return self.tc_results.pop(0) if self.tc_results else {
            'stdout': 'Test Result: PASS\n', 'stderr': '', 'exit_code': 0, 'terminated': True}


@pytest.fixture
def rig(tmp_path):
    source = tmp_path / 'tc'; source.mkdir()
    (source / 'single.py').write_text("print('Test Result: PASS')\n")
    (source / 'dual').mkdir()
    (source / 'dual' / 'pair.py').write_text("print('Test Result: PASS')\n")
    images = tmp_path / 'images' / 'release'; images.mkdir(parents=True)
    (images / 'flash.bat').write_bytes(b'@echo off\n')
    (images / 'image.bin').write_bytes(b'fixture-image')
    digest = lambda name: hashlib.sha256((images / name).read_bytes()).hexdigest()
    manifest = {'schema_version': 1, 'batch': 'flash.bat',
                'files': {name: digest(name) for name in ('flash.bat', 'image.bin')}}
    fastboot = tmp_path / 'fastboot.exe'; fastboot.write_bytes(b'fake executable, never launched')
    boards = {key: {'com': board['com'], 'baudrate': 115200, 'line_ending': 'cr',
                    'lkshell_prompt': 'lkshell>', 'boot_marker': 'BOOT_READY', 'serial': 'serial-' + key}
              for key, board in [('a', A), ('b', B)]}
    profile = {'enabled': True, 'image_root': str(tmp_path / 'images'), 'fastboot': str(fastboot),
               'batch_sha256': manifest['files']['flash.bat'], 'success_marker': 'FLASH COMPLETE',
               'failure_markers': ['FAILED'], 'boards': boards}
    config = {'source_root': str(source), 'boards': [A, B],
              'flashing': {'profiles': {'fixture': profile}}}
    host = Host(config, tmp_path / 'runtime', ports=lambda: {'COM31', 'COM32'})
    io = FakeIO(); host.flashing.io = io
    catalog = host.catalog()

    def request(dual=False):
        ids = ['single.py', 'dual/pair.py'] if dual else ['single.py']
        tests = [next(tc for tc in catalog['tests'] if tc['id'] == identity) for identity in ids]
        return {'id': uid(), 'runner_id': host.identity, 'profile': 'fixture', 'bundle': 'release', 'manifest': manifest,
                'source_revision': catalog['revision'], 'connection': {'a': A | {'node': 'n295'},
                'b': B | {'node': 'n296'} if dual else None}, 'template': TEMPLATE,
                'cases': {'boot': ['single.py'], 'functional': ids}, 'tests': tests,
                'baseline': {'attempt_id': 'fixture-attempt'}}

    # The catalog's boards include node identity when configured.
    host.configured_boards = [A | {'node': 'n295'}, B | {'node': 'n296'}]
    yield host, io, request, images, source, profile
    host.close()


def completed(host, identity):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = host.get(identity)
        if value['state'] != 'RUNNING':
            return value
        time.sleep(.01)
    pytest.fail('Fake pipeline did not finish')


def test_dual_flash_is_sequential_and_com_released_before_mapped_tc(rig):
    host, io, request, *_ = rig
    payload = request(dual=True)
    host.flashing.start(payload)
    result = completed(host, payload['id'])
    assert result['state'] == 'DONE' and result['outcome'] == 'SUCCEEDED'
    assert result['cases'] == {'boot': 'PASS', 'functional': 'PASS'}
    assert [f['serial'] for f in result['flashes']] == ['serial-a', 'serial-b']
    assert all(f['boot_ready'] for f in result['flashes'])
    assert [t['tc_id'] for t in result['tests']] == ['single.py', 'dual/pair.py']
    assert [e[0] for e in io.events].count('flash') == 2
    assert io.events.index(('flash', 'serial-a')) < io.events.index(('reboot lkshell', 'serial-b'))
    assert io.events.index(('close', 'serial-b')) < next(i for i, e in enumerate(io.events) if e[0] == 'tc')
    assert all(io.events.index(('reboot lkshell', serial)) < io.events.index(('wait:lkshell>', serial))
               < io.events.index(('fast', serial)) < io.events.index(('devices', serial))
               < io.events.index(('flash', serial)) < io.events.index(('wait:BOOT_READY', serial))
               for serial in ('serial-a', 'serial-b'))


@pytest.mark.parametrize('cause,reason', [('serial', 'BOARD_MISMATCH'), ('batch-error', 'FLASH_FAILED'),
                                           ('batch-exit', 'FLASH_FAILED'), ('no-marker', 'FLASH_FAILED'),
                                           ('boot', 'CONSOLE_TIMEOUT')])
def test_device_failures_never_start_tc(rig, cause, reason):
    host, io, request, *_ = rig
    io.fail = cause
    payload = request()
    host.flashing.start(payload)
    result = completed(host, payload['id'])
    assert result['outcome'] == 'FAILED' and result['reason'] == reason
    assert not result['tests'] and not any(event[0] == 'tc' for event in io.events)


@pytest.mark.parametrize('stdout,exit_code,expected', [
    ('Test Result: FAIL\n', 0, 'FAILED'),
    ('Test Result: PASS\n', 1, 'FAILED'),
    ('noise PASS only\n', 0, 'FAILED'),
])
def test_tc_verdicts_are_not_inferred_from_unstructured_text(rig, stdout, exit_code, expected):
    host, io, request, *_ = rig
    io.tc_results = [{'stdout': stdout, 'stderr': '', 'exit_code': exit_code, 'terminated': True}]
    payload = request()
    host.flashing.start(payload)
    result = completed(host, payload['id'])
    assert result['outcome'] == expected
    if stdout.startswith('Test Result: FAIL'):
        assert result['cases'] == {'boot': 'FAIL', 'functional': 'FAIL'}
        assert result['reason'] == ''
    else:
        assert result['reason'] == 'TC_EXECUTION'


def test_image_change_is_rejected_before_any_device_command(rig):
    host, io, request, images, *_ = rig
    payload = request()
    (images / 'image.bin').write_bytes(b'changed after manifest')
    host.flashing.start(payload)
    result = completed(host, payload['id'])
    assert result['reason'] == 'IMAGE_CHANGED'
    assert io.events == []


def test_image_growth_during_copy_hits_streaming_capacity_limit(rig, monkeypatch):
    from pathlib import Path
    from gui_test.execution.flashing import FlashRequest
    host, io, request, images, source, profile = rig
    payload = request()
    profile['max_bundle_bytes'] = sum((images / name).stat().st_size for name in payload['manifest']['files'])
    original_open = Path.open
    image = images / 'image.bin'

    def growing_open(path, mode='r', *args, **kwargs):
        if path == image and mode == 'rb':
            with original_open(path, 'ab') as writable:
                writable.write(b'growth')
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', growing_open)
    with pytest.raises(TestError) as exc:
        host.flashing.copy_bundle(FlashRequest.model_validate(payload), profile,
                                  host.runtime / 'growing-copy')
    assert exc.value.code == 'IMAGE_SPACE'
    assert io.events == []


def test_snapshot_and_profile_require_reviewed_exact_inputs(rig):
    host, io, request, images, source, profile = rig
    payload = request()
    (source / 'single.py').write_text('changed')
    host.flashing.start(payload)
    assert completed(host, payload['id'])['reason'] == 'SOURCE_CHANGED'
    assert io.events == []
    source.joinpath('single.py').write_text("print('Test Result: PASS')\n")
    profile['boards']['a'].pop('boot_marker')
    bad = request()
    with pytest.raises(TestError) as exc:
        host.flashing.start(bad)
    assert exc.value.code == 'FLASH_NOT_CONFIGURED'
    assert io.events == []


def test_pinned_tc_metadata_and_case_ids_are_checked_before_device_io(rig):
    host, io, request, *_ = rig
    changed = request()
    changed['tests'][0]['parser'] = {'allowed_codes': [7]}
    host.flashing.start(changed)
    assert completed(host, changed['id'])['reason'] == 'SOURCE_CHANGED'
    assert io.events == []
    duplicate = request()
    duplicate['cases']['functional'] = ['single.py', 'single.py']
    with pytest.raises(TestError) as exc:
        host.flashing.start(duplicate)
    assert exc.value.code == 'CASE_MAPPING'
    assert io.events == []


def test_duplicate_fastboot_identity_fails_closed(rig):
    host, io, request, images, source, profile = rig
    profile['boards']['b']['serial'] = profile['boards']['a']['serial']
    with pytest.raises(TestError) as exc:
        host.flashing.start(request(dual=True))
    assert exc.value.code == 'BOARD_MISMATCH'
    assert io.events == []


@pytest.mark.parametrize('field,value', [('schema_version', True), ('batch', ['flash.bat'])])
def test_malformed_manifest_is_rejected_as_contract_error(rig, field, value):
    from gui_test.execution.flashing import validate_manifest
    host, io, request, *_ = rig
    manifest = request()['manifest'] | {field: value}
    with pytest.raises(TestError) as exc:
        validate_manifest(manifest)
    assert exc.value.code == 'IMAGE_MANIFEST'
    assert io.events == []


def test_duplicate_id_replay_and_host_reservation(rig):
    host, io, request, *_ = rig
    payload = request()
    initial = host.flashing.start(payload)
    replay = host.flashing.start(payload)
    assert replay['id'] == initial['id']
    with pytest.raises(TestError) as exc:
        host.flashing.start(payload | {'profile': 'different'})
    assert exc.value.code == 'IDEMPOTENCY_CONFLICT'
    completed(host, payload['id'])
    assert sum(e[0] == 'flash' for e in io.events) == 1


def test_flash_reserves_host_against_common_tc_and_does_not_use_tc_lease(rig):
    host, io, request, *_ = rig
    entered, release = threading.Event(), threading.Event()
    original = io.flash

    def held_flash(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)

    io.flash = held_flash
    payload = request()
    host.flashing.start(payload)
    assert entered.wait(3)
    assert payload['id'] not in host.leases
    with pytest.raises(TestError) as exc:
        host.flashing.start(request())
    assert exc.value.code == 'RESERVATION_CONFLICT'
    tc = {'id': uid(), 'tc_id': 'single.py', 'source_revision': host.catalog()['revision'],
          'connection': {'a': A | {'node': 'n295'}}, 'template': TEMPLATE}
    with pytest.raises(TestError) as exc:
        host.start(tc)
    assert exc.value.code == 'RESERVATION_CONFLICT'
    # A missing browser poll cannot expire a flash (unlike a standalone TC lease).
    time.sleep(.05)
    assert host.get(payload['id'])['state'] == 'RUNNING'
    release.set()
    assert completed(host, payload['id'])['outcome'] == 'SUCCEEDED'


@pytest.mark.parametrize('capture_error,flashing,stop_result', [
    (False, True, False), (True, True, True), (False, False, False),
])
def test_process_setup_and_stop_failures_preserve_unknown_hardware(
        rig, monkeypatch, capture_error, flashing, stop_result):
    host, *_ = rig
    trees = []

    class BrokenTree:
        def __init__(self, *args, **kwargs):
            self.process = type('Process', (), {'stdout': None, 'stderr': None})()
            self.closed = False
            trees.append(self)

        def stopped(self):
            raise OSError('process status unavailable')

        def stop(self):
            return stop_result

        def close(self):
            self.closed = True

    def broken_capture(*args, **kwargs):
        if capture_error:
            raise OSError('capture initialization failed after launch')
        return object()

    monkeypatch.setattr(flashing_module, 'ProcessTree', BrokenTree)
    monkeypatch.setattr(flashing_module, 'Capture', broken_capture)
    with pytest.raises(UnknownHardware) as exc:
        host.flashing.run(['fake'], host.runtime, 1, flashing=flashing)
    assert exc.value.code == 'HARDWARE_UNKNOWN'
    assert len(trees) == 1 and trees[0].closed


@pytest.mark.parametrize('ending,suffix', [('cr', b'\r'), ('lf', b'\n'), ('crlf', b'\r\n')])
def test_serial_console_discards_stale_prompt_before_command(monkeypatch, ending, suffix):
    from collections import deque
    import serial
    from gui_test.execution.flashing import SerialConsole

    class Port:
        def __init__(self):
            self.input = deque()
            self.writes = []
            self.resets = 0
            self.closed = False

        def reset_input_buffer(self):
            self.input.clear()
            self.resets += 1

        def read(self, count):
            return self.input.popleft() if self.input else b''

        def write(self, data):
            self.writes.append(data)

        def flush(self):
            pass

        def close(self):
            self.closed = True

    port = Port()
    monkeypatch.setattr(serial, 'Serial', lambda **kwargs: port)
    console = SerialConsole({'com': 'COM31', 'baudrate': 115200, 'line_ending': ending})
    try:
        port.input.append(b'lkshell>')
        deadline = time.monotonic() + 1
        while b'lkshell>' not in console.buffer and time.monotonic() < deadline:
            time.sleep(.002)
        assert b'lkshell>' in console.buffer
        console.command('reboot lkshell')
        assert port.writes == [b'reboot lkshell' + suffix]
        assert port.resets >= 2
        with pytest.raises(TestError) as exc:
            console.wait('lkshell>', .06)
        assert exc.value.code == 'CONSOLE_TIMEOUT'
        port.input.append(b'lkshell>')
        console.wait('lkshell>', .5)
    finally:
        console.close()
    assert port.closed


def test_http_reconcile_tombstone_and_restart_unknown(rig):
    host, io, request, *_ = rig
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1', 50000)) as client:
        headers = {'Authorization': 'Bearer ' + TOKEN}
        assert client.get('/v1/identity', headers=headers).json() == {'runner_id': host.identity}
        absent = request()
        tombstone = client.post(f"/v1/executions/{absent['id']}/reconcile", headers=headers).json()
        assert tombstone['not_started'] is True and tombstone['runner_id'] == host.identity
        reply = client.post('/v1/flash-tests', headers=headers, json=absent)
        assert reply.status_code == 409
        assert io.events == []
        active = request()
        host.flashing.start(active)
        completed(host, active['id'])
        assert client.post(f"/v1/executions/{active['id']}/cancel", headers=headers).status_code == 409
    # A persisted RUNNING record after a process restart must require reconciliation.
    pending = request()
    from gui_test.core.models import digest
    import json, sqlite3
    record = {'id': pending['id'], 'kind': 'flash-test', 'state': 'RUNNING', 'terminated': False}
    with sqlite3.connect(host.db) as db:
        db.execute('INSERT INTO jobs VALUES(?,?,?)', (pending['id'], digest(pending), json.dumps(record)))
    host.recover()
    assert host.get(pending['id'])['state'] == 'UNKNOWN'
    with pytest.raises(TestError) as exc:
        host.flashing.start(request())
    assert exc.value.code == 'RESERVATION_CONFLICT'


def test_runner_identity_persists_in_same_runtime_and_changes_with_new_runtime(rig):
    host, io, request, images, source, profile = rig
    original = host.identity
    config = {'source_root': str(source), 'boards': [A, B],
              'flashing': {'profiles': {'fixture': profile}}}
    same = Host(config, host.runtime, ports=lambda: {'COM31', 'COM32'})
    other = Host(config, host.runtime.parent / 'other-runtime', ports=lambda: {'COM31', 'COM32'})
    try:
        assert same.identity == original
        assert other.identity != original
        same.flashing.io = io
        with pytest.raises(TestError) as exc:
            same.flashing.start(request() | {'runner_id': other.identity})
        assert exc.value.code == 'RUNNER_CHANGED'
        assert io.events == []
    finally:
        same.close()
        other.close()
