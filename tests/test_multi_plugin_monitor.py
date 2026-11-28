"""T-324 task Monitor isolation, operator routing, and Qt task selection."""
from io import BytesIO
import json
import secrets
import threading
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.api.shared_monitor import create_shared_monitor
from backend.gui_test.connector import monitor_tasks, ssh_tunnel
from backend.gui_test.connector.supervisor import Manager
from backend.gui_test.core.models import TestError as ConnectorError
from backend.gui_test.core.monitor_identity import monitor_proof
from test_direct_connector_unit3 import _setup_host

TASK_A, TASK_B = 'a' * 32, 'b' * 32
SSH_A = {'server': 'primary.example', 'account': 'operator', 'ssh_port': 22}
SSH_B = {'server': 'secondary.example', 'account': 'other', 'ssh_port': 2222}


@pytest.fixture
def shared_host(tmp_path):
    _, _, host, app = _setup_host(tmp_path)
    with host.sharing.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        host.sharing.enable(db)
        a = host.sharing.issue(db, 'account', 'one')['token']
        b = host.sharing.issue(db, 'account', 'two')['token']
        keys = {
            'monitor-a': host.sharing.approve_monitor(db, 'one', 'monitor-a', 'default', 9876, protected_listener=True)['token'],
            'monitor-b': host.sharing.approve_monitor(db, 'two', 'monitor-b', 'second', 9976, protected_listener=True)['token'],
        }
    with TestClient(app, base_url='http://127.0.0.1:8771', client=('127.0.0.1', 5001)) as client:
        for task, monitor, account in ((TASK_A, 'monitor-a', a), (TASK_B, 'monitor-b', b)):
            response = client.put('/v1/sharing/tasks/' + task,
                                  headers={'Authorization': 'Bearer ' + account, 'X-Bsp-Task-Key': secrets.token_urlsafe(36)},
                                  json={'project': 'Project ' + task[:1], 'monitor_id': monitor})
            assert response.status_code == 200, response.text
        yield host, client, keys


def as_transport(client):
    def dispatch(request):
        response = client.request(request.method, request.url.raw_path.decode(), headers=request.headers, content=request.content)
        return httpx.Response(response.status_code, json=response.json())
    return httpx.MockTransport(dispatch)


@pytest.fixture
def windows_admin(shared_host):
    host, _, _ = shared_host
    return {'Authorization': 'Bearer ' + host.sharing.admin.load(readonly=True)}


def task_url(task):
    return '/api/v1/plugin-task/' + task


def redeem(client, task, ticket):
    return client.post(task_url(task) + '/session', json={'ticket': ticket}, headers={'Origin': str(client.base_url).rstrip('/')})


def test_shared_listener_denies_global_paths_by_default(tmp_path, monkeypatch):
    runtime = tmp_path / 'uncreated'
    instance = secrets.token_hex(16)
    monkeypatch.setenv('AGENT_MONITOR_INSTANCE', instance)
    monkeypatch.setenv('AGENT_MONITOR_RELEASE', 'installed')
    key = tmp_path / 'monitor-key.json'
    token = secrets.token_urlsafe(32)
    installation = {'schema_version': 1, 'monitor_id': 'approved', 'runner_id': TASK_A, 'token': token}
    key.write_text(json.dumps(installation))
    key.chmod(0o600)
    config = {'sharing_monitor_id': 'approved', 'connector_port': 8771, 'sharing_monitor_key_file': key}
    with pytest.raises(ValueError, match='approval of its protected listener'):
        create_app(runtime, **config, trust_protected_loopback=True)
    key.write_text(json.dumps(installation | {'protected_listener': False}))
    with pytest.raises(ValueError, match='approval of its protected listener'):
        create_app(runtime, **config, trust_protected_loopback=True)
    key.write_text(json.dumps(installation | {'protected_listener': True}))
    with pytest.raises(ValueError, match='protected Host socket'):
        create_app(runtime, **config)
    app = create_app(runtime, **config, trust_protected_loopback=True)
    with TestClient(app, client=('127.0.0.1', 5002)) as browser:
        for path in ('/', '/gui-test/', '/gui-test/live/', '/api/v1/config', '/api/v1/jobs',
                     '/api/v1/gui-test/live/connector/direct/runs', '/docs', '/openapi.json'):
            assert browser.get(path).status_code == 404
        health = browser.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin'}).json()
        assert health == {'status': 'ok', 'mode': 'shared-task-monitor', 'monitor_id': 'approved'}
        challenge = secrets.token_hex(32)
        proof = browser.get('/api/v1/health', headers={'X-Bsp-Monitor-Challenge': challenge}).json()
        assert proof['monitor_proof'] == monitor_proof(token, 'approved', challenge)
        assert token not in json.dumps(proof)
        managed = browser.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin', 'X-Bsp-Monitor-Instance': instance}).json()
        assert managed['managed_runtime'] == str(runtime)
        browser.cookies.set('session', 'unrelated')
        assert browser.get(task_url(TASK_A)).status_code == 401
        shell = browser.get('/plugin-task/')
        assert shell.status_code == 200 and shell.headers['Referrer-Policy'] == 'no-referrer'
        assert 'Cache-Control' in shell.headers and 'no-store' in shell.headers['Cache-Control']
        assert not runtime.exists()
    with TestClient(app, client=('203.0.113.5', 5002)) as remote:
        assert remote.get('/api/v1/health').status_code == 403
    key.chmod(0o644)
    with pytest.raises(ValueError, match='owner-only'):
        create_app(runtime, **config, trust_protected_loopback=True)


def test_two_monitor_tabs_use_one_time_scoped_host_permissions(shared_host, windows_admin, tmp_path):
    host, client, keys = shared_host
    app_a = create_shared_monitor(tmp_path, 'monitor-a', 8771, monitor_token=keys['monitor-a'],
                                  protected_listener=True, transport=as_transport(client))
    app_b = create_shared_monitor(tmp_path, 'monitor-b', 8771, monitor_token=keys['monitor-b'],
                                  protected_listener=True, transport=as_transport(client))
    wrong_key_app = create_shared_monitor(tmp_path, 'monitor-a', 8771, monitor_token=secrets.token_urlsafe(32),
                                          protected_listener=True, transport=as_transport(client))
    with (TestClient(app_a, client=('127.0.0.1', 5002)) as tab_a,
          TestClient(app_b, client=('127.0.0.1', 5003)) as tab_b):
        ticket_a = client.post(f'/v1/sharing/tasks/{TASK_A}/view-tickets', headers=windows_admin).json()['ticket']
        ticket_b = client.post(f'/v1/sharing/tasks/{TASK_B}/view-tickets', headers=windows_admin).json()['ticket']
        with TestClient(wrong_key_app, client=('127.0.0.1', 5004)) as wrong_key:
            assert redeem(wrong_key, TASK_A, ticket_a).status_code == 403
        assert redeem(tab_b, TASK_A, ticket_a).status_code == 403
        assert redeem(tab_a, TASK_B, ticket_a).status_code == 403
        assert tab_a.post(task_url(TASK_A) + '/session', json={'ticket': ticket_a},
                          headers={'Origin': 'http://other.example'}).status_code == 403
        view_a = redeem(tab_a, TASK_A, ticket_a)
        assert view_a.status_code == 200 and 'set-cookie' not in view_a.headers
        assert redeem(tab_a, TASK_A, ticket_a).status_code == 403
        view_b = redeem(tab_b, TASK_B, ticket_b)
        headers_a = {'Authorization': 'Bearer ' + view_a.json()['view_token']}
        headers_b = {'Authorization': 'Bearer ' + view_b.json()['view_token']}
        assert client.get(f'/v1/sharing/tasks/{TASK_A}/view', headers=headers_a).status_code == 401
        assert tab_a.get(task_url(TASK_A), headers=headers_a).json()['task']['project'] == 'Project a'
        assert tab_b.get(task_url(TASK_B), headers=headers_b).json()['task']['project'] == 'Project b'
        assert tab_a.get(task_url(TASK_A), headers=headers_b).status_code == 403
        assert tab_b.get(task_url(TASK_B), headers=headers_a).status_code == 403
        assert tab_b.get(task_url(TASK_A), headers=headers_a).status_code == 403
        assert tab_b.get(task_url(TASK_B) + f'?run_id={TASK_A}', headers=headers_b).status_code == 403
        assert tab_b.get(task_url(TASK_B) + f'/runs/{TASK_A}/attempts/{TASK_A}/logs', headers=headers_b).status_code == 403
        assert tab_a.get('/api/v1/config', headers=headers_a).status_code == 404
        assert tab_a.get(task_url(TASK_A), headers=windows_admin).status_code == 403
        with host.sharing.connect() as db:
            host.sharing.revoke(db, 'account', 'one')
        assert tab_a.get(task_url(TASK_A), headers=headers_a).status_code == 403
        assert tab_b.get(task_url(TASK_B), headers=headers_b).status_code == 200


def test_manager_routes_installations_without_fallback_and_uses_current_generation(shared_host, monkeypatch, tmp_path):
    host, client, keys = shared_host
    manager = object.__new__(Manager)
    manager.runtime = host.runtime
    manager.control_lock = threading.RLock()
    manager.host_url = 'http://127.0.0.1:8771'
    manager.host_runner_id = host.identity
    manager.settings = SimpleNamespace(read=lambda: {'_setup': SSH_A})
    profiles = manager.runtime / 'shared-monitor-ssh.json'
    profiles.write_text(json.dumps({'profiles': {'second': SSH_B}}))
    forwards = []
    current = 81
    change_generation = False
    accepted_proof = True
    tickets_issued = []

    def forward(setup, remote, generation):
        forwards.append((setup['server'], setup['ssh_port'], remote, generation))
        return remote + 10000

    manager.ssh_supervisor = SimpleNamespace(
        snapshot=lambda: {'tunnel': {'transport_started_at': current}},
        shared_generation_live=lambda generation: generation == current,
        shared_forward_live=lambda generation, port: generation == current and not change_generation,
        forward_shared_monitor=forward,
    )
    real_httpx = httpx.Client
    host_transport = as_transport(client)
    def dispatch(request):
        if request.url.port == 8771:
            if request.url.path.endswith('/view-tickets'):
                tickets_issued.append(request.url.path)
            return host_transport.handle_request(request)
        assert 'authorization' not in request.headers
        if request.method == 'HEAD':
            assert request.url.path == '/plugin-task/'
            return httpx.Response(200, headers={'Content-Type': 'text/html'})
        monitor_id = {19876: 'monitor-a', 19976: 'monitor-b'}[request.url.port]
        proof = (monitor_proof(keys[monitor_id], monitor_id, request.headers['X-Bsp-Monitor-Challenge'])
                 if accepted_proof else 'a' * 64)
        return httpx.Response(200, json={'status': 'ok', 'mode': 'shared-task-monitor', 'monitor_id': monitor_id,
                                         'monitor_proof': proof})
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real_httpx(transport=httpx.MockTransport(dispatch), **kw))

    with pytest.raises(ConnectorError, match='목록에서 선택'):
        manager.open_task_monitor()
    for task, port in ((TASK_A, 19876), (TASK_B, 19976)):
        url = urlsplit(manager.open_task_monitor(task)['url'])
        assert url.port == port and url.hostname == '127.0.0.1'
        assert parse_qs(url.query) == {'task': [task]} and parse_qs(url.fragment)['ticket']
    assert forwards == [('primary.example', 22, 9876, 81), ('secondary.example', 2222, 9976, 81)]
    profiles.unlink()
    with pytest.raises(ConnectorError) as missing:
        manager.open_task_monitor(TASK_B)
    assert missing.value.code == 'MONITOR_UNREGISTERED'
    with pytest.raises(ConnectorError) as denied:
        manager.open_task_monitor('c' * 32)
    assert denied.value.code == 'MONITOR_ACCESS_DENIED'
    assert len(forwards) == 2
    assert urlsplit(manager.open_task_monitor()['url']).port == 19876
    accepted_proof = False
    with pytest.raises(ConnectorError) as mismatched:
        manager.open_task_monitor(TASK_A)
    assert mismatched.value.code == 'MONITOR_IDENTITY_MISMATCH'
    assert len(tickets_issued) == 3
    accepted_proof = True
    current = 82
    change_generation = True
    with pytest.raises(ConnectorError) as failed:
        manager.open_task_monitor(TASK_A)
    assert failed.value.code == 'MONITOR_OFFLINE'
    assert forwards[-1] == ('primary.example', 22, 9876, 82)


def test_tunnel_proves_binds_tracks_multiple_routes_and_discards_previous_generation(tmp_path, monkeypatch):
    processes = []
    class FakeChild:
        status = None
        def poll(self): return self.status
        def terminate(self): self.status = 0
        def wait(self, timeout): return self.status

    def spawn(argv, **kwargs):
        child = FakeChild()
        _, local, _, remote = argv[argv.index('-L') + 1].split(':')
        child.stderr = BytesIO((f'debug1: Local connections to 127.0.0.1:{local} forwarded to remote address 127.0.0.1:{remote}\n'
                                f'debug1: Local forwarding listening on 127.0.0.1 port {local}.\n'
                                'debug1: channel 0: new [port listener]\n').encode())
        processes.append(child)
        return child
    supervisor = ssh_tunnel.SshTunnelSupervisor(tmp_path, SSH_A, actual_local_runner_port=8772, popen=spawn)
    monkeypatch.setattr(supervisor, '_remember_ssh', lambda *_: None)
    supervisor.last_preflight = {'ssh_path': 'ssh'}
    supervisor.ssh_state = 'CONNECTED'
    supervisor._r_proc = FakeChild()
    supervisor.transport_started_at = 1
    first = supervisor.forward_shared_monitor(SSH_A, 9876, 1)
    second = supervisor.forward_shared_monitor(SSH_B, 9976, 1)
    assert first != second
    assert supervisor.forward_shared_monitor(SSH_A, 9876, 1) == first
    assert len(processes) == 2
    supervisor._terminate_procs()
    assert not supervisor.shared_forward_live(1, first)
    assert all(child.poll() == 0 for child in processes)
    supervisor._r_proc = FakeChild()
    supervisor.transport_started_at = 2
    assert supervisor.forward_shared_monitor(SSH_A, 9876, 2) not in {first, second}
    supervisor._terminate_procs()


def test_qt_selects_active_owner_and_pins_requested_task(tmp_path, monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QThreadPool
    from backend.gui_test.connector.gui import ConnectorWindow, QDesktopServices
    from backend.gui_test.connector.preview import MockConnector

    class Adapter(MockConnector):
        preview = False
        def status(self):
            current = time.time()
            tasks = [{'task_id': task, 'project': project, 'account': 'op', 'last_seen_at': current - i,
                      'monitor_state': 'APPROVED'}
                     for i, (task, project) in enumerate(((TASK_A, 'Latest'), (TASK_B, 'Owner')))]
            return super().status() | {'state': 'CONNECTED', 'fresh': True, 'last_checked_at': current,
                'shared_monitor': {'state': 'READY', 'tasks': tasks, 'default_task_id': TASK_B, 'active_task_id': TASK_B}}
        def open_task_monitor(self, task):
            return {'url': f'http://127.0.0.1:19876/plugin-task/?task={task}#ticket={secrets.token_urlsafe(32)}'}

    opened = []
    monkeypatch.setattr(QDesktopServices, 'openUrl', lambda qurl: opened.append(qurl) or True)
    app = QApplication.instance() or QApplication([])
    adapter = Adapter(tmp_path)
    adapter.connect()
    window = ConnectorWindow(adapter)
    window.timer.stop()
    pool = QThreadPool.globalInstance()
    try:
        assert pool.waitForDone(5000)
        app.processEvents()
        assert window.monitor_task.currentData() == TASK_B
        assert '마지막 보고 Latest' in window.plugin_status.text() and 'Run 소유 작업 Owner' in window.plugin_status.text()
        window.dashboard_button.click()
        assert pool.waitForDone(5000)
        app.processEvents()
        assert parse_qs(urlsplit(opened[0].toString()).query) == {'task': [TASK_B]}
        window.select_monitor_task(window.monitor_task.findData(TASK_A))
        window.dashboard_button.click()
        assert pool.waitForDone(5000)
        app.processEvents()
        assert parse_qs(urlsplit(opened[1].toString()).query) == {'task': [TASK_A]}
        window.render(adapter.status() | {'fresh': False})
        assert not window.dashboard_button.isEnabled()
        assert '오프라인' in window.plugin_status.text()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
