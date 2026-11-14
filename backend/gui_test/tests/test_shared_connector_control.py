"""Shared connector control uses mocked HTTP/Qt only; never opens a board or SSH."""
import copy
import json
import os
import sqlite3
import time

import httpx
import pytest

from backend.gui_test.connector import shared_control as control
from backend.gui_test.connector.settings import Settings
from backend.gui_test.core.models import TestError, digest
from backend.gui_test.execution import launch
from backend.gui_test.execution.host import Host

BOARD = {'board_id': 'board-a', 'host': 'TEST-PC', 'com': 'COM7', 'node': None}


@pytest.fixture
def profile(tmp_path):
    settings = Settings(tmp_path)
    settings.save({'_setup': {'server': 'linux.example', 'account': 'tester'},
                   'boards': [BOARD], 'serial_transport': 'native', 'python': 'C:/TC/python.exe'})
    return settings


def desired(settings, runner_id='runner-a', **patch):
    payload = {'runner_id': runner_id, 'settings': patch or {'board_names': {'board-a': 'renamed'}}}
    return dict(payload, desired_revision=digest(payload), state='PENDING')


def staged(profile, application, state='PENDING'):
    control.remember_desired(profile.home, application, application['runner_id'])
    path = control.pending_file(profile.home)
    value = json.loads(path.read_text()); value['state'] = state
    path.write_text(json.dumps(value))
    return path


def inventory(profile, application, **changes):
    value = profile.read()
    return dict({'runner_id': application['runner_id'], 'checked_at': time.time(),
                 'host_busy': False, 'reserved': False, 'boards': value['boards'],
                 'mapping_revision': digest(value['boards']),
                 'configuration_fields': {k: digest(v) for k, v in value.items()}}, **changes)


def test_request_uses_only_current_receipt_and_explicit_no_proxy_no_redirect_client(tmp_path, monkeypatch):
    monkeypatch.setattr(launch, 'read_active', lambda runtime: {'dashboard_url': 'http://127.0.0.1:18766'})
    calls, options = [], []
    real_client = httpx.Client
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={'revision': 'fixture'})
    def client(**kwargs):
        options.append(kwargs)
        return real_client(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(httpx, 'Client', client)
    assert control.request(tmp_path, 'settings', 'PUT', {'expected_revision': 'old'}) == {'revision': 'fixture'}
    assert options == [{'timeout': 10, 'trust_env': False, 'follow_redirects': False}]
    assert str(calls[0].url) == 'http://127.0.0.1:18766/api/v1/gui-test/live/integration/settings'
    assert calls[0].headers['X-Bsp-Service'] == 'plugin'
    assert json.loads(calls[0].content) == {'expected_revision': 'old'}


def test_disconnected_and_transport_errors_never_change_local_profile(profile, monkeypatch):
    before = profile.path.read_bytes()
    monkeypatch.setattr(launch, 'read_active', lambda runtime: None)
    with pytest.raises(TestError) as error: control.request(profile.home, 'settings')
    assert error.value.code == 'CONNECTOR_DISCONNECTED'
    monkeypatch.setattr(launch, 'read_active', lambda runtime: {'dashboard_url': 'http://127.0.0.1:18766'})
    real_client = httpx.Client
    def fail(request): raise httpx.ConnectError('private transport diagnostic', request=request)
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(fail), **kw))
    with pytest.raises(TestError) as error: control.request(profile.home, 'settings', 'PUT', {})
    assert error.value.code == 'SHARED_UNAVAILABLE'
    assert 'private transport' not in str(error.value)
    assert profile.path.read_bytes() == before


def test_path_browser_encodes_server_path_and_rejects_unknown_kind(profile, monkeypatch):
    calls = []
    monkeypatch.setattr(control, 'request', lambda *args: calls.append(args) or {})
    control.paths(profile.home, 'installer', '/srv/images/a & b')
    assert calls[0][1] == 'paths?kind=installer&path=%2Fsrv%2Fimages%2Fa+%26+b'
    with pytest.raises(TestError): control.paths(profile.home, 'windows', 'Z:/private')
    assert len(calls) == 1


def test_desired_revision_is_identity_pinned_and_stale_ack_is_ignored(profile, monkeypatch):
    a = desired(profile)
    control.remember_desired(profile.home, a, 'other-runner')
    assert not control.pending_file(profile.home).exists()
    staged(profile, a, 'SAVED')
    control.remember_desired(profile.home, a, a['runner_id'])
    assert json.loads(control.pending_file(profile.home).read_text())['state'] == 'SAVED'
    newer = desired(profile, board_names={'board-a': 'newer'})
    control.remember_desired(profile.home, newer, newer['runner_id'])
    assert json.loads(control.pending_file(profile.home).read_text())['desired_revision'] == newer['desired_revision']
    monkeypatch.setattr(control, 'request', lambda *a, **kw: pytest.fail('stale receipt sent'))
    control.acknowledge(profile.home, a, inventory(profile, a))


def test_pending_settings_do_not_modify_an_active_host(profile, monkeypatch):
    host = Host(profile.read(), profile.home / 'runtime', ports=lambda: {'COM7'})
    app = desired(profile, host.identity)
    path = staged(profile, app)
    before = profile.path.read_bytes(), path.read_bytes()
    with launch.LaunchLock(profile.home / 'runtime/setup-launch.lock'):
        with pytest.raises(RuntimeError): control.apply_pending(profile.home)
    assert (profile.path.read_bytes(), path.read_bytes()) == before


@pytest.mark.parametrize('state', ['RUNNING', 'UNKNOWN'])
def test_disconnected_unresolved_work_blocks_profile_change(profile, monkeypatch, state):
    host = Host(profile.read(), profile.home / 'runtime', ports=lambda: {'COM7'})
    with sqlite3.connect(host.db) as connection:
        connection.execute('INSERT INTO jobs VALUES(?,?,?)', ('unresolved', 'fingerprint', json.dumps({
            'id': 'unresolved', 'state': state, 'connection': {'a': BOARD}})))
    app = desired(profile, host.identity, boards=[dict(BOARD, com='COM8')])
    path = staged(profile, app)
    before = profile.path.read_bytes(), path.read_bytes()
    monkeypatch.setattr(launch, 'read_active', lambda runtime: None)
    with pytest.raises(TestError) as error: control.apply_pending(profile.home)
    assert error.value.code == 'CONNECTOR_BUSY'
    assert (profile.path.read_bytes(), path.read_bytes()) == before


def test_pending_previous_runner_identity_cannot_edit_replacement_host(profile, monkeypatch):
    Host(profile.read(), profile.home / 'runtime', ports=lambda: {'COM7'})
    app = desired(profile, 'previous-runner', boards=[dict(BOARD, com='COM8')])
    path = staged(profile, app)
    before = profile.path.read_bytes(), path.read_bytes()
    monkeypatch.setattr(launch, 'read_active', lambda runtime: None)
    with pytest.raises(TestError) as error: control.apply_pending(profile.home)
    assert error.value.code == 'RUNNER_CHANGED'
    assert (profile.path.read_bytes(), path.read_bytes()) == before


@pytest.mark.parametrize('flag', ['host_busy', 'reserved'])
def test_saved_profile_does_not_mean_applied_while_host_is_busy(profile, monkeypatch, flag):
    app = desired(profile)
    profile.save(app['settings']); staged(profile, app, 'SAVED')
    calls = []
    monkeypatch.setattr(control, 'request', lambda *args: calls.append(args))
    control.acknowledge(profile.home, app, inventory(profile, app, **{flag: True}))
    assert calls[-1][3]['state'] == 'BLOCKED' and calls[-1][3]['applied_revision'] == ''


def test_applied_receipt_requires_host_mapping_revision_not_only_saved_file(profile, monkeypatch):
    old = inventory(profile, desired(profile))
    app = desired(profile, serial_transport='proxy', serial_settings={'board-a': {'baudrate': 9600}})
    profile.save(app['settings']); staged(profile, app, 'SAVED')
    calls = []
    monkeypatch.setattr(control, 'request', lambda *args: calls.append(args))
    # Board names/COMs match but this inventory is from the old native Host.
    control.acknowledge(profile.home, app, inventory(profile, app, mapping_revision=old['mapping_revision'], configuration_fields=old['configuration_fields']))
    assert not any(call[3]['state'] == 'APPLIED' for call in calls)


def test_matching_idle_host_can_acknowledge_saved_desired_revision(profile, monkeypatch):
    app = desired(profile)
    profile.save(app['settings']); staged(profile, app, 'SAVED')
    calls = []
    monkeypatch.setattr(control, 'request', lambda *args: calls.append(args))
    control.acknowledge(profile.home, app, inventory(profile, app))
    assert calls[-1][1:] == ('connector-settings/receipt', 'POST', {
        'runner_id': app['runner_id'], 'desired_revision': app['desired_revision'], 'state': 'APPLIED',
        'reason': '', 'applied_revision': digest(app['settings'])})


@pytest.fixture
def qt():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


@pytest.fixture
def panel(qt, tmp_path):
    from backend.gui_test.connector.preview import MockConnector
    from backend.gui_test.connector.shared_settings_ui import SharedSettingsPanel
    adapter = MockConnector(tmp_path)
    class Owner:
        errors = []
        def operation(self, operation, done=None):
            try:
                value = operation()
                if done: done(value)
            except Exception as exc: self.show_error(str(exc))
        def show_error(self, value): self.errors.append(value)
    owner = Owner(); owner.adapter = adapter; owner.errors = []
    widget = SharedSettingsPanel(owner); widget.accept(adapter.shared_settings())
    yield widget, owner, adapter
    widget.close(); widget.deleteLater()


def test_qt_edit_save_and_conflict_preserve_draft_until_explicit_reload(panel):
    from PySide6.QtTest import QTest
    widget, owner, adapter = panel
    widget.installer.selectAll(); QTest.keyClicks(widget.installer, '/srv/images/next.bat')
    widget.seconds.setValue(77); widget.use_default.setChecked(True)
    assert widget.dirty
    widget.save()
    assert not owner.errors and not widget.dirty
    assert adapter.shared_settings()['timeouts']['default_seconds'] == 77
    assert adapter.shared_settings()['integration']['installer_path'] == '/srv/images/next.bat'
    QTest.keyClicks(widget.profile, '-draft')
    draft = widget.profile.text()
    adapter.shared['revision'] = 'server-new-revision'
    widget.accept(adapter.shared_settings())
    assert widget.profile.text() == draft and widget.dirty
    widget.save()
    assert owner.errors and widget.profile.text() == draft and widget.dirty
    widget.reload()
    assert widget.value['revision'] == 'server-new-revision' and not widget.dirty


def test_qt_server_browser_uses_linux_roots_without_local_file_dialog(panel, qt):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QListWidget, QPushButton
    widget, owner, adapter = panel
    calls = []; original = adapter.server_paths
    adapter.server_paths = lambda kind, path='': calls.append((kind, path)) or original(kind, path)
    errors = []
    def select():
        try:
            dialog = QApplication.activeModalWidget()
            listing = dialog.findChild(QListWidget)
            listing.itemDoubleClicked.emit(listing.item(0))
            assert calls[-1] == ('installer', '/srv/images')
            listing.setCurrentRow(0)
            next(b for b in dialog.findChildren(QPushButton) if b.text() == '선택').click()
        except BaseException as exc:
            errors.append(exc)
            QApplication.activeModalWidget().reject()
    QTimer.singleShot(0, select)
    widget.browse(widget.installer, 'installer')
    assert not errors, errors
    assert widget.installer.text() == '/srv/images/install.bat' and widget.dirty
    assert calls == [('installer', ''), ('installer', '/srv/images')]


def test_qt_save_response_cannot_overwrite_edits_made_while_request_in_flight(panel):
    widget, owner, adapter = panel
    pending = []
    owner.operation = lambda fn, done=None: pending.append((fn, done))
    widget.profile.setText('submitted'); widget.mark_dirty(); widget.save()
    # The real owner runs operations asynchronously while editors remain enabled.
    widget.profile.setText('new-unsaved-draft'); widget.mark_dirty()
    operation, callback = pending.pop()
    callback(operation())
    assert widget.profile.text() == 'new-unsaved-draft' and widget.dirty


def test_idle_identity_pinned_pending_profile_is_saved_without_losing_private_fields(profile):
    host = Host(profile.read(), profile.home / 'runtime', ports=lambda: {'COM7'})
    app = desired(profile, host.identity)
    staged(profile, app)
    before = profile.read()
    control.apply_pending(profile.home)
    current = profile.read()
    assert current['board_names'] == app['settings']['board_names']
    assert current['_setup'] == before['_setup'] and current['python'] == before['python']
    assert json.loads(control.pending_file(profile.home).read_text())['state'] == 'SAVED'


def test_central_application_from_another_runner_never_sends_receipt(profile, monkeypatch):
    app = desired(profile)
    profile.save(app['settings']); staged(profile, app, 'SAVED')
    monkeypatch.setattr(control, 'request', lambda *a, **kw: pytest.fail('foreign identity acknowledged'))
    control.acknowledge(profile.home, dict(app, runner_id='foreign'), inventory(profile, app))


@pytest.mark.parametrize('foreign', [False, True])
def test_supervisor_probe_verifies_host_identity_before_shared_registration(profile, monkeypatch, foreign):
    from backend.gui_test.connector.supervisor import Manager
    manager = object.__new__(Manager)
    manager.home = profile.home; manager.settings = profile; manager.error = ''; manager.thread = None
    manager.storage_cache = {'runtime_bytes': 1}; manager.storage_checked = time.monotonic()
    manager.console_cursor = 0; manager.console_epoch = None
    app = desired(profile)
    inv = inventory(profile, app)
    if foreign: inv['runner_id'] = 'replacement-host'
    receipt = {'runner_id': app['runner_id'], 'runner_url': 'http://127.0.0.1:18771',
               'dashboard_url': 'http://127.0.0.1:18766', 'remote_runner_port': 8771, 'phase': 'ssh_running'}
    monkeypatch.setattr(launch, 'read_active', lambda runtime: receipt)
    visited = []
    def handle(request):
        visited.append(request.url.path)
        if request.url.path.endswith('/inventory'): return httpx.Response(200, json=inv)
        if request.url.path.endswith('/console'): return httpx.Response(200, json={'boards': [], 'cursor': 1, 'epoch': 'fixture'})
        if request.url.path.endswith('/recent-executions'): return httpx.Response(200, json={'executions': []})
        return httpx.Response(200, json={'source_ready': True})
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(handle), **kw))
    shared = {'connector_application': app, 'revision': 'fixture'}
    requested = []
    def request(home, suffix, method='GET', value=None):
        requested.append((suffix, method, value))
        return shared if suffix == 'settings' else []
    monkeypatch.setattr(control, 'request', request)
    if foreign:
        with pytest.raises(TestError) as error: manager.probe()
        assert error.value.code == 'RUNNER_CHANGED'
        assert not requested and visited == ['/v1/inventory']
    else:
        result = manager.probe()
        assert result['state'] == 'CONNECTED' and result['shared_settings'] == shared
        assert result['stages']['roundtrip'] == 'READY'
        assert requested[0][0] == 'settings' and requested[-1][0] == 'analyses'
        assert json.loads(control.pending_file(profile.home).read_text())['runner_id'] == app['runner_id']


def test_qt_application_status_refreshes_even_when_common_settings_revision_is_unchanged(panel):
    widget, owner, adapter = panel
    value = adapter.shared_settings()
    assert '적용됨' in widget.status.text()
    value['connector_application'] = {'state': 'PENDING', 'desired_revision': 'new-windows-mapping'}
    widget.accept(value)
    assert '적용 대기' in widget.status.text()
    value['connector_application']['state'] = 'BLOCKED'
    widget.accept(value)
    assert '연결 재시작 대기' in widget.status.text()


def test_connector_window_displays_shared_analysis_response_without_detaching_on_close(qt, tmp_path, monkeypatch):
    from backend.gui_test.connector.gui import ConnectorWindow
    from backend.gui_test.connector.preview import MockConnector
    def operation(self, fn, done=None):
        result = fn()
        if done: done(result)
    monkeypatch.setattr(ConnectorWindow, 'operation', operation)
    adapter = MockConnector(tmp_path); adapter.connect()
    window = ConnectorWindow(adapter); window.timer.stop()
    try:
        value = adapter.status(); value['analyses'] = {'analyses': [{'status': 'LEASED'}]}
        window.render(value)
        assert '분석 LEASED' in window.space.text()
        assert window.shared_panel.value['revision'] == adapter.shared_settings()['revision']
        window.close()
        assert adapter.connected
    finally:
        window.close(); window.deleteLater()


def test_explicit_null_optional_board_node_matches_validated_host_configuration(profile, monkeypatch):
    app = desired(profile, boards=[dict(BOARD, com='COM8')])
    profile.save(app['settings'])
    host = Host(profile.read(), profile.home / 'runtime', ports=lambda: {'COM8'})
    app['runner_id'] = host.identity
    app['desired_revision'] = digest({'runner_id': host.identity, 'settings': app['settings']})
    staged(profile, app, 'SAVED')
    calls = []
    monkeypatch.setattr(control, 'request', lambda *args: calls.append(args))
    control.acknowledge(profile.home, app, host.inventory())
    assert calls[-1][3]['state'] == 'APPLIED'
