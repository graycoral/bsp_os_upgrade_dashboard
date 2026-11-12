"""RQ-62 / T-218~220: setup discovery uses no real devices or programs."""
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

from scripts import setup_flashing as flash
from scripts import setup_runtime as setup


@pytest.mark.parametrize('location', ['saved', 'path', 'ANDROID_HOME', 'ANDROID_SDK_ROOT', 'LOCALAPPDATA'])
def test_discovery_resolves_installed_executable_without_running_it(tmp_path, monkeypatch, location):
    for key in ('ANDROID_HOME', 'ANDROID_SDK_ROOT', 'LOCALAPPDATA'):
        monkeypatch.delenv(key, raising=False)
    suffix = 'Android/Sdk/platform-tools/fastboot.exe' if location == 'LOCALAPPDATA' else 'platform-tools/fastboot.exe'
    exe = tmp_path / suffix
    exe.parent.mkdir(parents=True)
    exe.touch()
    monkeypatch.setattr(flash.shutil, 'which', lambda _: str(exe) if location == 'path' else None)
    if location not in ('saved', 'path'):
        monkeypatch.setenv(location, str(tmp_path))
    monkeypatch.setattr(flash.subprocess, 'run', lambda *_a, **_k: pytest.fail('path discovery executed a program'))
    assert flash.find_fastboot(str(exe) if location == 'saved' else '') == str(exe.resolve())


def test_missing_executable_and_shell_wrappers_are_not_discovered(tmp_path, monkeypatch):
    for key in ('ANDROID_HOME', 'ANDROID_SDK_ROOT', 'LOCALAPPDATA'):
        monkeypatch.delenv(key, raising=False)
    wrapper = tmp_path / 'fastboot.cmd'
    wrapper.touch()
    monkeypatch.setattr(flash.shutil, 'which', lambda _: str(wrapper))
    assert flash.find_fastboot(str(tmp_path / 'missing.exe')) == ''


def test_devices_only_query_strips_credentials_and_parses_unique_serials(monkeypatch):
    monkeypatch.setenv('GUI_TEST_RUNNER_TOKEN', 'private-token')
    monkeypatch.setenv('ANDROID_SERIAL', 'stale-target')
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        assert argv == ['C:/Android tools/fastboot.exe', 'devices']
        assert kwargs['shell'] is False and kwargs['timeout'] == 10
        assert kwargs['stdin'] == subprocess.DEVNULL
        assert not {'GUI_TEST_RUNNER_TOKEN', 'ANDROID_SERIAL'} & kwargs['env'].keys()
        return SimpleNamespace(returncode=0, stdout=b'A\tfastboot\nB fastboot usb:123\nA fastboot\nnoise\n? fastboot\nC offline\n')
    monkeypatch.setattr(flash.subprocess, 'run', run)
    assert flash.fastboot_devices('C:/Android tools/fastboot.exe') == ['A', 'B']
    assert len(calls) == 1


@pytest.mark.parametrize('failure', ['timeout', 'missing', 'exit', 'large', 'empty'])
def test_devices_failure_allows_manual_configuration(monkeypatch, failure):
    def run(*_a, **_k):
        if failure == 'timeout':
            raise subprocess.TimeoutExpired('fastboot', 10)
        if failure == 'missing':
            raise FileNotFoundError()
        return SimpleNamespace(returncode=1 if failure == 'exit' else 0,
                               stdout=b'x' * 65537 if failure == 'large' else b'')
    monkeypatch.setattr(flash.subprocess, 'run', run)
    assert flash.fastboot_devices('fastboot.exe') == []


def test_single_target_is_automatic_but_multiple_board_mapping_is_explicit(monkeypatch):
    board = {'board_id': 'a'}
    monkeypatch.setattr(flash, 'ask', lambda *_a, **_k: pytest.fail('unexpected manual serial'))
    monkeypatch.setattr(flash, 'yes', lambda *_a, **_k: pytest.fail('unexpected selection'))
    assert flash.board_serial(board, '', ['A'], True) == 'A'
    assert flash.board_serial(board, 'A', ['A'], True) == 'A'
    selections = []
    monkeypatch.setattr(flash, 'yes', lambda label, *_: selections.append(label) or True)
    monkeypatch.setattr(flash, 'number', lambda *_: 1)
    assert flash.board_serial(board, '', ['A'], False) == 'A'
    assert flash.board_serial(board, 'OLD', ['A'], True) == 'A'
    assert len(selections) == 2
    monkeypatch.setattr(flash, 'number', lambda *_: 2)
    assert flash.board_serial(board, '', ['A', 'B'], True) == 'B'


def configure_fixture(tmp_path, monkeypatch, boards, profile=None):
    w = setup.Wizard(root=tmp_path, windows=True, home=tmp_path / 'home')
    setup.save_json(w.config, {'boards': boards, 'future': 'kept',
                              'flashing': {'profiles': {'board-flash': profile}} if profile else {}})
    image = tmp_path / 'images'
    image.mkdir()
    batch = tmp_path / 'flash.bat'
    batch.write_bytes(b'@echo off\r\nexit /b 0\r\n')
    paths = iter([str(image), str(batch)])
    monkeypatch.setattr(flash, 'checked_path', lambda *_a, **_k: next(paths))
    monkeypatch.setattr(flash, 'find_fastboot', lambda *_: 'C:/tools/fastboot.exe')
    monkeypatch.setattr(flash, 'fastboot_devices', lambda *_: ['SERIAL7'])
    monkeypatch.setattr(flash, 'yes', lambda label, *_: not label.startswith('이 프로파일을 비활성화'))
    monkeypatch.setattr(flash, 'number', lambda _label, default, *_a: int(default))
    monkeypatch.setattr(w, 'preview_save', lambda path, draft: setup.save_json(path, draft))
    return w


def test_common_settings_asked_once_and_materialized_for_legacy_runtime(tmp_path, monkeypatch):
    boards = [{'board_id': 'a', 'com': 'COM7'}, {'board_id': 'b', 'com': 'COM8'}]
    w = configure_fixture(tmp_path, monkeypatch, boards)
    monkeypatch.setattr(flash, 'fastboot_devices', lambda *_: ['A', 'B'])
    prompts = []
    answers = iter(['board-flash', 'DONE', 'FAILED', 'cr', 'lkshell>', 'login:'])
    def ask(label, *_a, **_k):
        prompts.append(label)
        return next(answers)
    monkeypatch.setattr(flash, 'ask', ask)
    serial_choices = iter([1, 2])
    monkeypatch.setattr(flash, 'number', lambda label, default, *_a:
                        next(serial_choices) if '장치 번호' in label else int(default))
    flash.windows(w)
    saved = setup.read_json(w.config)
    profile = saved['flashing']['profiles']['board-flash']
    assert len(prompts) == 6
    for board in boards:
        cfg = profile['boards'][board['board_id']]
        assert cfg['com'] == board['com']
        assert {key: cfg[key] for key in flash.CONSOLE_FIELDS} == profile['console_defaults']
    assert [cfg['serial'] for cfg in profile['boards'].values()] == ['A', 'B']
    assert saved['future'] == 'kept'


def test_existing_board_overrides_and_extra_fields_survive(tmp_path, monkeypatch):
    a = {'com': 'COM7', 'baudrate': 9600, 'line_ending': 'lf', 'lkshell_prompt': 'old>',
         'boot_marker': 'old boot', 'serial': 'SERIAL7', 'future': 1}
    common = dict(a, baudrate=115200, line_ending='cr')
    profile = {'boards': {'a': a}, 'console_defaults': common, 'future': 2}
    w = configure_fixture(tmp_path, monkeypatch, [{'board_id': 'a', 'com': 'COM7'}], profile)
    monkeypatch.setattr(flash, 'yes', lambda label, *_:
                        not label.startswith(('이 프로파일을 비활성화', '이 보드에도 새 공통값')))
    def answer(label, default='', **_kwargs):
        return {'퓨징 프로파일 이름': 'board-flash', '배치 전체 성공 시 출력되는 정확한 문구': 'DONE'}.get(label, default)
    monkeypatch.setattr(flash, 'ask', answer)
    flash.windows(w)
    saved = setup.read_json(w.config)['flashing']['profiles']['board-flash']
    assert saved['boards']['a'] == {**a, 'login_prompt': 'login :'}
    assert saved['future'] == 2


def test_duplicate_device_choice_does_not_save_partial_configuration(tmp_path, monkeypatch):
    w = configure_fixture(tmp_path, monkeypatch, [{'board_id': 'a', 'com': 'COM7'}, {'board_id': 'b', 'com': 'COM8'}])
    before = w.config.read_bytes()
    answers = iter(['board-flash', 'DONE', 'FAILED', 'cr', 'lkshell>', 'login:'])
    monkeypatch.setattr(flash, 'ask', lambda *_a, **_k: next(answers))
    with pytest.raises(ValueError, match='serial이 중복'):
        flash.windows(w)
    assert w.config.read_bytes() == before


def test_recommended_defaults_and_command_cannot_be_readiness_marker(monkeypatch):
    defaults = {}
    def ask(label, default='', check=None, **_kwargs):
        defaults[label] = default
        if 'lkshell 진입' in label:
            assert not check('reboot lkshell') and not check('fast') and not check('fastboot init success')
            assert check('lkshell>')
            return 'lkshell>'
        return default or 'login:'
    monkeypatch.setattr(flash, 'ask', ask)
    monkeypatch.setattr(flash, 'number', lambda _label, default, *_a: default)
    cfg = flash.console_settings({'lkshell_prompt': 'reboot lkshell'})
    assert cfg['line_ending'] == 'cr' and cfg['baudrate'] == 115200
    assert cfg['boot_marker'] == cfg['login_prompt'] == 'login :'
    assert defaults['lkshell 진입 후 실제 출력되는 준비 문구 (명령어 아님)'] == ''


@pytest.mark.parametrize('marker', ['fastboot init success', 'login :'])
def test_readiness_marker_is_detected_inside_log_not_only_final_line(marker):
    import threading
    from backend.gui_test.execution.flashing import SerialConsole
    console = SerialConsole.__new__(SerialConsole)
    console.failed = False
    console.lock = threading.Lock()
    console.buffer = bytearray(('earlier output\r\n**** ' + marker + ' \r\nlater output\r\n').encode())
    console.wait(marker, 1)
