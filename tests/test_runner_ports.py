"""Runner port overrides; all services, SSH and device operations are mocked."""
import copy
import os
from pathlib import Path
import signal
import tempfile

import pytest

from scripts import setup_runtime as setup
from scripts import setup_flashing as flash
from scripts import windows_runner_entry as entry


TOKEN = "fixture-token-" + "a" * 48
STATE = {"server": "linux.test", "account": "operator", "ssh_port": 2222}


@pytest.fixture
def cli_home():
    # pytest --basetemp may be inside the checkout; real CLI settings must not be.
    with tempfile.TemporaryDirectory(prefix="bsp-runner-port-settings-") as temporary:
        home = Path(temporary).resolve() / "private"
        assert not home.is_relative_to(setup.ROOT.resolve())
        yield home


def make_wizard(tmp_path, *, windows=True, **ports):
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    return setup.Wizard(root=root, windows=windows, home=tmp_path / "private", **ports)


def test_port_omission_keeps_8771_and_existing_tunnel_defaults(tmp_path):
    w = make_wizard(tmp_path)
    assert w.runner_port == 8771
    assert w.runner_url == "http://127.0.0.1:8771"
    argv = setup.ssh_argv(STATE)
    assert argv[argv.index("-L") + 1] == "127.0.0.1:8766:127.0.0.1:8766"
    assert argv[argv.index("-R") + 1] == "127.0.0.1:8771:127.0.0.1:8771"
    assert argv[argv.index("-p") + 1] == "2222"


@pytest.mark.parametrize("option", ["--port", "--runner-port"])
def test_exe_cli_passes_custom_ports_to_wizard_without_saving(tmp_path, monkeypatch, option, cli_home):
    made = []
    actual_wizard = setup.Wizard

    def create(**kwargs):
        w = actual_wizard(root=tmp_path, windows=True, **kwargs)
        monkeypatch.setattr(w, "menu", lambda: None)
        made.append(w)
        return w

    monkeypatch.setattr(setup, "Wizard", create)
    assert entry.main([option, "18771", "--dashboard-port", "18766",
                       "--remote-runner-port", "28771", "--remote-dashboard-port", "28766",
                       "--ssh-port", "2200", "--home", str(cli_home)]) == 0
    w, = made
    assert (w.runner_port, w.dashboard_port, w.remote_runner_port,
            w.remote_dashboard_port, w.ssh_port) == (18771, 18766, 28771, 28766, 2200)
    assert not w.home.exists(), "CLI overrides must not create or rewrite personal settings"


def test_exe_cli_omitted_port_still_uses_8771(tmp_path, monkeypatch, cli_home):
    made = []
    actual_wizard = setup.Wizard

    def create(**kwargs):
        w = actual_wizard(root=tmp_path, windows=True, **kwargs)
        monkeypatch.setattr(w, "menu", lambda: None)
        made.append(w)
        return w

    monkeypatch.setattr(setup, "Wizard", create)
    assert entry.main(["--home", str(cli_home)]) == 0
    assert made[0].runner_port == 8771


@pytest.mark.parametrize("option", ["--port", "--runner-port", "--dashboard-port",
                                    "--remote-runner-port", "--remote-dashboard-port", "--ssh-port"])
@pytest.mark.parametrize("value", ["0", "65536", "-1", "not-a-port"])
def test_invalid_cli_ports_fail_before_opening_menu(monkeypatch, option, value):
    monkeypatch.setattr(setup.Wizard, "menu", lambda _: pytest.fail("invalid port reached menu"))
    with pytest.raises(SystemExit) as failure:
        entry.main([option, value])
    assert failure.value.code == 2


def test_windows_rejects_same_local_ports_but_allows_cross_machine_numbers(tmp_path):
    with pytest.raises(ValueError):
        make_wizard(tmp_path, runner_port=18771, dashboard_port=18771)
    w = make_wizard(tmp_path, runner_port=18771, dashboard_port=18766,
                    remote_runner_port=18766, remote_dashboard_port=18771)
    assert w.runner_url == "http://127.0.0.1:18771"


@pytest.mark.parametrize("value", [True, False, 0, 65536, "18771", 18771.0])
def test_non_cli_port_validation_rejects_invalid_values_before_networking(value, monkeypatch):
    monkeypatch.setattr(setup, "build_opener", lambda *_: pytest.fail("invalid port reached HTTP"))
    with pytest.raises(ValueError):
        setup.runner_get("/identity", TOKEN, value)
    with pytest.raises(ValueError):
        setup.ssh_argv(STATE, runner_port=value)


def test_custom_ssh_forwarding_maps_each_endpoint_and_preserves_saved_state():
    saved = copy.deepcopy(STATE)
    argv = setup.ssh_argv(STATE, runner_port=18771, dashboard_port=18766,
                          remote_runner_port=28771, remote_dashboard_port=28766, ssh_port=2200)
    assert argv[argv.index("-L") + 1] == "127.0.0.1:18766:127.0.0.1:28766"
    assert argv[argv.index("-R") + 1] == "127.0.0.1:28771:127.0.0.1:18771"
    assert argv[argv.index("-p") + 1] == "2200"
    assert "ExitOnForwardFailure=yes" in argv
    assert STATE == saved


def test_only_port_override_changes_windows_listener_without_requiring_linux_config_change():
    argv = setup.ssh_argv(STATE, runner_port=18771)
    assert argv[argv.index("-R") + 1] == "127.0.0.1:8771:127.0.0.1:18771"
    assert argv[argv.index("-L") + 1] == "127.0.0.1:8766:127.0.0.1:8766"


@pytest.mark.parametrize("args", [
    pytest.param(["--port", "18771", "--dashboard-port", "18771"],
                 marks=pytest.mark.skipif(os.name != "nt", reason="Windows CLI local endpoints")),
    ["--remote-runner-port", "28771", "--remote-dashboard-port", "28771"],
])
def test_conflicting_cli_endpoints_fail_before_opening_menu(monkeypatch, args):
    monkeypatch.setattr(setup.Wizard, "menu", lambda _: pytest.fail("conflicting ports reached menu"))
    with pytest.raises(SystemExit) as failure:
        entry.main(args)
    assert failure.value.code == 2


@pytest.mark.parametrize("port", [1, 65535])
def test_runner_http_override_keeps_loopback_no_proxy_or_redirect(monkeypatch, port):
    seen = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, limit):
            assert limit == 2_000_001
            return b'{"runner_id":"fixture"}'

    class Opener:
        def open(self, request, timeout):
            seen.append((request.full_url, request.get_header("Authorization"), timeout))
            return Response()

    def opener(*handlers):
        assert isinstance(handlers[0], setup.ProxyHandler) and handlers[0].proxies == {}
        assert isinstance(handlers[1], setup.NoRedirect)
        return Opener()

    monkeypatch.setattr(setup, "build_opener", opener)
    assert setup.runner_get("/identity", TOKEN, port) == {"runner_id": "fixture"}
    assert seen == [(f"http://127.0.0.1:{port}/v1/identity", "Bearer " + TOKEN, 5)]


class Process:
    def __init__(self, code=None):
        self.returncode = code
        self.signals = []

    def poll(self): return self.returncode
    def send_signal(self, value):
        self.signals.append(value)
        self.returncode = 0
    def wait(self, timeout): return self.returncode


def test_windows_custom_port_is_shared_by_listener_probe_readiness_and_tunnel(
        tmp_path, monkeypatch, capsys):
    w = make_wizard(tmp_path, runner_port=18771, dashboard_port=18766,
                    remote_runner_port=28771, remote_dashboard_port=28766, ssh_port=2200)
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    setup.save_json(w.config, {"_setup": STATE, "future": "preserved"})
    w.state = setup.read_json(w.config)["_setup"]
    before = w.config.read_bytes()
    runner, transport = Process(), Process(0)
    spawned, probes, reads = [], [], []
    monkeypatch.setattr(setup.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200, raising=False)
    monkeypatch.setattr(setup.signal, "CTRL_BREAK_EVENT", 21, raising=False)
    monkeypatch.setattr(w, "environment", lambda: {setup.TOKEN_ENV: TOKEN})
    monkeypatch.setattr(setup.shutil, "which", lambda _: "ssh")
    monkeypatch.setattr(setup, "require_free", probes.append)
    monkeypatch.setattr(setup, "runner_get", lambda *args: reads.append(args) or {"runner_id": "fixture"})
    monkeypatch.setattr(setup.subprocess, "Popen", lambda argv, **kw:
                        spawned.append((argv, kw)) or [runner, transport][len(spawned) - 1])
    w.start()
    argv = spawned[0][0]
    assert argv[argv.index("--port") + 1] == "18771"
    assert probes == [18771, 18766]
    assert reads == [("/identity", TOKEN, 18771)]
    tunnel = spawned[1][0]
    assert tunnel[tunnel.index("-L") + 1] == "127.0.0.1:18766:127.0.0.1:28766"
    assert tunnel[tunnel.index("-R") + 1] == "127.0.0.1:28771:127.0.0.1:18771"
    assert tunnel[tunnel.index("-p") + 1] == "2200"
    assert setup.TOKEN_ENV not in spawned[1][1]["env"]
    assert runner.signals == [setup.signal.CTRL_BREAK_EVENT]
    assert "http://127.0.0.1:18766" in capsys.readouterr().out
    assert w.config.read_bytes() == before


@pytest.mark.parametrize("windows,expected_port", [(True, 18771), (False, 28771)])
def test_connection_check_uses_local_or_reverse_endpoint_without_rewriting_config(
        tmp_path, monkeypatch, windows, expected_port):
    w = make_wizard(tmp_path, windows=windows, runner_port=18771, remote_runner_port=28771)
    setup.save_json(w.config, {"runner": "windows-http", "url": w.runner_url, "_setup": STATE})
    before = w.config.read_bytes()
    seen = []
    monkeypatch.setattr(w.tokens, "load", lambda: TOKEN)

    def read(path, token, port):
        seen.append((path, token, port))
        return {"runner_id": "fixture", "revision": "frozen"}

    monkeypatch.setattr(setup, "runner_get", read)
    w.check()
    assert seen == [(path, TOKEN, expected_port) for path in ("/identity", "/boards", "/catalog")]
    assert w.config.read_bytes() == before


def test_linux_custom_reverse_url_requires_explicit_saved_configuration(tmp_path, monkeypatch):
    w = make_wizard(tmp_path, windows=False, remote_runner_port=28771)
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    setup.save_json(w.config, {"runner": "windows-http", "url": "http://127.0.0.1:8771"})
    before = w.config.read_bytes()
    monkeypatch.setattr(w, "environment", lambda: {setup.TOKEN_ENV: TOKEN})
    monkeypatch.setattr(w, "linux_start", lambda _: pytest.fail("mismatched URL started services"))
    with pytest.raises(ValueError):
        w.start()
    assert w.config.read_bytes() == before


def test_linux_api_uses_remote_dashboard_target_and_preserves_runner_url(tmp_path, monkeypatch):
    w = make_wizard(tmp_path, windows=False, remote_runner_port=28771, remote_dashboard_port=28766)
    w.python.parent.mkdir(parents=True)
    w.python.touch()
    (w.root / "apps/web/dist").mkdir(parents=True)
    (w.root / "apps/web/dist/index.html").touch()
    setup.save_json(w.config, {"runner": "windows-http", "url": w.runner_url})
    before = w.config.read_bytes()
    api, worker = Process(), Process(17)
    spawned, probes = [], []
    monkeypatch.setattr(w, "environment", lambda: {setup.TOKEN_ENV: TOKEN})
    monkeypatch.setattr(setup, "require_free", probes.append)
    monkeypatch.setattr(setup.subprocess, "Popen", lambda argv, **kw:
                        spawned.append((argv, kw)) or [api, worker][len(spawned) - 1])
    with pytest.raises(RuntimeError, match="17"):
        w.start()
    argv = spawned[0][0]
    assert argv[argv.index("--port") + 1] == "28766"
    assert probes == [28766]
    assert api.signals == [signal.SIGINT]
    assert w.config.read_bytes() == before


def test_linux_flash_configuration_queries_and_saves_custom_reverse_port(tmp_path, monkeypatch):
    w = make_wizard(tmp_path, windows=False, remote_runner_port=28771)
    w.runtime.mkdir(parents=True)
    monkeypatch.setattr(w.tokens, "load", lambda: TOKEN)
    replies = iter(["BSP", "board-flash", "release", "boot", "1"])
    monkeypatch.setattr(flash, "ask", lambda *_args, **_kwargs: next(replies))
    monkeypatch.setattr(flash, "number", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(flash, "yes", lambda label, *_args: label.startswith("이 모듈"))
    calls = []

    def read(route, token, port):
        calls.append((route, token, port))
        if route == "/boards":
            return {"boards": [{"host": "fixture", "board_id": "a", "com": "COM7"}]}
        return {"tests": [{"id": "single.py", "kind": "Single", "after": [], "disabled_reason": ""}]}

    monkeypatch.setattr(flash, "runner_get", read)
    monkeypatch.setattr(w, "preview_save", lambda path, draft: setup.save_json(path, draft))
    flash.linux(w)
    assert calls == [(route, TOKEN, 28771) for route in ("/boards", "/catalog")]
    saved = setup.read_json(w.runtime / "device-test.json")
    assert saved["url"] == "http://127.0.0.1:28771"
    assert saved["modules"]["BSP"]["cases"] == {"boot": ["single.py"]}
