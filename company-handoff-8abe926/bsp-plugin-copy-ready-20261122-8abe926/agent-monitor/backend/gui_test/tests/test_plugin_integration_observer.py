"""T-205/207: RX evidence is epoch scoped; no real serial port is opened."""
import json
import queue
import threading

import pytest

from backend.gui_test.core.models import TestError
from backend.gui_test.execution.console_observer import ConsoleObserver


@pytest.fixture
def observer(tmp_path):
    value = ConsoleObserver(tmp_path / 'console', {'panic_signatures': ['Kernel panic - not syncing'],
        'boot_signatures': ['BOOT START'], 'login_markers': ['로그인:']})
    yield value
    value.close()


def test_chunked_utf8_login_and_kernel_panic_are_observed_in_current_epoch(observer):
    start = observer.boundary('BOOT_WAIT', boot=True, expected_boot=True)
    for data in [b'BOOT ST', b'ART\n', '로그인:'.encode()[:2], '로그인:'.encode()[2:],
                 b'Kernel pa', b'nic - not syncing']:
        observer.feed(data)
    evidence = observer.evidence(start)
    assert evidence['panic'] is True and evidence['unexpected_boot'] is False
    assert evidence['complete'] is True
    assert {e['kind'] for e in evidence['events']} == {'panic_signatures', 'boot_signatures', 'login_markers'}


def test_boot_boundary_never_reuses_old_login_or_combines_stale_partial(observer):
    observer.feed('로그인:'.encode())
    observer.feed(b'Kernel pa')
    start = observer.boundary('POST_FLASH_BOOT', boot=True)
    observer.feed(b'nic - not syncing')
    evidence = observer.evidence(start)
    assert evidence['events'] == [] and evidence['panic'] is False
    observer.feed('로그인:'.encode())
    assert [e['kind'] for e in observer.evidence(start)['events']] == ['login_markers']


def test_phase_boundary_discards_incomplete_utf8_without_fabricating_marker(observer):
    encoded = '로그인:'.encode()
    observer.feed(encoded[:2])
    start = observer.boundary('TC')
    observer.feed(encoded[2:])
    evidence = observer.evidence(start)
    assert evidence['events'] == [] and evidence['complete'] is False
    assert any(g['reason'] == 'DECODE_ERROR' for g in evidence['gaps'])


def test_acquisition_gap_invalidates_evidence_and_does_not_bridge_partial_panic(observer):
    start = observer.boundary('TC')
    observer.feed(b'Kernel pa')
    observer.gap('DISCONNECTED')
    observer.feed(b'nic - not syncing')
    evidence = observer.evidence(start)
    assert evidence['panic'] is False and evidence['complete'] is False
    assert evidence['gaps'][0]['reason'] == 'DISCONNECTED'


def test_full_disk_queue_never_waits_for_the_producer_and_records_dropped_byte_range(observer, monkeypatch):
    start = observer.boundary('TC')
    def full(record):
        raise queue.Full
    monkeypatch.setattr(observer.queue, 'put_nowait', full)
    finished = threading.Event()
    def receive():
        observer.feed(b'new console bytes')
        finished.set()
    producer = threading.Thread(target=receive, daemon=True)
    producer.start()
    assert finished.wait(.5), 'RX producer must not wait for disk queue capacity'
    evidence = observer.evidence(start)
    gap = evidence['gaps'][-1]
    assert gap['reason'] == 'QUEUE_OVERFLOW'
    assert gap['start'] == start['offset'] and gap['end'] == start['offset'] + len(b'new console bytes')
    assert evidence['complete'] is False


def test_retention_rotation_is_distinct_from_acquisition_loss(tmp_path):
    observer = ConsoleObserver(tmp_path / 'console', {'rotate_bytes': 240, 'rotate_count': 2})
    try:
        for _ in range(6):
            observer.feed(b'console data ' * 6)
            observer.queue.join()
        evidence = observer.evidence({'offset': 0, 'boot_epoch': 0, 'phase_epoch': 0})
        assert evidence['rotations'] > 0 and evidence['retained_from'] > 0
        assert evidence['gaps'] == [] and evidence['complete'] is True
    finally:
        observer.close()
    receipt = json.loads((tmp_path / 'console/receipt.json').read_text(encoding='utf-8'))
    assert receipt['retained_from'] > 0 and receipt['gaps'] == []


def test_overlong_marker_is_rejected_before_observer_thread_starts(tmp_path):
    with pytest.raises(TestError):
        ConsoleObserver(tmp_path / 'invalid', {'panic_signatures': ['x' * 1025]})
