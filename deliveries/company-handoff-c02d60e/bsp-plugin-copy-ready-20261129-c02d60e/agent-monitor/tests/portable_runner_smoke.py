"""Opt-in packaged EXE checks: BSP_RUNNER_EXE=<onedir exe or zip>.

Run explicitly with pytest tests/portable_runner_smoke.py. All artifacts stay in
pytest's temporary directory. No SSH, COM device, flash, or model is contacted.
The packaged API is queried read-only; harmless TC execution uses the helper.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import hashlib

import pytest


pytestmark = pytest.mark.skipif(os.name != 'nt' or not os.environ.get('BSP_RUNNER_EXE'),
                               reason='requires Windows and BSP_RUNNER_EXE packaged artifact')
TOKEN = 'portable-smoke-token-' + 'a' * 48


@pytest.fixture(scope='module')
def artifact(tmp_path_factory):
    source = Path(os.environ['BSP_RUNNER_EXE']).resolve(strict=True)
    destination = tmp_path_factory.mktemp('portable 한글 outside repo') / 'Runner with spaces'
    if source.suffix.lower() == '.zip':
        destination.mkdir()
        with zipfile.ZipFile(source) as archive:
            for member in archive.infolist():
                assert (destination / member.filename).resolve().is_relative_to(destination.resolve())
            archive.extractall(destination)
        matches = list(destination.rglob('BSPRunner.exe'))
        if not matches:
            matches = [p for p in destination.rglob('*.exe') if (p.parent / '_internal').is_dir()]
        assert len(matches) == 1, 'expected one onedir Runner executable'
        exe = matches[0]
    else:
        shutil.copytree(source.parent, destination)
        exe = destination / source.name
    # Windows system tools are available; installed Python and pip are absent.
    system = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    env = dict(os.environ, PATH=str(system / 'System32'), GUI_TEST_RUNNER_TOKEN=TOKEN)
    for name in list(env):
        if name.upper() in ('PYTHONHOME', 'PYTHONPATH') or name.upper().startswith('_PYI_'):
            env.pop(name)
    assert shutil.which('python', path=env['PATH']) is None
    assert shutil.which('pip', path=env['PATH']) is None
    return exe, env, destination.parent


def test_packaged_default_wizard_exits_without_system_python(artifact):
    exe, env, work = artifact
    result = subprocess.run([str(exe), '--home', str(work / 'private home')], input=b'0\n',
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work, env=env, timeout=30)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    # Redirected frozen consoles may default to CP949 independently of the
    # Python test runner. Localized menus must survive and remain valid UTF-8.
    menu = result.stdout.decode('utf-8')
    result.stderr.decode('utf-8')
    assert any('\uac00' <= char <= '\ud7a3' for char in menu), 'localized setup menu missing'
    assert not (work / 'private home' / 'venv').exists()


@pytest.mark.parametrize('gate', [b'', b'?', b'!'])
def test_packaged_helper_gate_and_external_tc_environment(artifact, tmp_path, gate):
    exe, env, work = artifact
    marker = tmp_path / 'result.json'
    tc = tmp_path / 'harmless TC 한글.py'
    tc.write_text('import json,os,sys\nfrom pathlib import Path\n'
                  'Path(sys.argv[1]).write_text(json.dumps(dict(argv=sys.argv[2:], '
                  'secret=any(k.upper()=="GUI_TEST_RUNNER_TOKEN" for k in os.environ), '
                  'boot=[k for k in os.environ if k.upper().startswith("_PYI_")])))\n', encoding='utf-8')
    result = subprocess.run([str(exe), '--contained-child', '--', sys.executable, str(tc), str(marker),
                             'space value', '한글', '&literal'], input=gate, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=work, env=env, timeout=30)
    if gate != b'!':
        assert result.returncode == 125
        assert not marker.exists()
    else:
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        assert json.loads(marker.read_text()) == {'argv': ['space value', '한글', '&literal'],
                                                 'secret': False, 'boot': []}


def test_packaged_helper_stays_idle_until_gate(artifact, tmp_path):
    exe, env, work = artifact
    marker = tmp_path / 'unexpected'
    p = subprocess.Popen([str(exe), '--contained-child', '--', sys.executable, '-c',
                          'from pathlib import Path; import sys; Path(sys.argv[1]).touch()', str(marker)],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=work, env=env)
    try:
        time.sleep(.5)
        assert p.poll() is None
        assert not marker.exists()
        _, stderr = p.communicate(b'', timeout=30)
        assert p.returncode == 125, stderr.decode(errors='replace')
        assert not marker.exists()
    finally:
        if p.poll() is None:
            p.kill()
            p.wait(timeout=10)


def get(url, token=None):
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=2) as response:
        return json.load(response)


def test_packaged_api_auth_catalog_and_persistent_identity(artifact, tmp_path):
    exe, env, work = artifact
    source = tmp_path / 'shared TC'
    source.mkdir()
    (source / 'fixture.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
    config = tmp_path / 'runner.json'
    config.write_text(json.dumps({'source_root': str(source), 'python': sys.executable,
                                  'boards': [{'host': 'fixture', 'board_id': 'a', 'com': 'COM9999'}]}), encoding='utf-8')
    runtime = tmp_path / 'persistent runtime'
    identities = []
    for _ in range(2):
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        base = f'http://127.0.0.1:{port}/v1'
        # Files prevent pipe buffering from blocking a server during startup.
        with (tmp_path / 'runner.log').open('ab') as log:
            p = subprocess.Popen([str(exe), '--runner', '--config', str(config), '--runtime', str(runtime),
                                  '--port', str(port)], cwd=work, env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 30
                while True:
                    assert p.poll() is None, 'packaged host exited; inspect local runner.log'
                    try:
                        identity = get(base + '/identity', TOKEN)
                        break
                    except (OSError, ValueError):
                        if time.monotonic() >= deadline:
                            pytest.fail('packaged API not ready; inspect local runner.log')
                        time.sleep(.1)
                for invalid in (None, 'wrong-token'):
                    with pytest.raises(urllib.error.HTTPError) as error:
                        get(base + '/identity', invalid)
                    assert error.value.code == 401
                identities.append(identity['runner_id'])
                assert identity['source_snapshot_v1'] is True
                catalog = get(base + '/catalog', TOKEN)
                assert catalog['revision']
                assert any(tc['path'] == 'fixture.py' for tc in catalog['tests'])
                assert 'boards' in get(base + '/boards', TOKEN)
                # Capability advertisement is exercised against the actual frozen
                # snapshot upload endpoint, with no execution or board request.
                if not identities[:-1]:
                    from backend.gui_test.core.sources import SourceService
                    from backend.gui_test.core.store import Store
                    from backend.gui_test.execution.source_snapshots import create_archive
                    service = SourceService(Store(tmp_path / 'snapshot manager' / 'runs.db'))
                    inspected = service.inspect('server-folder', str(source))
                    service.apply(inspected['inspection_id'], None, 0)
                    descriptor = service.descriptor()
                    original = file_state(source)
                    with create_archive(service.directory(descriptor), descriptor) as archive:
                        payload = archive.read()
                    upload = urllib.request.Request(base + '/source-snapshots/' + descriptor['snapshot_id'],
                        data=payload, method='PUT', headers={'Authorization': 'Bearer ' + TOKEN,
                                                           'Content-Type': 'application/zip'})
                    with urllib.request.urlopen(upload, timeout=10) as response:
                        acknowledged = json.load(response)
                    assert acknowledged['snapshot_id'] == descriptor['snapshot_id']
                    assert acknowledged['source_revision'] == descriptor['source_revision']
                    assert file_state(source) == original
                duplicate = subprocess.run([str(exe), '--runner', '--config', str(config),
                                            '--runtime', str(runtime), '--port', str(port)],
                                           cwd=work, env=env, stdout=log, stderr=log, timeout=20)
                assert duplicate.returncode != 0
                assert get(base + '/identity', TOKEN) == identity
            finally:
                p.terminate()
                p.wait(timeout=15)
    assert identities[0] == identities[1]


def file_state(root):
    if not root.exists(): return {}
    result = {}
    for path in [root, *root.rglob('*')]:
        info = path.stat()
        result[str(path.relative_to(root))] = (info.st_mode, info.st_mtime_ns,
                                              path.read_bytes() if path.is_file() else None)
    return result


def packaged_command(artifact, args, timeout=30):
    exe, env, work = artifact
    return subprocess.run([str(exe), *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, cwd=work, env=env, timeout=timeout)


def test_packaged_setup_help_profiles_and_generated_launchers_without_python(artifact, tmp_path):
    exe, env, work = artifact
    home = tmp_path / 'private profile'
    help_result = packaged_command(artifact, ['--help'])
    assert help_result.returncode == 0
    help_text = help_result.stdout.decode('utf-8')
    for action in ('menu', 'run', 'doctor', 'ports', '--save', '--only'):
        assert action in help_text
    args = ['ports', '--save', '--home', str(home), '--port', '19771', '--dashboard-port', '19766']
    assert packaged_command(artifact, args).returncode == 0
    saved = json.loads((home / 'setup-ports.json').read_text(encoding='utf-8'))
    assert saved['version'] == 1
    assert saved['ports']['runner_port'] == 19771
    before = file_state(home)
    result = packaged_command(artifact, ['ports', '--home', str(home)])
    assert result.returncode == 0
    assert 'runner_port=19771 origin=profile' in result.stdout.decode('utf-8')
    assert file_state(home) == before
    for name, action in (('launch-run.cmd', 'run'), ('diagnose.cmd', 'doctor')):
        launcher = exe.parent / name
        assert launcher.is_file()
        text = launcher.read_text(encoding='utf-8-sig').lower()
        assert 'pause' not in text and 'python' not in text
        for args, expected in ((['--help'], 0), (['--home', str(home)], 1), (['--unknown-option'], 2)):
            command = '"' + str(launcher) + '" ' + subprocess.list2cmdline(args)
            launched = subprocess.run(command, shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, cwd=work, env=env, timeout=30)
            assert launched.returncode == expected, (action, args, launched.stdout, launched.stderr)
    assert file_state(home) == before


def test_packaged_guide_and_command_sources_have_checksum_provenance(artifact):
    exe, _, _ = artifact
    guide = exe.parent / 'GUIDE.md'
    assert guide.is_file()
    info = json.loads((exe.parent / 'build-info.json').read_text(encoding='utf-8'))
    hashes = info['source_sha256']
    assert hashlib.sha256(guide.read_bytes()).hexdigest() == hashes['docs/gui_test/RUN_AND_DIAGNOSE.md']
    for name in ('scripts/setup_runtime.py', 'scripts/setup_ports.py', 'scripts/run.sh', 'scripts/doctor.sh'):
        assert len(hashes[name]) == 64
    checksums = (exe.parent / 'SHA256SUMS').read_text(encoding='utf-8')
    for name in ('GUIDE.md', 'launch-run.cmd', 'diagnose.cmd'):
        actual = hashlib.sha256((exe.parent / name).read_bytes()).hexdigest()
        assert f'{actual}  {name}' in checksums


def test_packaged_doctor_authenticates_local_fixture_and_is_readonly(artifact, tmp_path):
    from scripts.setup_runtime import TokenStore
    home = tmp_path / 'doctor home'
    home.mkdir()
    (home / 'windows-runner.json').write_text(json.dumps({'source_root': 'private-TC-source-path'}))
    (home / 'runtime').mkdir()
    (home / 'runtime' / 'gui-test-settings.json').write_text('{"catalog_timeout_seconds":173}')
    (home / 'runtime' / 'runs.db').write_bytes(b'doctor must preserve this sentinel')
    TokenStore(home, True).save(TOKEN)
    calls = []
    state = {'reject': False}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            calls.append(self.path)
            if self.headers.get('Authorization') != 'Bearer ' + TOKEN or state['reject']:
                self.send_response(401); self.end_headers(); self.wfile.write(TOKEN.encode()); return
            values = {'/v1/identity': {'runner_id': 'fixture', 'source_snapshot_v1': True},
                      '/v1/boards': {'boards': []}, '/v1/catalog': {'revision': 'fixture', 'tests': []}}
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps(values[self.path]).encode())
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    before = file_state(home)
    try:
        common = ['doctor', '--home', str(home), '--port', str(server.server_port)]
        result = packaged_command(artifact, common)
        assert result.returncode == 0, result.stderr.decode('utf-8')
        assert calls == ['/v1/identity', '/v1/boards', '/v1/catalog']
        output = result.stdout.decode('utf-8')
        assert 'timeout_seconds=173' in output
        assert 'result=SUCCESS' in output and 'elapsed_seconds=' in output
        calls.clear()
        result = packaged_command(artifact, common + ['--only', 'boards'])
        assert result.returncode == 0
        assert calls == ['/v1/boards']
        state['reject'] = True
        result = packaged_command(artifact, common + ['--only', 'identity'])
        assert result.returncode == 1
        failure = result.stdout.decode('utf-8') + result.stderr.decode('utf-8')
        assert 'result=AUTH' in failure
        assert TOKEN not in failure and 'private-TC-source-path' not in failure and 'Traceback' not in failure
        assert file_state(home) == before
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_frozen_process_tree_cancels_descendants(artifact, tmp_path, monkeypatch):
    from backend.gui_test.execution.process import ProcessTree
    exe, env, work = artifact
    ready = tmp_path / 'child-ready'
    child = tmp_path / 'child.py'
    child.write_text('from pathlib import Path\nimport sys,time\n'
                     'Path(sys.argv[1]).write_text(str(__import__("os").getpid()))\ntime.sleep(120)\n', encoding='utf-8')
    parent = tmp_path / 'parent.py'
    parent.write_text('import subprocess,sys,time\nsubprocess.Popen(sys.argv[1:])\ntime.sleep(120)\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(exe))
    monkeypatch.setattr(sys, '_MEIPASS', str(exe.parent / '_internal'), raising=False)
    with (tmp_path / 'tree.log').open('wb') as log:
        tree = ProcessTree([str(Path(os.environ.get('BSP_TC_PYTHON', sys._base_executable)).resolve()),
                            str(parent), str(Path(os.environ.get('BSP_TC_PYTHON', sys._base_executable)).resolve()),
                            str(child), str(ready)], work, log, log, env=env)
        try:
            deadline = time.monotonic() + 20
            while not ready.exists() and time.monotonic() < deadline:
                assert tree.process.poll() is None, 'helper exited before fixture descendant started'
                time.sleep(.05)
            assert ready.exists(), 'fixture descendant not started'
            assert tree.stop(), 'Job Object did not establish termination'
            assert tree.stopped()
        finally:
            tree.stop()
            tree.close()
