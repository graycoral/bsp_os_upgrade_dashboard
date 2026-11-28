"""Company mock acceptance for the exported plugin's status, watch and activation hook."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import select
import signal
import subprocess
import sys
import threading

import pytest

from backend.gui_test.standalone.connector_observation import observe_run

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = 'a' * 32
RUNNER_ID = 'b' * 32


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    destination = tmp_path_factory.mktemp('vendor') / 'plugin package'
    result = subprocess.run([sys.executable, '-B', str(ROOT / 'apps/agent-monitor/plugin.py'),
                             '--project-root', str(ROOT), 'export', '--output', str(destination),
                             '--without-ui'], capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return destination


@pytest.fixture
def endpoint():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, data, code=200):
            body = json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            server.requests.append(('GET', self.path))
            if self.path == '/v1/identity' and server.online:
                self.respond({'runner_id': server.runner, 'capabilities': ['direct-connector-v1']})
            elif self.path == '/v1/diagnostics/connection':
                self.respond({})
            elif self.path == '/v1/inventory':
                self.respond({'runner_id': server.runner})
            elif self.path == '/v1/connector-runs/' + RUN_ID:
                self.respond(server.run)
            elif self.path == '/v1/connector-runs/active':
                self.respond({'run': server.active})
            elif self.path == '/v1/connector-runs?limit=1&project=fixture':
                self.respond({'runs': [server.run]})
            else:
                self.respond({'code': 'NOT_FOUND', 'message': 'Run 조회 실패'}, 404)

        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            server.requests.append((self.command, self.path))
            self.respond({}, 200 if self.path == '/v1/peer/hello' else 405)

        do_PUT = do_POST

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.requests = []
    server.online = True
    server.active = None
    server.runner = RUNNER_ID
    server.run = {'origin': {'project': 'fixture'}, 'runner_id': RUNNER_ID, 'run_id': RUN_ID, 'state': 'RUNNING', 'outcome': None,
                  'version': 1, 'analysis_latched': False}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def command(package, home, endpoint, *args, hook=False):
    prefix = ([str(package / 'agent-monitor/examples/activate-connector-watch.sh')] if hook else
              [sys.executable, '-IB', str(package / 'plugin.py')])
    return [*prefix, '--home', str(home), '--project', 'fixture',
            '--connector-port', str(endpoint.server_port), *args]


def invoke(argv):
    return subprocess.run(argv, capture_output=True, timeout=25, env=process_env())


def process_env():
    return dict(os.environ, BSP_PLUGIN_PYTHON=sys.executable, PYTHONIOENCODING='ascii')


def start(argv):
    return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            bufsize=0, env=process_env())


def line(proc):
    assert select.select([proc.stdout], [], [], 15)[0], 'watch did not flush a JSON line'
    raw = proc.stdout.readline()
    assert raw.endswith(b'\n'), (raw, proc.poll())
    return json.loads(raw.decode('utf-8'))


def cleanup(proc):
    if proc.poll() is None:
        proc.kill()
    proc.communicate(timeout=10)


@pytest.mark.parametrize('phase,outcome,latch,state,code', [
    ('QUEUED', None, False, 'queued', 0), ('FLASHING', None, False, 'flashing', 0),
    ('RUNNING', None, False, 'running', 0), ('PAUSE_REQUESTED', None, False, 'pause_requested', 0),
    ('CANCEL_REQUESTED', None, False, 'cancel_requested', 0), ('FINALIZING', None, False, 'finalizing', 0),
    ('PAUSED', None, True, 'hold', 4), ('PAUSED', None, False, 'paused', 4),
    ('UNKNOWN', None, False, 'unknown', 3), ('COMPLETED', 'PASSED', False, 'passed', 0),
    ('COMPLETED', 'FAILED', False, 'failed', 5), ('COMPLETED', 'ABORTED', False, 'aborted', 5),
    ('COMPLETED', 'CANCELLED', False, 'cancelled', 5),
    ('COMPLETED', 'SUPERSEDED_BY_REPREPARE', False, 'superseded_by_reprepare', 5),
])
def test_run_schema(phase, outcome, latch, state, code):
    class Client:
        def get_run(self, run_id):
            return {'runner_id': RUNNER_ID, 'run_id': run_id, 'state': phase, 'outcome': outcome,
                    'analysis_latched': latch, 'version': 2}
    records = []
    assert observe_run(Client(), RUN_ID, watch=False, emit=records.append) == code
    assert records == [{'schema_version': 1, 'type': 'run', 'runner_id': RUNNER_ID, 'run_id': RUN_ID,
                        'state': state, 'phase': phase, 'outcome': outcome, 'version': 2}]


@pytest.mark.skipif(os.name != 'posix', reason='The company plugin observes subprocess pipes on Linux/macOS')
def test_packaged_status_and_read_only_run_watch(package, endpoint, tmp_path):
    def cli(*args):
        return command(package, tmp_path, endpoint, *args)

    for online, runner, state, code in [(True, RUNNER_ID, 'connected', 0),
                                        (True, 'c' * 32, 'runner_changed', 3),
                                        (False, None, 'disconnected', 3)]:
        endpoint.online = online
        endpoint.runner = runner
        result = invoke(cli('status', '--json'))
        assert result.returncode == code and result.stderr == b''
        record, = map(json.loads, result.stdout.splitlines())
        assert (record['type'], record['schema_version'], record['state'], record['runner_id']) == (
            'connection', 1, state, runner)
    endpoint.online = True
    endpoint.runner = RUNNER_ID
    endpoint.requests.clear()
    proc = start(cli('test', 'watch', RUN_ID, '--json'))
    try:
        assert line(proc)['state'] == 'running'
        assert not select.select([proc.stdout], [], [], .55)[0]
        endpoint.run = dict(endpoint.run, state='PAUSED', version=2, analysis_latched=True)
        assert line(proc)['state'] == 'hold'
        assert proc.wait(timeout=10) == 4
        assert proc.communicate() == (b'', b'')
    finally:
        cleanup(proc)
    for phase, outcome, state, code in [('UNKNOWN', None, 'unknown', 3),
                                        ('COMPLETED', 'FAILED', 'failed', 5),
                                        ('COMPLETED', 'PASSED', 'passed', 0)]:
        endpoint.run = dict(endpoint.run, state=phase, outcome=outcome, version=3)
        result = invoke(cli('test', 'status', RUN_ID, '--json'))
        record, = map(json.loads, result.stdout.splitlines())
        assert result.returncode == code and result.stderr == b''
        assert (record['state'], record['phase'], record['outcome']) == (state, phase, outcome)
    bad = invoke(cli('test', 'status', 'missing', '--json'))
    assert bad.returncode == 1 and bad.stdout == b'' and json.loads(bad.stderr)['code'] == 'NOT_FOUND'
    invalid = invoke(cli('test', 'list', '--json'))
    assert invalid.returncode == 2 and invalid.stdout == b'' and invalid.stderr
    endpoint.run = dict(endpoint.run, state='RUNNING', outcome=None)
    proc = start(cli('test', 'watch', RUN_ID, '--json'))
    try:
        assert line(proc)['state'] == 'running'
        proc.send_signal(signal.SIGINT)
        assert proc.wait(timeout=10) == 130
        assert proc.communicate() == (b'', b'')
    finally:
        cleanup(proc)
    assert all(method == 'GET' and path.startswith('/v1/connector-runs/') for method, path in endpoint.requests)


def test_status_without_id_uses_selection_then_active_then_latest(package, endpoint, tmp_path):
    cli = command(package, tmp_path, endpoint, 'test', 'status', '--json')
    selected = tmp_path / 'plugin-state' / 'selected-run.txt'
    selected.parent.mkdir(parents=True)
    selected.write_text(RUN_ID, encoding='utf-8')
    active = '/v1/connector-runs/active'
    for calls in [('/v1/connector-runs/' + RUN_ID,) * 2, (active,), (active, '/v1/connector-runs?limit=1&project=fixture')]:
        result = invoke(cli)
        assert result.returncode == 0 and json.loads(result.stdout)['run_id'] == RUN_ID
        assert endpoint.requests == [('GET', path) for path in calls]
        endpoint.requests.clear()
        if selected.exists():
            selected.unlink()
            endpoint.active = endpoint.run
        else:
            endpoint.active = None


@pytest.mark.skipif(os.name != 'posix', reason='The connection supervisor runs on Linux/macOS')
def test_packaged_hook_and_manual_share_lock_and_recover(package, endpoint, tmp_path):
    home_a, home_b = tmp_path / 'manual', tmp_path / 'automatic'
    manual = command(package, home_a, endpoint, 'connect', '--watch')
    hook = command(package, home_b, endpoint, hook=True)
    for owner, duplicate in [(manual, hook), (hook, manual)]:
        proc = start(owner)
        try:
            initial = line(proc)
            assert initial.get('event') == 'CONNECTED' or initial.get('state') == 'connected'
            proc.send_signal(signal.SIGSTOP)
            before = len(endpoint.requests)
            other = invoke(duplicate)
            assert other.returncode == 0 and other.stderr == b''
            assert json.loads(other.stdout)['state'] == 'already_watching'
            assert before == len(endpoint.requests)
            proc.send_signal(signal.SIGCONT)
            if owner == hook:
                endpoint.runner = 'c' * 32
                changed = line(proc)
                assert (changed['state'], changed['runner_id']) == ('runner_changed', endpoint.runner)
                endpoint.online = False
                assert line(proc)['state'] == 'disconnected'
                endpoint.runner = RUNNER_ID
                endpoint.online = True
                assert line(proc)['state'] == 'connected'
                proc.send_signal(signal.SIGINT)
                assert proc.wait(timeout=10) == 130
        finally:
            cleanup(proc)
    assert not [req for req in endpoint.requests if req[0] == 'POST' and req[1] != '/v1/peer/hello']
    assert not (home_a / 'service.json').exists() and not (home_b / 'service.json').exists()


def test_rebound_live_runner_is_reported_before_connected(tmp_path):
    from backend.gui_test.standalone.direct_connector_client import DirectConnectorClient

    with_client = DirectConnectorClient(runtime_dir=tmp_path / 'runtime')
    runners = iter([RUNNER_ID, 'c' * 32, 'c' * 32])
    with_client.diagnose = lambda: {'code': 'CONNECTED', 'linux_diagnostics': {'reachable': True}}
    with_client.inventory = lambda: {'runner_id': next(runners)}
    events = []
    try:
        with_client.watch_connection(machine=True, on_change=events.append, interval=0, max_iterations=3)
    finally:
        with_client.close()
    assert [record['state'] for record in events] == ['connected', 'runner_changed', 'connected']
    assert events[1]['code'] == 'RUNNER_CHANGED' and events[1]['runner_id'] == 'c' * 32


@pytest.mark.skipif(os.name != 'posix', reason='The connection supervisor runs on Linux/macOS')
def test_reexec_and_hook_start_together_with_one_polling_owner(package, endpoint, tmp_path):
    # Supply the already installed test interpreter for the prepare-env response.
    # The actual plugin reexec, hook and file lock are exercised as processes.
    release = tmp_path / 'installed'
    release.mkdir()
    (release / '.venv').symlink_to(Path(sys.executable).parent.parent, target_is_directory=True)
    launcher = """
import importlib.util,sys
spec=importlib.util.spec_from_file_location('entry', sys.argv[1])
plugin=importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
plugin._has_direct_deps=lambda:False
def prepared(*args, **kwargs):
    print('mock prepare-env',file=sys.stderr,flush=True)
    return {'path':sys.argv[2]}
plugin.manager_result=prepared
raise SystemExit(plugin.main(sys.argv[3:]))
"""
    manual = command(package, tmp_path / 'manual', endpoint, 'connect', '--watch', '--json')
    reexec = [sys.executable, '-IB', '-c', launcher, str(package / 'plugin.py'), str(release), *manual[3:]]
    hook = command(package, tmp_path / 'hook', endpoint, hook=True)
    first, second = start(reexec), start(hook)
    try:
        results = [line(first), line(second)]
        states = [r['state'] for r in results]
        assert sorted(states) == ['already_watching', 'connected']
        duplicate = (first, second)[states.index('already_watching')]
        owner = (first, second)[states.index('connected')]
        assert duplicate.wait(timeout=10) == 0
        owner.send_signal(signal.SIGINT)
        assert owner.wait(timeout=10) == 130
        assert first.communicate() == (b'', b'mock prepare-env\n')
        assert second.communicate() == (b'', b'')
        assert endpoint.requests.count(('GET', '/v1/identity')) == 1
    finally:
        cleanup(first)
        cleanup(second)


@pytest.mark.parametrize('suffix', [
    ['--hom', 'other', 'help'], ['status', '--home', 'other'],
    ['status', '--hom=other'], ['connect', '--wat'], ['settings', '--ki', 'flash'],
    ['modules', 'list', '--runtime-i', 'x'], ['verify', '.', '--prist'],
    ['monitor', '--port=8766'], ['help', '--project', 'other'],
])
def test_plugin_rejects_short_or_misplaced_options_before_setup(tmp_path, monkeypatch, suffix):
    import importlib.util
    spec = importlib.util.spec_from_file_location('strict_entry', ROOT / 'apps/agent-monitor/plugin.py')
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    monkeypatch.setattr(plugin, '_has_direct_deps', lambda: False)
    monkeypatch.setattr(plugin, 'manager_result', lambda *a, **kw: pytest.fail('unexpected setup or Monitor access'))
    with pytest.raises(SystemExit) as error:
        plugin.main(['--home', str(tmp_path / 'home'), *suffix])
    assert error.value.code == 2
    assert not (tmp_path / 'home').exists()


@pytest.fixture(scope='module')
def watch_venv(tmp_path_factory):
    if sys.prefix != sys.base_prefix:
        return Path(sys.prefix)
    import venv
    root = tmp_path_factory.mktemp('watch-venv')
    venv.EnvBuilder(system_site_packages=True).create(root)
    return root


def test_read_only_watch_observes_connection_and_runner_change_without_windows_writes(package, endpoint, tmp_path, watch_venv):
    from backend.gui_test.core.shared_settings_store import SharedSettingsStore
    tc_root = tmp_path / 'scripts'
    tc_root.mkdir()
    (tc_root / 'sample.py').write_text('pass\n')
    store = SharedSettingsStore(tmp_path / 'runtime')
    saved = store.read()
    store.save({'expected_revision': saved['revision'],
                'integration': saved['integration'] | {'tc_root': str(tc_root), 'source_roots': [str(tmp_path)]},
                'timeouts': {k: v for k, v in saved['timeouts'].items() if k != 'revision'}})
    cli = command(package, tmp_path, endpoint, 'connect', '--watch', '--read-only', '--no-provision', '--json')
    proc = start([str(watch_venv / 'bin/python'), *cli[1:]])
    try:
        assert line(proc)['state'] == 'connected'
        endpoint.runner = 'c' * 32
        assert line(proc)['state'] == 'runner_changed'
    finally:
        cleanup(proc)
    assert endpoint.requests
    assert all(method == 'GET' for method, path in endpoint.requests)


def test_unprovisioned_watch_exits_before_network_or_install(package, endpoint, tmp_path):
    home = tmp_path / 'not-installed'
    cli = command(package, home, endpoint, 'connect', '--watch', '--no-provision')
    cli.insert(1, '-S')
    result = invoke(cli)
    assert result.returncode == 6, result.stderr
    assert json.loads(result.stderr)['code'] == 'NOT_PROVISIONED'
    assert result.stdout == b'' and not home.exists() and endpoint.requests == []


def test_no_provision_rejects_broken_managed_interpreter(package, endpoint, tmp_path):
    home = tmp_path / 'home'
    release = home / 'releases' / 'incomplete'
    python = release / '.venv/bin/python'
    python.parent.mkdir(parents=True)
    python.touch(mode=0o600)
    (release / 'requirements.lock').write_bytes((package / 'agent-monitor/requirements.lock').read_bytes())
    (home / 'current.json').write_text(json.dumps({'path': str(release)}))
    cli = command(package, home, endpoint, 'connect', '--watch', '--no-provision')
    cli.insert(1, '-S')
    result = invoke(cli)
    assert result.returncode == 6 and json.loads(result.stderr)['code'] == 'NOT_PROVISIONED'
    assert not (home / 'start.lock').exists() and endpoint.requests == []


def test_no_provision_reuses_existing_managed_venv(package, endpoint, tmp_path, watch_venv):
    from shutil import copyfile
    home = tmp_path / 'home'
    release = home / 'releases' / 'installed'
    release.mkdir(parents=True)
    (release / '.venv').symlink_to(watch_venv, target_is_directory=True)
    (release / 'backend').symlink_to(package / 'agent-monitor/backend', target_is_directory=True)
    copyfile(package / 'agent-monitor/requirements.lock', release / 'requirements.lock')
    (home / 'current.json').write_text(json.dumps({'path': str(release)}))
    cli = command(package, home, endpoint, 'connect', '--watch', '--no-provision', '--read-only', '--json')
    cli.insert(1, '-S')
    proc = start(cli)
    try:
        assert line(proc)['state'] == 'connected'
    finally:
        cleanup(proc)
    assert not (home / 'start.lock').exists()
