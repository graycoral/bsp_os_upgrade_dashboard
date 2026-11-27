"""Exercise the Manager tunnel against a private loopback OpenSSH server."""
from contextlib import ExitStack
import getpass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import shlex
import shutil
import socket
import subprocess
import threading
import time

import pytest

from backend.gui_test.connector.ssh_tunnel import SshTunnelSupervisor
from backend.gui_test.execution.launch import LaunchLock, process_identity, write_host_active


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize('mode', ['active', 'restricted', 'force_command', 'wrong_runner', 'occupied', 'host_down'])
def test_real_ssh_bind_with_no_success_log(tmp_path, mode, monkeypatch):
    if os.name != 'posix':
        pytest.skip('POSIX sshd fixture')
    sshd = shutil.which('sshd') or '/usr/sbin/sshd'
    if not Path(sshd).is_file() or not all(shutil.which(cmd) for cmd in ('ssh', 'ssh-keygen', 'curl')):
        pytest.skip('OpenSSH server and client required for loopback test')

    runner_id = 'a' * 32
    requests = []
    peer_reports = []
    restricted = mode in ('restricted', 'force_command')
    endpoint_runner_id = 'b' * 32 if mode == 'wrong_runner' else runner_id

    class Host(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()
            if self.path == '/v1/diagnostics/connection':
                self.wfile.write(json.dumps({'runner_id': runner_id, 'peers': {'recent': peer_reports}}).encode())
                return
            self.wfile.write(json.dumps({
                'schema_version': 'direct-connector-v1', 'service': 'bsp-board-connector',
                'runner_id': endpoint_runner_id, 'capabilities': ['direct-connector-v1'],
            }).encode())

        def do_POST(self):
            assert self.path == '/v1/peer/hello'
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            peer_reports.append(dict(data, observed_at=time.time(), stale=False))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')

        def log_message(self, *args):
            pass

    for key in ('host', 'client'):
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(tmp_path / key)], check=True)
    ssh_port = free_port()
    config = tmp_path / 'sshd_config'
    sessions = 0 if mode == 'restricted' else 2
    forced = 'ForceCommand /bin/false\n' if mode == 'force_command' else ''
    config.write_text(
        f'ListenAddress 127.0.0.1\nPort {ssh_port}\nHostKey "{tmp_path}/host"\n'
        f'PidFile "{tmp_path}/pid"\nAuthorizedKeysFile "{tmp_path}/client.pub"\n'
        f'{forced}MaxSessions {sessions}\nAllowTcpForwarding remote\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nAllowUsers {getpass.getuser()}\n'
    )
    known = tmp_path / 'known_hosts'
    known.write_text(f'[127.0.0.1]:{ssh_port} ' + (tmp_path / 'host.pub').read_text())
    attempts = []
    # The probe and the transport must both use the isolated known_hosts file.
    ssh = tmp_path / 'ssh'
    ssh.write_text("#!/bin/sh\nexec " + shlex.join([
        shutil.which('ssh'), '-F', '/dev/null', '-o', 'LogLevel=DEBUG1' if mode == 'host_down' else 'LogLevel=ERROR',
        '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={known}',
    ]) + ' "$@"\n')
    ssh.chmod(0o700)

    def spawn(argv, **kwargs):
        proc = subprocess.Popen(argv, **kwargs)
        attempts.append(proc)
        return proc

    with ExitStack() as stack:
        local_port = free_port()

        def start_host():
            http = ThreadingHTTPServer(('127.0.0.1', local_port), Host)
            stack.callback(http.server_close)
            threading.Thread(target=http.serve_forever, daemon=True).start()
            stack.callback(http.shutdown)
        if mode != 'host_down':
            start_host()
        server = stack.enter_context(subprocess.Popen([sshd, '-D', '-e', '-f', str(config)]))
        stack.callback(server.terminate)
        remote = local_port if mode == 'occupied' else free_port()
        # For the passive path the Host timestamps reports on receipt.
        peer = {'client_status': 'OK', 'stale': False, 'target_port': remote,
                'linux_host': 'localhost', 'observed_at': time.time() - 100}
        if restricted:
            peer_reports.append(peer)

        supervisor = SshTunnelSupervisor(
            tmp_path / 'runtime', {'server': '127.0.0.1', 'ssh_port': ssh_port,
                                   'account': getpass.getuser(), 'ssh_key': str(tmp_path / 'client')},
            actual_local_runner_port=local_port, remote_runner_port=remote,
            bind_timeout=2, popen=spawn, backoff_schedule=(0.1,),
            preflight_fn=lambda *args, **kwargs: {'ok': True, 'ssh_path': str(ssh)},
        )
        deadline = time.monotonic() + 3
        while True:
            try:
                with socket.create_connection(('127.0.0.1', ssh_port), timeout=0.1):
                    break
            except OSError:
                assert server.poll() is None and time.monotonic() < deadline
                time.sleep(0.03)
        runtime = tmp_path / 'runtime'
        stack.enter_context(LaunchLock(runtime / 'runner.lock'))
        host_process = process_identity(os.getpid())
        if host_process is None:
            # macOS has neither Windows process handles nor Linux /proc.
            host_process = {'pid': os.getpid(), 'creation_time': 'loopback-host-fixture'}
            monkeypatch.setattr('backend.gui_test.execution.launch.process_identity',
                                lambda pid: host_process if pid == os.getpid() else None)
        write_host_active(runtime, {
            'version': 2, 'launch_id': 'c' * 32, 'owner': host_process, 'runner': host_process,
            'runner_id': runner_id, 'runner_port': local_port, 'local_state': 'READY',
            'manager_attached': True, 'started_at': time.time(),
        })
        supervisor.start()
        stack.callback(supervisor.stop)
        if mode == 'occupied':
            deadline = time.monotonic() + 4
            while supervisor.snapshot()['ssh_diagnostic']['code'] != 'SSH_REMOTE_PORT_BUSY':
                assert supervisor.snapshot()['ssh_state'] != 'CONNECTED' and time.monotonic() < deadline
                time.sleep(0.02)
            assert not attempts
            return
        if mode in ('wrong_runner', 'host_down') or restricted:
            deadline = time.monotonic() + 6
            while supervisor.snapshot()['ssh_diagnostic']['code'] != 'SSH_BIND_UNVERIFIED':
                assert time.monotonic() < deadline and supervisor.snapshot()['ssh_state'] != 'CONNECTED'
                time.sleep(0.03)
            # A healthy -R remains available beyond the old bind timeout.
            time.sleep(supervisor.bind_timeout + 0.1)
            assert supervisor.snapshot()['ssh_state'] != 'CONNECTED' and len(attempts) == 1
            if restricted:
                # Use the actual Linux identity check and peer/hello over the configured -R.
                from backend.gui_test.core.connector_diagnostics import diagnose_connector_endpoint
                result = diagnose_connector_endpoint(
                    remote, expected_runner_id=runner_id, linux_host='localhost',
                )
                assert result['connected'] and result['peer_notified']
            elif mode == 'host_down':
                start_host()
            else:
                endpoint_runner_id = runner_id
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline and supervisor.snapshot()['ssh_state'] != 'CONNECTED':
            assert server.poll() is None
            time.sleep(0.05)
        assert supervisor.snapshot()['ssh_state'] == 'CONNECTED', supervisor.snapshot()
        assert '/v1/identity' in requests
        time.sleep(supervisor.bind_timeout + 0.2)
        assert supervisor.snapshot()['ssh_state'] == 'CONNECTED'
        assert len(attempts) == 1 and attempts[0].poll() is None


@pytest.mark.parametrize(('payload', 'expected'), [
    (b'{"schema_version":"direct-connector-v1","service":"unrelated","runner_id":"local"}\n200', False),
    (b'{"schema_version":"direct-connector-v1","service":"bsp-board-connector","runner_id":"other"}\n200', False),
    (b'{}\n302', False),
    (b'bad JSON\n200', False),
    (b'forced command only', None),
    (b'x' * 70000, None),
])
def test_probe_rejects_unverified_output(tmp_path, payload, expected):
    import sys
    from unittest.mock import patch
    from backend.gui_test.connector.ssh_tunnel import probe_remote_identity

    fake = tmp_path / 'response'
    fake.write_bytes(payload)
    ssh = subprocess.Popen
    argv_seen = []

    def run_fixture(argv, **kwargs):
        argv_seen.extend(argv)
        return ssh([sys.executable, '-c',
                    'import sys; sys.stdout.buffer.write(open(sys.argv[1], "rb").read())', str(fake)], **kwargs)

    with patch('backend.gui_test.connector.ssh_tunnel.subprocess.Popen', run_fixture):
        result, _ = probe_remote_identity('ssh', {'account': 'bsp', 'server': 'linux', 'ssh_key': 'test key'},
                                          2222, 18771, 'local', 2, lambda: False)
    assert result is expected
    assert 'ClearAllForwardings=yes' in argv_seen and '-R' not in argv_seen and '-L' not in argv_seen
    assert '2222' in argv_seen and 'test key' in argv_seen
    assert '127.0.0.1:18771/v1/identity' in argv_seen[-1]
