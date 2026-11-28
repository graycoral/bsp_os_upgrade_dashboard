"""Exercise the Manager tunnel against a private loopback OpenSSH server."""
from contextlib import ExitStack
import getpass
from http.client import HTTPConnection, HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
from pathlib import Path
import os
import shlex
import shutil
import socket
import signal
import sys
import subprocess
import tempfile
import threading
import time

import pytest

from backend.gui_test.connector.ssh_tunnel import SshTunnelSupervisor
from backend.gui_test.execution.launch import LaunchLock, process_identity, write_host_active


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@pytest.mark.parametrize('mode', ['active', 'restricted', 'force_command', 'wrong_runner', 'occupied', 'host_down',
                                  'auth_only', 'delayed_probe', 'orphan_stop', 'manual_tunnel', 'linux_settings', 'offline_store'])
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
            if self.path == '/api/v1/gui-test/live/integration/settings' and mode == 'linux_settings':
                self.wfile.write(json.dumps({'revision':'linux-r1', 'integration':{'tc_root':'/company/board/tcs'},
                                             'timeouts':{'default_seconds':120}}).encode())
                return
            if self.path == '/v1/inventory':
                self.wfile.write(json.dumps({'runner_id': runner_id, 'boards': [{'board_id': 'B1'}]}).encode())
                return
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
    if mode == 'offline_store':
        from backend.gui_test.core.shared_settings_store import SharedSettingsStore
        remote_home = tmp_path / 'ssh-account'
        store = SharedSettingsStore(remote_home / '.local/share/bsp-agent-monitor/runtime')
        store.save({'expected_revision':store.read()['revision'], 'integration':{
            'tc_root':'/srv/firmware/tcs', 'source_roots':['/srv/firmware']}, 'timeouts':{}})
        shell = tmp_path / 'account-shell'
        shell.write_text(f'#!/bin/sh\nexport HOME={shlex.quote(str(remote_home))}\nexec /bin/sh -c "$SSH_ORIGINAL_COMMAND"\n')
        shell.chmod(0o700)
        forced = f'ForceCommand {shlex.quote(str(shell))}\n'
    transport_started = tmp_path / 'transport-started'
    if mode == 'delayed_probe':
        # Delay the remote command after authentication, before it runs curl.
        script = tmp_path / 'delayed-probe'
        script.write_text(f'#!/bin/sh\nif test -f {shlex.quote(str(transport_started))}; then sleep 16; fi\n'
                          'exec /bin/sh -c "$SSH_ORIGINAL_COMMAND"\n')
        script.chmod(0o700)
        forced = f'ForceCommand {shlex.quote(str(script))}\n'
    known = tmp_path / 'known_hosts'
    known.write_text(f'[127.0.0.1]:{ssh_port} ' + (tmp_path / 'host.pub').read_text())
    attempts = []
    # The probe and the transport must both use the isolated known_hosts file.
    ssh = tmp_path / 'ssh'
    auth_log = ''
    if mode == 'auth_only':
        auth_log = ('for arg in "$@"; do\n  if test "$arg" = "-R"; then\n'
                    + "    printf '%s\\n' " + ' '.join(["'Authenticated to test server'"] * 17)
                    + " >&2\n    break\n  fi\ndone\n")
    ssh.write_text("#!/bin/sh\n" + auth_log + "exec " + shlex.join([
        shutil.which('ssh'), '-F', '/dev/null', '-o', 'LogLevel=DEBUG1' if mode == 'host_down' else 'LogLevel=ERROR',
        '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={known}',
    ]) + ' "$@"\n')
    ssh.chmod(0o700)

    def spawn(argv, **kwargs):
        if mode == 'delayed_probe':
            transport_started.touch()
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
        # sshd StrictModes checks ancestors up to the account home. CI tmp directories
        # can have a world-writable parent even when pytest creates them with mode 0700.
        key_dir = stack.enter_context(tempfile.TemporaryDirectory(prefix='.connector-test-', dir=Path.home()))
        authorized_keys = Path(key_dir) / 'authorized_keys'
        authorized_keys.write_bytes((tmp_path / 'client.pub').read_bytes())
        config.write_text(
            f'ListenAddress 127.0.0.1\nPort {ssh_port}\nHostKey "{tmp_path}/host"\n'
            f'PidFile "{tmp_path}/pid"\nAuthorizedKeysFile "{authorized_keys}"\n'
            f'{forced}MaxSessions {sessions}\nAllowTcpForwarding remote\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nAllowUsers {getpass.getuser()}\n'
        )
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
            popen=spawn, backoff_schedule=(0.1,),
            **({} if mode in ('auth_only', 'delayed_probe') else {'bind_timeout': 2}),
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
        if mode == 'offline_store':
            from backend.gui_test.connector.ssh_tunnel import probe_remote_settings
            value = probe_remote_settings(str(ssh), supervisor.setup_cfg, ssh_port, free_port(), lambda: False)
            assert value['read_only'] and value['integration']['tc_root'] == '/srv/firmware/tcs'
            return
        if mode == 'linux_settings':
            from backend.gui_test.connector.ssh_tunnel import probe_remote_settings
            value = probe_remote_settings(str(ssh), supervisor.setup_cfg, ssh_port, local_port, lambda: False)
            assert value and value['integration']['tc_root'] == '/company/board/tcs'
            assert value['read_only'] and not attempts
            return
        if mode == 'orphan_stop':
            exercise_orphan_stop(tmp_path, ssh, supervisor.setup_cfg, local_port, remote, runner_id, monkeypatch)
            return
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
        if mode == 'manual_tunnel':
            from backend.gui_test.connector.ssh_tunnel import build_ssh_r_argv
            manual = stack.enter_context(subprocess.Popen(build_ssh_r_argv(
                ssh, supervisor.setup_cfg, actual_local_runner_port=local_port,
                remote_runner_port=remote, ssh_port=ssh_port)))
            stack.callback(manual.terminate)
            deadline = time.monotonic() + 4
            while True:
                try:
                    with socket.create_connection(('127.0.0.1', remote), timeout=.2):
                        break
                except OSError:
                    assert manual.poll() is None and time.monotonic() < deadline
                    time.sleep(.03)
        supervisor.start()
        stack.callback(supervisor.stop)
        if mode == 'manual_tunnel':
            deadline = time.monotonic() + 6
            while (snap := supervisor.snapshot())['ssh_diagnostic']['code'] != 'SSH_REMOTE_PORT_BUSY':
                assert time.monotonic() < deadline
                time.sleep(.03)
            assert '수동 터널' in snap['ssh_diagnostic']['detail']
            assert not attempts and manual.poll() is None and '/v1/identity' in requests
            manual.terminate()
            manual.wait(timeout=3)

        if mode in ('auth_only', 'delayed_probe'):
            # Independently read the server-side port, as the company operator did.
            deadline = time.monotonic() + 5
            while True:
                client = HTTPConnection('127.0.0.1', remote, timeout=1)
                try:
                    client.request('GET', '/v1/identity')
                    response = client.getresponse()
                    assert response.status == 200 and json.loads(response.read())['runner_id'] == runner_id
                    client.request('GET', '/v1/inventory')
                    response = client.getresponse()
                    assert response.status == 200 and len(json.loads(response.read())['boards']) == 1
                    break
                except (OSError, HTTPException):
                    assert time.monotonic() < deadline
                    time.sleep(0.03)
                finally:
                    client.close()
            # Cross the old production deadline. Both versions run this identical test.
            time.sleep(16.1)
            deadline = time.monotonic() + 4
            while supervisor.snapshot()['ssh_state'] != 'CONNECTED' and time.monotonic() < deadline:
                time.sleep(0.05)
            snap = supervisor.snapshot()
            pids = [proc.pid for proc in attempts]
            assert len(pids) == 1, f'healthy reverse tunnel restarted: {pids=}, state={snap["ssh_state"]}'
            assert snap['ssh_state'] == 'CONNECTED', snap['ssh_diagnostic']
            assert attempts[0].poll() is None
            if mode == 'auth_only':
                lines = snap['ssh_diagnostic']['recent_redacted_lines']
                assert lines.count('Authenticated to test server') == 17
                assert not any('forward success' in line.lower() for line in lines)
            else:
                assert supervisor.bind_timeout == 60
            return
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


@pytest.mark.skipif(os.name != 'posix', reason='exercise the remote POSIX shell command')
@pytest.mark.parametrize(('ss_result', 'expected'), [
    ('exit 0', 'FREE'), ('echo \'LISTEN 0 128 127.0.0.1:18771 0.0.0.0:* users:(("sshd",pid=55,fd=7))\'', 'BUSY'),
    ('exit 1', 'UNKNOWN'), ('echo unexpected', 'UNKNOWN'), (None, 'UNKNOWN'),
])
def test_remote_listener_inspection(tmp_path, monkeypatch, ss_result, expected):
    from backend.gui_test.connector.ssh_tunnel import probe_remote_listener
    sleeper = tmp_path / 'sleep'
    sleeper.write_text('#!/bin/sh\nexit 0\n')
    sleeper.chmod(0o700)
    ss = tmp_path / 'ss'
    ss.write_text('#!/bin/sh\ntest "$1" = "-H" && test "$2" = "-ltnp" && test "$3" = "sport = :18771" || exit 2\n'
                  + (ss_result or 'exit 0') + '\n')
    ss.chmod(0o700)
    popen = subprocess.Popen

    def run(argv, **kwargs):
        assert 'ClearAllForwardings=yes' in argv and '-R' not in argv and '-L' not in argv
        assert 'StrictHostKeyChecking=yes' in argv and '2222' in argv and 'lab@linux' in argv
        kwargs['env']['PATH'] = str(tmp_path) + os.pathsep + kwargs['env'].get('PATH', '')
        return popen(['/bin/sh', '-c', argv[-1] if ss_result is not None else 'true'], **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', run)
    report = probe_remote_listener({'server': 'linux', 'account': 'lab', 'ssh_key': 'private-key-path',
                                    'ssh_port': 2222, 'remote_runner_port': 18771})
    assert report['state'] == expected and 'ssh_key' not in report
    if expected == 'BUSY':
        assert report['listeners'] == [{'address': '127.0.0.1:18771', 'process': 'users:(("sshd",pid=55,fd=7))'}]


def mac_test_identity(pid):
    # The product's process handles target Windows and Linux. Inspect only this
    # fixture's disposable SSH on macOS, where /proc and pidfd are unavailable.
    row = subprocess.run(['ps', '-p', str(pid), '-o', 'stat=', '-o', 'lstart='],
                         capture_output=True, text=True).stdout.strip().split(maxsplit=1)
    if len(row) == 2 and 'Z' not in row[0]:
        return {'pid': pid, 'creation_time': row[1]}
    return None


def run_tunnel_owner(runtime, ssh, cfg, local, remote, shutdown):
    from backend.gui_test.connector import ssh_tunnel
    from backend.gui_test.execution import launch
    if sys.platform == 'darwin':
        ssh_tunnel.process_identity = launch.process_identity = mac_test_identity
    supervisor = SshTunnelSupervisor(runtime, cfg, actual_local_runner_port=local, remote_runner_port=remote,
                                     preflight_fn=lambda *a, **kw: {'ok': True, 'ssh_path': str(ssh)})
    supervisor.start()
    try:
        deadline = time.monotonic() + 30
        while not shutdown.exists() and time.monotonic() < deadline:
            time.sleep(.05)
    finally:
        supervisor.stop()


def exercise_orphan_stop(home, ssh, cfg, local, remote, runner_id, monkeypatch):
    from backend.gui_test.connector import emergency, ssh_ownership
    from backend.gui_test.connector.ssh_tunnel import build_ssh_r_argv
    from backend.gui_test.execution import force_stop, launch

    ctx = multiprocessing.get_context('spawn')
    runtime = home / 'runtime'
    monkeypatch.setenv('PATH', str(home) + os.pathsep + os.environ['PATH'])
    def wait_identity(port):
        deadline = time.monotonic() + 6
        while True:
            client = HTTPConnection('127.0.0.1', port, timeout=1)
            try:
                client.request('GET', '/v1/identity')
                assert json.loads(client.getresponse().read())['runner_id'] == runner_id
                return
            except (OSError, HTTPException):
                assert time.monotonic() < deadline
                time.sleep(.03)
            finally:
                client.close()

    def start_owner(stack):
        done = home / 'stop-test-owner'
        done.unlink(missing_ok=True)
        owner = ctx.Process(target=run_tunnel_owner, args=(runtime, ssh, cfg, local, remote, done))
        owner.start()
        def cleanup():
            done.touch()
            owner.join(6)
            if owner.is_alive():
                owner.kill()
                owner.join(5)
        stack.callback(cleanup)
        return owner

    with ExitStack() as stack:
        manual_port = free_port()
        manual = stack.enter_context(subprocess.Popen(build_ssh_r_argv(
            ssh, cfg, actual_local_runner_port=local, remote_runner_port=manual_port, ssh_port=cfg['ssh_port'])))
        stack.callback(manual.terminate)
        wait_identity(manual_port)
        owner = start_owner(stack)
        wait_identity(remote)
        def recorded_owner():
            deadline = time.monotonic() + 4
            while not (owners := ssh_ownership.read(runtime)['owners']):
                assert time.monotonic() < deadline
                time.sleep(.03)
            return owners[0]['process']
        owned = recorded_owner()
        owner.kill()
        owner.join(5)
        assert owner.exitcode is not None
        wait_identity(remote)
        inspect = launch.process_identity
        if sys.platform == 'darwin':
            inspect = mac_test_identity
            monkeypatch.setattr(launch, 'process_identity', inspect)
            monkeypatch.setattr(force_stop, 'process_identity', inspect)
            class FixtureHandle:
                def __init__(self, identity):
                    assert identity == owned and self.alive()
                    self.identity = identity
                def alive(self): return inspect(owned['pid']) == owned
                def pause(self): pass
                def close(self): pass
                def kill(self):
                    if self.alive():
                        os.kill(owned['pid'], signal.SIGTERM)
            monkeypatch.setattr(force_stop, 'PinnedProcess', FixtureHandle)
        def cleanup_orphan():
            if inspect(owned['pid']) == owned:
                os.kill(owned['pid'], signal.SIGTERM)
        stack.callback(cleanup_orphan)
        result = emergency.force_stop(home)
        assert result['state'] == 'FORCE_STOPPED' and result['targets'] == [owned]
        assert result['remote_ports'][0]['state'] == ('FREE' if shutil.which('ss') else 'UNKNOWN')
        with socket.socket() as sock:
            assert sock.connect_ex(('127.0.0.1', remote)) != 0
        assert manual.poll() is None
        wait_identity(manual_port)
        force_stop.require_force_complete(runtime / 'force-stop.json')
        start_owner(stack)
        wait_identity(remote)
        assert recorded_owner() != owned


@pytest.mark.skipif(os.name != 'posix', reason='execute the remote curl command in a local POSIX shell')
def test_read_linux_settings_without_dashboard_forward_or_plugin(tmp_path, monkeypatch):
    from backend.gui_test.connector.ssh_tunnel import probe_remote_settings
    requests = []
    class Settings(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, self.headers.get('X-Bsp-Service')))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(self.server.body)
        def log_message(self, *args): pass
    with ThreadingHTTPServer(('127.0.0.1', 0), Settings) as http:
        http.body = json.dumps({'revision':'r2', 'integration':{'tc_root':'/linux/tcs', 'metadata':{'local':'only'}},
                                'timeouts':{'default_seconds':330}}).encode()
        threading.Thread(target=http.serve_forever, daemon=True).start()
        popen = subprocess.Popen
        def remote(argv, **kwargs):
            assert 'ClearAllForwardings=yes' in argv and '-R' not in argv
            assert 'StrictHostKeyChecking=yes' in argv and argv[-2] == 'qa@linux'
            return popen(['/bin/sh', '-c', argv[-1]], **kwargs)
        monkeypatch.setattr(subprocess, 'Popen', remote)
        try:
            doc = probe_remote_settings('ssh', {'server':'linux', 'account':'qa'}, 2222, http.server_port, lambda:False)
            assert doc['integration']['tc_root'] == '/linux/tcs' and doc['read_only']
            assert f'127.0.0.1:{http.server_port}/api/v1/gui-test/live/integration/settings' in doc['settings_source']
            assert 'metadata' not in doc['integration']
            assert requests == [('/api/v1/gui-test/live/integration/settings', 'plugin')]
            for http.body, message in [(b'', '출력이 비어'), (b'{}', '응답을 확인할 수 없')]:
                error = probe_remote_settings('ssh', {'server':'linux', 'account':'qa'}, 2222, http.server_port, lambda:False)
                assert message in error['settings_probe_error'] and 'integration' not in error
        finally:
            http.shutdown()


@pytest.mark.skipif(os.name != 'posix', reason='Simulates the command executed on the Linux SSH server')
def test_read_bound_linux_tc_settings_when_monitor_and_plugin_are_offline(tmp_path, monkeypatch):
    from backend.gui_test.connector.ssh_tunnel import probe_remote_settings
    from backend.gui_test.core.shared_settings_store import SharedSettingsStore
    home = tmp_path / 'linux-user'
    managed = home / '.local/share/bsp-agent-monitor'
    managed.mkdir(parents=True)
    runtime = tmp_path / 'company runtime'
    (managed / 'runtime-location.json').write_text(json.dumps({'path':str(runtime)}))
    store = SharedSettingsStore(runtime)
    base = store.read()
    store.save({'expected_revision':base['revision'], 'integration':{'source_roots':['/company/tcs'],
                           'tc_root':'/company/tcs/selected', 'metadata':{'linux_private':'keep here'}},
                           'timeouts':{'default_seconds':91}})
    before = store.path.read_bytes()
    real_popen = subprocess.Popen
    def remote(argv, **kwargs):
        assert 'ClearAllForwardings=yes' in argv and 'StrictHostKeyChecking=yes' in argv
        kwargs['env'] = dict(kwargs['env'], HOME=str(home))
        return real_popen(['/bin/sh', '-c', argv[-1]], **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', remote)
    monitor_port = free_port()
    cfg = {'server':'linux', 'account':'qa'}
    def load(*, port=monitor_port, runner=None):
        args = ('ssh', cfg, 22, port, lambda: False)
        return probe_remote_settings(*args) if runner is None else probe_remote_settings(*args, runner_id=runner)
    doc = load()
    assert doc and doc['integration']['tc_root'] == '/company/tcs/selected'
    assert doc['read_only'] and doc['timeouts']['default_seconds'] == 91
    assert 'linux_private' not in json.dumps(doc)
    assert str(store.path) in doc['settings_source'] and 'SSH' in doc['settings_source']
    assert store.path.read_bytes() == before
    store.pin_runner_if_unset('a' * 32)
    assert '커넥터' in load(runner='b' * 32)['settings_probe_error']
    assert load(runner='a' * 32)['integration']['tc_root'] == '/company/tcs/selected'

    store.save({'expected_revision':store.read()['revision'], 'integration':{'tc_root':''}, 'timeouts':{'default_seconds':91}})
    assert load(runner='a' * 32)['integration']['tc_root'] == ''

    class Forbidden(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_error(403)
        def log_message(self, *args):
            pass
    with ThreadingHTTPServer(('127.0.0.1', 0), Forbidden) as http:
        threading.Thread(target=http.serve_forever, daemon=True).start()
        try:
            assert 'HTTP 오류' in load(port=http.server_port, runner='a' * 32)['settings_probe_error']
        finally:
            http.shutdown()
    cfg['connector_bootstrap'] = {'format':'gui-test-connector-bootstrap-v1',
        'identity':{'runtime_id':'fixed-service','package_version':'1'},
        'endpoint':{'server':'linux','account':'qa','ssh_port':22,'remote_dashboard_port':monitor_port}}
    assert 'v1' in load(runner='a' * 32)['settings_probe_error']
    del cfg['connector_bootstrap']
    (managed / 'runtime-location.json').write_text(json.dumps({'path':str(tmp_path / 'missing')}))
    assert str(tmp_path / 'missing' / 'shared-settings.db') in load()['settings_probe_error']
    assert not (tmp_path / 'missing').exists()
