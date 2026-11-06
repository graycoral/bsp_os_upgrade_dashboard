"""RQ-59: noninteractive setup uses local fixtures, never SSH or device I/O."""
import io
import json
import builtins
from http.client import BadStatusLine, IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from backend.gui_test.catalog_settings import CatalogSettings
from scripts import setup_runtime as setup


TOKEN = 'fixture-private-token-' + 'a' * 48
PORTS = {'runner_port': 18771, 'dashboard_port': 18766,
         'remote_runner_port': 28771, 'remote_dashboard_port': 28766, 'ssh_port': 2200}
RESPONSES = {'/identity': {'runner_id': 'fixture-runner'}, '/boards': {'boards': []},
             '/catalog': {'revision': 'fixture-revision', 'tests': []}}


def snapshot(root):
    """Reads may update access times; compare bytes, names, modes and modification times."""
    if not root.exists(): return {}
    result = {}
    for path in [root, *root.rglob('*')]:
        info = path.stat()
        result[str(path.relative_to(root))] = (info.st_mode, info.st_mtime_ns,
                                              path.read_bytes() if path.is_file() else None)
    return result


@pytest.fixture
def cli(tmp_path, monkeypatch):
    root, home = tmp_path / 'repo', tmp_path / 'private home'
    root.mkdir()
    actual = setup.Wizard
    made = []
    monkeypatch.setattr(setup, 'ROOT', root)
    def create(**kwargs):
        wizard = actual(root=root, windows=True, **kwargs)
        made.append(wizard)
        return wizard
    monkeypatch.setattr(setup, 'Wizard', create)
    return root, home, made


def profile(home, ports=PORTS):
    path = home / 'setup-ports.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'version': 1, 'ports': ports}), encoding='utf-8')
    return path


def fake_http(monkeypatch, values=None, error=None, before=None):
    calls = []
    class Response:
        def __init__(self, value): self.value = value
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, _limit): return json.dumps(self.value).encode('utf-8')
    class Opener:
        def open(self, request, timeout):
            endpoint = '/' + request.full_url.rsplit('/', 1)[-1]
            calls.append((endpoint, request.full_url, timeout, request.get_header('Authorization')))
            if before: before(endpoint, timeout)
            if error: raise error
            return Response((RESPONSES if values is None else values)[endpoint])
    monkeypatch.setattr(setup, 'build_opener', lambda *_: Opener())
    return calls


@pytest.mark.parametrize('command,method', [(None, 'menu'), ('menu', 'menu'), ('run', 'start')])
def test_commands_dispatch_only_the_selected_action(cli, monkeypatch, command, method):
    _, home, _ = cli
    selected = []
    # Patch the real class retained by the factory, so construction remains exercised.
    # The factory's class is reached through a harmless first construction.
    wizard = setup.Wizard(home=home)
    cls = type(wizard)
    for name in ('menu', 'start', 'install', 'check'):
        monkeypatch.setattr(cls, name, lambda self, _name=name: selected.append(_name))
    assert setup.main(([command] if command else []) + ['--home', str(home)]) == 0
    assert selected == [method]
    assert not home.exists()


@pytest.mark.parametrize('args', [
    ['run', '--save'], ['doctor', '--save'], ['menu', '--save'], ['ports', '--only', 'catalog'],
    ['run', '--only', 'identity'], ['doctor', '--only', 'unknown'], ['unknown-command'],
])
def test_invalid_command_combinations_exit_two_before_constructing_wizard(cli, monkeypatch, args):
    _, home, _ = cli
    monkeypatch.setattr(setup, 'Wizard', lambda **_: pytest.fail('invalid arguments reached local configuration'))
    with pytest.raises(SystemExit) as error:
        setup.main([*args, '--home', str(home)])
    assert error.value.code == 2
    assert not home.exists()


def test_profile_precedence_and_explicit_save_leave_runner_config_untouched(cli, capsys):
    root, home, made = cli
    path = profile(home)
    config = home / 'windows-runner.json'
    config.write_text(json.dumps({'_setup': {'ssh_port': 2222}, 'future': {'keep': True}}))
    before = snapshot(home)
    assert setup.main(['ports', '--home', str(home), '--port', '19771']) == 0
    current = made[-1]
    assert (current.runner_port, current.dashboard_port, current.remote_runner_port,
            current.remote_dashboard_port, current.ssh_port) == (19771, 18766, 28771, 28766, 2200)
    output = capsys.readouterr().out
    for value in ('19771', '18766', str(path), 'CLI', 'profile'):
        assert value.lower() in output.lower()
    assert snapshot(home) == before
    assert setup.main(['ports', '--save', '--home', str(home), '--port', '19771']) == 0
    assert json.loads(path.read_text()) == {'version': 1, 'ports': {**PORTS, 'runner_port': 19771}}
    assert config.read_bytes() == before['windows-runner.json'][2]
    assert not (root / '.runtime').exists()


@pytest.mark.parametrize('windows', [True, False])
def test_profile_is_platform_local_and_constructor_overrides_do_not_persist(tmp_path, windows):
    root, home = tmp_path / 'repo', tmp_path / 'home'
    root.mkdir()
    path = (home if windows else root / '.runtime') / 'setup-ports.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'version': 1, 'ports': PORTS}))
    before = snapshot(tmp_path)
    wizard = setup.Wizard(root=root, windows=windows, home=home, runner_port=19771)
    assert wizard.runner_port == 19771
    assert wizard.remote_runner_port == PORTS['remote_runner_port']
    assert wizard.ssh_port == 2200
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize('bad', [
    {'version': True, 'ports': PORTS}, {'version': 2, 'ports': PORTS}, {'ports': PORTS},
    {'version': 1, 'ports': {**PORTS, 'future': 9}}, {'version': 1, 'ports': PORTS, 'future': 9},
    *({'version': 1, 'ports': {**PORTS, 'runner_port': value}} for value in (True, 0, 65536, '18771', 18771.0)),
    {'version': 1, 'ports': {**PORTS, 'dashboard_port': 18771}},
    {'version': 1, 'ports': {**PORTS, 'remote_dashboard_port': 28771}},
])
def test_invalid_profile_fails_closed_without_fallback_or_mutation(cli, monkeypatch, bad):
    _, home, _ = cli
    path = profile(home)
    path.write_text(json.dumps(bad))
    before = snapshot(home)
    monkeypatch.setattr(setup, 'build_opener', lambda *_: pytest.fail('invalid profile reached network'))
    assert setup.main(['ports', '--home', str(home)]) == 1
    assert snapshot(home) == before


def test_failed_port_profile_replace_preserves_previous_version(cli, monkeypatch):
    _, home, _ = cli
    path = profile(home)
    before = path.read_bytes()
    def fail(*_): raise OSError('private-disk-error-do-not-echo')
    monkeypatch.setattr(setup.os, 'replace', fail)
    assert setup.main(['ports', '--save', '--home', str(home), '--port', '19771']) == 1
    assert path.read_bytes() == before
    assert list(home.iterdir()) == [path]


@pytest.mark.parametrize('only,endpoints', [(None, ['/identity', '/boards', '/catalog']),
    ('identity', ['/identity']), ('boards', ['/boards']), ('catalog', ['/catalog'])])
def test_doctor_reads_only_selected_endpoints_with_stage_progress_and_no_writes(cli, monkeypatch, capsys, only, endpoints):
    _, home, _ = cli
    profile(home)
    (home / 'windows-runner.json').write_text(json.dumps({'source_root': 'private-TC-path'}))
    (home / 'runs.db').write_bytes(b'fixture database sentinel')
    before = snapshot(home)
    loads = []
    def load(self, *, readonly=False):
        loads.append(readonly)
        return TOKEN
    monkeypatch.setattr(setup.TokenStore, 'load', load)
    def unexpected(*_, **__): pytest.fail('selected diagnostic read unrelated catalog settings')
    if only in ('identity', 'boards'):
        monkeypatch.setattr(CatalogSettings, 'read', unexpected)
    else:
        CatalogSettings(home / 'runtime' / 'gui-test-settings.json').save(173)
        before = snapshot(home)
    progress = []
    print_calls = []
    def record_print(*args, **kwargs):
        print_calls.append((' '.join(map(str, args)), kwargs.get('flush', False)))
        builtins.print(*args, **kwargs)
    monkeypatch.setattr(setup, 'print', record_print, raising=False)
    def stage(endpoint, timeout):
        progress.append(capsys.readouterr().out)
        assert print_calls[-1][1] is True
        assert 'stage=' + endpoint.lstrip('/') in print_calls[-1][0]
        assert '18771' in progress[-1]
        assert str(timeout) in progress[-1]
    calls = fake_http(monkeypatch, before=stage)
    args = ['doctor', '--home', str(home)] + (['--only', only] if only else [])
    assert setup.main(args) == 0
    assert [call[0] for call in calls] == endpoints
    assert [call[2] for call in calls] == [173 if endpoint == '/catalog' else 5 for endpoint in endpoints]
    assert all(call[3] == 'Bearer ' + TOKEN for call in calls)
    assert loads == [True]
    output = ''.join(progress) + capsys.readouterr().out
    assert TOKEN not in output and 'private-TC-path' not in output
    assert snapshot(home) == before


@pytest.mark.parametrize('error', [
    TimeoutError('private-timeout-detail'), URLError(TimeoutError('private-timeout-detail')),
    URLError(ConnectionRefusedError('private-connect-detail')),
    HTTPError('http://private-host/private-TC-path', 401, TOKEN, {}, io.BytesIO(TOKEN.encode())),
    HTTPError('http://private-host/private-TC-path', 403, TOKEN, {}, io.BytesIO(TOKEN.encode())),
    HTTPError('http://private-host/private-TC-path', 503, TOKEN, {}, io.BytesIO(TOKEN.encode())),
])
def test_doctor_failures_are_controlled_sanitized_and_readonly(cli, monkeypatch, capsys, error):
    _, home, _ = cli
    profile(home)
    (home / 'windows-runner.json').write_text('{}')
    before = snapshot(home)
    monkeypatch.setattr(setup.TokenStore, 'load', lambda self, *, readonly=False: TOKEN)
    calls = fake_http(monkeypatch, error=error)
    assert setup.main(['doctor', '--only', 'identity', '--home', str(home)]) == 1
    assert len(calls) == 1
    output = capsys.readouterr()
    text = output.out + output.err
    for private in (TOKEN, 'private-host', 'private-TC-path', 'private-timeout-detail', 'private-connect-detail', 'Traceback'):
        assert private not in text
    category = ('AUTH' if isinstance(error, HTTPError) and error.code in (401, 403) else
                'RESPONSE' if isinstance(error, HTTPError) else
                'TIMEOUT' if isinstance(error, TimeoutError) or isinstance(getattr(error, 'reason', None), TimeoutError)
                else 'CONNECT')
    assert 'result=' + category in text
    assert 'elapsed_seconds=' in text
    if isinstance(error, HTTPError):
        assert str(error.code) in text
    assert snapshot(home) == before


@pytest.mark.parametrize('endpoint,payload', [('identity', {}), ('identity', {'runner_id': 7}),
    ('boards', {'boards': {}}), ('catalog', {'revision': 7, 'tests': []}),
    ('catalog', {'revision': 'valid', 'tests': {}})])
def test_doctor_rejects_malformed_endpoint_responses(cli, monkeypatch, capsys, endpoint, payload):
    _, home, _ = cli
    home.mkdir()
    (home / 'windows-runner.json').write_text('{}')
    before = snapshot(home)
    monkeypatch.setattr(setup.TokenStore, 'load', lambda self, *, readonly=False: TOKEN)
    fake_http(monkeypatch, values={'/' + endpoint: payload})
    assert setup.main(['doctor', '--only', endpoint, '--home', str(home)]) == 1
    assert TOKEN not in capsys.readouterr().out
    assert snapshot(home) == before


def test_doctor_missing_token_never_creates_private_directory(cli, monkeypatch, capsys):
    _, home, _ = cli
    monkeypatch.setattr(setup, 'build_opener', lambda *_: pytest.fail('missing token reached HTTP'))
    assert setup.main(['doctor', '--only', 'identity', '--home', str(home)]) == 1
    assert not home.exists()
    assert 'Traceback' not in capsys.readouterr().err


@pytest.mark.parametrize('override,expected', [(None, 100), ('37', 37)])
def test_doctor_catalog_default_and_cli_override_do_not_save_preferences(cli, monkeypatch, override, expected):
    _, home, _ = cli
    home.mkdir()
    (home / 'windows-runner.json').write_text('{}')
    before = snapshot(home)
    monkeypatch.setattr(setup.TokenStore, 'load', lambda self, *, readonly=False: TOKEN)
    calls = fake_http(monkeypatch)
    args = ['doctor', '--only', 'catalog', '--home', str(home)]
    if override is not None: args += ['--catalog-timeout', override]
    assert setup.main(args) == 0
    assert [(call[0], call[2]) for call in calls] == [('/catalog', expected)]
    assert snapshot(home) == before


@pytest.mark.parametrize('boundary', ['open', 'read'])
def test_doctor_malformed_http_transport_is_sanitized_response_failure(cli, monkeypatch, capsys, boundary):
    _, home, _ = cli
    home.mkdir()
    (home / 'windows-runner.json').write_text('{}')
    before = snapshot(home)
    monkeypatch.setattr(setup.TokenStore, 'load', lambda self, *, readonly=False: TOKEN)
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, _limit):
            raise IncompleteRead(('private-HTTP-body-' + TOKEN).encode(), 999)
    class Opener:
        def open(self, _request, timeout):
            if boundary == 'open':
                raise BadStatusLine('private-HTTP-status-' + TOKEN)
            return Response()
    monkeypatch.setattr(setup, 'build_opener', lambda *_: Opener())
    assert setup.main(['doctor', '--only', 'identity', '--home', str(home)]) == 1
    output = capsys.readouterr()
    text = output.out + output.err
    assert 'result=RESPONSE' in text
    for secret in (TOKEN, 'private-HTTP', 'Traceback', 'IncompleteRead', 'BadStatusLine'):
        assert secret not in text
    assert snapshot(home) == before


def test_linux_ports_save_warns_about_existing_runner_url_without_rewriting_it(cli, monkeypatch, capsys):
    root, home, _ = cli
    cls = type(setup.Wizard(home=home))
    monkeypatch.setattr(setup, 'Wizard', lambda **kwargs: cls(root=root, windows=False, **kwargs))
    runtime = root / '.runtime'
    runtime.mkdir()
    config = runtime / 'gui-test.json'
    config.write_text(json.dumps({'runner': 'windows-http', 'url': 'http://127.0.0.1:8771', 'future': 42}))
    original, original_mtime = config.read_bytes(), config.stat().st_mtime_ns
    assert setup.main(['ports', '--save', '--remote-runner-port', '28771', '--home', str(home)]) == 0
    assert json.loads((runtime / 'setup-ports.json').read_text())['ports']['remote_runner_port'] == 28771
    assert config.read_bytes() == original and config.stat().st_mtime_ns == original_mtime
    output = capsys.readouterr().out
    assert '메뉴1' in output or 'menu 1' in output.lower()
    assert 'URL' in output and '28771' in output


def test_run_missing_setup_returns_sanitized_failure_without_install_or_process(cli, monkeypatch, capsys):
    _, home, _ = cli
    monkeypatch.setattr(setup.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('unconfigured run launched a process'))
    monkeypatch.setattr(setup.subprocess, 'run', lambda *_a, **_k: pytest.fail('unconfigured run invoked installer'))
    assert setup.main(['run', '--home', str(home)]) == 1
    text = capsys.readouterr()
    assert 'CONFIG' in text.out
    assert 'Traceback' not in text.err
    assert not home.exists()


def test_linux_doctor_rejects_url_mismatch_before_token_or_network(cli, monkeypatch, capsys):
    root, home, _ = cli
    cls = type(setup.Wizard(home=home))
    monkeypatch.setattr(setup, 'Wizard', lambda **kwargs: cls(root=root, windows=False, **kwargs))
    runtime = root / '.runtime'
    runtime.mkdir()
    (runtime / 'gui-test.json').write_text(json.dumps({'runner': 'windows-http', 'url': 'http://127.0.0.1:8771'}))
    before = snapshot(root)
    monkeypatch.setattr(setup.TokenStore, 'load', lambda *_a, **_k: pytest.fail('invalid local URL read token'))
    monkeypatch.setattr(setup, 'build_opener', lambda *_: pytest.fail('invalid local URL contacted HTTP'))
    assert setup.main(['doctor', '--only', 'identity', '--remote-runner-port', '28771', '--home', str(home)]) == 1
    assert 'result=CONFIG' in capsys.readouterr().out
    assert snapshot(root) == before
    assert not home.exists()


@pytest.mark.parametrize('windows', [True, False])
def test_token_readonly_load_never_prepares_or_changes_local_files(tmp_path, monkeypatch, windows):
    home = tmp_path / 'private'
    token = setup.TokenStore(home, windows)
    def forbidden(*_a, **_k): pytest.fail('readonly token load prepared private directory')
    monkeypatch.setattr(token, 'prepare', forbidden)
    with pytest.raises(ValueError):
        token.load(readonly=True)
    assert not home.exists()
    home.mkdir()
    token.path.write_bytes(TOKEN.encode('ascii'))
    if windows:
        monkeypatch.setattr(setup, 'dpapi', lambda data, decrypt=False: data)
    else:
        import os
        if not hasattr(os, 'getuid'):
            pytest.skip('Linux ownership check requires Linux')
        home.chmod(0o700)
        token.path.chmod(0o600)
    before = snapshot(home)
    assert token.load(readonly=True) == TOKEN
    assert snapshot(home) == before


@pytest.mark.parametrize('raw', ['{', '[]', 'null',
    '{"version":1,"version":1,"ports":{}}',
    '{"version":1,"ports":{"runner_port":8771,"runner_port":18771}}'])
def test_malformed_or_duplicate_profile_is_never_silently_defaulted(cli, raw):
    _, home, _ = cli
    path = profile(home)
    path.write_text(raw)
    before = snapshot(home)
    assert setup.main(['ports', '--home', str(home)]) == 1
    assert snapshot(home) == before


@pytest.mark.skipif(__import__('os').name == 'nt', reason='Bash thin wrappers run on Linux')
@pytest.mark.parametrize('action', ['run', 'doctor'])
def test_thin_shell_launcher_forwards_action_arguments_and_exit_from_foreign_cwd(tmp_path, action):
    import os
    import subprocess
    scripts = tmp_path / 'project with spaces' / 'scripts'
    scripts.mkdir(parents=True)
    repository = Path(__file__).resolve().parents[1]
    (scripts / (action + '.sh')).write_bytes((repository / 'scripts' / (action + '.sh')).read_bytes())
    (scripts / 'setup.sh').write_text('printf \'%s\\n\' "$@" > "$CAPTURE"\nexit 7\n')
    capture = tmp_path / 'captured arguments'
    result = subprocess.run(['bash', str(scripts / (action + '.sh')), '--home', 'two words', '--port', '19771'],
                            cwd=tmp_path, env={**os.environ, 'CAPTURE': str(capture)},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 7
    assert capture.read_text().splitlines() == [action, '--home', 'two words', '--port', '19771']


@pytest.mark.parametrize('stage,category,port,exit_code', [
    ('port', 'PORT_UNAVAILABLE', 19771, None),
    ('ssh', 'CONFIG', 2200, None),
    ('ssh', 'PROCESS_EXIT', 2200, 7),
    ('runner', 'CONNECT', 19771, None),
    ('runner', 'TIMEOUT', 19771, None),
    ('runner', 'PROCESS_EXIT', 19771, 9),
])
def test_run_failure_output_uses_typed_category_and_never_raw_exception(
        cli, monkeypatch, capsys, stage, category, port, exit_code):
    _, home, _ = cli
    cls = type(setup.Wizard(home=home))
    private = 'private-run-error-' + TOKEN
    def fail(self):
        if stage == 'port':
            raise setup.PortUnavailableError(port) from OSError(private)
        raise setup.RunFailure(stage, category, private, port=port, exit_code=exit_code) from OSError(private)
    monkeypatch.setattr(cls, 'start', fail)
    assert setup.main(['run', '--home', str(home)]) == 1
    output = capsys.readouterr()
    text = output.out + output.err
    assert f'action=run stage={stage} result={category} port={port}' in text
    if exit_code is not None:
        assert f'exit_code={exit_code}' in text
    for secret in (private, TOKEN, 'Traceback', 'OSError'):
        assert secret not in text
    if stage == 'runner':
        assert 'setup-runner.log' in text
    assert not home.exists()
