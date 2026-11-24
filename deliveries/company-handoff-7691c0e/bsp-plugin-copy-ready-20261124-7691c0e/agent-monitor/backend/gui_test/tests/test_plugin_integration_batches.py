"""T-204/207: durable host-wide reservation across gaps, failures and restart."""
import json
import sqlite3

import pytest

from backend.gui_test.core.models import TestError, uid
from backend.gui_test.execution.batches import BatchReservations
from backend.gui_test.execution.host import Host


A = {'host': 'fixture-pc', 'board_id': 'a', 'com': 'COM31'}
TEMPLATE = {'single': ['python', '{tc_path}', '{com_a}'],
            'dual': ['python', '{tc_path}', '{com_a}', '{com_b}']}


@pytest.fixture
def rig(tmp_path):
    source = tmp_path / 'tc'; source.mkdir()
    (source / 'case.py').write_text("print('Test Result: PASS')")
    host = Host({'source_root': str(source), 'boards': [A]}, tmp_path / 'runtime', ports=lambda: {'COM31'})
    batch = BatchReservations(host)
    request = {'id': uid(), 'runner_id': host.identity, 'request_id': 'one-intent', 'connection': {'a': A}}
    yield host, batch, request
    host.close()


def test_parent_replay_is_idempotent_but_changed_request_conflicts(rig):
    _, batches, request = rig
    receipt = batches.reserve(request)
    assert batches.reserve(request) == receipt
    with pytest.raises(TestError) as error:
        batches.reserve(request | {'request_id': 'different-intent'})
    assert error.value.code == 'IDEMPOTENCY_CONFLICT'


def test_parent_holds_host_when_no_child_runs_and_blocks_legacy_tc(rig):
    host, batches, request = rig
    batches.reserve(request)
    with pytest.raises(TestError) as error:
        host.start({'id': uid(), 'tc_id': 'case.py', 'source_revision': host.catalog()['revision'],
                    'connection': {'a': A}, 'template': TEMPLATE})
    assert error.value.code == 'RESERVATION_CONFLICT'
    with pytest.raises(TestError) as error:
        batches.reserve(request | {'id': uid(), 'request_id': 'competing-intent'})
    assert error.value.code == 'RESERVATION_CONFLICT'


@pytest.mark.parametrize('wrong', ['token', 'epoch', 'bool-epoch'])
def test_stale_owner_cannot_validate_cancel_or_release_parent(rig, wrong):
    _, batches, request = rig
    receipt = batches.reserve(request)
    auth = {'token': receipt['token'], 'epoch': receipt['epoch']}
    if wrong == 'token': auth['token'] = 'unrelated-owner-token'
    elif wrong == 'epoch': auth['epoch'] += 1
    else: auth['epoch'] = True
    for operation in (lambda: batches.validate(receipt['id'], **auth),
                      lambda: batches.cancel(receipt['id'], auth),
                      lambda: batches.release(receipt['id'], auth)):
        with pytest.raises(TestError) as error:
            operation()
        assert error.value.code == 'BATCH_STALE'
    assert batches.status(receipt['id'])['state'] == 'RESERVED'


def test_unknown_parent_survives_restart_and_never_expires_or_releases_from_age(rig):
    host, batches, request = rig
    receipt = batches.reserve(request)
    batches.update(receipt['id'], state='FLASHING', created_at='2000-01-01T00:00:00Z')
    restarted = BatchReservations(host)
    restarted.recover()
    assert restarted.status(receipt['id'])['state'] == 'UNKNOWN'
    auth = {'token': receipt['token'], 'epoch': receipt['epoch']}
    assert restarted.reconcile(receipt['id'], auth)['state'] == 'UNKNOWN'
    with pytest.raises(TestError) as error:
        restarted.release(receipt['id'], auth)
    assert error.value.code == 'HARDWARE_UNKNOWN'


@pytest.mark.parametrize('child_state,terminated', [('RUNNING', False), ('UNKNOWN', False), ('DONE', False)])
def test_child_without_proven_termination_keeps_parent_reserved(rig, child_state, terminated):
    host, batches, request = rig
    receipt = batches.reserve(request)
    child = {'id': uid(), 'batch_id': receipt['id'], 'state': child_state, 'terminated': terminated}
    with sqlite3.connect(host.db) as connection:
        connection.execute('INSERT INTO jobs VALUES(?,?,?)', (child['id'], 'fixture', json.dumps(child)))
    with pytest.raises(TestError) as error:
        batches.release(receipt['id'], {'token': receipt['token'], 'epoch': receipt['epoch']})
    assert error.value.code == 'HARDWARE_UNKNOWN'
    assert batches.status(receipt['id'])['state'] != 'RELEASED'


def test_release_is_idempotent_after_proven_children_termination_and_next_epoch_increases(rig):
    _, batches, request = rig
    receipt = batches.reserve(request)
    auth = {'token': receipt['token'], 'epoch': receipt['epoch']}
    first = batches.release(receipt['id'], auth)
    assert first['state'] == 'RELEASED' and batches.release(receipt['id'], auth) == first
    next_receipt = batches.reserve(request | {'id': uid(), 'request_id': 'next-intent'})
    assert next_receipt['epoch'] > receipt['epoch'] and next_receipt['token'] != receipt['token']
