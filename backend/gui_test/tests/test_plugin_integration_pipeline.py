"""T-204/205/207: real Windows batch orchestration with fake I/O and RX only."""
import pytest

from backend.gui_test.core.models import TestError, uid
from backend.gui_test.execution import flashing as flashing_module
from backend.gui_test.execution import host as host_module
from backend.gui_test.execution.console_observer import ConsoleObserver
from backend.gui_test.execution.installer_snapshots import freeze_installer
from backend.gui_test.tests.test_flashing import rig, completed, TEMPLATE, A


@pytest.fixture
def batch_rig(rig, monkeypatch):
    host, io, request, images, source, profile = rig
    for key, cfg in profile['boards'].items():
        cfg['login_prompt'] = cfg['boot_marker']
        cfg['observer'] = {'port': 'COM41' if key == 'a' else 'COM42',
                           'rx_only_confirmed': True, 'control_lines_isolated': True,
                           'panic_signatures': ['Kernel panic'], 'boot_signatures': ['BOOT START'],
                           'login_markers': [cfg['login_prompt']]}
    class RX:
        def read(self, size): return b''
        def close(self): pass
    monkeypatch.setattr(flashing_module, 'ConsoleObserver', lambda directory, config: ConsoleObserver(directory, config, source=RX()))
    descriptor = freeze_installer(str(images / 'flash.bat'), [str(images.parent)], host.runtime / 'installer-snapshots')
    parent = host.batches.reserve({'id': uid(), 'runner_id': host.identity, 'request_id': 'one-physical-intent',
                                  'connection': request()['connection']})
    payload = {'id': uid(), 'token': parent['token'], 'epoch': parent['epoch'], 'profile': 'fixture',
               'profile_revision': host.flashing.profile_info('fixture')['revision'],
               'snapshot_id': descriptor['snapshot_id'], 'manifest': descriptor,
               'connection': request()['connection'], 'source_revision': host.catalog()['revision']}
    original_flash = io.flash
    def observed_flash(*args):
        value = original_flash(*args)
        observer = host.flashing.observers[parent['id']][0]
        observer.feed(b'BOOT START\n')
        observer.feed(b'BOOT_READY')
        return value
    io.flash = observed_flash
    yield host, io, parent, payload
    host.flashing.close_observers(parent['id'])


def test_prepare_replay_flashes_once_then_closes_control_com_while_parent_stays_held(batch_rig):
    host, io, parent, payload = batch_rig
    host.flashing.start_prepare(parent['id'], payload)
    result = completed(host, payload['id'])
    host.threads[-1].join(timeout=3)
    assert result['state'] == 'DONE' and result['phase'] == 'READY'
    assert result['flashes'][0]['fresh_login_ready'] is True
    assert host.batches.status(parent['id'])['state'] == 'READY'
    host.flashing.start_prepare(parent['id'], payload)
    assert sum(event[0] == 'flash' for event in io.events) == 1
    assert io.events[-1][0] == 'close'
    with pytest.raises(TestError) as error:
        host.start({'id': uid(), 'tc_id': 'single.py', 'source_revision': host.catalog()['revision'],
                    'connection': payload['connection'], 'template': TEMPLATE})
    assert error.value.code == 'RESERVATION_CONFLICT'
    assert not any(event[0] == 'tc' for event in io.events)


@pytest.mark.parametrize('field', ['serial', 'batch_sha256', 'success_marker'])
def test_mutated_runner_profile_is_rejected_before_first_hardware_command(batch_rig, field):
    host, io, parent, payload = batch_rig
    profile = host.flashing.config['profiles']['fixture']
    if field == 'serial': profile['boards']['a']['serial'] = 'changed-target'
    elif field == 'batch_sha256': profile[field] = '0' * 64
    else: profile[field] = 'different-success-marker'
    with pytest.raises(TestError) as error:
        host.flashing.start_prepare(parent['id'], payload)
    assert error.value.code == 'FLASH_PROFILE_CHANGED'
    assert io.events == [] and host.batches.status(parent['id'])['state'] == 'RESERVED'


@pytest.mark.parametrize('failure', ['boot', 'serial', 'panic', 'gap'])
def test_pre_tc_failure_keeps_parent_unknown_and_blocks_next_work(batch_rig, failure):
    host, io, parent, payload = batch_rig
    if failure in {'boot', 'serial'}: io.fail = failure
    original = io.flash
    def flash(*args):
        value = original(*args)
        observer = host.flashing.observers[parent['id']][0]
        if failure == 'panic': observer.feed(b'Kernel panic')
        if failure == 'gap': observer.gap('DISCONNECTED')
        return value
    io.flash = flash
    host.flashing.start_prepare(parent['id'], payload)
    result = completed(host, payload['id'])
    host.threads[-1].join(timeout=3)
    assert result['state'] == 'UNKNOWN' and result['phase'] == 'UNKNOWN'
    assert host.batches.status(parent['id'])['state'] == 'UNKNOWN'
    assert not any(event[0] == 'tc' for event in io.events)
    with pytest.raises(TestError) as error:
        host.batches.release(parent['id'], {'token': parent['token'], 'epoch': parent['epoch']})
    assert error.value.code == 'HARDWARE_UNKNOWN'


@pytest.mark.parametrize('unsafe', ['panic', 'gap'])
def test_console_failure_during_final_capture_drain_cannot_publish_child_pass(batch_rig, monkeypatch, unsafe):
    host, _, parent, payload = batch_rig
    host.flashing.start_prepare(parent['id'], payload)
    completed(host, payload['id']); host.threads[-1].join(timeout=3)
    observer = host.flashing.observers[parent['id']][0]
    class Tree:
        def __init__(self, *args, **kwargs):
            self.process = type('Process', (), {'stdout': None, 'stderr': None, 'poll': lambda self: 0})()
        def stopped(self): return True
        def stop(self): return True
        def close(self): pass
    class Capture:
        def __init__(self, *args, **kwargs): pass
        def snapshot(self): return {'stdout': 'Test Result: PASS\n', 'stderr': ''}, False
        def drain(self):
            if unsafe == 'panic': observer.feed(b'Kernel panic')
            else: observer.gap('DISCONNECTED')
            return True
    monkeypatch.setattr(host_module, 'ProcessTree', Tree)
    monkeypatch.setattr(host_module, 'Capture', Capture)
    child = host.start({'id': uid(), 'tc_id': 'single.py', 'source_revision': host.catalog()['revision'],
        'connection': payload['connection'], 'template': TEMPLATE,
        'batch_id': parent['id'], 'batch_token': parent['token'], 'batch_epoch': parent['epoch']})
    result = completed(host, child['id']); host.threads[-1].join(timeout=3)
    assert result.get('forced_state') in {'ERROR', 'UNKNOWN'}, result
    assert host.batches.status(parent['id'])['state'] == 'UNKNOWN'
    with pytest.raises(TestError):
        host.batches.release(parent['id'], {'token': parent['token'], 'epoch': parent['epoch']})
