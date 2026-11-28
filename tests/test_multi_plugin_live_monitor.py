"""T-324. Resolve a Windows target and redeem its grant against real loopback services."""
from contextlib import contextmanager
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import uvicorn

from backend.api.shared_monitor import create_shared_monitor
from backend.gui_test.connector import monitor_tasks
from test_direct_connector_unit4 import _start_live_host


@contextmanager
def monitor_service(runtime, host, account, monitor_id, host_port):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        with host.sharing.connect() as db:
            principal = host.sharing.issue(db, 'account', account)
            installation = host.sharing.approve_monitor(db, account, monitor_id, 'default', port, protected_listener=True)
        app = create_shared_monitor(runtime, monitor_id, host_port, monitor_token=installation['token'],
                                    protected_listener=installation['protected_listener'], trust_protected_loopback=True)
        server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level='warning'))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 8
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started
            yield port, principal
        finally:
            server.should_exit = True
            thread.join(8)


class LocalForward:
    """Only the SSH forwarding is simulated. The returned port serves the real Monitor."""
    def forward_shared_monitor(self, setup, remote_port, generation):
        return remote_port

    def shared_forward_live(self, generation, port):
        return True


def test_windows_target_opens_registered_linux_monitor_and_pins_each_work(tmp_path):
    host, host_port, server, thread = _start_live_host(tmp_path)
    host_url = f'http://127.0.0.1:{host_port}'
    runtime = tmp_path / 'winhome/runtime'
    try:
        with host.sharing.connect() as db:
            host.sharing.enable(db)
        with monitor_service(tmp_path, host, 'alice', 'monitor-a', host_port) as first, \
                monitor_service(tmp_path, host, 'bob', 'monitor-b', host_port) as second, \
                httpx.Client(trust_env=False) as browser:
            tasks = []
            for account, monitor_id, (port, principal) in [('alice', 'monitor-a', first), ('bob', 'monitor-b', second)]:
                task_id = uuid4().hex
                headers = {'Authorization': 'Bearer ' + principal['token'],
                           'X-Bsp-Task-ID': task_id, 'X-Bsp-Task-Key': secrets.token_urlsafe(36)}
                tasks.append((task_id, account, monitor_id, port, headers))
            with httpx.Client(headers=monitor_tasks.admin_headers(runtime), trust_env=False) as operator:
                for task_id, account, monitor_id, port, headers in tasks:
                    response = browser.put(host_url + '/v1/sharing/tasks/' + task_id, headers=headers,
                                           json={'project': 'project-' + account, 'monitor_id': monitor_id})
                    assert response.status_code == 200, response.text
                profile = {'server': '127.0.0.1', 'account': 'bsp', 'ssh_port': 22}
                selection, rows = monitor_tasks.task_list(operator, host_url, runtime, profile, True)
                assert selection['default_task_id'] is None
                for task_id, account, monitor_id, port, _ in tasks:
                    row = next(row for row in rows if row['task_id'] == task_id)
                    setup, destination_port = monitor_tasks.destination(runtime, profile, row)
                    url = monitor_tasks.monitor_url(operator, row, setup, destination_port, LocalForward(), 1, host_url)
                    parts = urlsplit(url)
                    assert parts.port == port and parse_qs(parts.query)['task'] == [task_id]
                    origin = f'http://127.0.0.1:{port}'
                    assert browser.get(origin + parts.path).status_code == 200
                    path = origin + '/api/v1/plugin-task/' + task_id
                    request = {'json': {'ticket': parse_qs(parts.fragment)['ticket'][0]}, 'headers': {'Origin': origin}}
                    session = browser.post(path + '/session', **request)
                    assert session.status_code == 200, session.text
                    view = browser.get(path, headers={'Authorization': 'Bearer ' + session.json()['view_token']})
                    assert view.status_code == 200 and view.json()['task']['project'] == 'project-' + account
                    assert browser.post(path + '/session', **request).status_code == 403
                    assert browser.get(origin + '/api/v1/jobs').status_code in (403, 404)
    finally:
        server.should_exit = True
        thread.join(8)
