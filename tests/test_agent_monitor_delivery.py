"""Copyable monitor releases retain source closure and exclude installed/runtime data."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_delivery():
    spec = importlib.util.spec_from_file_location('agent_monitor_delivery_tests', ROOT / 'apps/agent-monitor/delivery.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def delivery(): return load_delivery()


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'editable monitor source'
    files = {'backend/api/main.py': '# api', 'backend/worker/main.py': '# worker',
             'scripts/setup_runtime.py': '# setup', 'apps/agent-monitor/manage.py': '# manager',
             'apps/agent-monitor/delivery.py': '# delivery', 'board-connector.cmd': '@echo off',
             'requirements.lock': 'example==1.0', 'run.sh': '#!/bin/sh',
             'apps/web/dist/index.html': '<main>built monitor</main>',
             'apps/gui-test/static/index.html': '<main>built standalone</main>'}
    for name, text in files.items():
        path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
    return root


def test_source_export_is_deterministic_and_copied_source_can_export_again(delivery, source, tmp_path):
    first = delivery.export(source, tmp_path / 'copy one')
    second = delivery.export(source, tmp_path / 'copy two')
    assert first['release'] == second['release'] and first['files'] == second['files']
    assert first['include_ui'] and first['company_acceptance'] == 'NOT_RUN'
    assert first['source_head'] is None
    assert delivery.verify(tmp_path / 'copy one')['release'] == first['release']
    copied = delivery.export(tmp_path / 'copy one', tmp_path / 'copy three')
    assert copied['release'] == first['release'] and copied['files'] == first['files']


def test_corrupt_source_bytes_and_incomplete_dependency_closure_are_rejected(delivery, source, tmp_path):
    delivery.export(source, tmp_path / 'copy')
    (tmp_path / 'copy/backend/api/main.py').write_text('changed')
    with pytest.raises(ValueError, match='integrity'): delivery.verify(tmp_path / 'copy')
    (source / 'scripts/setup_runtime.py').unlink()
    with pytest.raises(ValueError, match='closure'): delivery.export(source, tmp_path / 'incomplete')
    assert not (tmp_path / 'incomplete').exists()


def test_manifest_release_must_equal_hash_of_verified_file_map(delivery, source, tmp_path):
    output = tmp_path / 'copy'; delivery.export(source, output)
    path = output / delivery.MANIFEST
    manifest = json.loads(path.read_text()); manifest['release'] = '9' * 64; path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError): delivery.verify(output)


@pytest.mark.parametrize('name', ['apps/gui-test/runtime/settings.json', 'apps/gui-test/logs/receipt.json',
    'backend/.runtime/source-private.json', 'scripts/.local-reports/diagnostic.json',
    'apps/web/node_modules/vendored.js', 'apps/web/.env.local',
    'apps/gui-test/.build/venv/Lib/site-packages/installed.py'])
def test_runtime_install_and_secret_inputs_are_never_in_source_delivery(delivery, source, tmp_path, name):
    private = source / name; private.parent.mkdir(parents=True, exist_ok=True); private.write_text('private bytes')
    manifest = delivery.export(source, tmp_path / 'copy')
    assert name not in manifest['files'] and not (tmp_path / 'copy' / name).exists()


def test_source_symlink_and_manifest_traversal_are_rejected(delivery, source, tmp_path):
    linked = source / 'backend/private.py'
    try: linked.symlink_to(source / 'backend/api/main.py')
    except OSError: pytest.skip('Symlink creation unavailable to this OS user')
    with pytest.raises(ValueError, match='symlink'): delivery.export(source, tmp_path / 'linked copy')
    linked.unlink()
    output = tmp_path / 'copy'; delivery.export(source, output)
    path = output / delivery.MANIFEST; value = json.loads(path.read_text())
    value['files']['../outside.py'] = '0' * 64; path.write_text(json.dumps(value))
    with pytest.raises(ValueError): delivery.verify(output)


def test_ui_is_prebuilt_by_default_and_without_ui_is_explicit(delivery, source, tmp_path):
    (source / 'apps/web/dist/index.html').unlink()
    with pytest.raises(ValueError, match='UI'): delivery.export(source, tmp_path / 'needs ui')
    value = delivery.export(source, tmp_path / 'headless source', include_ui=False)
    assert value['include_ui'] is False
    assert not any(name.startswith(('apps/web/dist/', 'apps/gui-test/static/')) for name in value['files'])


def test_actual_export_starts_isolated_api_and_imports_connector_without_original_repository(delivery, tmp_path):
    import os
    import socket
    import subprocess
    import sys
    import time
    import urllib.request
    if not (ROOT / 'apps/web/dist/index.html').is_file(): pytest.skip('Build both UIs before copy acceptance')
    copied = tmp_path / 'independent source'
    delivery.export(ROOT, copied)
    delivery.verify(copied)
    environment = {k: v for k, v in os.environ.items() if k not in {'PYTHONPATH', 'PYTHONHOME'}}
    environment.update(AGENT_MONITOR_INSTANCE='copied-test-instance', AGENT_MONITOR_RELEASE='copied-test-release')
    code = ("import pathlib,backend.api.main,backend.gui_test.connector.supervisor; "
            "from backend.gui_test.connector.preview import MockConnector; "
            "a=MockConnector(pathlib.Path('mock')); v=a.shared_settings(); "
            "v['integration']['flash_profile']='copied-source'; "
            "assert a.save_shared_settings({'expected_revision':v['revision'],'integration':v['integration'],'timeouts':v['timeouts']})['integration']['flash_profile']=='copied-source'; "
            "assert pathlib.Path(backend.api.main.__file__).resolve().is_relative_to(pathlib.Path.cwd()); "
            "assert pathlib.Path(backend.gui_test.connector.supervisor.__file__).resolve().is_relative_to(pathlib.Path.cwd()); print('copied imports and mock save OK')")
    result = subprocess.run([sys.executable, '-c', code], cwd=copied, env=environment, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr[-3000:]
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    runtime = tmp_path / 'independent runtime'
    log_path = tmp_path / 'copied-api.log'
    with log_path.open('w') as log:
        process = subprocess.Popen([sys.executable, str(copied / 'scripts/serve_monitor.py'), '--runtime', str(runtime), '--port', str(port)],
                                   cwd=copied, env=environment, stdout=log, stderr=log)
        try:
            health = None
            for _ in range(80):
                assert process.poll() is None, log_path.read_text()[-3000:]
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health', timeout=1) as response:
                        health = json.load(response); break
                except OSError: time.sleep(.1)
            assert health and health['status'] in {'ok', 'degraded'}
            assert not health.get('worker_running', False)
            assert health.get('managed_instance') == 'copied-test-instance'
            assert health.get('managed_release') == 'copied-test-release'
            assert health.get('managed_runtime') == str(runtime)
            request = urllib.request.Request(f'http://127.0.0.1:{port}/api/v1/gui-test/live/integration/settings',
                                             headers={'X-Bsp-Service': 'plugin'})
            with urllib.request.urlopen(request, timeout=5) as response: settings = json.load(response)
            assert len(settings['revision']) == 64 and settings['integration']['installer_path'] == ''
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=5) as response: html = response.read()
            assert b'/assets/' in html
        finally:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
