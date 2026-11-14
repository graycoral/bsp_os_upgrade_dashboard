"""Windows mirror lifecycle checks; no COM, SSH, processes or native GUI."""
import copy
import json
import threading
from types import SimpleNamespace

import pytest

from backend.gui_test.connector import shared_control
from backend.gui_test.connector.mirror import public_profile
from backend.gui_test.connector.mirror_client import MirrorClient, bounded_state
from backend.gui_test.connector.settings import Settings
from backend.gui_test.connector.web_actions import ManagerActions, save_profile
from backend.gui_test.core.models import TestError, digest
from backend.gui_test.execution import launch
from backend.gui_test.execution.host import Host
from backend.gui_test.tests.test_shared_connector_control import BOARD, desired, inventory, staged


@pytest.fixture
def manager(tmp_path):
    settings = Settings(tmp_path)
    settings.save({'_setup': {'server': 'linux.example', 'account': 'tester'},
                   'boards': [BOARD], 'serial_transport': 'proxy'})
    return SimpleNamespace(home=tmp_path, settings=settings, control_lock=threading.RLock(),
                           mirror_applying=False, thread=None, shutdown=threading.Event())


def command(manager, **changes):
    return {'command_id': 'c' * 32, 'runner_id': 'r' * 32, 'session_id': 's' * 32,
            'claim_token': 'private-claim', 'revision': digest(public_profile(manager.settings.read())),
            'action': 'putty', 'body': {'board_id': BOARD['board_id']}} | changes


def test_lost_receipt_retried_after_restart_without_repeating_action(manager, monkeypatch):
    calls = []
    monkeypatch.setattr(ManagerActions, 'action', lambda *args: calls.append(args) or {'opened': True, 'manual_lease': 'PRIVATE'})
    client = MirrorClient(manager)
    monkeypatch.setattr(client, 'request', lambda *args: (_ for _ in ()).throw(TestError('offline')))
    client._execute({'command': command(manager), 'phase': 'CLAIMED'})
    record = json.loads(next(client.directory.glob('*.json')).read_text())
    assert record['phase'] == 'DONE' and record['receipt']['state'] == 'APPLIED'
    assert 'PRIVATE' not in json.dumps(record['receipt'])
    restarted = MirrorClient(manager)
    receipts = []
    monkeypatch.setattr(restarted, 'request', lambda *args: receipts.append(args) or {'state': 'APPLIED'})
    restarted.flush()
    restarted.flush()
    assert len(calls) == len(receipts) == 1
    assert not list(client.directory.glob('*.json'))


def test_claimed_without_result_is_never_replayed(manager, monkeypatch):
    client = MirrorClient(manager)
    client._write({'command': command(manager), 'phase': 'CLAIMED'})
    monkeypatch.setattr(client, 'request', lambda *args: pytest.fail('uncertain command replayed'))
    client.flush()
    assert json.loads(next(client.directory.glob('*.json')).read_text())['phase'] == 'CLAIMED'


def test_stale_profile_fails_before_hardware_action(manager, monkeypatch):
    client = MirrorClient(manager)
    receipts = []
    monkeypatch.setattr(client, 'request', lambda *args: receipts.append(args))
    monkeypatch.setattr(ManagerActions, 'action', lambda *args: pytest.fail('stale command executed'))
    client._execute({'command': command(manager, revision='old'), 'phase': 'CLAIMED'})
    assert receipts[0][1]['state'] == 'FAILED'
    assert receipts[0][1]['result']['code'] == 'SETTINGS_CHANGED'


def test_transport_budget_preserves_actual_board_log_tail():
    payload = {'profile': {}, 'ports': [], 'executions': [
        {'id': str(i), 'board_ids': ['A'], 'stdout': '한글\\\n' * 65536 + 'END', 'stderr': 'z' * 65536}
        for i in range(8)], 'execution_paths': []}
    body = bounded_state(payload, {})
    assert len(json.dumps(body).encode()) <= 60000
    assert len(json.dumps(body, ensure_ascii=False).encode()) <= 60000
    value = body['projection']
    assert value['logs_truncated'] and value['executions']
    assert value['executions'][0]['stdout'].endswith('END')
    assert value['executions'][0]['board_ids'] == ['A']


def test_owner_preserves_hidden_observer_values_and_inactive_roundtrip(manager):
    settings = manager.settings
    observer = {'port': 'COM8', 'redact_values': ['private'], 'vendor_extension': {'key': 'preserve'}}
    settings.save({'console_observers': {BOARD['board_id']: observer}})
    projection = public_profile(settings.read())
    assert 'private' not in json.dumps(projection)
    projection['board_names'] = {BOARD['board_id']: 'renamed'}
    settings.save(projection)
    assert settings.read()['console_observers'][BOARD['board_id']] == observer
    settings.save({'connector_inactive_boards': [{'board': BOARD, 'name': 'saved', 'observer': {'port': 'COM8'}}]})
    inactive = settings.read()['connector_inactive_boards'][0]
    assert inactive['observer']['redact_values'] == ['private']
    settings.save({'console_observers': {BOARD['board_id']: {'port': 'COM9'}}})
    assert settings.read()['console_observers'][BOARD['board_id']]['redact_values'] == ['private']


def test_pending_profile_baseline_rejects_later_windows_edit(manager):
    settings = manager.settings
    host = Host(settings.read(), manager.home / 'runtime', ports=lambda: {'COM7'})
    application = desired(settings, host.identity, board_names={BOARD['board_id']: 'remote'})
    application['expected_profile_revision'] = digest(public_profile(settings.read()))
    staged(settings, application)
    settings.save({'board_names': {BOARD['board_id']: 'local-newer'}})
    before = settings.path.read_bytes()
    with pytest.raises(TestError) as error:
        shared_control.apply_pending(manager.home)
    assert error.value.code == 'SETTINGS_CHANGED'
    assert settings.path.read_bytes() == before


def test_old_applied_receipt_is_revoked_when_actual_host_drifted(manager, monkeypatch):
    settings = manager.settings
    application = desired(settings, board_names={BOARD['board_id']: 'remote'})
    application['state'] = 'APPLIED'
    staged(settings, application, 'SAVED')
    settings.save({'board_names': {BOARD['board_id']: 'local-newer'}})
    sent = []
    monkeypatch.setattr(shared_control, 'request', lambda *args: sent.append(args))
    shared_control.acknowledge(manager.home, application, inventory(settings, application))
    assert sent[-1][3]['state'] == 'BLOCKED'


def test_force_apply_restages_previous_saved_revision(manager):
    app = desired(manager.settings)
    staged(manager.settings, app, 'SAVED')
    shared_control.remember_desired(manager.home, app, app['runner_id'], force=True)
    assert json.loads(shared_control.pending_file(manager.home).read_text())['state'] == 'PENDING'


def test_apply_rejects_invalid_patch_without_disconnect_and_clears_guard(manager, monkeypatch):
    app = desired(manager.settings, boards=[])
    monkeypatch.setattr(shared_control, 'request', lambda *args: {'connector_application': app})
    manager._disconnect = lambda: pytest.fail('invalid config stopped live connector')
    with pytest.raises(TestError):
        MirrorClient(manager)._apply(app['desired_revision'], digest(public_profile(manager.settings.read())))
    assert not manager.mirror_applying


def test_apply_busy_failure_preserves_settings(manager, monkeypatch):
    app = desired(manager.settings, 'r' * 32)
    monkeypatch.setattr(shared_control, 'request', lambda *args: {'connector_application': app})
    monkeypatch.setattr(launch, 'read_active', lambda *args: {'runner_id': app['runner_id']})
    def busy():
        raise TestError('TC still running', 'CONNECTOR_BUSY', 409)
    manager._disconnect = busy
    before = manager.settings.path.read_bytes()
    with pytest.raises(TestError) as error:
        MirrorClient(manager)._apply(app['desired_revision'], digest(public_profile(manager.settings.read())))
    assert error.value.code == 'CONNECTOR_BUSY' and manager.settings.path.read_bytes() == before
    assert not manager.mirror_applying


def test_local_save_cannot_race_disconnected_reconfiguration_gap(manager):
    manager.mirror_applying = True
    with pytest.raises(TestError) as error:
        save_profile(manager, {'board_names': {BOARD['board_id']: 'racing'}})
    assert error.value.code == 'CONNECTOR_BUSY'


def test_applied_configuration_stays_applied_during_tc(manager, monkeypatch):
    settings = manager.settings
    app = desired(settings, board_names={BOARD['board_id']: 'named'})
    settings.save(app['settings'])
    app['state'] = 'APPLIED'
    staged(settings, app, 'SAVED')
    monkeypatch.setattr(shared_control, 'request', lambda *args: pytest.fail('busy TC revoked matching applied proof'))
    shared_control.acknowledge(manager.home, app, inventory(settings, app, host_busy=True))


def test_reconnect_reports_applied_only_after_saved_config_and_new_host_proof(manager, monkeypatch):
    host = Host(manager.settings.read(), manager.home / 'runtime', ports=lambda: {'COM7'})
    app = desired(manager.settings, host.identity, board_names={BOARD['board_id']: 'remote-name'})
    active = [{'runner_id': host.identity}]
    monkeypatch.setattr(launch, 'read_active', lambda *args: active[0])
    def request(home, suffix, method='GET', value=None):
        if suffix == 'connector-settings/receipt':
            app.update(value)
        return {'connector_application': copy.deepcopy(app)}
    monkeypatch.setattr(shared_control, 'request', request)
    manager._disconnect = lambda: active.__setitem__(0, None)
    def connect(*, desired_revision):
        shared_control.apply_pending(manager.home, expected_revision=desired_revision)
        active[0] = {'runner_id': host.identity}
    manager._connect = connect
    def probe():
        shared_control.acknowledge(manager.home, app, inventory(manager.settings, app))
        return {'state': 'CONNECTED'}
    manager.probe = probe
    result = MirrorClient(manager)._apply(app['desired_revision'], digest(public_profile(manager.settings.read())))
    assert result['applied'] and app['state'] == 'APPLIED'
    assert manager.settings.read()['board_names'][BOARD['board_id']] == 'remote-name'
    assert not manager.mirror_applying


def test_effective_inactive_snapshot_proves_hidden_values_without_uploading_them(manager, monkeypatch):
    settings = manager.settings
    settings.save({'console_observers': {BOARD['board_id']: {'port': 'COM8', 'redact_values': ['hidden']}}})
    host = Host(settings.read(), manager.home / 'runtime', ports=lambda: {'COM7'})
    app = desired(settings, host.identity, connector_inactive_boards=[{
        'board': BOARD, 'name': 'restore', 'observer': {'port': 'COM8'}}])
    staged(settings, app)
    shared_control.apply_pending(manager.home)
    sent = []
    monkeypatch.setattr(shared_control, 'request', lambda *args: sent.append(args))
    shared_control.acknowledge(manager.home, app, inventory(settings, app))
    assert sent[-1][3]['state'] == 'APPLIED'
    assert 'hidden' not in json.dumps(sent[-1][3])


def test_heartbeat_and_control_probes_are_serialized(manager, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import time
    from backend.gui_test.connector.supervisor import Manager
    running = [0]
    manager.probe_lock = threading.RLock()
    def probe(self):
        running[0] += 1
        assert running[0] == 1
        time.sleep(.01)
        running[0] -= 1
        return 'observed'
    monkeypatch.setattr(Manager, '_probe', probe)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: Manager.probe(manager), range(8))) == ['observed'] * 8


def test_windows_shrink_then_dashboard_restore_retains_rx_and_redaction(manager):
    settings = manager.settings
    other = dict(BOARD, board_id='board-b', com='COM9')
    observer = {'port': 'COM10', 'redact_values': ['secret'], 'vendor_extension': True}
    settings.save({'boards': [BOARD, other], 'serial_transport': 'native',
                   'console_observers': {other['board_id']: observer}})
    settings.save({'boards': [BOARD], 'console_observers': {},
                   'connector_inactive_boards': [{'board': other, 'name': 'B', 'observer': observer}]})
    assert other['board_id'] not in settings.read()['console_observers']
    # Dashboard sends editable fields, never reconstructed public observers.
    settings.save({'boards': [BOARD, other], 'connector_inactive_boards': []})
    assert settings.read()['console_observers'][other['board_id']] == observer
