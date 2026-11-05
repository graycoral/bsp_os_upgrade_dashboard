"""First-run setup checks; no real SSH, board, TC, flash, or model operation."""
import copy
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys

import pytest

from scripts import setup_flashing as flash
from scripts import setup_runtime as setup


TOKEN = "fixture-token-" + "a" * 48
BOARD_A = {"host": "pc-one", "board_id": "a", "com": "COM7", "node": "n295"}
BOARD_B = {"host": "pc-one", "board_id": "b", "com": "COM8", "node": "n296"}


def wizard(tmp_path, windows=True):
    root = tmp_path / "repo"
    root.mkdir()
    home = tmp_path / "private"
    return setup.Wizard(root=root, windows=windows, home=home)


@pytest.fixture
def win_process_constants(monkeypatch):
    """Windows startup uses these flags even when its children are mocked on Linux."""
    monkeypatch.setattr(setup.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(setup.signal, "CTRL_BREAK_EVENT", 21, raising=False)


def test_json_edits_preserve_unknown_fields_and_back_up_each_prior_version(tmp_path):
    path = tmp_path / "runner.json"
    original = {"boards": [BOARD_A], "future_field": {"nested": 42}}
    setup.save_json(path, original)
    second = {**original, "_setup": {"server": "linux.test", "account": "operator"}}
    setup.save_json(path, second)
    setup.save_json(path, {**second, "python": "C:/Python/python.exe"})
    assert setup.read_json(path)["future_field"] == {"nested": 42}
    backups = [json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.glob("*.bak")]
    assert original in backups and second in backups


def test_failed_atomic_replace_keeps_original_and_prior_backup(tmp_path, monkeypatch):
    path = tmp_path / "runner.json"
    setup.save_json(path, {"revision": 1})
    setup.save_json(path, {"revision": 2})
    old_backups = {p.name: p.read_bytes() for p in tmp_path.glob("*.bak")}
    monkeypatch.setattr(setup.os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError, match="replace failed"):
        setup.save_json(path, {"revision": 3})
    assert setup.read_json(path) == {"revision": 2}
    assert all((tmp_path / name).read_bytes() == value for name, value in old_backups.items())
    assert not list(tmp_path.glob("runner.json.*.tmp"))


def test_atomic_write_rejects_symlink(tmp_path):
    target = tmp_path / "target.json"
    target.write_text("original", encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="링크"):
        setup.save_json(link, {"replacement": True})
    assert target.read_text(encoding="utf-8") == "original"


def test_preview_cancel_preserves_exact_config(tmp_path, monkeypatch):
    w = wizard(tmp_path)
    setup.save_json(w.config, {"keep": "exact"})
    before = w.config.read_bytes()
    monkeypatch.setattr(setup, "yes", lambda *_args, **_kw: False)
    assert w.preview_save(w.config, {"keep": "changed"}) is False
    assert w.config.read_bytes() == before
    assert not list(w.home.glob("*.bak"))


def test_token_validation_rejects_short_non_ascii_and_whitespace():
    for bad in ("short", "x" * 4097, "x" * 31 + " ", "x" * 32 + "é"):
        with pytest.raises(ValueError):
            setup.TokenStore.validate(bad)
    assert setup.TokenStore.validate(TOKEN) == TOKEN


@pytest.mark.skipif(os.name != "nt", reason="DPAPI requires Windows user context")
def test_windows_dpapi_roundtrip_stores_no_plaintext(tmp_path):
    store = setup.TokenStore(tmp_path / "private", windows=True)
    store.save(TOKEN)
    assert store.path.name.endswith(".dpapi")
    assert TOKEN.encode() not in store.path.read_bytes()
    assert store.load() == TOKEN


@pytest.mark.skipif(os.name == "nt", reason="POSIX owner and mode contract runs on Linux CI")
def test_linux_token_permissions_and_rejects_world_readable(tmp_path):
    store = setup.TokenStore(tmp_path / "private", windows=False)
    store.save(TOKEN)
    assert store.home.stat().st_mode & 0o777 == 0o700
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert store.load() == TOKEN
    store.path.chmod(0o644)
    with pytest.raises(ValueError, match="600"):
        store.load()


@pytest.mark.parametrize("boards", [
    [{**BOARD_A, "com": "COM0"}],
    [{**BOARD_A, "com": "COM7;echo bad"}],
    [BOARD_A, {**BOARD_B, "com": "com7"}],
    [BOARD_A, {**BOARD_B, "board_id": "A"}],
    [BOARD_A, {**BOARD_B, "node": "N295"}],
    [BOARD_A, {**BOARD_B, "host": "another-pc"}],
    [{**BOARD_A, "node": "$(touch bad)"}],
])
def test_rejects_invalid_or_duplicate_board_registration(boards):
    with pytest.raises(ValueError):
        setup.validate_boards(boards)


def test_ssh_argv_is_fixed_forwarding_without_shell_interpolation():
    state = {"server": "linux.test", "account": "operator", "ssh_port": 2222}
    argv = setup.ssh_argv(state)
    assert argv[-5:] == ["-p", "2222", "-l", "operator", "linux.test"]
    assert "127.0.0.1:8766:127.0.0.1:8766" in argv
    assert "127.0.0.1:8771:127.0.0.1:8771" in argv
    for field, value in (("server", "host;touch bad"), ("account", "bob$(id)"), ("ssh_port", True)):
        with pytest.raises(ValueError):
            setup.ssh_argv({**state, field: value})


def test_runner_read_uses_loopback_no_proxy_or_redirect(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, limit):
            assert limit == 2_000_001
            return b'{"runner_id":"fixture"}'

    class Opener:
        def open(self, request, timeout):
            seen.update(url=request.full_url, authorization=request.get_header("Authorization"), timeout=timeout)
            return Response()

    def opener(*handlers):
        assert isinstance(handlers[0], setup.ProxyHandler)
        assert handlers[0].proxies == {}
        assert isinstance(handlers[1], setup.NoRedirect)
        return Opener()

    monkeypatch.setattr(setup, "build_opener", opener)
    assert setup.runner_get("/identity", TOKEN) == {"runner_id": "fixture"}
    assert seen == {"url": "http://127.0.0.1:8771/v1/identity", "authorization": "Bearer " + TOKEN, "timeout": 5}
    with pytest.raises(ValueError, match="리다이렉트"):
        setup.NoRedirect().redirect_request(None, None, None, None, None, None)


def test_runner_read_rejects_oversize_response(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self, _limit):
            return b"x" * 2_000_001

    class Opener:
        def open(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(setup, "build_opener", lambda *_: Opener())
    with pytest.raises(ValueError, match="너무 큽니다"):
        setup.runner_get("/catalog", TOKEN)


def test_windows_connection_reuses_saved_values_and_one_authoritative_file(tmp_path, monkeypatch):
    w = wizard(tmp_path)
    shared = tmp_path / "tc-share"
    shared.mkdir()
    python = tmp_path / "python.exe"
    python.touch()
    first = {"source_root": str(shared), "python": str(python), "boards": [BOARD_A],
             "metadata": {"single/tc1.py": {"timeout": 29}}, "future": {"keep": True},
             "_setup": {"server": "linux.test", "account": "operator", "ssh_port": 2222}}
    setup.save_json(w.config, first)
    w = setup.Wizard(root=w.root, windows=True, home=w.home)
    prompts = []

    def ask_default(label, default="", **_kwargs):
        prompts.append((label, default))
        return str(default)

    monkeypatch.setattr(setup, "checked_path", lambda _label, default="", _directory=False: default)
    monkeypatch.setattr(setup, "ask", ask_default)
    monkeypatch.setattr(setup, "number", lambda _label, default, *_: default)
    monkeypatch.setattr(setup, "yes", lambda label, *_args: label.startswith("이 설정을 저장"))
    monkeypatch.setattr(w, "token_setup", lambda: None)
    w.connection()
    saved = setup.read_json(w.config)
    assert saved == first
    assert w.state == first["_setup"]
    assert ("Linux SSH 서버 주소", "linux.test") in prompts
    assert len(list(w.home.glob("*.json"))) == 1


def test_linux_connection_preserves_other_runner_settings(tmp_path, monkeypatch):
    w = wizard(tmp_path, windows=False)
    setup.save_json(w.config, {"future": {"keep": 1}, "timeout": 17})
    monkeypatch.setattr(setup, "yes", lambda *_args, **_kw: True)
    monkeypatch.setattr(w, "token_setup", lambda: None)
    w.connection()
    assert setup.read_json(w.config) == {"future": {"keep": 1}, "timeout": 17,
                                         "runner": "windows-http", "url": "http://127.0.0.1:8771"}


def test_menu_restarts_from_saved_configuration_without_reasking(tmp_path, monkeypatch):
    w = wizard(tmp_path)
    setup.save_json(w.config, {"boards": [BOARD_A]})
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    choices = []

    def choose(_label, default, **_kwargs):
        choices.append(default)
        return "0"

    monkeypatch.setattr(setup, "ask", choose)
    monkeypatch.setattr(w, "connection", lambda: pytest.fail("connection prompted again"))
    w.menu()
    assert choices == ["3"]


def test_menu_defaults_to_install_when_config_exists_but_venv_missing(tmp_path, monkeypatch):
    w = wizard(tmp_path)
    setup.save_json(w.config, {"boards": [BOARD_A]})
    choices = []

    def choose(_label, default, **_kwargs):
        choices.append(default)
        return "0"

    monkeypatch.setattr(setup, "ask", choose)
    w.menu()
    assert choices == ["2"]


def test_start_refuses_missing_config_without_mock_fallback(tmp_path):
    w = wizard(tmp_path)
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    with pytest.raises(ValueError, match="Mock"):
        w.start()


def test_linux_start_requires_fixed_windows_http_loopback(tmp_path, monkeypatch):
    w = wizard(tmp_path, windows=False)
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    monkeypatch.setattr(w, "environment", lambda: {setup.TOKEN_ENV: TOKEN})
    monkeypatch.setattr(setup, "require_free", lambda _port: pytest.fail("port checked before config"))
    for config in ({"runner": "mock", "url": "http://127.0.0.1:8771"},
                   {"runner": "windows-http", "url": "http://127.0.0.1:8766"},
                   {"runner": "windows-http", "url": "http://other:8771"}):
        setup.save_json(w.config, config)
        with pytest.raises(ValueError, match="8771"):
            w.start()


def test_windows_start_scopes_token_to_runner_and_stops_owned_child(tmp_path, monkeypatch, win_process_constants):
    w = wizard(tmp_path)
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    setup.save_json(w.config, {"boards": [BOARD_A], "_setup": {"server": "linux.test", "account": "operator"}})
    w.state = setup.read_json(w.config)["_setup"]
    child = FakeProcess()
    transport = FakeProcess(code=0)
    spawned = []
    monkeypatch.setattr(w, "environment", lambda: {setup.TOKEN_ENV: TOKEN, "PATH": "fixture"})
    monkeypatch.setattr(setup.shutil, "which", lambda _: "ssh")
    monkeypatch.setattr(setup, "require_free", lambda _: None)
    monkeypatch.setattr(setup.subprocess, "Popen", lambda argv, **kw: spawned.append((argv, kw)) or
                        [child, transport][len(spawned)-1])
    monkeypatch.setattr(setup, "runner_get", lambda path, token: {"runner_id": "fixture"})
    w.start()
    argv, options = spawned[0]
    assert argv[:3] == [str(w.python), "-m", "backend.gui_test.execution.host"]
    assert argv[argv.index("--config") + 1] == str(w.config)
    assert options["env"][setup.TOKEN_ENV] == TOKEN
    assert options["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
    assert spawned[1][0][0] == "ssh"
    assert setup.TOKEN_ENV not in spawned[1][1]["env"]
    assert transport.terminated is False
    assert child.signals == [signal.CTRL_BREAK_EVENT]


def test_windows_runner_start_failure_still_stops_owned_child(tmp_path, monkeypatch, win_process_constants):
    w = wizard(tmp_path)
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    setup.save_json(w.config, {"boards": [BOARD_A]})
    w.state = {"server": "linux.test", "account": "operator"}
    child = FakeProcess()
    monkeypatch.setattr(w, "environment", lambda: {setup.TOKEN_ENV: TOKEN})
    monkeypatch.setattr(setup.shutil, "which", lambda _: "ssh")
    monkeypatch.setattr(setup, "require_free", lambda _: None)
    monkeypatch.setattr(setup.subprocess, "Popen", lambda *_args, **_kwargs: child)
    monkeypatch.setattr(setup, "runner_get", lambda *_args: (_ for _ in ()).throw(ValueError("unready")))
    monkeypatch.setattr(setup.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="시간 초과"):
        w.start()
    assert child.signals == [signal.CTRL_BREAK_EVENT]


class FakeProcess:
    def __init__(self, code=None):
        self.returncode = code
        self.signals = []
        self.terminated = False

    def poll(self):
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        self.returncode = 0

    def wait(self, timeout):
        assert timeout in (1, 5)
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.terminated = True
        self.returncode = -9


def test_windows_runner_death_after_readiness_stops_owned_ssh(tmp_path, monkeypatch, win_process_constants):
    w = wizard(tmp_path)
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    setup.save_json(w.config, {"_setup": {"server": "linux.test", "account": "operator"}})
    w.state = setup.read_json(w.config)["_setup"]
    runner, transport = FakeProcess(), FakeProcess()
    calls = []

    def popen(*_args, **_kwargs):
        calls.append(1)
        return [runner, transport][len(calls)-1]

    def die(_seconds):
        runner.returncode = 8

    monkeypatch.setattr(w, "environment", lambda: {setup.TOKEN_ENV: TOKEN})
    monkeypatch.setattr(setup.shutil, "which", lambda _: "ssh")
    monkeypatch.setattr(setup, "require_free", lambda _: None)
    monkeypatch.setattr(setup.subprocess, "Popen", popen)
    monkeypatch.setattr(setup, "runner_get", lambda *_args: {"runner_id": "fixture"})
    monkeypatch.setattr(setup.time, "sleep", die)
    with pytest.raises(RuntimeError, match="실행기가 종료"):
        w.start()
    assert len(calls) == 2
    assert transport.terminated is True
    assert runner.signals == []


def test_linux_child_failure_cleans_up_worker_before_api(tmp_path, monkeypatch):
    w = wizard(tmp_path, windows=False)
    (w.root / "apps/web/dist").mkdir(parents=True)
    (w.root / "apps/web/dist/index.html").touch()
    api, worker = FakeProcess(), FakeProcess(code=17)
    spawned = []
    monkeypatch.setattr(setup.subprocess, "Popen", lambda argv, **kw: spawned.append((argv, kw)) or [api, worker][len(spawned)-1])
    with pytest.raises(RuntimeError, match="17"):
        w.linux_start({setup.TOKEN_ENV: TOKEN})
    assert len(spawned) == 2
    assert all(options["start_new_session"] is True for _, options in spawned)
    assert api.signals == [signal.SIGINT]
    assert worker.signals == []  # It had already exited.


def test_linux_second_child_spawn_failure_cleans_up_first(tmp_path, monkeypatch):
    w = wizard(tmp_path, windows=False)
    (w.root / "apps/web/dist").mkdir(parents=True)
    (w.root / "apps/web/dist/index.html").touch()
    api = FakeProcess()
    calls = []

    def popen(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("spawn failed")
        return api

    monkeypatch.setattr(setup.subprocess, "Popen", popen)
    with pytest.raises(OSError, match="spawn failed"):
        w.linux_start({})
    assert api.signals == [signal.SIGINT]


@pytest.mark.skipif(os.name == "nt", reason="real POSIX session cleanup runs on Linux CI")
def test_linux_ctrl_c_stops_only_new_session_dummy_children(tmp_path, monkeypatch):
    w = wizard(tmp_path, windows=False)
    (w.root / "apps/web/dist").mkdir(parents=True)
    (w.root / "apps/web/dist/index.html").touch()
    children = []
    actual_popen = subprocess.Popen

    def spawn_dummy(_argv, **kwargs):
        assert kwargs["start_new_session"] is True
        child = actual_popen([sys.executable, "-c", "import time; time.sleep(60)"],
                             cwd=kwargs["cwd"], env=kwargs["env"], start_new_session=True)
        children.append(child)
        return child

    monkeypatch.setattr(setup.subprocess, "Popen", spawn_dummy)
    monkeypatch.setattr(setup.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        with pytest.raises(KeyboardInterrupt):
            w.linux_start({})
        assert len(children) == 2
        assert all(child.poll() is not None for child in children)
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=5)


@pytest.mark.parametrize("value", ["../outside", "/absolute", "C:/windows", "folder\\file", "CON", "x/COM1.txt", "x//y", "x/./y", "x/ending."])
def test_flash_bundle_rejects_unsafe_relative_path(value):
    assert not flash.relative(value)


def test_flash_cases_require_enabled_tc_order_and_dual_nodes():
    tests = [{"id": "boot", "kind": "Single", "after": []},
             {"id": "dual", "kind": "Dual", "after": ["boot"]},
             {"id": "disabled", "kind": "Single", "disabled_reason": "missing", "after": []}]
    connection = {"a": BOARD_A, "b": BOARD_B}
    flash.check_cases({"boot": ["boot"], "functional": ["dual"]}, tests, connection)
    for cases, conn in (({"boot": ["dual", "boot"]}, connection),
                        ({"boot": ["disabled"]}, connection),
                        ({"boot": ["boot"], "functional": ["dual"]}, {"a": BOARD_A, "b": None}),
                        ({"boot": []}, connection)):
        with pytest.raises(ValueError):
            flash.check_cases(cases, tests, conn)


def test_legacy_dual_com_template_allows_boards_without_node_names():
    a = {key: value for key, value in BOARD_A.items() if key != "node"}
    b = {key: value for key, value in BOARD_B.items() if key != "node"}
    tests = [{"id": "dual.py", "kind": "Dual", "after": []}]
    cases = {"boot": ["dual.py"]}
    with pytest.raises(ValueError, match="노드"):
        flash.check_cases(cases, tests, {"a": a, "b": b})
    flash.check_cases(cases, tests, {"a": a, "b": b},
                      {"dual": ["python", "{tc_path}", "-p", "{com_a}", "-p2", "{com_b}"]})


def test_disable_flash_profile_preserves_original_fields(tmp_path, monkeypatch):
    w = wizard(tmp_path)
    profile = {"enabled": True, "image_root": "C:/images", "boards": {"a": {"serial": "ABC"}},
               "future_field": 91}
    setup.save_json(w.config, {"boards": [BOARD_A], "flashing": {"profiles": {"board-flash": profile}}})
    monkeypatch.setattr(flash, "ask", lambda *_args, **_kwargs: "board-flash")
    monkeypatch.setattr(flash, "yes", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(w, "preview_save", lambda path, draft: setup.save_json(path, draft))
    flash.windows(w)
    saved = setup.read_json(w.config)
    assert saved["flashing"]["profiles"]["board-flash"] == {**profile, "enabled": False}
    assert saved["boards"] == [BOARD_A]


def test_windows_flash_profile_enables_only_after_explicit_configuration(tmp_path, monkeypatch):
    w = wizard(tmp_path)
    setup.save_json(w.config, {"boards": [BOARD_A], "future": "kept"})
    image_root = tmp_path / "images"
    image_root.mkdir()
    fastboot = tmp_path / "fastboot.exe"
    fastboot.touch()
    batch = tmp_path / "flash.bat"
    batch.write_bytes(b"@echo off\r\nexit /b 0\r\n")
    paths = iter([str(image_root), str(fastboot), str(batch)])
    responses = iter(["board-flash", "FLASH COMPLETE", "FAILED|fastboot: error:", "crlf",
                      "lkshell ready", "boot ready", "SERIAL7"])
    monkeypatch.setattr(flash, "checked_path", lambda *_args, **_kwargs: next(paths))
    monkeypatch.setattr(flash, "ask", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(flash, "number", lambda _label, default, *_args: int(default or 115200))
    monkeypatch.setattr(flash, "yes", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(w, "preview_save", lambda path, draft: setup.save_json(path, draft))
    flash.windows(w)
    saved = setup.read_json(w.config)
    profile = saved["flashing"]["profiles"]["board-flash"]
    assert profile["enabled"] is True
    assert profile["batch_sha256"] == __import__("hashlib").sha256(batch.read_bytes()).hexdigest()
    assert profile["boards"]["a"] == {"com": "COM7", "baudrate": 115200, "line_ending": "crlf",
                                       "lkshell_prompt": "lkshell ready", "boot_marker": "boot ready",
                                       "serial": "SERIAL7"}
    assert saved["future"] == "kept"
    assert batch.read_bytes() == b"@echo off\r\nexit /b 0\r\n"


def test_windows_flash_profile_prunes_stale_board_mapping_after_rename(tmp_path, monkeypatch):
    w = wizard(tmp_path)
    image_root = tmp_path / "images"
    image_root.mkdir()
    fastboot = tmp_path / "fastboot.exe"
    fastboot.touch()
    batch = tmp_path / "flash.bat"
    batch.write_bytes(b"@echo off\n")
    stale = {"old-id": {"serial": "OLD", "com": "COM7"}}
    setup.save_json(w.config, {"boards": [{**BOARD_A, "board_id": "renamed"}],
                               "flashing": {"profiles": {"board-flash": {"boards": stale}}}})
    paths = iter([str(image_root), str(fastboot), str(batch)])
    answers = iter(["board-flash", "FLASH COMPLETE", "FAILED", "lf", "ready", "booted", "NEW"])
    monkeypatch.setattr(flash, "checked_path", lambda *_args, **_kwargs: next(paths))
    monkeypatch.setattr(flash, "ask", lambda *_args, **_kwargs: next(answers))
    monkeypatch.setattr(flash, "number", lambda _label, default, *_args: int(default or 115200))
    monkeypatch.setattr(flash, "yes", lambda label, *_args: not label.startswith("이 프로파일을 비활성화"))
    monkeypatch.setattr(w, "preview_save", lambda path, draft: setup.save_json(path, draft))
    flash.windows(w)
    boards = setup.read_json(w.config)["flashing"]["profiles"]["board-flash"]["boards"]
    assert set(boards) == {"renamed"}
    assert boards["renamed"]["serial"] == "NEW"


def test_linux_flash_configuration_only_saves_selected_module(tmp_path, monkeypatch):
    w = wizard(tmp_path, windows=False)
    w.runtime.mkdir(parents=True)
    path = w.runtime / "device-test.json"
    setup.save_json(path, {"future": 73, "modules": {"other": {"enabled": False, "keep": 1}}})
    monkeypatch.setattr(w.tokens, "load", lambda: TOKEN)
    replies = iter(["BSP", "board-flash", "release", "boot,functional", "1", "1"])
    monkeypatch.setattr(flash, "ask", lambda *_args, **_kwargs: next(replies))
    monkeypatch.setattr(flash, "number", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(flash, "yes", lambda label, *_args: label.startswith("이 모듈") or label.startswith("이 모듈을") or label.startswith("이 모듈의"))
    monkeypatch.setattr(flash, "runner_get", lambda route, _token: {"boards": [BOARD_A]} if route == "/boards" else
                        {"tests": [{"id": "single.py", "kind": "Single", "after": [], "disabled_reason": ""}]})
    monkeypatch.setattr(w, "preview_save", lambda target, draft: setup.save_json(target, draft))
    flash.linux(w)
    saved = setup.read_json(path)
    assert saved["future"] == 73 and saved["modules"]["other"] == {"enabled": False, "keep": 1}
    assert saved["modules"]["BSP"]["bundle"] == "release"
    assert saved["modules"]["BSP"]["cases"] == {"boot": ["single.py"], "functional": ["single.py"]}
    assert saved["url"] == "http://127.0.0.1:8771"
    assert saved["enabled"] is True and saved["modules"]["BSP"]["enabled"] is True


def test_linux_manifest_menu_invokes_only_hash_helper_and_remembers_paths(tmp_path, monkeypatch):
    w = wizard(tmp_path, windows=False)
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    setup.save_json(w.config, {"runner": "windows-http", "url": "http://127.0.0.1:8771", "future": 9})
    image_root = tmp_path / "built-images"
    image_root.mkdir()
    output = tmp_path / "manifest.json"
    invoked = []
    monkeypatch.setattr(setup, "checked_path", lambda *_args, **_kwargs: str(image_root))
    replies = iter(["flash.bat", str(output)])
    monkeypatch.setattr(setup, "ask", lambda *_args, **_kwargs: next(replies))
    monkeypatch.setattr(setup, "yes", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(w, "command", lambda argv, env=None: invoked.append(argv))
    w.manifest()
    assert invoked == [[w.python, "-m", "scripts.create_flash_manifest", "--root", str(image_root),
                        "--batch", "flash.bat", "--output", str(output)]]
    saved = setup.read_json(w.config)
    assert saved["_setup"]["manifest"] == {"root": str(image_root), "batch": "flash.bat", "output": str(output)}
    assert saved["future"] == 9
    assert not output.exists()  # This test intercepted the hash helper; no image or device operation ran.


def test_scripts_are_entrypoints_without_direct_hardware_commands():
    root = Path(__file__).resolve().parents[1]
    shell = (root / "scripts/setup.sh").read_text(encoding="utf-8")
    ps = (root / "scripts/setup.ps1").read_text(encoding="utf-8-sig")
    cmd = (root / "scripts/setup.cmd").read_text(encoding="utf-8-sig")
    for source in (shell, ps, cmd):
        assert "setup_runtime.py" in source
        assert not any(term in source.lower() for term in ("fastboot", "reboot lkshell", "tc1.py"))
    assert '"$@"' in shell
    assert "$LASTEXITCODE" in ps
    assert "%errorlevel%" in cmd.lower()
    assert 'py -3 -x utf8 "%~dp0setup_runtime.py"' in cmd.lower()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell wrapper runs on Windows")
def test_powershell_wrapper_propagates_fake_python_failure(tmp_path):
    root = Path(__file__).resolve().parents[1]
    fake = tmp_path / "fake-python.cmd"
    fake.write_text("@echo off\r\nexit /b 7\r\n", encoding="ascii")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(root / "scripts/setup.ps1"),
                             "-PythonExecutable", str(fake)], capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "7" in result.stderr or "7" in result.stdout


@pytest.mark.skipif(os.name != "nt", reason="CMD wrapper runs on Windows")
def test_cmd_wrapper_preserves_python_exit_code_without_hardware_calls():
    if not shutil.which("python"):
        pytest.skip("python not on PATH")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["cmd.exe", "/d", "/c", str(root / "scripts/setup.cmd"),
                             "--definitely-invalid-option"], input="\n", capture_output=True,
                            text=True, timeout=20)
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows CMD and PowerShell wrappers")
@pytest.mark.parametrize("line_endings", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("code", [0, 7])
def test_direct_windows_wrappers_launch_sibling_targets_from_other_cwd(tmp_path, line_endings, code):
    """Exercise real shells with harmless targets, including a spaced script path."""
    root = Path(__file__).resolve().parents[1]
    scripts = tmp_path / "project with spaces" / "scripts"
    scripts.mkdir(parents=True)
    other_cwd = tmp_path / "unrelated working directory"
    other_cwd.mkdir()
    for name in ("setup.cmd", "setup.ps1", "build.cmd"):
        source = (root / "scripts" / name).read_text(encoding="utf-8-sig")
        (scripts / name).write_bytes(source.replace("\r\n", "\n").replace("\n", line_endings).encode("utf-8"))

    python_target = (
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['WRAPPER_CAPTURE']).write_text(json.dumps({"
        "'cwd': os.getcwd(), 'argv': sys.argv[1:], 'script': __file__}), encoding='utf-8')\n"
        "sys.exit(int(os.environ['WRAPPER_EXIT']))\n"
    )
    (scripts / "setup_runtime.py").write_text(python_target, encoding="utf-8")
    ps_target = (
        "[IO.File]::WriteAllText($env:WRAPPER_CAPTURE, "
        "(@{ cwd = (Get-Location).Path; argv = @($args); script = $PSCommandPath } "
        "| ConvertTo-Json -Compress))\n"
        "exit [int]$env:WRAPPER_EXIT\n"
    )
    (scripts / "build.ps1").write_bytes(ps_target.replace("\n", line_endings).encode("utf-8"))
    env = {**os.environ, "WRAPPER_EXIT": str(code)}

    for wrapper, args in (("setup.cmd", ["alpha", "two words"]),
                          ("setup.ps1", []), ("build.cmd", ["alpha", "two words"])):
        capture = tmp_path / (wrapper + ".json")
        env["WRAPPER_CAPTURE"] = str(capture)
        if wrapper.endswith(".ps1"):
            argv = ["powershell.exe", "-NoLogo", "-NoProfile", "-File", str(scripts / wrapper), *args]
            result = subprocess.run(argv, cwd=other_cwd, env=env, input="\n",
                                    capture_output=True, text=True, timeout=25)
        else:
            command = '"' + str(scripts / wrapper) + '" ' + subprocess.list2cmdline(args)
            result = subprocess.run(command, shell=True, cwd=other_cwd, env=env, input="\n",
                                    capture_output=True, text=True, timeout=25)
        assert capture.exists(), (wrapper, result.stdout, result.stderr)
        actual = json.loads(capture.read_text(encoding="utf-8"))
        assert Path(actual["cwd"]).resolve() == other_cwd.resolve()
        target = "build.ps1" if wrapper == "build.cmd" else "setup_runtime.py"
        assert Path(actual["script"]).resolve() == (scripts / target).resolve()
        assert actual["argv"] == args
        assert result.returncode == code or (wrapper == "setup.ps1" and code == 7 and result.returncode == 1)


@pytest.mark.skipif(os.name == "nt", reason="Bash entrypoint runs on Linux CI")
def test_bash_wrapper_forwards_help_without_starting_services():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["bash", str(root / "scripts/setup.sh"), "--help"],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0
    assert "--home" in result.stdout
