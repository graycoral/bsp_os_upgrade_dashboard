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
    monkeypatch.setattr(boot, 'healthy', lambda python, pins, root: python in ready)
    return root, home, calls, ready, logging.getLogger('bootstrap-test')


def test_first_launch_installs_once_and_repeat_is_offline(rig):
    root, home, calls, ready, log = rig
    config = (home / 'windows-runner.json').read_bytes()
    first = boot.prepare(root, home, log)
    assert first in ready and len(calls) == 2
    assert calls[1].count('-r') == 2
    assert boot.prepare(root, home, log) == first
    assert len(calls) == 2
    assert (home / 'windows-runner.json').read_bytes() == config


def test_source_edit_does_not_reinstall_but_pin_change_builds_new_environment(rig):
    root, home, calls, ready, log = rig
    old = boot.prepare(root, home, log)
    (root / 'source.py').write_text('# changed GUI source')
    assert boot.prepare(root, home, log) == old
    assert len(calls) == 2
    (root / boot.LOCKFILES[1]).write_text('# comment only\n Qt-example==2.0\n')
    assert boot.prepare(root, home, log) == old and len(calls) == 2
    (root / boot.LOCKFILES[1]).write_text('Qt-example==2.1\n')
    new = boot.prepare(root, home, log)
    assert new != old and old.exists() and new.exists() and len(calls) == 4


def test_existing_complete_venv_is_reused_without_modification(rig):
    root, home, calls, ready, log = rig
    old = root / '.venv' / 'Scripts' / 'python.exe'
    ready.add(old)
    assert boot.prepare(root, home, log) == old
    assert calls == []


def test_failed_upgrade_preserves_previous_environment_and_settings(rig, monkeypatch):
    root, home, calls, ready, log = rig
    old = boot.prepare(root, home, log)
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
        boot.prepare(root, home, log)
    assert old.exists() and sorted(p.name for p in cache.iterdir()) == before
    assert json.loads((home / 'windows-runner.json').read_text())['keep'] == 'existing board settings'


def test_corrupt_environment_is_replaced_without_removing_old_one(rig):
    root, home, calls, ready, log = rig
    old = boot.prepare(root, home, log)
    ready.remove(old)
    new = boot.prepare(root, home, log)
    assert new != old and old.exists()
    assert boot.prepare(root, home, log) == new
    assert len(calls) == 4


def test_install_lock_prevents_concurrent_mutation(rig):
    root, home, calls, ready, log = rig
    with LaunchLock(home / 'connector-environments' / 'install.lock'):
        with pytest.raises(RuntimeError):
            boot.prepare(root, home, log)
    assert not calls


def test_invalid_cache_pointer_cannot_launch_arbitrary_python(rig, tmp_path):
    root, home, calls, ready, log = rig
    _, key = boot.requirements(root)
    cache = home / 'connector-environments'
    cache.mkdir()
    (cache / (key + '.json')).write_text(json.dumps({'directory': '../untrusted'}))
    python = boot.prepare(root, home, log)
    assert python.is_relative_to(cache) and len(calls) == 2


@pytest.mark.parametrize('text', ['example>=1', '-r elsewhere', 'example==2.0'])
def test_invalid_or_conflicting_pins_fail_before_install(rig, text):
    root, home, calls, ready, log = rig
    (root / boot.LOCKFILES[1]).write_text(text)
    with pytest.raises(ValueError):
        boot.prepare(root, home, log)
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
def test_cmd_with_space_path_forwards_arguments_and_failure_code(tmp_path, exit_code, line_ending):
    root = tmp_path / 'Source with spaces & symbol'
    (root / 'scripts').mkdir(parents=True)
    (root / 'board-connector.cmd').write_bytes((ROOT / 'board-connector.cmd').read_text().replace('\n', line_ending).encode())
    # Discovery uses installed Python; the stub replaces installation/GUI/hardware work.
    (root / 'scripts' / 'board_connector.py').write_text(
        'import json,sys\nfrom pathlib import Path\n'
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
def test_main_launches_prepared_python_with_saved_home(rig, monkeypatch, install_only, child_exit, expected):
    from types import SimpleNamespace
    root, home, calls, ready, log = rig
    python = home / 'prepared' / 'Scripts' / 'python.exe'
    monkeypatch.setattr(boot, 'os', SimpleNamespace(name='nt'))
    monkeypatch.setattr(boot, 'ROOT', root)
    monkeypatch.setattr(boot, 'prepare', lambda r, h, l: python)
    launches = []
    def run(argv, **kwargs):
        launches.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, child_exit)
    monkeypatch.setattr(boot.subprocess, 'run', run)
    assert boot.main(['--home', str(home), *(['--install-only'] if install_only else [])]) == expected
    if install_only:
        assert not launches
    else:
        assert launches[0][0] == [str(python), '-X', 'utf8', '-B', '-m', 'backend.gui_test.connector', '--home', str(home)]
        assert launches[0][1]['cwd'] == root
