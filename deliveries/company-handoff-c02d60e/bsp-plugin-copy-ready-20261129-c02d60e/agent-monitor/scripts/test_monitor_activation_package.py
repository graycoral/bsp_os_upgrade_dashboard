"""T-323/T-324 smoke using a copied full plugin, disposable runtimes and loopback only."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import sysconfig
import tempfile
import time
import urllib.error
import urllib.request
import venv


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def execute(argv, *, cwd, env, expected=0):
    args = list(map(str, argv))
    print(f'+ {args}', flush=True)
    try:
        result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as exc:
        print(f'timeout\nstdout:\n{exc.stdout!r}\nstderr:\n{exc.stderr!r}', flush=True)
        raise
    print(f'exit {result.returncode}\nstdout:\n{result.stdout}stderr:\n{result.stderr}', flush=True)
    assert result.returncode == expected, args
    return result


def dependency_fixture(release):
    # Create a local interpreter prefix without pip and reuse installed pinned imports.
    path = release / '.venv'
    venv.EnvBuilder(with_pip=False, symlinks=True).create(path)
    sites = {sysconfig.get_path(kind) for kind in ('purelib', 'platlib')}
    site = Path(sysconfig.get_path('purelib', 'venv', vars={'base': str(path), 'platbase': str(path)}))
    (site / 'monitor-test-dependencies.pth').write_text('\n'.join(sorted(sites)) + '\n', encoding='utf-8')
    return path / 'bin/python'


def prepare_managed_fixture(source, home, runtime, release_id):
    release = home / 'releases' / release_id
    shutil.copytree(source, release)
    prepared_python = dependency_fixture(release)
    (home / 'current.json').write_text(json.dumps({'release': release_id, 'path': str(release)}))
    (home / 'runtime-location.json').write_text(json.dumps({'path': str(runtime)}))
    return release, prepared_python


def stop_monitor(source, home, runtime, release, prepared_python, status, *, project, env):
    receipt_path = home / 'service.json'
    if not receipt_path.is_file():
        return
    receipt = read_json(receipt_path)
    assert receipt['runtime'] == str(runtime) and receipt['path'] == str(release), receipt
    manager = source / 'apps/agent-monitor/manage.py'
    execute([prepared_python, '-B', manager, 'stop', '--home', home], cwd=project, env=env)
    deadline = time.monotonic() + 20
    stop_result = home / 'stop-result.json'
    while time.monotonic() < deadline:
        if stop_result.is_file():
            stopped = read_json(stop_result)
            assert stopped['instance'] == receipt['instance'] and stopped['state'] == 'STOPPED', stopped
            if not receipt_path.exists():
                break
        time.sleep(0.1)
    else:
        raise RuntimeError(f'Temporary Monitor did not confirm graceful stop: {home}')
    assert status()['state'] == 'STOPPED'
    with socket.socket() as check:
        check.settimeout(1)
        assert check.connect_ex(('127.0.0.1', receipt['port'])) != 0


def smoke_shared(work, plugin, source, release_id, command, *, project, env):
    home, runtime = work / 'shared-home', work / 'shared-runtime'
    release, prepared_python = prepare_managed_fixture(source, home, runtime, release_id)
    monitor_id = 'package-fixture-monitor'
    credential = work / 'issued-monitor-key.json'
    token = secrets.token_urlsafe(36)
    fd = os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump({'schema_version': 1, 'monitor_id': monitor_id, 'token': token,
                   'runner_id': 'c' * 32, 'protected_listener': True}, stream)

    with socket.socket() as runner, socket.socket() as listener:
        # Reserve the isolated fixture endpoint throughout the test. No Host is required for activation.
        runner.bind(('127.0.0.1', 0))
        runner_port = runner.getsockname()[1]
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.close()
        url = f'http://127.0.0.1:{port}'
        opts = ['--home', home, '--runtime', runtime, '--connector-port', runner_port, '--monitor-port', port]
        activation = ['monitor', 'ensure', '--no-provision', '--sharing-monitor-id']

        def status():
            return json.loads(command(plugin, *opts, 'monitor', 'status').stdout)

        try:
            result = command(plugin, *opts, *activation, monitor_id, '--sharing-monitor-key-file', credential,
                             '--trust-protected-loopback')
            assert token not in result.stdout + result.stderr
            receipt_path = home / 'service.json'
            receipt = read_json(receipt_path)
            initial = json.loads(result.stdout)
            assert initial['state'] == 'READY' and initial['reused'] is False
            assert initial['mode'] == 'shared-task-monitor' and initial['monitor_id'] == monitor_id
            assert initial['url'] == url and initial['release'] == release_id
            assert 'worker' not in receipt['children']
            assert (home / 'sharing-monitor-key.json').stat().st_mode & 0o077 == 0

            reused = command(plugin, *opts, *activation, monitor_id)
            assert json.loads(reused.stdout) == initial | {'reused': True}
            assert read_json(receipt_path) == receipt
            wrong = command(plugin, *opts, *activation, 'different-monitor', expected=1)
            assert json.loads(wrong.stderr)['code'] == 'MONITOR_MODE_MISMATCH'
            assert read_json(receipt_path) == receipt
            current = status()
            assert current['state'] == 'READY' and current['deployment']['state'] == 'MATCHED'
            assert current['health']['managed_instance'] == receipt['instance']

            challenge = secrets.token_hex(32)
            proof = hmac.digest(token.encode('ascii'), f'bsp-monitor-v1:{monitor_id}:{challenge}'.encode('ascii'), 'sha256').hex()
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            health = urllib.request.Request(url + '/api/v1/health', headers={'X-Bsp-Monitor-Challenge': challenge})
            with opener.open(health, timeout=5) as response:
                assert json.load(response) == {'status': 'ok', 'mode': 'shared-task-monitor', 'monitor_id': monitor_id,
                                               'monitor_proof': proof}
            with opener.open(url + '/plugin-task/', timeout=5) as response:
                assert response.read() == (release / 'backend/api/shared_monitor_assets/index.html').read_bytes()
            for route in ('/api/v1/jobs', '/api/v1/gui-test/live/runs'):
                try:
                    with opener.open(url + route, timeout=5):
                        raise AssertionError(f'Shared Monitor exposed the full API: {route}')
                except urllib.error.HTTPError as exc:
                    assert exc.code in {403, 404}, route
            assert not (home / 'install.log').exists()
            print('Shared copied Monitor matched its cryptographic identity, reused its process and denied full APIs.', flush=True)
        finally:
            stop_monitor(source, home, runtime, release, prepared_python, status, project=project, env=env)


def smoke(work, package):
    project, user_home = work / 'project', work / 'user-home'
    project.mkdir()
    user_home.mkdir()
    env = {'HOME': str(user_home), 'PATH': os.defpath, 'TMPDIR': str(work),
           'PYTHONDONTWRITEBYTECODE': '1', 'PIP_NO_INDEX': '1', 'PIP_CONFIG_FILE': os.devnull}

    def command(entry, *args, expected=0):
        return execute([sys.executable, '-IB', entry, *args], cwd=project, env=env, expected=expected)

    origin = ROOT / 'apps/agent-monitor/plugin.py'
    if package is None:
        package = work / 'exported'
        selection = command(origin, 'export', '--output', package)
    else:
        selection = command(origin, 'verify', package, '--pristine')
    release_id = json.loads(selection.stdout)['release']
    copied = work / 'copied-plugin'
    shutil.copytree(package, copied, symlinks=True)
    plugin = copied / 'plugin.py'
    assert json.loads(command(plugin, 'verify', copied, '--pristine').stdout)['release'] == release_id
    source = copied / 'agent-monitor'
    assert read_json(source / 'AGENT_MONITOR_SOURCE.json')['include_ui'] is True

    empty = work / 'empty-home'
    refused = command(plugin, '--home', empty, 'monitor', 'ensure', '--no-provision', expected=6)
    assert not refused.stdout and json.loads(refused.stderr)['code'] == 'NOT_PROVISIONED'
    for name in ('current.json', 'runtime-location.json', 'service.json', 'install.log', 'releases'):
        assert not (empty / name).exists(), name

    contract = source / 'contracts/plugin-cli-v1.json'
    has_sharing = contract.is_file() and 'task create' in read_json(contract).get('commands', {})
    home, runtime = work / 'managed-home', work / 'runtime'
    release, prepared_python = prepare_managed_fixture(source, home, runtime, release_id)

    with socket.socket() as runner, socket.socket() as listener:
        # Hold this unused port so the Monitor background probe never reaches another runner.
        runner.bind(('127.0.0.1', 0))
        runner_port = runner.getsockname()[1]
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.close()
        execute([prepared_python, '-B', '-c',
                 'import sys; from backend.gui_test.core.shared_settings_store import SharedSettingsStore; '
                 'SharedSettingsStore(sys.argv[1]).save_preferences({"preferred_connector_port": int(sys.argv[2])})',
                 runtime, runner_port], cwd=release, env=env)
        url = f'http://127.0.0.1:{port}'
        opts = ['--home', home, '--runtime', runtime]
        receipt_path = home / 'service.json'

        def ensure():
            return json.loads(command(plugin, *opts, '--monitor-port', port,
                                      'monitor', 'ensure', '--no-provision').stdout)

        def status():
            return json.loads(command(plugin, *opts, 'monitor', 'status').stdout)

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                concurrent = [pool.submit(ensure) for _ in range(2)]
                responses = [future.result() for future in concurrent]
            assert sorted(item['reused'] for item in responses) == [False, True]
            live = status()
            receipt = read_json(receipt_path)
            instance = receipt['instance']
            assert live['state'] == 'READY' and live['deployment']['state'] == 'MATCHED'
            assert live['health']['worker_running'] is True
            assert live['health']['managed_instance'] == instance
            assert live['health']['managed_source'] == str(release)
            responses.append(ensure())
            assert responses[-1]['reused'] is True and read_json(receipt_path) == receipt
            for item in responses:
                assert item == {'state': 'READY', 'home': str(home), 'runtime': str(runtime),
                                'release': release_id, 'port': port, 'url': url, 'reused': item['reused']}

            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            dist = release / 'apps/web/dist'
            assets = [('/', dist / 'index.html')]
            assets += [(f'/assets/{path.name}', path) for path in sorted((dist / 'assets').iterdir()) if path.is_file()]
            for route, path in assets:
                with opener.open(url + route, timeout=5) as response:
                    assert response.read() == path.read_bytes(), route
            print(f'GET bundled UI and assets matched ({len(assets)} files)', flush=True)
            for route in ('/api/v1/jobs', '/api/v1/gui-test/live/runs'):
                with opener.open(url + route, timeout=5) as response:
                    assert json.load(response) == [], route

            windows = work / 'windows-export'
            command(plugin, *opts, '--monitor-port', port, '--connector-port', runner_port,
                    'connect', 'export', '--output', windows, '--server', 'linux.example', '--account', 'fixture')
            bootstrap = read_json(windows / 'connector-connection.json')['endpoint']
            assert bootstrap['remote_dashboard_port'] == port and bootstrap['remote_runner_port'] == runner_port
            assert (windows / 'start-board-connector.bat').is_file()
            if has_sharing:
                assert (windows / 'scripts/manage_connector_sharing.py').is_file()
            assert not (home / 'install.log').exists()
            assert list((home / 'releases').iterdir()) == [release]
            command(plugin, 'verify', copied, '--pristine')
        finally:
            stop_monitor(source, home, runtime, release, prepared_python, status, project=project, env=env)

    if has_sharing:
        smoke_shared(work, plugin, source, release_id, command, project=project, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', type=Path)
    parser.add_argument('--package', type=Path, help='Verify a previously exported full plugin package')
    args = parser.parse_args()
    reports = args.reports.resolve()
    package = args.package.expanduser().absolute() if args.package is not None else None
    work = Path(tempfile.mkdtemp(prefix='monitor-activation-')).resolve()
    print(f'Temporary package smoke: {work}', flush=True)

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        smoke(work, package)
    finally:
        homes = [(work / 'managed-home', 'package'), (work / 'shared-home', 'package-shared')]
        for home, prefix in homes:
            for log in home.glob('*.log'):
                shutil.copy2(log, reports / f'{prefix}-{log.name}')
        if any((home / 'service.json').exists() for home, _ in homes):
            print(f'Temporary Monitor receipt preserved for diagnosis: {work}', flush=True)
        else:
            shutil.rmtree(work)


if __name__ == '__main__':
    main()
