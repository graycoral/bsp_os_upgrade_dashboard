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
                catalog = get(base + '/catalog', TOKEN)
                assert catalog['revision']
                assert any(tc['path'] == 'fixture.py' for tc in catalog['tests'])
                assert 'boards' in get(base + '/boards', TOKEN)
                duplicate = subprocess.run([str(exe), '--runner', '--config', str(config),
                                            '--runtime', str(runtime), '--port', str(port)],
                                           cwd=work, env=env, stdout=log, stderr=log, timeout=20)
                assert duplicate.returncode != 0
                assert get(base + '/identity', TOKEN) == identity
            finally:
                p.terminate()
                p.wait(timeout=15)
    assert identities[0] == identities[1]


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
