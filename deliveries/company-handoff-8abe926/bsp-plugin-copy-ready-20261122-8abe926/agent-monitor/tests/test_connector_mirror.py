"""One-shot Manager commands use mocked clocks/registration, never Windows I/O."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json

import pytest

from backend.gui_test.connector.mirror import ConnectorMirror, public_profile
from backend.gui_test.connector.registry import ConnectorRegistry
from backend.gui_test.core.models import TestError, digest


@pytest.fixture
def rig(tmp_path):
    clock, mapping = [100.0], ['mapping-one']

    class Remote:
        def request(self, path):
            if path == '/identity':
                return {'runner_id': 'runner', 'connector_inventory_v1': True}
            if path == '/inventory':
                return {'runner_id': 'runner', 'mapping_revision': mapping[0], 'host_busy': False, 'reserved': False,
                        'boards': [{'board_id': 'A', 'state': 'CONNECTED',
                                    'serial_proxy': {'owner': None, 'putty_connected': False}}]}
            raise AssertionError(path)

    registry = ConnectorRegistry(tmp_path, factory=lambda url: Remote(), clock=lambda: clock[0])
    registry.register('http://127.0.0.1:8771', 'runner')
    registry.save_console({'runner_id': 'runner', 'boards': []})
    mirror = ConnectorMirror(registry)
    profile = {'boards': [{'board_id': 'A', 'host': 'windows', 'com': 'COM1'}], 'board_names': {'A': 'Board A'},
               'serial_transport': 'proxy', 'python': r'C:\Python\python.exe'}
    projection = {'runner_id': 'runner', 'session_id': 'boot-one', 'revision': digest(profile), 'profile': profile,
                  'ports': [{'com': 'COM1', 'description': 'USB serial'}], 'state': 'CONNECTED', 'error': ''}
    mirror.publish(projection)
    return mirror, registry, clock, mapping, projection


def request(projection, key='request-one', action='putty', body=None):
    return {key_: projection[key_] for key_ in ('runner_id', 'session_id', 'revision')} | {
        'idempotency_key': key, 'action': action, 'body': body if body is not None else {'board_id': 'A'}}


def claim(mirror, projection):
    return mirror.claim({key: projection[key] for key in ('runner_id', 'session_id')})['command']


def receipt(command, **changes):
    return {key: command[key] for key in ('runner_id', 'session_id', 'claim_token')} | {
        'state': 'APPLIED', 'result': {'opened': True}} | changes


def rejected(code, call):
    with pytest.raises(TestError) as error:
        call()
    assert error.value.code == code


def refresh(rig, *, url='http://127.0.0.1:8771'):
    mirror, registry, _, _, projection = rig
    registry.register(url, 'runner')
    registry.save_console({'runner_id': 'runner', 'boards': []})
    mirror.publish(projection, expected_registration=registry.read())


def test_projection_whitelists_nested_secrets_and_bounds_status(rig):
    mirror, _, _, _, projection = rig
    dirty = copy.deepcopy(projection)
    dirty['profile'].update(_setup={'ssh_key': 'PRIVATE-KEY'}, flashing={'secret': 'PRIVATE-FLASH'}, unknown='PRIVATE-EXTRA')
    dirty['profile']['boards'][0]['token'] = 'PRIVATE-BOARD'
    dirty['ports'][0]['secret'] = 'PRIVATE-PORT'
    dirty['executions'] = [{'id': 'execution-one', 'state': 'RUNNING', 'argv': ['PRIVATE-ARGV'], 'token': 'PRIVATE-TOKEN',
                            'board_ids': ['A'], 'stdout': 'password=PRIVATE-STDOUT\n' + 'x' * 20000, 'stderr': 'Bearer PRIVATE-STDERR'}] * 100
    dirty['execution_paths'] = [{'id': 'execution-one', 'working_directory': 'https://user:PRIVATE-PASSWORD@example.com/source?token=PRIVATE-QUERY'}]
    dirty['server_paths'] = {'selected_tc_source': '/source', 'secret': 'PRIVATE-PATH',
                             'run': {'id': 'run-one', 'argv': 'PRIVATE-RUN', 'execution_ids': ['execution-one']}}
    dirty['error'] = 'e' * 10000
    snapshot = mirror.publish(dirty)
    assert snapshot['schema'] == 'connector-mirror-v1' and snapshot['fresh']
    assert 'PRIVATE-' not in json.dumps(snapshot)
    assert len(snapshot['projection']['executions']) == 8
    assert len(snapshot['projection']['executions'][0]['stdout']) == 16_384
    assert snapshot['projection']['executions'][0]['board_ids'] == ['A']
    assert len(snapshot['projection']['error']) == 1024
    assert snapshot['projection']['execution_paths'][0]['working_directory'] == 'https://example.com/source'
    assert snapshot['projection']['logs_truncated']


def test_inactive_editor_drafts_and_rx_configuration_preserved_without_private_fields():
    observer = {'port': 'COM8', 'rx_only_confirmed': True, 'control_lines_isolated': True,
                'panic_signatures': ['Kernel panic'], 'token': 'PRIVATE-OBSERVER'}
    profile = {'boards': [], 'console_observers': {'A': observer}, 'connector_inactive_boards': [{
        'board': {'board_id': 'B', 'host': 'windows', 'com': 'COM7', 'secret': 'PRIVATE-BOARD'},
        'name': 'Inactive B', 'observer': observer, 'baudrate': 9600, 'secret': 'PRIVATE-DRAFT'}]}
    safe = public_profile(profile)
    draft = safe['connector_inactive_boards'][0]
    assert draft['board'] == {'board_id': 'B', 'host': 'windows', 'com': 'COM7'}
    assert draft['name'] == 'Inactive B' and draft['baudrate'] == 9600
    assert draft['observer'] == safe['console_observers']['A']
    assert draft['observer']['rx_only_confirmed']
    assert draft['observer']['panic_signatures'] == ['Kernel panic']
    assert 'PRIVATE-' not in json.dumps(safe)
    malformed = public_profile({'board_names': {'A': {'private': 'PRIVATE-NESTED'}}})
    assert malformed == {'board_names': {'A': ''}}


def test_publisher_log_truncation_flag_preserved_when_server_does_not_trim(rig):
    mirror, _, _, _, projection = rig
    assert mirror.publish(dict(projection, logs_truncated=True))['projection']['logs_truncated']


def test_command_survives_restart_and_ack_is_not_inferred(rig):
    mirror, registry, _, _, projection = rig
    command = mirror.create(request(projection))
    assert command['state'] == 'QUEUED'
    reloaded = ConnectorMirror(registry)
    claimed = claim(reloaded, projection)
    assert claimed['command_id'] == command['command_id'] and claimed['state'] == 'RUNNING'
    assert claim(mirror, projection) is None
    assert mirror.get(command['command_id'])['state'] == 'RUNNING'
    done = mirror.finish(command['command_id'], receipt(claimed))
    assert done['state'] == 'APPLIED' and done['result'] == {'opened': True}
    assert mirror.finish(command['command_id'], receipt(claimed)) == done
    rejected('RECEIPT_CONFLICT', lambda: mirror.finish(command['command_id'], receipt(claimed, state='FAILED')))
    assert 'claim_token' not in json.dumps(mirror.snapshot())
    assert 'idempotency_key' not in json.dumps(mirror.snapshot())


def test_concurrent_duplicate_creation_and_claim_are_atomic(rig):
    mirror, _, _, _, projection = rig
    with ThreadPoolExecutor(max_workers=8) as pool:
        created = list(pool.map(lambda _: mirror.create(request(projection)), range(12)))
    assert len({value['command_id'] for value in created}) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: claim(mirror, projection), range(12)))
    assert sum(value is not None for value in claims) == 1
    rejected('CONNECTOR_BUSY', lambda: mirror.create(request(projection, key='another')))


def test_duplicate_key_returns_original_even_when_stale_and_rejects_different_payload(rig):
    mirror, _, clock, _, projection = rig
    original = mirror.create(request(projection))
    clock[0] += 16
    assert mirror.create(request(projection)) == original
    rejected('IDEMPOTENCY_CONFLICT', lambda: mirror.create(request(projection, action='manual', body={'board_id': 'A', 'manual': True})))


def test_concurrent_distinct_requests_have_only_one_active_winner(rig):
    mirror, _, _, _, projection = rig

    def create(index):
        try:
            return mirror.create(request(projection, key='request-' + str(index)))['state']
        except TestError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        states = list(pool.map(create, range(12)))
    assert states.count('QUEUED') == 1
    assert states.count('CONNECTOR_BUSY') == 11


def test_profile_revision_change_expires_queued_without_running_it(rig):
    mirror, _, _, _, projection = rig
    queued = mirror.create(request(projection))
    profile = dict(projection['profile'], board_names={'A': 'Updated board A'})
    mirror.publish(dict(projection, profile=profile, revision=digest(profile)))
    assert mirror.get(queued['command_id'])['state'] == 'EXPIRED'
    assert claim(mirror, projection) is None


@pytest.mark.parametrize('part', ['registration', 'projection'])
def test_control_needs_fresh_registration_and_manager_projection(rig, part):
    mirror, registry, clock, _, projection = rig
    clock[0] += 16
    if part == 'registration':
        mirror.publish(projection)
    else:
        registry.register('http://127.0.0.1:8771', 'runner')
    assert not mirror.snapshot()['fresh']
    rejected('CONNECTOR_STALE', lambda: mirror.create(request(projection)))
    rejected('CONNECTOR_STALE', lambda: claim(mirror, projection))


def test_wrong_revision_board_and_session_rejected_without_queueing(rig):
    mirror, _, _, _, projection = rig
    for changed in ({'revision': 'old'}, {'session_id': 'boot-zero'}, {'runner_id': 'other'}):
        rejected('MANAGER_CHANGED', lambda: mirror.create(request(projection) | changed))
    rejected('BOARD_NOT_FOUND', lambda: mirror.create(request(projection, body={'board_id': 'B'})))
    assert mirror.snapshot()['commands'] == []


def test_session_replacement_expires_queued_fences_running_and_rejects_old_publish(rig):
    mirror, _, _, _, projection = rig
    queued = mirror.create(request(projection))
    replaced = dict(projection, session_id='boot-two')
    mirror.publish(replaced)
    assert mirror.get(queued['command_id'])['state'] == 'EXPIRED'
    rejected('MANAGER_CHANGED', lambda: mirror.publish(projection))
    running = mirror.create(request(replaced, key='new-command'))
    claimed = claim(mirror, replaced)
    mirror.publish(dict(replaced, session_id='boot-three'))
    assert mirror.get(running['command_id'])['state'] == 'UNKNOWN'
    rejected('CONNECTOR_BUSY', lambda: mirror.create(request(dict(replaced, session_id='boot-three'), key='third')))
    # A real persisted acknowledgement from the original boot may settle UNKNOWN;
    # the replacement session still cannot claim or manufacture the old token.
    rejected('MANAGER_CHANGED', lambda: mirror.finish(running['command_id'], receipt(claimed, session_id='boot-three')))
    assert mirror.finish(running['command_id'], receipt(claimed))['state'] == 'APPLIED'


def test_queue_ttl_expires_and_is_not_claimed_after_reconnect(rig):
    mirror, _, clock, _, projection = rig
    queued = mirror.create(request(projection))
    clock[0] += 60
    refresh(rig)
    assert claim(mirror, projection) is None
    assert mirror.get(queued['command_id'])['state'] == 'EXPIRED'
    assert mirror.create(request(projection))['state'] == 'EXPIRED'
    assert mirror.create(request(projection, key='new'))['state'] == 'QUEUED'


@pytest.mark.parametrize('action,body,ttl', [('putty', {'board_id': 'A'}, 60),
                                          ('apply-settings', {'desired_revision': 'desired-one'}, 180)])
def test_running_timeout_unknown_never_replayed_and_late_ack_converges(rig, action, body, ttl):
    mirror, _, clock, _, projection = rig
    queued = mirror.create(request(projection, action=action, body=body))
    claimed = claim(mirror, projection)
    assert claimed['expires_at'] == clock[0] + ttl
    clock[0] += ttl
    refresh(rig)
    assert claim(mirror, projection) is None
    assert mirror.get(queued['command_id'])['state'] == 'UNKNOWN'
    rejected('CONNECTOR_BUSY', lambda: mirror.create(request(projection, key='new')))
    assert mirror.finish(queued['command_id'], receipt(claimed))['state'] == 'APPLIED'
    assert mirror.create(request(projection, key='after-receipt'))['state'] == 'QUEUED'


def test_receipt_identity_token_and_queued_state_cannot_forge_ack(rig):
    mirror, _, _, _, projection = rig
    queued = mirror.create(request(projection))
    rejected('MANAGER_CHANGED', lambda: mirror.finish(queued['command_id'], receipt(dict(queued, claim_token='invented'))))
    claimed = claim(mirror, projection)
    for changed in ({'claim_token': 'wrong'}, {'claim_token': '유효하지않음'}, {'session_id': 'other'}, {'runner_id': 'other'}):
        rejected('MANAGER_CHANGED', lambda: mirror.finish(queued['command_id'], receipt(claimed, **changed)))
    done = mirror.finish(queued['command_id'], receipt(claimed, state='FAILED', result={'code': 'BUSY', 'message': 'blocked', 'argv': 'PRIVATE'}))
    assert done['state'] == 'FAILED' and done['result'] == {'code': 'BUSY', 'message': 'blocked'}


def test_transport_or_mapping_change_expires_queued_and_delayed_publication(rig):
    mirror, registry, _, mapping, projection = rig
    previous = registry.read()
    queued = mirror.create(request(projection))
    mapping[0] = 'mapping-two'
    registry.register('http://127.0.0.1:8772', 'runner')
    assert not mirror.snapshot()['fresh']
    assert mirror.get(queued['command_id'])['state'] == 'EXPIRED'
    rejected('CONNECTOR_STALE', lambda: mirror.publish(projection, expected_registration=previous))
    mirror.publish(projection, expected_registration=registry.read())
    assert not mirror.snapshot()['fresh']
    registry.save_console({'runner_id': 'runner', 'boards': []})
    assert mirror.snapshot()['fresh']


def test_running_receipt_survives_same_session_transport_and_profile_change(rig):
    mirror, registry, _, mapping, projection = rig
    queued = mirror.create(request(projection, action='apply-settings', body={'desired_revision': 'desired-two'}))
    claimed = claim(mirror, projection)
    mapping[0] = 'mapping-two'
    registry.register('http://127.0.0.1:8772', 'runner')
    profile = dict(projection['profile'], board_names={'A': 'Updated board A'})
    mirror.publish(dict(projection, profile=profile, revision=digest(profile)), expected_registration=registry.read())
    assert mirror.get(queued['command_id'])['state'] == 'RUNNING'
    assert mirror.finish(queued['command_id'], receipt(claimed))['state'] == 'APPLIED'


def test_revision_must_match_sanitized_profile_digest(rig):
    mirror, _, _, _, projection = rig
    rejected('SETTINGS_CONFLICT', lambda: mirror.publish(dict(projection, revision='incorrect')))
    assert mirror.snapshot()['projection']['revision'] == projection['revision']


def test_stale_console_blocks_control_despite_fresh_manager_and_registration(rig):
    mirror, registry, clock, _, projection = rig
    clock[0] += 16
    registry.register('http://127.0.0.1:8771', 'runner')
    mirror.publish(projection)
    assert not mirror.snapshot()['fresh']
    rejected('CONNECTOR_STALE', lambda: mirror.create(request(projection)))


def test_host_validation_runs_only_on_new_request_and_preserves_original_replay(rig):
    mirror, _, _, _, projection = rig
    validated = []
    original = mirror.create(request(projection), validate=lambda value: validated.append(value))
    assert len(validated) == 1

    def reject(_):
        raise TestError('Desired revision changed', 'SETTINGS_CHANGED', 409)

    assert mirror.create(request(projection), validate=reject) == original
    claimed = claim(mirror, projection)
    mirror.finish(original['command_id'], receipt(claimed))
    rejected('SETTINGS_CHANGED', lambda: mirror.create(request(projection, key='new'), validate=reject))
    assert len(mirror.snapshot()['commands']) == 1


def unknown_request(rig, *, replace=True):
    mirror, _, clock, _, projection = rig
    queued = mirror.create(request(projection))
    claimed = claim(mirror, projection)
    if replace:
        clock[0] += 1
        current = dict(projection, session_id='boot-two')
        mirror.publish(current)
    else:
        clock[0] += 60
        refresh(rig)
        current = projection
    command = mirror.get(queued['command_id'])
    assert command['state'] == 'UNKNOWN'
    return command, claimed, current


def acknowledgement(command, current):
    return {key: current[key] for key in ('runner_id', 'session_id')} | {'expected_updated_at': command['updated_at']}


def change_inventory(registry, change):
    with registry.connection() as c:
        value = json.loads(c.execute('SELECT data FROM registration WHERE id=1').fetchone()[0])
        change(value['inventory'])
        c.execute('UPDATE registration SET data=? WHERE id=1', (json.dumps(value),))


def test_abandon_requires_replacement_session_and_does_not_guess_old_outcome_or_replay(rig):
    mirror, *_ = rig
    unknown, _, current = unknown_request(rig)
    abandoned = mirror.abandon(unknown['command_id'], acknowledgement(unknown, current))
    assert abandoned['state'] == 'ABANDONED'
    assert abandoned['result']['code'] == 'UNKNOWN_ACKNOWLEDGED' and abandoned['result']['outcome_unknown']
    assert abandoned['abandoned_at'] == abandoned['updated_at']
    assert abandoned['abandoned_by_session_id'] == current['session_id']
    assert claim(mirror, current) is None
    assert mirror.create(request(rig[-1]))['state'] == 'ABANDONED'  # The old key never executes again.
    assert mirror.create(request(current, key='new-explicit-intent'))['state'] == 'QUEUED'


def test_abandon_rejects_timeout_while_original_manager_session_still_active(rig):
    mirror, *_ = rig
    unknown, _, current = unknown_request(rig, replace=False)
    rejected('MANAGER_RESTART_REQUIRED', lambda: mirror.abandon(unknown['command_id'], acknowledgement(unknown, current)))
    assert mirror.get(unknown['command_id'])['state'] == 'UNKNOWN'
    rejected('CONNECTOR_BUSY', lambda: mirror.create(request(current, key='cannot-bypass')))


@pytest.mark.parametrize('state', ['QUEUED', 'RUNNING', 'APPLIED', 'FAILED'])
def test_abandon_cannot_override_active_or_known_terminal_result(rig, state):
    mirror, _, _, _, projection = rig
    command = mirror.create(request(projection))
    if state != 'QUEUED':
        claimed = claim(mirror, projection)
        if state in {'APPLIED', 'FAILED'}:
            mirror.finish(command['command_id'], receipt(claimed, state=state))
    current = mirror.get(command['command_id'])
    rejected('COMMAND_NOT_UNKNOWN', lambda: mirror.abandon(current['command_id'], acknowledgement(current, projection)))
    assert mirror.get(current['command_id'])['state'] == state


@pytest.mark.parametrize('change', [
    lambda inventory: inventory.update(host_busy=True),
    lambda inventory: inventory.update(reserved=True),
    lambda inventory: inventory.pop('host_busy'),
    lambda inventory: inventory.update(boards=[]),
    lambda inventory: inventory['boards'][0].update(state='RUNNING'),
    lambda inventory: inventory['boards'][0].update(state='UNKNOWN'),
    lambda inventory: inventory['boards'][0].update(state='RESERVED'),
    lambda inventory: inventory['boards'][0].pop('state'),
    lambda inventory: inventory['boards'][0].update(serial_proxy={'owner': 'manual', 'putty_connected': False}),
    lambda inventory: inventory['boards'][0].update(serial_proxy={'owner': 'execution', 'putty_connected': False}),
    lambda inventory: inventory['boards'][0].update(serial_proxy={'owner': None, 'putty_connected': True}),
    lambda inventory: inventory['boards'][0].update(serial_proxy={'owner': None}),
    lambda inventory: inventory['boards'][0].pop('serial_proxy'),
])
def test_abandon_rejects_busy_manual_or_missing_ownership_observations(rig, change):
    mirror, registry, *_ = rig
    unknown, _, current = unknown_request(rig)
    change_inventory(registry, change)
    rejected('CONNECTOR_BUSY', lambda: mirror.abandon(unknown['command_id'], acknowledgement(unknown, current)))
    assert mirror.get(unknown['command_id'])['state'] == 'UNKNOWN'


def test_abandon_cas_identity_freshness_and_state_are_required(rig):
    mirror, _, clock, _, _ = rig
    unknown, _, current = unknown_request(rig)
    value = acknowledgement(unknown, current)
    rejected('COMMAND_CHANGED', lambda: mirror.abandon(unknown['command_id'], value | {'expected_updated_at': -1}))
    rejected('MANAGER_CHANGED', lambda: mirror.abandon(unknown['command_id'], value | {'session_id': 'other-boot'}))
    rejected('MANAGER_CHANGED', lambda: mirror.abandon(unknown['command_id'], value | {'runner_id': 'other-runner'}))
    clock[0] += 16
    rejected('CONNECTOR_STALE', lambda: mirror.abandon(unknown['command_id'], value))


def test_late_authentic_receipt_after_abandon_retains_audit_and_does_not_change_new_command(rig):
    mirror, *_ = rig
    unknown, claimed, current = unknown_request(rig)
    abandoned = mirror.abandon(unknown['command_id'], acknowledgement(unknown, current))
    rejected('COMMAND_NOT_UNKNOWN', lambda: mirror.abandon(unknown['command_id'], acknowledgement(abandoned, current)))
    newer = mirror.create(request(current, key='new-explicit-request'))
    rejected('MANAGER_CHANGED', lambda: mirror.finish(unknown['command_id'], receipt(claimed, session_id=current['session_id'])))
    actual = mirror.finish(unknown['command_id'], receipt(claimed))
    assert actual['state'] == 'APPLIED' and actual['abandoned_at'] == abandoned['abandoned_at']
    assert actual['abandoned_by_session_id'] == current['session_id']
    assert mirror.get(newer['command_id'])['state'] == 'QUEUED'
    assert mirror.finish(unknown['command_id'], receipt(claimed)) == actual


@pytest.mark.parametrize('change', [{'expected_updated_at': True}, {'expected_updated_at': float('nan')},
                                  {'expected_updated_at': None}, {'extra': True}, {'session_id': ''}])
def test_abandon_rejects_invalid_acknowledgement_shape(rig, change):
    mirror, *_ = rig
    unknown, _, current = unknown_request(rig)
    with pytest.raises(TestError) as error:
        mirror.abandon(unknown['command_id'], acknowledgement(unknown, current) | change)
    assert error.value.status == 422


@pytest.mark.parametrize('change', [{'action': 'disconnect'}, {'action': 'connect'}, {'action': []},
                                  {'body': {'argv': ['command']}}, {'body': {'board_id': 'A', 'extra': True}},
                                  {'action': 'manual', 'body': {'board_id': 'A', 'manual': 1}},
                                  {'action': 'apply-settings', 'body': {'profile': {'_setup': 'private'}}},
                                  {'idempotency_key': ''}, {'revision': None}, {'extra': True}])
def test_invalid_command_shape_or_unsupported_action_is_422(rig, change):
    mirror, _, _, _, projection = rig
    with pytest.raises(TestError) as error:
        mirror.create(request(projection) | change)
    assert error.value.status == 422
    assert mirror.snapshot()['commands'] == []
