"""Plugin ownership, uncertain intents, selection and shared file API contracts."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.core.models import TestError, digest
from backend.gui_test.standalone.integration import create_app
from backend.gui_test.standalone.plugin_client import PluginClient
from backend.gui_test.standalone.plugin_runtime import PluginSession
from backend.gui_test.standalone.plugin_settings_file import SettingsFileBridge
from backend.gui_test.standalone.plugin_commands import command_parser, dispatch
from backend.gui_test.tests.test_plugin_integration_service import rig
from backend.gui_test.tests.test_plugin_integration_http import client_for


class Client:
    url = 'http://127.0.0.1:8766'
    expected = {'runtime_id': 'runtime', 'package_version': '1'}
    def __init__(self):
        self.fresh = False; self.calls = []; self.fail = False
        self.value = {'revision': 'r1', 'integration': {'installer_path': '/srv/install.bat', 'global_defaults': ['*.py']}, 'timeouts': {}}
        self.rows = {c * 32: {'id': c * 32, 'version': 1, 'state': 'RUNNING', 'simulation': False,
                            'integration': {'config': {'runner_id': 'runner'}}} for c in 'ab'}
    def health(self): return {'worker_running': True}
    def settings(self): return deepcopy(self.value)
    def connector_mirror(self): return {'fresh': self.fresh, 'inventory': {'runner_id': 'runner', 'fresh': self.fresh}}
    def save_settings(self, value):
        if value.get('expected_revision', value.get('revision')) != self.value['revision']:
            raise TestError('stale', 'SETTINGS_CHANGED')
        self.value = dict(deepcopy(value), revision='r2'); return self.settings()
    def start(self, key, installer, patterns, token=None):
        self.calls.append((key, installer, patterns, token))
        if self.fail: raise TestError('offline', 'SERVICE_CONNECTION_FAILED', 503)
        return self.rows['a' * 32]
    def run(self, identity): return deepcopy(self.rows[identity])
    def action(self, identity, action, *, key, expected_version):
        self.calls.append((identity, action, key, expected_version))
        if self.fail: raise TestError('offline', 'SERVICE_CONNECTION_FAILED', 503)
        return self.run(identity)
    def runs(self): return [{'id': identity} for identity in self.rows]
    def preview(self, installer, patterns): return {'preparation_id': 'p', 'state': 'PREPARING'}
    def preparation(self, identity): return {'state': 'READY', 'prepared_token': 'fixed-token'}


def session(client, tmp_path, **kw):
    return PluginSession(client, project='project-A', state_dir=tmp_path / 'state', **kw)


def test_late_connection_stale_recovery_notify_once_without_ever_claiming(tmp_path):
    client = Client(); events = []
    plugin = session(client, tmp_path, notify=events.append)
    assert not plugin.refresh()['connection_ready']
    client.fresh = True
    assert plugin.refresh()['connection_ready'] and not plugin.refresh()['execution_ready']
    client.fresh = False; plugin.refresh(); client.fresh = True; plugin.refresh()
    assert [event['state'] for event in events] == ['WAITING_CONNECTOR', 'READY', 'WAITING_CONNECTOR', 'READY']
    plugin.close(); assert client.calls == []


def test_save_draft_never_rebases_and_poll_preserves_edits(tmp_path):
    client = Client(); plugin = session(client, tmp_path)
    draft = plugin.begin_edit()['value']; draft['integration']['global_defaults'] = ['edited.py']
    plugin.edit(draft); client.value['revision'] = 'r2'
    snapshot = plugin.refresh()
    assert snapshot['settings_draft']['value']['integration']['global_defaults'] == ['edited.py']
    assert snapshot['settings']['revision'] == 'r2'
    with pytest.raises(TestError): plugin.save_edit()
    with plugin.store.transaction() as state: assert state['settings_draft']['conflict']
    draft['expected_revision'] = 'r2'
    with pytest.raises(TestError): plugin.edit(draft)
    assert client.settings()['integration']['global_defaults'] == ['*.py']


def test_uncertain_start_restarts_with_identical_key_body_and_token(tmp_path):
    client = Client(); plugin = session(client, tmp_path)
    plugin.preview(); client.fail = True
    with pytest.raises(TestError): plugin.start()
    original = deepcopy(client.calls[-1])
    client.value['integration']['installer_path'] = '/srv/changed.bat'
    restarted = session(client, tmp_path); client.fail = False
    assert restarted.start()['id'] == 'a' * 32
    assert client.calls[-1] == original
    assert restarted.run()['id'] == 'a' * 32
    assert (tmp_path / 'state').glob('*.json')


def test_changed_preview_is_not_silently_replaced(tmp_path):
    client = Client(); plugin = session(client, tmp_path); plugin.preview()
    client.value['integration']['installer_path'] = '/srv/new.bat'
    with pytest.raises(TestError) as error: plugin.start()
    assert error.value.code == 'PREVIEW_CHANGED' and client.calls == []


def test_reading_other_run_does_not_change_explicit_selection_or_pending_action(tmp_path):
    client = Client(); plugin = session(client, tmp_path)
    plugin.select('a' * 32); plugin.run('b' * 32)
    client.fail = True
    with pytest.raises(TestError): plugin.action('cancel')
    original = client.calls[-1]; assert original[0] == 'a' * 32
    client.rows['a' * 32]['version'] = 99
    client.fail = False; session(client, tmp_path).action('cancel')
    assert client.calls[-1] == original
    other = PluginSession(client, project='project-B', state_dir=tmp_path / 'state')
    with pytest.raises(TestError): other.action('cancel')


def test_actual_run_summary_contract_is_classified_using_detail(rig, tmp_path):
    manager, service = rig[:2]
    accepted = service.start('test', 'plugin-principal', rig[3])
    with manager.store.transaction() as c:
        run = manager.store.get(c, accepted['id']); run['simulation'] = False
        manager.store.save(c, run, 'TEST_HARDWARE_RECORD_ONLY')
    with client_for(rig, tmp_path) as http:
        health = http.get('/api/v1/health').json()
        client = PluginClient('http://127.0.0.1', expected_identity={k: health[k] for k in ('runtime_id', 'package_version')}, client=http)
        # The actual list intentionally omits integration and simulation.
        assert 'integration' not in client.runs()[0]
        rows = session(client, tmp_path).runs()
        assert [run['id'] for run in rows] == [accepted['id']]


@pytest.fixture
def api(tmp_path):
    app = create_app(tmp_path / 'runtime', start_worker=False)
    with TestClient(app, client=('127.0.0.1', 1234), base_url='http://127.0.0.1') as http:
        health = http.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin'}).json()
        yield PluginClient('http://127.0.0.1', expected_identity={k: health[k] for k in ('runtime_id', 'package_version')}, client=http)


def edit_timeout(path, value):
    content = json.loads(path.read_text()); content['timeouts']['default_seconds'] = value
    path.write_text(json.dumps(content))


def test_shared_file_remote_only_local_only_both_and_restart_use_real_cas(api, tmp_path):
    path = tmp_path / 'external shared/settings.json'; bridge = SettingsFileBridge(api, path)
    assert bridge.sync()['state'] == 'SYNCED'
    remote = api.settings(); remote['timeouts']['default_seconds'] = 77; api.save_settings(remote)
    assert bridge.sync()['state'] == 'SYNCED'
    assert json.loads(path.read_text())['timeouts']['default_seconds'] == 77
    edit_timeout(path, 88); original = path.read_bytes()
    assert bridge.sync()['state'] == 'LOCAL_EDIT' and path.read_bytes() == original
    assert bridge.push()['state'] == 'SYNCED' and api.settings()['timeouts']['default_seconds'] == 88
    assert SettingsFileBridge(api, path).sync()['state'] == 'SYNCED'
    edit_timeout(path, 99); remote = api.settings(); remote['timeouts']['default_seconds'] = 111; api.save_settings(remote)
    original = path.read_bytes()
    assert bridge.sync()['state'] == 'CONFLICT'
    assert bridge.push()['state'] == 'CONFLICT'
    assert path.read_bytes() == original and api.settings()['timeouts']['default_seconds'] == 111


def test_settings_import_response_lost_is_verified_and_file_mutation_preserved(api, tmp_path, monkeypatch):
    path = tmp_path / 'settings.json'; bridge = SettingsFileBridge(api, path); bridge.sync(); edit_timeout(path, 42)
    actual = api.import_settings
    def lost(value, *, validate_only=False):
        result = actual(value, validate_only=validate_only)
        if not validate_only: raise TestError('lost', 'SERVICE_CONNECTION_FAILED', 503)
        return result
    monkeypatch.setattr(api, 'import_settings', lost)
    assert bridge.push()['state'] == 'SYNCED' and api.settings()['timeouts']['default_seconds'] == 42
    edit_timeout(path, 43)
    def editor(value, *, validate_only=False):
        result = actual(value, validate_only=validate_only)
        if not validate_only: edit_timeout(path, 44)
        return result
    monkeypatch.setattr(api, 'import_settings', editor)
    assert bridge.push()['state'] == 'CONFLICT'
    assert json.loads(path.read_text())['timeouts']['default_seconds'] == 44


def test_shared_file_binding_duplicate_json_and_local_edits_are_not_overwritten(api, tmp_path):
    path = tmp_path / 'settings.json'; bridge = SettingsFileBridge(api, path); bridge.sync()
    api.expected = dict(api.expected, runtime_id='different')
    with pytest.raises(TestError): bridge.sync()
    path.write_text('{"format": 1, "format": 2}')
    # Restore matching binding to verify strict local JSON handling.
    api.expected = bridge.binding['identity']
    with pytest.raises(ValueError): SettingsFileBridge(api, path).push()
    assert path.read_text() == '{"format": 1, "format": 2}'


def test_file_checkpoint_failure_after_import_recovers_exact_content_without_overwrite(api, tmp_path, monkeypatch):
    import backend.gui_test.standalone.plugin_runtime as runtime
    path = tmp_path / 'settings.json'; bridge = SettingsFileBridge(api, path); bridge.sync(); edit_timeout(path, 54)
    original = runtime.atomic_json
    def broken(target, value):
        if '.plugin-file-state' in str(target): raise OSError('checkpoint failed')
        return original(target, value)
    monkeypatch.setattr(runtime, 'atomic_json', broken)
    with pytest.raises(OSError): bridge.push()
    assert api.settings()['timeouts']['default_seconds'] == 54
    preserved = path.read_bytes()
    monkeypatch.setattr(runtime, 'atomic_json', original)
    assert bridge.sync()['state'] == 'SYNCED' and path.read_bytes() == preserved


def test_apply_receipt_lookup_never_reissues_and_next_terminal_intent_is_allowed(tmp_path):
    client = Client(); calls = []
    client.value['connector_application'] = {'state': 'APPLIED'}
    client.save_connector_settings = lambda value: dict(value, desired_revision='desired')
    client.connector_command = lambda action, body, **kw: calls.append((action, body, kw)) or {'command_id': str(len(calls)) * 32, 'state': 'QUEUED'}
    receipts = {'1' * 32: {'command_id': '1' * 32, 'state': 'RUNNING'}}
    client.connector_command_receipt = lambda identity: receipts[identity]
    plugin = session(client, tmp_path)
    value = {'runner_id': 'runner', 'settings': {}, 'expected_revision': 'r1'}
    plugin.apply_connector(value)
    assert plugin.apply_connector(value)['state'] == 'RUNNING' and len(calls) == 1
    with pytest.raises(TestError): plugin.apply_connector(dict(value, settings={'new': True}))
    receipts['1' * 32]['state'] = 'APPLIED'
    plugin.apply_connector(dict(value, settings={'new': True}))
    assert len(calls) == 2


def test_desired_response_lost_is_recovered_with_original_snapshot_before_command(tmp_path):
    client = Client(); requests = []; commands = []
    desired = {'runner_id': 'runner', 'settings': {}, 'desired_revision': 'accepted'}
    def save(value):
        requests.append(deepcopy(value))
        if len(requests) == 1: raise TestError('lost', 'SERVICE_CONNECTION_FAILED', 503)
        raise TestError('stale', 'SETTINGS_CHANGED', 409)
    client.value['connector_application'] = desired
    client.save_connector_settings = save
    client.connector_command = lambda action, body, **kw: commands.append((body, kw)) or {'command_id': 'c' * 32, 'state': 'QUEUED'}
    plugin = session(client, tmp_path)
    body = {'runner_id': 'runner', 'settings': {}, 'expected_revision': 'old'}
    with pytest.raises(TestError): plugin.apply_connector(body)
    plugin = session(client, tmp_path)
    assert plugin.apply_connector()['command_id'] == 'c' * 32
    assert requests == [body, body] and len(commands) == 1
    assert commands[0][0]['desired_revision'] == 'accepted'


def test_file_edit_immediately_after_atomic_write_never_becomes_clean(api, tmp_path, monkeypatch):
    import backend.gui_test.standalone.plugin_settings_file as module
    path = tmp_path / 'settings.json'; bridge = SettingsFileBridge(api, path)
    original = module.atomic_json
    def edit_after_write(target, value):
        original(target, value)
        if target == path: edit_timeout(path, 222)
    monkeypatch.setattr(module, 'atomic_json', edit_after_write)
    assert bridge.sync()['state'] == 'CONFLICT'
    monkeypatch.setattr(module, 'atomic_json', original)
    remote = api.settings(); remote['timeouts']['default_seconds'] = 333; api.save_settings(remote)
    assert bridge.sync()['state'] == 'CONFLICT'
    assert json.loads(path.read_text())['timeouts']['default_seconds'] == 222


def test_confirmed_desired_rejection_allows_corrected_explicit_request(tmp_path):
    client = Client(); accepted = []
    client.value['connector_application'] = {'settings': {'other': True}}
    def save(value):
        if value['expected_revision'] == 'invalid': raise TestError('invalid', 'INVALID', 422)
        return dict(value, desired_revision='d')
    client.save_connector_settings = save
    client.connector_command = lambda *args, **kw: accepted.append(args) or {'command_id': 'c' * 32}
    plugin = session(client, tmp_path)
    with pytest.raises(TestError): plugin.apply_connector({'runner_id': 'runner', 'settings': {}, 'expected_revision': 'invalid'})
    assert plugin.apply_connector({'runner_id': 'runner', 'settings': {}, 'expected_revision': 'correct'})['command_id'] == 'c' * 32
    assert len(accepted) == 1


def test_abandoned_connector_request_allows_new_explicit_apply_but_unknown_does_not(tmp_path):
    client = Client(); calls = []
    client.save_connector_settings = lambda value: dict(value, desired_revision='d')
    client.connector_command = lambda *args, **kw: calls.append(args) or {'command_id': 'c' * 32}
    state = ['UNKNOWN']
    client.connector_command_receipt = lambda identity: {'command_id': identity, 'state': state[0]}
    plugin = session(client, tmp_path)
    value = {'runner_id': 'runner', 'settings': {}, 'expected_revision': 'r1'}
    plugin.apply_connector(value)
    with pytest.raises(TestError): plugin.apply_connector(dict(value, settings={'changed': True}))
    state[0] = 'ABANDONED'
    plugin.apply_connector(dict(value, settings={'changed': True}))
    assert len(calls) == 2


def test_shared_file_symlink_swap_after_construction_is_rejected_before_import(api, tmp_path):
    path = tmp_path / 'settings.json'; bridge = SettingsFileBridge(api, path); bridge.sync()
    outside = tmp_path / 'other.json'; outside.write_bytes(path.read_bytes())
    path.unlink(); path.symlink_to(outside)
    before = api.settings()
    with pytest.raises(ValueError): bridge.push()
    with pytest.raises(ValueError): bridge.sync()
    assert api.settings() == before
