"""Active endpoint discovery uses live ownership, never rewrites desired ports."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.error import HTTPError, URLError

import pytest

from scripts import setup_runtime as setup


def receipt(port=18771):
    from backend.gui_test.execution.launch import process_identity
    identity = process_identity(os.getpid())
    return {'version': 1, 'launch_id': 'a' * 32, 'owner': identity, 'runner': identity,
            'runner_id': 'c' * 32, 'runner_port': port, 'dashboard_port': 18766,
            'remote_runner_port': 28771, 'remote_dashboard_port': 28766, 'ssh_port': 2200,
            'phase': 'ssh_running', 'runner_url': f'http://127.0.0.1:{port}',
            'dashboard_url': 'http://127.0.0.1:18766'}


@contextmanager
def live_receipt(runtime, value):
    from backend.gui_test.execution.launch import LaunchLock, write_receipt
    runtime.mkdir(parents=True, exist_ok=True)
    startup = {key: value[key] for key in
               ('version', 'launch_id', 'owner', 'runner', 'runner_id', 'runner_port')}
    write_receipt(runtime / ('launch-' + value['launch_id'] + '.json'), startup)
    write_receipt(runtime / 'active-endpoints.json', value)
    with LaunchLock(runtime / 'setup-launch.lock'), LaunchLock(runtime / 'runner.lock'):
        yield


def test_live_receipt_requires_both_os_locks_and_matching_startup(tmp_path):
    from backend.gui_test.execution.launch import LaunchLock, read_active
    value = receipt()
    with live_receipt(tmp_path, value):
        assert read_active(tmp_path) == value
        startup = tmp_path / ('launch-' + value['launch_id'] + '.json')
        changed = json.loads(startup.read_text())
        changed['runner_id'] = 'd' * 32
        startup.write_text(json.dumps(changed))
        with pytest.raises(ValueError):
            read_active(tmp_path)
    with pytest.warns(RuntimeWarning):
        assert read_active(tmp_path) is None
    # A launcher without its Host cannot advertise a running endpoint.
    with LaunchLock(tmp_path / 'setup-launch.lock'):
        with pytest.raises(ValueError):
            read_active(tmp_path)


def test_pid_reuse_is_stale_even_when_numeric_pid_matches(tmp_path):
    from backend.gui_test.execution.launch import read_active
    value = receipt()
    with live_receipt(tmp_path, value), pytest.warns(RuntimeWarning):
        assert read_active(tmp_path, inspect_process=lambda pid: {
            'pid': pid, 'creation_time': 'a-different-process-generation'}) is None


def test_unlocked_corrupt_receipt_is_stale_but_locked_corruption_is_error(tmp_path):
    from backend.gui_test.execution.launch import LaunchLock, read_active
    (tmp_path / 'active-endpoints.json').write_text('{invalid', encoding='utf-8')
    with pytest.warns(RuntimeWarning):
        assert read_active(tmp_path) is None
    with LaunchLock(tmp_path / 'setup-launch.lock'), pytest.raises(ValueError):
        read_active(tmp_path)


@contextmanager
def identity_server():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path, self.headers.get('Authorization')))
            value = {'runner_id': 'c' * 32}
            payload = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_doctor_contacts_actual_loopback_endpoint_without_saving_profile(tmp_path, monkeypatch):
    home = tmp_path / 'private home'
    wizard = setup.Wizard(root=tmp_path, windows=True, home=home)
    setup.save_json(wizard.config, {'python': 'external-python', '_setup': {}})
    monkeypatch.setattr(wizard.tokens, 'load', lambda **kw: 'fixture-private-token')
    before = wizard.config.read_bytes()
    with identity_server() as (port, calls), live_receipt(wizard.runtime, receipt(port)):
        assert wizard.doctor('identity') == 0
        assert calls == [('/v1/identity', 'Bearer fixture-private-token')]
        assert wizard.runner_port == 8771 and wizard.remote_runner_port == 8771
        assert not wizard.ports_profile.path.exists()
        assert wizard.config.read_bytes() == before


def test_explicit_cli_runner_port_takes_priority_over_valid_live_receipt(tmp_path, monkeypatch):
    with identity_server() as (port, calls):
        wizard = setup.Wizard(root=tmp_path, windows=True, home=tmp_path / 'home', runner_port=port)
        setup.save_json(wizard.config, {'_setup': {}})
        monkeypatch.setattr(wizard.tokens, 'load', lambda **kw: 'fixture-private-token')
        with live_receipt(wizard.runtime, receipt(port + 1 if port < 65535 else port - 1)):
            assert wizard.doctor('identity') == 0
        assert calls


def test_linux_does_not_discover_windows_active_endpoints(tmp_path, monkeypatch):
    wizard = setup.Wizard(root=tmp_path, windows=False, home=tmp_path / 'home')
    setup.save_json(wizard.config, {'runner': 'windows-http', 'url': wizard.runner_url})
    monkeypatch.setattr(wizard.tokens, 'load', lambda **kw: 'fixture-private-token')
    seen = []
    monkeypatch.setattr(setup, 'runner_get', lambda path, token, *a, **kw:
                        seen.append(a[0] if a else 8771) or {'runner_id': 'c' * 32})
    with live_receipt(wizard.runtime, receipt(18771)):
        assert wizard.doctor('identity') == 0
    assert seen == [8771]


RUNNER_FIXTURE = r'''
import argparse,json,os,sys
from pathlib import Path
from http.server import HTTPServer,BaseHTTPRequestHandler
from backend.gui_test.execution.launch import LaunchLock,bind_loopback,process_identity,write_receipt
p=argparse.ArgumentParser()
for option in ('config','runtime','port','launch-id','startup-receipt','owner-pid','owner-created'):
    p.add_argument('--'+option,required=True)
p.add_argument('--allow-port-fallback',action='store_true')
a=p.parse_args()
runtime=Path(a.runtime)
wrong_identity=json.loads(Path(a.config).read_text()).get('_fixture_wrong_identity',False)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.headers.get('Authorization') != 'Bearer '+os.environ['GUI_TEST_RUNNER_TOKEN']:
            self.send_error(401); return
        body=json.dumps({'runner_id':('d' if wrong_identity else 'c')*32}).encode()
        self.send_response(200); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self,*args): pass
with LaunchLock(runtime/'runner.lock'),bind_loopback(int(a.port),allow_fallback=a.allow_port_fallback) as listener:
    receipt={'version':1,'launch_id':a.launch_id,'owner':{'pid':int(a.owner_pid),'creation_time':a.owner_created},
             'runner':process_identity(os.getpid()),'runner_id':'c'*32,'runner_port':listener.getsockname()[1]}
    server=HTTPServer(listener.getsockname(),Handler,bind_and_activate=False)
    server.socket.close(); server.socket=listener; server.server_address=listener.getsockname(); server.timeout=.05
    write_receipt(Path(a.startup_receipt),receipt)
    print('fixture-ready',receipt,flush=True)
    while not (runtime/'fixture-stop').exists(): server.handle_request()
'''


@pytest.mark.parametrize('explicit_port,identity_mismatch', [(False, False), (True, False), (False, True)])
def test_launch_real_children_fallback_ssh_failure_and_owned_cleanup(tmp_path, monkeypatch, explicit_port, identity_mismatch):
    """Real kernel sockets/locks/HTTP/PIDs; only external executables are local doubles."""
    from backend.gui_test.execution.launch import bind_loopback
    import socket
    root = Path(__file__).resolve().parents[1]
    runner_script = tmp_path / 'fake runner.py'
    runner_script.write_text(RUNNER_FIXTURE, encoding='utf-8')
    ssh_script = tmp_path / 'fake ssh.py'
    ssh_result = tmp_path / 'ssh-result.json'
    ssh_script.write_text(
        'import json,os,sys\nfrom pathlib import Path\n'
        'Path(sys.argv[1]).write_text(json.dumps({"args":sys.argv[2:],'
        '"token_present":"GUI_TEST_RUNNER_TOKEN" in os.environ}))\nsys.exit(7)\n', encoding='utf-8')
    real_popen = subprocess.Popen
    children = []
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        preferred = occupied.getsockname()[1]
        wizard = setup.Wizard(root=root, windows=True, home=tmp_path / 'private home',
                              **({'runner_port': preferred} if explicit_port else {}))
        if not explicit_port:
            wizard.ports_profile.save({'runner_port': preferred, 'dashboard_port': 8766,
                                       'remote_runner_port': 28771, 'remote_dashboard_port': 28766, 'ssh_port': 2200})
            wizard = setup.Wizard(root=root, windows=True, home=wizard.home)
        wizard.python = Path(sys.executable)
        wizard.state = {'server': 'fixture.invalid', 'account': 'fixture-user'}
        setup.save_json(wizard.config, {'_setup': wizard.state, '_fixture_wrong_identity': identity_mismatch})
        before = wizard.config.read_bytes()
        profile_before = wizard.ports_profile.path.read_bytes() if wizard.ports_profile.path.exists() else None
        monkeypatch.setattr(wizard, 'environment', lambda: {**os.environ, setup.TOKEN_ENV: 'fixture-private-token',
                                                           'PYTHONPATH': str(root)})
        monkeypatch.setattr(setup.shutil, 'which', lambda *a, **kw: 'fixture-ssh')
        monkeypatch.setattr(setup.subprocess, 'CREATE_NEW_PROCESS_GROUP', 0, raising=False)
        def spawn(argv, **kwargs):
            if argv[0] == 'fixture-ssh':
                command = [sys.executable, '-B', str(ssh_script), str(ssh_result), *argv[1:]]
            else:
                command = [argv[0], '-B', str(runner_script), *argv[argv.index('--config'):]]
            kwargs.pop('creationflags', None)
            child = real_popen(command, **kwargs)
            children.append(child)
            return child
        monkeypatch.setattr(setup.subprocess, 'Popen', spawn)
        def graceful_owned_stop(child, windows=False):
            (wizard.runtime / 'fixture-stop').touch()
            child.wait(timeout=8)
        monkeypatch.setattr(wizard, 'stop_owned', graceful_owned_stop)
        # An unrelated live process must survive the entire failing launch.
        unrelated = real_popen([sys.executable, '-B', '-c', 'import time; time.sleep(30)'])
        try:
            with pytest.raises(setup.RunFailure) as failure:
                wizard.start()
            if explicit_port or identity_mismatch:
                assert failure.value.stage == 'runner'
                if identity_mismatch:
                    assert failure.value.category == 'CONFIG'
                    assert failure.value.__cause__ is None, 'must reach authenticated identity comparison'
                assert not ssh_result.exists()
            else:
                assert failure.value.stage == 'ssh' and failure.value.exit_code == 7, (
                    failure.value.category, str(failure.value), repr(failure.value.__cause__), children[0].pid)
                result = json.loads(ssh_result.read_text())
                assert result['token_present'] is False
                args = result['args']
                reverse = args[args.index('-R') + 1].split(':')
                assert reverse[1] == '28771' and int(reverse[-1]) != preferred
                assert args[args.index('-p') + 1] == '2200'
                assert ':28766' in args[args.index('-L') + 1]
            assert len(children) == (1 if explicit_port or identity_mismatch else 2)
            assert all(child.poll() is not None for child in children)
            assert unrelated.poll() is None
            assert wizard.config.read_bytes() == before
            assert (wizard.ports_profile.path.read_bytes() if profile_before else None) == profile_before
            assert not (wizard.runtime / 'active-endpoints.json').exists()
            assert not list(wizard.runtime.glob('launch-*.json'))
        finally:
            (wizard.runtime / 'fixture-stop').touch()
            for child in children:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
            unrelated.terminate()
            unrelated.wait(timeout=5)


@pytest.mark.parametrize('lock_name', ['setup-launch.lock', 'runner.lock'])
def test_existing_launcher_or_direct_host_prevents_second_child(tmp_path, monkeypatch, lock_name):
    from backend.gui_test.execution.launch import LaunchLock
    wizard = setup.Wizard(root=tmp_path, windows=True, home=tmp_path / 'private')
    wizard.python = Path(sys.executable)
    setup.save_json(wizard.config, {'_setup': {}})
    monkeypatch.setattr(wizard, 'environment', lambda: {setup.TOKEN_ENV: 'fixture-private-token'})
    monkeypatch.setattr(setup.subprocess, 'Popen', lambda *a, **kw: pytest.fail('duplicate launch spawned child'))
    with LaunchLock(wizard.runtime / lock_name), pytest.raises(RuntimeError):
        wizard.start()


@pytest.mark.parametrize('only', ['boards', 'catalog'])
@pytest.mark.parametrize('error,category', [
    (HTTPError('http://127.0.0.1/', 401, 'fixture', {}, None), 'AUTH'),
    (HTTPError('http://127.0.0.1/', 403, 'fixture', {}, None), 'AUTH'),
    (TimeoutError('fixture'), 'TIMEOUT'),
    (URLError(TimeoutError('fixture')), 'TIMEOUT'),
    (URLError(ConnectionRefusedError('fixture')), 'CONNECT')])
def test_active_only_diagnosis_identity_preflight_preserves_error_category(tmp_path, monkeypatch, capsys, only, error, category):
    wizard = setup.Wizard(root=tmp_path, windows=True, home=tmp_path / 'home')
    setup.save_json(wizard.config, {'_setup': {}})
    monkeypatch.setattr(wizard.tokens, 'load', lambda **kw: 'fixture-private-token')
    calls = []
    def fail_identity(route, token, *args, **kwargs):
        calls.append(route)
        raise error
    monkeypatch.setattr(setup, 'runner_get', fail_identity)
    with live_receipt(wizard.runtime, receipt()):
        assert wizard.doctor(only) == 1
    assert calls == ['/identity']
    output = capsys.readouterr().out
    assert 'stage=identity' in output and f'result={category}' in output
    assert f'stage={only}' not in output
