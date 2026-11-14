"""Source bootstrap tests use fake installs; Windows CMD tests never launch hardware."""
import json
import logging
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import board_connector as boot
from backend.gui_test.execution.launch import LaunchLock

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def rig(tmp_path, monkeypatch):
    root, home = tmp_path / 'source with spaces', tmp_path / 'user home'
    for path, text in zip(boot.LOCKFILES, ('example==1.0\n', 'Qt-example==2.0\n')):
        file = root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    for name in ('scripts/board_connector.py', 'backend/gui_test/connector/__main__.py',
                 'backend/gui_test/connector/web_assets/index.html', 'backend/gui_test/connector/web_assets/host.mjs',
                 'packages/gui-test-ui/src/connector_web/view.mjs', 'packages/gui-test-ui/src/connector_web/style.css'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('# fixture')
    home.mkdir()
    (home / 'windows-runner.json').write_text('{"keep":"existing board settings"}')
    calls, ready = [], set()
    def install(argv, cwd, log, stage):
        calls.append([str(arg) for arg in argv])
        assert cwd == root
        if argv[1:3] == ['-m', 'venv']:
            python = Path(argv[3]) / 'Scripts' / 'python.exe'
            python.parent.mkdir(parents=True)
            python.touch()
        else:
            ready.add(Path(argv[0]))
    monkeypatch.setattr(boot, 'run_step', install)
    monkeypatch.setattr(boot, 'healthy', lambda python, pins, root, **kwargs: python in ready)
    # Public-tool bootstrapping belongs to a separate Windows setup path;
    # these fixtures must never run a real package manager.
    monkeypatch.setattr(boot, 'prepare_public_tools', lambda *a, **k: None)
    return root, home, calls, ready, logging.getLogger('bootstrap-test')


def test_first_launch_installs_once_and_repeat_is_offline(rig):
    root, home, calls, ready, log = rig
    config = (home / 'windows-runner.json').read_bytes()
    first = boot.prepare(root, home, log, ui='qt')
    assert first in ready and len(calls) == 2
    assert calls[1].count('-r') == 2
    assert boot.prepare(root, home, log, ui='qt') == first
    assert len(calls) == 2
    assert (home / 'windows-runner.json').read_bytes() == config


def test_source_edit_does_not_reinstall_but_pin_change_builds_new_environment(rig):
    root, home, calls, ready, log = rig
    old = boot.prepare(root, home, log, ui='qt')
    (root / 'source.py').write_text('# changed GUI source')
    assert boot.prepare(root, home, log, ui='qt') == old
    assert len(calls) == 2
    (root / boot.LOCKFILES[1]).write_text('# comment only\n Qt-example==2.0\n')
    assert boot.prepare(root, home, log, ui='qt') == old and len(calls) == 2
    (root / boot.LOCKFILES[1]).write_text('Qt-example==2.1\n')
    new = boot.prepare(root, home, log, ui='qt')
    assert new != old and old.exists() and new.exists() and len(calls) == 4


def test_existing_complete_venv_is_reused_without_modification(rig):
    root, home, calls, ready, log = rig
    old = root / '.venv' / 'Scripts' / 'python.exe'
    ready.add(old)
    assert boot.prepare(root, home, log, ui='qt') == old
    assert calls == []


def test_failed_upgrade_preserves_previous_environment_and_settings(rig, monkeypatch):
    root, home, calls, ready, log = rig
    old = boot.prepare(root, home, log, ui='qt')
    cache = home / 'connector-environments'
    before = sorted(p.name for p in cache.iterdir())
    (root / boot.LOCKFILES[1]).write_text('Qt-example==2.1\n')
    real = boot.run_step
    def fail(argv, *args):
        if 'pip' in argv:
            raise RuntimeError('offline fixture')
        return real(argv, *args)
    monkeypatch.setattr(boot, 'run_step', fail)
    with pytest.raises(RuntimeError, match='offline'):
        boot.prepare(root, home, log, ui='qt')
    assert old.exists() and sorted(p.name for p in cache.iterdir()) == before
    assert json.loads((home / 'windows-runner.json').read_text())['keep'] == 'existing board settings'


def test_corrupt_environment_is_replaced_without_removing_old_one(rig):
    root, home, calls, ready, log = rig
    old = boot.prepare(root, home, log, ui='qt')
    ready.remove(old)
    new = boot.prepare(root, home, log, ui='qt')
    assert new != old and old.exists()
    assert boot.prepare(root, home, log, ui='qt') == new
    assert len(calls) == 4


def test_install_lock_prevents_concurrent_mutation(rig):
    root, home, calls, ready, log = rig
    with LaunchLock(home / 'connector-environments' / 'install.lock'):
        with pytest.raises(RuntimeError):
            boot.prepare(root, home, log, ui='qt')
    assert not calls


def test_invalid_cache_pointer_cannot_launch_arbitrary_python(rig, tmp_path):
    root, home, calls, ready, log = rig
    _, key = boot.requirements(root, ui='qt')
    cache = home / 'connector-environments'
    cache.mkdir()
    (cache / (key + '.json')).write_text(json.dumps({'directory': '../untrusted'}))
    python = boot.prepare(root, home, log, ui='qt')
    assert python.is_relative_to(cache) and len(calls) == 2


@pytest.mark.parametrize('text', ['example>=1', '-r elsewhere', 'example==2.0'])
def test_invalid_or_conflicting_pins_fail_before_install(rig, text):
    root, home, calls, ready, log = rig
    (root / boot.LOCKFILES[1]).write_text(text)
    with pytest.raises(ValueError):
        boot.prepare(root, home, log, ui='qt')
    assert calls == []


def test_health_probe_detects_missing_packages_without_installing(tmp_path):
    assert not boot.healthy(Path(sys.executable), {'missing-bootstrap-fixture-package': '0'}, ROOT)
    assert not boot.healthy(tmp_path / 'missing.exe', {}, ROOT)


def test_child_environment_keeps_company_pip_config_but_not_connection_secrets(monkeypatch):
    monkeypatch.setenv('PIP_NO_INDEX', '1')
    monkeypatch.setenv('PIP_FIND_LINKS', 'C:/approved wheelhouse')
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', 'private')
    monkeypatch.setenv('GUI_TEST_INTEGRATION_TOKEN', 'private')
    monkeypatch.setenv('PYTHONHOME', 'unrelated interpreter')
    env = boot.child_env()
    assert env['PIP_NO_INDEX'] == '1' and env['PIP_FIND_LINKS'] == 'C:/approved wheelhouse'
    assert 'PYTHONHOME' not in env and not any(key.endswith('_TOKEN') for key in env if key.startswith('GUI_TEST_'))


def test_failed_pip_records_stage_and_exit_without_raw_secret(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(boot.subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a[0], 7))
    with caplog.at_level(logging.INFO), pytest.raises(RuntimeError):
        boot.run_step(['python', '-m', 'pip', 'private-index-token'], tmp_path, logging.getLogger('bootstrap'), 'Install')
    assert 'exit=7' in caplog.text and 'private-index-token' not in caplog.text


@pytest.mark.skipif(sys.platform != 'win32', reason='Real Windows CMD entrypoint')
@pytest.mark.parametrize('exit_code', [0, 17])
@pytest.mark.parametrize('line_ending', ['\n', '\r\n'], ids=['lf', 'crlf'])
@pytest.mark.parametrize('folder', ['Source with spaces & symbol', '괄호 (source) ! percent % source'])
def test_cmd_with_space_path_forwards_arguments_and_failure_code(tmp_path, exit_code, line_ending, folder):
    root = tmp_path / folder
    (root / 'scripts').mkdir(parents=True)
    for name in ('backend/gui_test/connector/__main__.py', 'apps/gui-test/requirements.lock'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
    (root / 'board-connector.cmd').write_bytes((ROOT / 'board-connector.cmd').read_text().replace('\n', line_ending).encode())
    # Discovery uses installed Python; the stub replaces installation/GUI/hardware work.
    (root / 'scripts' / 'board_connector.py').write_text(
        'import json,sys,os\nfrom pathlib import Path\n'
        'expected=os.environ.get("BOARD_CONNECTOR_EXPECT_PYTHON")\n'
        'assert not expected or expected==".".join(map(str,sys.version_info[:2])),sys.version\n'
        'Path(__file__).with_name("arguments.json").write_text(json.dumps(sys.argv[1:]))\n'
        f'sys.exit({exit_code})\n')
    args = ['--home', str(tmp_path / 'saved settings'), '--install-only']
    command = '"' + str(root / 'board-connector.cmd') + '" ' + subprocess.list2cmdline(args)
    result = subprocess.run(command, shell=True, cwd=tmp_path,
                            input='\n', capture_output=True, text=True, timeout=45)
    assert result.returncode == exit_code, result.stdout + result.stderr
    assert json.loads((root / 'scripts' / 'arguments.json').read_text()) == [
        '--home', str(tmp_path / 'saved settings'), '--install-only']


def test_unix_entrypoint_refuses_production_without_creating_home(tmp_path):
    if os.name == 'nt':
        pytest.skip('Non-Windows guard')
    home = tmp_path / 'not-created'
    assert boot.main(['--home', str(home)]) == 2
    assert not home.exists()


@pytest.mark.parametrize('install_only,child_exit,expected', [(True, 0, 0), (False, 0, 0), (False, 9, 1)])
@pytest.mark.parametrize('ui', ['browser', 'qt'])
def test_main_launches_prepared_python_with_saved_home(rig, monkeypatch, install_only, child_exit, expected, ui):
    from types import SimpleNamespace
    root, home, calls, ready, log = rig
    python = home / 'prepared' / 'Scripts' / 'python.exe'
    monkeypatch.setattr(boot, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(boot, 'ROOT', root)
    modes = []
    def prepare(r, h, l, ui):
        modes.append(ui)
        return python
    monkeypatch.setattr(boot, 'prepare', prepare)
    launches = []
    def run(argv, **kwargs):
        launches.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, child_exit)
    monkeypatch.setattr(boot.subprocess, 'run', run)
    assert boot.main(['--home', str(home), '--ui', ui, *(['--install-only'] if install_only else [])]) == expected
    assert modes == [ui]
    if install_only:
        assert not launches
    else:
        assert launches[0][0] == [str(python), '-X', 'utf8', '-B', '-m', 'backend.gui_test.connector', '--home', str(home), '--ui', ui]
        assert launches[0][1]['cwd'] == root


@pytest.mark.parametrize('version,bits,expected', [
    ((3, 10), 64, False), ((3, 11), 64, True), ((3, 12), 64, True),
    ((3, 13), 64, True), ((3, 14), 64, False), ((3, 13), 32, False),
])
def test_supported_python_versions(version, bits, expected):
    assert boot.supported_python(version, bits) is expected


def test_health_rejects_environment_from_different_python_minor(monkeypatch):
    from types import SimpleNamespace
    python = Path(sys.executable)
    monkeypatch.setattr(boot, 'sys', SimpleNamespace(version_info=(9, 9)))
    assert not boot.healthy(python, {}, ROOT)


@pytest.mark.skipif(sys.platform != 'win32', reason='Real Windows CMD entrypoint')
def test_cmd_reports_missing_source_before_python_discovery(tmp_path):
    wrapper = tmp_path / 'board-connector.cmd'
    wrapper.write_bytes((ROOT / 'board-connector.cmd').read_bytes())
    result = subprocess.run('"' + str(wrapper) + '"', shell=True, cwd=tmp_path,
                            input='\n', capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert '[BC-12]' in result.stdout and 'Missing file:' in result.stdout
    assert 'complete source folder' in result.stdout


def test_browser_installs_only_core_pins_and_reuses_separate_environment(rig):
    root, home, calls, ready, log = rig
    browser = boot.prepare(root, home, log, ui='browser')
    assert calls[-1].count('-r') == 1 and str(root / boot.LOCKFILES[1]) not in calls[-1]
    assert boot.prepare(root, home, log, ui='browser') == browser and len(calls) == 2
    qt = boot.prepare(root, home, log, ui='qt')
    assert qt != browser and qt.exists() and browser.exists() and calls[-1].count('-r') == 2


def test_default_main_is_browser_and_assets_missing_never_installs(rig, monkeypatch):
    from types import SimpleNamespace
    root, home, calls, ready, log = rig
    monkeypatch.setattr(boot, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(boot, 'ROOT', root)
    modes = []
    monkeypatch.setattr(boot, 'prepare', lambda r, h, l, ui: modes.append(ui) or Path('python.exe'))
    assert boot.main(['--install-only', '--home', str(home)]) == 0 and modes == ['browser']
    (root / 'packages/gui-test-ui/src/connector_web/view.mjs').unlink()
    assert boot.main(['--install-only', '--home', str(home)]) == 1 and modes == ['browser']


def test_diagnose_is_read_only_without_qt_or_existing_home(rig, monkeypatch, capsys):
    root, home, calls, ready, log = rig
    (root / boot.LOCKFILES[1]).unlink()
    absent = home / 'never-created'
    monkeypatch.setattr(boot, 'prepare', lambda *a, **k: pytest.fail('diagnose installed packages'))
    assert boot.diagnose(root, absent) == 0
    assert not absent.exists() and not calls
    assert '[BC-53]' in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != 'win32', reason='Real Windows CMD entrypoint')
def test_cmd_explicit_python_and_missing_override_diagnostics(tmp_path):
    root = tmp_path / 'source'
    for name in ('backend/gui_test/connector/__main__.py', 'apps/gui-test/requirements.lock', 'scripts/board_connector.py'):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('import sys; sys.exit(19)' if name.endswith('board_connector.py') else '')
    (root / 'board-connector.cmd').write_bytes((ROOT / 'board-connector.cmd').read_bytes())
    env = dict(os.environ, BOARD_CONNECTOR_PYTHON=sys.executable, LOCALAPPDATA=str(tmp_path / 'local'), ERRORLEVEL='99')
    command = '"' + str(root / 'board-connector.cmd') + '" --diagnose'
    result = subprocess.run(command, shell=True, cwd=tmp_path, env=env, input='\n', capture_output=True, text=True, timeout=30)
    assert result.returncode == 19 and '[BC-41]' in result.stdout
    logs = list((tmp_path / 'local/BspBoardConnector/logs').glob('launcher-*.log'))
    assert logs and str(Path(sys.executable)) in logs[0].read_text()
    env['BOARD_CONNECTOR_PYTHON'] = str(tmp_path / 'missing.exe')
    result = subprocess.run(command, shell=True, cwd=tmp_path, env=env, input='\n', capture_output=True, text=True, timeout=30)
    assert result.returncode == 3 and '[BC-31]' in result.stdout


def test_public_tool_reuse_does_not_start_package_manager(tmp_path, monkeypatch):
    monkeypatch.setattr(boot.shutil, 'which', lambda name: '/tools/' + name)
    monkeypatch.setattr(boot.subprocess, 'run', lambda *a, **k: pytest.fail('existing tools triggered install'))
    boot.prepare_public_tools(tmp_path, tmp_path/'home', logging.getLogger('public-tools'))
    assert not (tmp_path/'home').exists()


def test_public_tool_preparation_is_fixed_argv_and_refreshes_installed_path(tmp_path, monkeypatch):
    from types import SimpleNamespace
    root, home = tmp_path/'source', tmp_path/'home'
    script=root/'scripts/bootstrap-prerequisites.ps1';script.parent.mkdir(parents=True);script.write_text('# fixture')
    ssh=tmp_path/'new tools/ssh.exe';ssh.parent.mkdir();ssh.touch();fastboot=ssh.with_name('fastboot.exe');fastboot.touch()
    monkeypatch.setattr(boot.shutil,'which',lambda name:'/powershell.exe' if name=='powershell.exe' else None)
    calls=[]
    def run(argv,**kwargs):
        calls.append(argv)
        assert kwargs['shell'] is False and kwargs['stdin'] == subprocess.DEVNULL
        Path(argv[argv.index('-ReceiptPath')+1]).write_text(json.dumps({'tools':{'ssh.exe':str(ssh),'fastboot.exe':str(fastboot)}}))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(boot.subprocess,'run',run)
    boot.prepare_public_tools(root,home,logging.getLogger('public-tools'))
    assert len(calls)==1 and calls[0][:5]==['/powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File']
    assert str(ssh.parent) in os.environ['PATH'].split(os.pathsep)


def test_cmd_readonly_guard_precedes_missing_python_install():
    source=(ROOT/'board-connector.cmd').read_text()
    assert source.index('for %%A in (%*) do if /I "%%~A"=="--diagnose" goto missing_python') < source.index('[BC-29]')
    assert source.index(':missing_python') < source.index('[BC-30]')


@pytest.mark.skipif(os.name != 'nt',reason='Windows CMD contract')
@pytest.mark.parametrize('arguments',['--diagnose','--home "C:\\temporary profile" --diagnose'])
def test_cmd_diagnose_never_installs_missing_python(arguments,tmp_path):
    command='"'+str(ROOT/'board-connector.cmd')+'" '+arguments
    env=dict(os.environ,PATH=str(Path(os.environ['SystemRoot'])/'System32'))
    env.pop('BOARD_CONNECTOR_PYTHON',None)
    result=subprocess.run(['cmd.exe','/d','/c',command],env=env,input='\n',capture_output=True,text=True,timeout=30)
    assert '[BC-29]' not in result.stdout and 'winget install' not in result.stdout.lower()
