from io import BytesIO
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from backend.gui_test.connector import ssh_tunnel, supervisor
from backend.gui_test.core.connector_bootstrap import FORMAT


def health_document(**changes):
    return dict({'status': 'degraded', 'mode': 'integration', 'runtime_id': 'lab-runtime',
                 'package_version': '1.2.3', 'service_instance_id': 'monitor-instance',
                 'capabilities': ['shared-settings-v1', 'bsp-control-v1']}, **changes)


PINNED = {
    'format': FORMAT,
    'endpoint': {'server': 'linux.example', 'account': 'operator', 'ssh_port': 22,
                 'remote_dashboard_port': 9876},
    'identity': {'runtime_id': 'lab-runtime', 'package_version': '1.2.3'},
}


@pytest.mark.parametrize(('status', 'document', 'entry', 'ready'), [
    (200, health_document(), (200, 'text/html; charset=utf-8'), True),
    (200, health_document(status='ok'), (200, 'text/html'), True),
    (200, health_document(runtime_id='other-runtime'), None, False),
    (200, health_document(capabilities=['shared-settings-v1']), None, False),
    (200, {'status': 'ok'}, None, False),
    (200, ['not a health document'], None, False),
    (302, health_document(), None, False),
    (403, health_document(), None, False),
    (200, health_document(), (404, 'application/json'), False),
    (200, health_document(), (200, 'application/json'), False),
    (200, health_document(), (302, 'text/html'), False),
])
def test_monitor_health_checks_identity_capabilities_and_auth(monkeypatch, status, document, entry, ready):
    real_client = httpx.Client

    def reply(request):
        if request.method == 'HEAD':
            assert entry and str(request.url) == 'http://127.0.0.1:19876/'
            assert 'x-bsp-service' not in request.headers
            assert 'x-bsp-runtime-id' not in request.headers
            return httpx.Response(entry[0], headers={'content-type': entry[1], 'location': 'https://elsewhere.example'})
        assert str(request.url) == 'http://127.0.0.1:19876/api/v1/health'
        assert request.headers['x-bsp-service'] == 'plugin'
        assert request.headers['x-bsp-runtime-id'] == 'lab-runtime'
        assert request.headers['x-bsp-package-version'] == '1.2.3'
        return httpx.Response(status, json=document, headers={'location': 'https://elsewhere.example'})

    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(reply), **kwargs))
    assert ssh_tunnel.probe_dashboard_health('http://127.0.0.1:19876', PINNED) is ready


def test_stale_status_discards_monitor_url_and_direct_link_does_not_enable_legacy_control():
    connected = {'dashboard_url': 'http://127.0.0.1:19876', 'fresh': True, 'connection_mode': 'direct'}
    assert supervisor.stale_display(connected, 'Host unavailable')['dashboard_url'] == ''
    assert not supervisor.legacy_dashboard_url(connected)
    assert supervisor.legacy_dashboard_url(dict(connected, connection_mode='legacy')) == connected['dashboard_url']


@pytest.mark.parametrize(('remote_port', 'local_port', 'channel', 'ready'), [
    (9876, 19876, 'new [port listener]', True),
    (9876, 19876, 'new port-listener [port listener] (inactive timeout: 0)', True),
    (9877, 19876, 'new [port listener]', False),
    (9876, 19877, 'new [port listener]', False),
    (9876, 19876, 'new [client-session]', False),
    (9876, 19876, 'bind [127.0.0.1]:19876: Address already in use\ndebug1: channel 1: new [port listener]', False),
])
def test_ssh_observes_current_loopback_listener_on_old_and_new_openssh(tmp_path, remote_port, local_port, channel, ready):
    transport = ssh_tunnel.SshTunnelSupervisor(tmp_path, {}, actual_local_runner_port=8772)
    stderr = (f'debug1: Local connections to 127.0.0.1:19876 forwarded to remote address 127.0.0.1:{remote_port}\n'
              f'debug1: Local forwarding listening on 127.0.0.1 port {local_port}.\n'
              'debug1: fd 7 setting O_NONBLOCK\n'
              + (f'debug1: channel 0: {channel}\n' if channel.startswith('new') else channel + '\n'))
    forward = SimpleNamespace(stderr=BytesIO(stderr.encode()))
    transport._l_proc = forward
    transport._observe_dashboard_bind(forward, 19876, 9876)
    assert transport._l_bound is ready


@pytest.mark.parametrize(('local_port', 'remote_port', 'expected_attempts'), [
    (18766, None, 0), (8772, 8766, 0), (18766, 70000, 0), (18766, 8766, 1),
])
def test_dashboard_forward_skips_invalid_config_and_halts_on_auth_error(tmp_path, monkeypatch, local_port,
                                                                       remote_port, expected_attempts):
    attempts = []
    reverse = SimpleNamespace(poll=lambda: None, stdout=None, stderr=None)

    def spawn(argv, **kwargs):
        attempts.append(argv)
        return SimpleNamespace(poll=lambda: 255, stderr=BytesIO(b'Permission denied (publickey).\n'))

    cfg = {'server': 'linux', 'account': 'qa'}
    transport = ssh_tunnel.SshTunnelSupervisor(
        tmp_path, cfg, actual_local_runner_port=8772, local_dashboard_port=local_port,
        remote_dashboard_port=remote_port, stability_window=0, backoff_schedule=(0.01,), popen=spawn,
    )
    transport._r_proc = reverse
    monkeypatch.setattr(ssh_tunnel, 'probe_remote_identity', lambda *args: (True, ''))
    monkeypatch.setattr(transport, '_remember_ssh', lambda *args: None)
    thread = threading.Thread(target=transport._monitor_ssh_process, args=(reverse, None, 'ssh', cfg, 22, 8771))
    thread.start()
    try:
        deadline = time.monotonic() + 2
        while (transport.ssh_state != 'CONNECTED' or
               transport.optional_dashboard_forward not in ('NOT_CONFIGURED', 'LOCAL_DASHBOARD_FORWARD_SKIPPED')):
            assert time.monotonic() < deadline
            time.sleep(0.01)
        time.sleep(0.2)  # Observe several supervisor ticks after the optional failure.
        assert len(attempts) == expected_attempts
        assert transport.ssh_state == 'CONNECTED' and not transport.dashboard_url(transport.transport_started_at)
    finally:
        transport._stop_event.set()
        thread.join(timeout=2)
    assert not thread.is_alive()
    assert transport._start_optional_dashboard_forward('ssh', cfg, {}, {}, reverse) == (None, None)
    assert len(attempts) == expected_attempts


def test_manager_rechecks_live_generation_on_every_published_status(tmp_path):
    manager = supervisor.Manager.__new__(supervisor.Manager)
    manager.home = tmp_path
    manager.control_lock = threading.RLock()
    manager.putty_cleanup = {}
    manager.ssh_supervisor = SimpleNamespace(dashboard_url=lambda generation: 'http://127.0.0.1:19876' if generation == 23 else '')
    manager.cached = {'connection_mode': 'direct', 'state': 'CONNECTED', 'ssh_state': 'CONNECTED',
                      'dashboard_url': '', 'stages': {}, 'fresh': True, 'last_checked_at': time.time(),
                      'ssh_transport_started_at': 23}
    assert manager.status()['dashboard_url'] == 'http://127.0.0.1:19876'
    assert manager.status()['stages']['agent_monitor'] == 'CONNECTED'
    from fastapi.testclient import TestClient
    from backend.gui_test.connector.web_actions import ManagerActions
    with TestClient(supervisor.create_manager_app(manager, 'test-secret'), client=('127.0.0.1', 1234)) as client:
        response = client.get('/status', headers={'Authorization': 'Bearer test-secret'})
        assert response.status_code == 200 and response.json()['dashboard_url'] == 'http://127.0.0.1:19876'
    assert ManagerActions(manager).status()['dashboard_url'] == 'http://127.0.0.1:19876'

    manager.ssh_supervisor = SimpleNamespace(dashboard_url=lambda generation: '')
    manager.cached['dashboard_url'] = 'http://127.0.0.1:19876'
    assert manager.status()['dashboard_url'] == ''
    assert manager.status()['stages']['agent_monitor'] == 'OPTIONAL_OFFLINE'
    manager.cached['peers'] = {'agent_monitor': {'client_status': 'OK', 'stale': False}}
    assert manager.status()['dashboard_url'] == ''
    assert manager.status()['stages']['agent_monitor'] == 'CONNECTED'
    manager.ssh_supervisor = SimpleNamespace(dashboard_url=lambda generation: 'http://127.0.0.1:19876')
    manager.cached = supervisor.stale_display(manager.cached, 'Host unavailable')
    assert manager.status()['dashboard_url'] == ''


def test_qt_open_monitor_clears_live_button_on_poll_error_and_reconnect(tmp_path, monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QThreadPool
    from backend.gui_test.connector.gui import ConnectorWindow, QDesktopServices
    from backend.gui_test.connector.preview import MockConnector

    class Adapter(MockConnector):
        preview = False
        unavailable = False

        def status(self):
            if self.unavailable:
                raise RuntimeError('Manager endpoint unavailable')
            return super().status() | {'connection_mode': 'direct', 'dashboard_url': 'http://127.0.0.1:19876',
                                       'last_checked_at': time.time()}

    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda url: opened.append(url.toString()))
    app = QApplication.instance() or QApplication([])
    adapter = Adapter(tmp_path)
    adapter.connect()
    window = ConnectorWindow(adapter)
    window.timer.stop()
    pool = QThreadPool.globalInstance()
    try:
        assert pool.waitForDone(5000)
        app.processEvents()
        assert not window.dashboard_button.isHidden()
        window.dashboard_button.click()
        assert opened == ['http://127.0.0.1:19876']

        adapter.unavailable = True
        window.poll()
        assert pool.waitForDone(5000)
        app.processEvents()
        assert window.dashboard_button.isHidden() and not window.snapshot['dashboard_url']
        window.open_dashboard()
        assert len(opened) == 1

        adapter.unavailable = False
        window.render(adapter.status())
        window.render(adapter.status() | {'state': 'RECONNECTING'})
        assert window.dashboard_button.isHidden()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
