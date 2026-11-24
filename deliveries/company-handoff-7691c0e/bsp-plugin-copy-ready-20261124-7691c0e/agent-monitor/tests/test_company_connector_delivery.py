"""Company acceptance from the copyable CLI, temporary DBs and loopback fixtures."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
import uvicorn

from backend.gui_test.core.shared_settings_store import SharedSettingsStore
from backend.gui_test.standalone.plugin_commands import execute_direct
from test_direct_connector_unit4 import _start_live_host

ROOT = Path(__file__).resolve().parents[1]


def cli(entry, *args, cwd=None):
    return subprocess.run([sys.executable, '-I', '-B', str(entry), *map(str, args)],
                          cwd=cwd or ROOT, capture_output=True, text=True, timeout=45)


def ok(result):
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    if (ROOT.parent / 'PLUGIN_PACKAGE.json').is_file():
        return ROOT.parent
    target = tmp_path_factory.mktemp('company-package') / 'plugin'
    ok(cli(ROOT / 'apps/agent-monitor/plugin.py', 'export', '--without-ui', '--output', target))
    return target


@pytest.mark.parametrize('operation', ['export', 'windows', 'settings'])
def test_exports_protect_project_and_package_before_creating_paths(package, tmp_path, operation):
    company = tmp_path / 'company'
    company.mkdir()
    tools = tmp_path / 'launcher'
    tools.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(company, target_is_directory=True)
    cmd = {'export': ['export', '--without-ui', '--output'],
           'windows': ['connect', 'export', '--server', 'linux.test', '--account', 'bsp', '--output'],
           'settings': ['settings', 'export', '--file']}[operation]
    def run(destination, *project):
        return cli(package / 'plugin.py', '--home', tmp_path / 'home', '--runtime', tmp_path / 'runtime',
                   *project, *cmd, destination, cwd=tools)
    for dest in (company, alias / 'new' / 'result', tools / '..' / 'company' / 'new' / 'result',
                 package / 'forbidden-out', package / 'agent-monitor' / 'forbidden-out'):
        result = run(dest, '--project', 'company-id', '--project-root', company)
        assert result.returncode == 1 and 'outside the project' in result.stderr
    assert not (company / 'new').exists()
    assert not (package / 'forbidden-out').exists()
    assert run(company / 'forbidden', '--project', company).returncode == 1
    assert run(tools / 'forbidden', '--project', 'logical-key').returncode == 1
    subprocess.run(['git', 'init', '-q', tmp_path], check=True)
    assert run(company / 'forbidden', '--project', 'logical-key').returncode == 1
    if operation == 'settings':
        existing = company / 'original'
        existing.write_text('original bytes')
        target = tools / 'exchange'
        os.link(existing, target)
        result = ok(run(target, '--project-root', company))
        assert result['exported'] and existing.read_text() == 'original bytes'
        assert json.loads(target.read_text())['expected_revision']


def test_explicit_flash_and_no_clobber_prepared_file(tmp_path):
    counts = []
    def prepare(**options):
        counts.append(options)
        return {'project': options['project'], 'build': options['build'], 'runner_id': 'mock',
                'body': {'execution_mode': 'flash_and_test' if options['installer'] else 'tc_only'}}
    fake = SimpleNamespace(prepare_run=prepare,
                           store=SimpleNamespace(read=lambda: {'integration': {'installer_path': '/image.bat', 'flash_profile': 'bench'}}),
                           send_prepared_run=lambda value: {'run_id': 'fixed'})
    def execute(*args):
        execute_direct(fake, ['test', *map(str, args)], project='alpha', emit=lambda _: None)
    for op in ('preview', 'run', 'prepare', 'send'):
        for selected in ('--installer', '--flash-profile'):
            with pytest.raises(ValueError, match='explicit --flash'):
                execute(op, selected, 'value')
        with pytest.raises(SystemExit) as exc:
            execute(op, '--flas')
        assert exc.value.code == 2
    assert not counts
    path = tmp_path / 'request.json'
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        writes = [pool.submit(execute, 'prepare', '--build', build, '--file', path, '--flash') for build in ('B1', 'B2')]
    assert sum(result.exception() is None for result in writes) == 1
    first = path.read_bytes()
    with pytest.raises(ValueError, match='existing'):
        execute('prepare', '--build', 'another', '--file', path)
    with pytest.raises(ValueError, match='--flash'):
        execute('send', '--file', path)
    assert path.read_bytes() == first
    execute('send', '--file', path, '--flash')
    assert json.loads(path.read_bytes())['run_id'] == 'fixed'


def test_copied_cli_prepares_replays_and_observes_mock_board(package, tmp_path):
    host, port, server, thread = _start_live_host(tmp_path)
    try:
        home = tmp_path / 'home'
        runtime = tmp_path / 'linux'
        tc_root = tmp_path / 'suite'
        tc_root.mkdir()
        shutil.copyfile(package / 'agent-monitor/examples/connector-runs/mock_smoke.py', tc_root / 'mock_smoke.py')
        store = SharedSettingsStore(runtime)
        settings = store.read()
        store.save({'expected_revision': settings['revision'], 'integration': settings['integration'] |
                    {'tc_root': str(tc_root), 'source_roots': [str(tmp_path)]},
                    'timeouts': {k: v for k, v in settings['timeouts'].items() if k != 'revision'}})
        store.save_command_profile('default', {
            'single': ['python', '{tc_path}', '--com', '{com_a}'],
            'dual': ['python', '{tc_path}', '--a', '{com_a}', '--b', '{com_b}'],
        })
        def run(*args):
            return cli(package / 'plugin.py', '--project', 'company', '--project-root', tc_root,
                       '--home', home, '--runtime', runtime, '--connector-port', port, *args)
        path = tmp_path / 'prepared.json'
        report = ok(run('test', 'prepare', '--file', path, '--build', 'mock-build-7'))
        assert report['runner_id'] == host.identity
        assert not ok(run('test', 'runs'))['runs']
        value = json.loads(path.read_bytes())
        assert value['body']['execution_mode'] == 'tc_only' and value['build'] == 'mock-build-7'
        assert run('test', 'send', '--file', path, '--flash').returncode == 1
        assert not ok(run('test', 'runs'))['runs']
        first = ok(run('test', 'send', '--file', path))
        seen = ok(run('test', 'status', first['run_id'], '--json'))
        assert seen['type'] == 'run' and seen['run_id'] == first['run_id']
        status = run('test', 'watch', first['run_id'], '--json')
        assert status.returncode == 0, status.stderr
        assert json.loads(status.stdout.splitlines()[-1])['state'] == 'passed'
        second = ok(run('test', 'send', '--file', path))
        assert first['run_id'] == second['run_id'] == json.loads(path.read_bytes())['run_id']
        assert len(ok(run('test', 'runs'))['runs']) == 1
        assert not (home / 'service.json').exists()
    finally:
        server.should_exit = True
        thread.join(5)
        host.close()


def test_copied_module_cli_against_full_monitor(package, tmp_path):
    from backend.api.main import create_app
    app = create_app(tmp_path / 'monitor-runtime')
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning', access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    home = tmp_path / 'cli-home'
    try:
        deadline = time.monotonic() + 8
        while not server.started and time.monotonic() < deadline:
            time.sleep(.02)
        health = httpx.get(f'http://127.0.0.1:{port}/api/v1/health', trust_env=False).json()
        def modules(*args, runtime_id=health['runtime_id']):
            return cli(package / 'plugin.py', '--home', home, '--monitor-port', port, 'modules', *args,
                       '--runtime-id', runtime_id, '--package-version', health['package_version'])
        assert ok(modules('list')) == {'version': 0, 'modules': []}
        file = package / 'agent-monitor/examples/connector-runs/modules.json'
        published = ok(modules('publish', '--file', file, '--expected-version', '0'))
        assert published['version'] == 1 and published['modules'] == json.loads(file.read_bytes())
        empty = tmp_path / 'empty.json'
        empty.write_text('[]')
        conflict = modules('publish', '--file', empty, '--expected-version', 0)
        assert conflict.returncode == 1 and '409' in conflict.stderr and 'modules list' in conflict.stderr
        assert modules('publish', '--file', empty, '--expected-version', 1, runtime_id='wrong').returncode == 1
        assert modules('publish', '--file', tmp_path / 'missing', '--expected-version', 1).returncode == 1
        assert ok(modules('list')) == published
        assert ok(modules('publish', '--file', empty, '--expected-version', 1)) == {'version': 2, 'modules': []}
        assert cli(package / 'plugin.py', '--home', home, 'modules', 'list').returncode == 1
        assert not (home / 'service.json').exists()
    finally:
        server.should_exit = True
        thread.join(5)
        sock.close()


def test_release_evidence_matches_independent_pin_and_rejects_mutation(package, tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'apps/agent-monitor'))
    from delivery import MANIFEST, sha
    from plugin_delivery import export_plugin

    entry = package / 'plugin.py'
    source = tmp_path / 'previous-source'
    shutil.copytree(package / 'agent-monitor', source)
    previous_manifest = json.loads((source / MANIFEST).read_bytes())
    files = previous_manifest['files']
    # Stage a prior snapshot representing one added, one removed and one edited path.
    added = 'examples/connector-runs/modules.json'
    removed = 'examples/connector-runs/prior.json'
    edited = 'examples/connector-runs/mock_smoke.py'
    (source / added).unlink()
    del files[added]
    for path, data in ((removed, b'[]'), (edited, b'# previous fixture\n')):
        (source / path).write_bytes(data)
        files[path] = sha(data)
    previous_manifest['release'] = sha(json.dumps(files, sort_keys=True).encode())
    (source / MANIFEST).write_text(json.dumps(previous_manifest))
    prior = tmp_path / 'prior'
    export_plugin(source, prior, include_ui=previous_manifest['include_ui'])
    evidence = tmp_path / 'evidence'
    written = ok(cli(entry, 'release-evidence', prior, package, '--output', evidence))
    anchor = written['sha256']
    assert hashlib.sha256((evidence / 'RELEASE_EVIDENCE.json').read_bytes()).hexdigest() == anchor
    data = json.loads((evidence / 'RELEASE_EVIDENCE.json').read_bytes())
    assert data['prior']['release'] == previous_manifest['release']
    delta = evidence / 'MANIFEST_DELTA.tsv'
    rows = [line.split('\t') for line in delta.read_text().splitlines()]
    assert rows[0] == ['path', 'prior_sha256', 'current_sha256']
    assert rows[1:] == sorted(rows[1:])
    changes = {name: (before, after) for name, before, after in rows[1:]}
    assert changes['agent-monitor/' + added][0] == '-' and changes['agent-monitor/' + removed][1] == '-'
    assert all(value != '-' for value in changes['agent-monitor/' + edited])
    def verify(pin):
        return cli(entry, 'verify-evidence', prior, package, evidence, '--sha256', pin)
    assert ok(verify(anchor))['state'] == 'VERIFIED'
    assert verify('0' * 64).returncode == 1
    original = delta.read_bytes()
    delta.write_bytes(original + b'damage\n')
    assert verify(anchor).returncode == 1
    delta.write_bytes(original)
    (prior / 'agent-monitor' / edited).unlink()
    assert verify(anchor).returncode == 1


def test_instruction_free_package_cli_contract_and_signed_release(package, tmp_path):
    from backend.gui_test.standalone.plugin_parser import command_parser, module_parser
    source_has_instructions = (package / 'agent-monitor/AGENTS.md').is_file()
    assert source_has_instructions == (ROOT / 'AGENTS.md').is_file()
    current = tmp_path / 'company'
    entry = package / 'plugin.py'
    ok(cli(entry, 'export', '--output', current, '--without-ui', '--without-agent-instructions'))
    ok(cli(entry, 'verify', current, '--pristine'))
    tracked = json.loads((current / 'PLUGIN_PACKAGE.json').read_text())['files']
    assert not any(Path(name).name.lower() in {'agents.md', 'claude.md'} or '/.claude/agents/' in name for name in tracked)
    assert (package / 'agent-monitor/AGENTS.md').is_file() == source_has_instructions
    contract = json.loads((current / 'agent-monitor/contracts/plugin-cli-v1.json').read_text())
    assert contract['commands']['connect --watch --read-only']['effects'] == ['read', 'network']
    assert 'hardware' in contract['commands']['test send']['effects'] and '6' in contract['exit_codes']
    for prefix, parser in [('', command_parser(direct=True)), ('modules ', module_parser())]:
        for name, sub in parser._subparsers._group_actions[0].choices.items():
            assert set(sub._option_string_actions) == set(contract['options'][prefix + name])
    evidence = tmp_path / 'receipts'
    ok(cli(entry, 'release-evidence', package, current, '--output', evidence))
    notes = evidence / 'BEHAVIOR_CHANGES.json'
    changes = json.loads(notes.read_bytes())
    assert changes['current_release'] == json.loads((current / 'PLUGIN_PACKAGE.json').read_bytes())['release']
    assert changes['prior_release'] == json.loads((package / 'PLUGIN_PACKAGE.json').read_bytes())['release']
    key = tmp_path / 'test-only-key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    allowed = tmp_path / 'allowed_signers'
    allowed.write_text('release-fixture ' + key.with_suffix('.pub').read_text())
    receipt = evidence / 'RELEASE_EVIDENCE.json'
    subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', str(key), '-n', 'bsp-plugin-release-v1', str(receipt)], check=True)
    verify = [sys.executable, '-IB', str(ROOT / 'scripts/verify_signed_plugin.py'), str(package), str(current), str(evidence),
              '--allowed-signers', str(allowed), '--signature', str(receipt) + '.sig', '--identity']
    assert json.loads(subprocess.check_output([*verify, 'release-fixture']))['state'] == 'VERIFIED'
    assert subprocess.run([*verify, 'wrong-signer'], capture_output=True).returncode != 0
    notes.write_text('{}')
    assert subprocess.run([*verify, 'release-fixture'], capture_output=True).returncode != 0
    receipt.write_bytes(receipt.read_bytes() + b' ')
    assert subprocess.run([*verify, 'release-fixture'], capture_output=True).returncode != 0
