"""Real source export and copy-only execution, with no install/network/board I/O."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def delivery(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'apps/agent-monitor'))
    spec = importlib.util.spec_from_file_location('portable_plugin_delivery_test', ROOT / 'apps/agent-monitor/plugin_delivery.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_entire_plugin_copy_contains_matching_gui_artifact_and_can_reexport_without_original(delivery, tmp_path):
    output = tmp_path / '플러그인 package & copy'
    manifest = delivery.export_plugin(ROOT, output, include_ui=False)
    assert manifest['company_acceptance'] == 'NOT_RUN'
    assert manifest['windows']['kind'] == 'windows-gui-source'
    assert manifest['windows']['path'] == 'agent-monitor'
    assert not any('/.runtime/' in name or '/node_modules/' in name or '/.venv/' in name for name in manifest['files'])
    assert not list(output.glob('*.zip'))
    win_dir = output / 'agent-monitor'
    workflow = 'docs/agents/BOARD_CONNECTOR_PLUGIN_WORKFLOW.md'
    assert f'(agent-monitor/{workflow})' in (output / 'README.md').read_text(encoding='utf-8')
    assert (win_dir / workflow).read_bytes() == (ROOT / workflow).read_bytes()
    for required in delivery.REQUIRED:
        assert (win_dir / required).is_file(), f'missing {required}'
    assert b'backend.gui_test.connector' in (win_dir / 'scripts/board_connector.py').read_bytes()
    assert (win_dir / 'packaging/board-connector-inputs.lock.json').is_file()
    assert (win_dir / 'backend/gui_test/connector/test_status.py').is_file()
    assert '테스트 스크립트' in (win_dir / 'packages/gui-test-ui/src/connector_web/view.mjs').read_text(encoding='utf-8')
    env = dict(os.environ); env.pop('PYTHONPATH', None)
    for args in (['help'], ['verify', str(output)]):
        result = subprocess.run([sys.executable, '-I', str(output / 'plugin.py'), *args], cwd=tmp_path, env=env,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
    # Export from the delivered copy itself, with no original cwd/PYTHONPATH.
    second = tmp_path / 'another-copy'
    result = subprocess.run([sys.executable, '-I', str(output / 'plugin.py'), '--project-root', str(output), 'export', '--output', str(second), '--without-ui'],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert delivery.verify_plugin(second)['release'] == manifest['release']
    first_source = json.loads((win_dir / delivery.MANIFEST).read_text())
    second_source = json.loads((second / 'agent-monitor' / delivery.MANIFEST).read_text())
    assert second_source['source_head'] == first_source['source_head']
    assert second_source['source_dirty'] == first_source['source_dirty']
    # The shared facade and both Windows/Linux entry modules resolve from the
    # copied source under isolated Python, without a checkout on sys.path.
    code = """import sys,tempfile
sys.dont_write_bytecode = True
sys.path.insert(0,sys.argv[1])
from backend.gui_test.standalone.plugin_runtime import PluginSession
from backend.gui_test.connector.bootstrap import bootstrap_profile
from backend.gui_test.connector.preview import MockConnector
from backend.gui_test.connector.test_status import TestStatus
from backend.gui_test.connector.web import preview_app
from fastapi.testclient import TestClient
with tempfile.TemporaryDirectory() as home:
    connector=MockConnector(home)
    connector.connect()
    assert len(connector.status()['test_status']['rows']) == 5
    app=preview_app(connector,'http://127.0.0.1:8774')
    ui=app.state.browser_ui
    with TestClient(app,client=('127.0.0.1',1234),base_url='http://127.0.0.1:8774') as client:
        view=client.get(ui.prefix+'/view.mjs')
        assert view.status_code == 200 and '테스트 스크립트' in view.text
"""
    result = subprocess.run([sys.executable, '-I', '-c', code, str(second / 'agent-monitor')], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    (output / 'agent-monitor/scripts/board_connector.py').write_text('changed')
    with pytest.raises(ValueError, match='integrity'): delivery.verify_plugin(output)


def test_connection_directory_contains_profile_and_first_import_reuse_launcher(delivery, tmp_path):
    source = tmp_path / 'snapshot'
    delivery.export(ROOT, source, include_ui=False)
    profile = {'format': 'gui-test-connector-bootstrap-v1',
               'endpoint': {'server': 'linux.example', 'account': 'tester', 'ssh_port': 22, 'remote_dashboard_port': 8766},
               'identity': {'runtime_id': 'test', 'package_version': '0.1'}}
    output = tmp_path / 'connection-dir'
    receipt = delivery.windows_directory(source, output, profile=profile)
    assert receipt['path'] == str(output)
    assert json.loads((output / 'connector-connection.json').read_text()) == profile
    bat = (output / 'start-board-connector.bat').read_bytes()
    assert b'--bootstrap-profile' in bat
    assert b'--import-profile' not in bat
    assert 'ssh_key' not in (output / 'connector-connection.json').read_text()
    with pytest.raises(ValueError): delivery.windows_directory(source, output)
    with pytest.raises(ValueError): delivery.export_plugin(ROOT, ROOT / 'unsafe-export')


def test_missing_tc_status_module_cannot_be_delivered_as_current_connector(delivery, tmp_path):
    source = tmp_path / 'source'
    manifest = delivery.export(ROOT, source, include_ui=False)
    target = 'backend/gui_test/connector/test_status.py'
    (source / target).unlink()
    manifest['files'].pop(target)
    manifest['release'] = delivery.sha(json.dumps(manifest['files'], sort_keys=True).encode())
    (source / delivery.MANIFEST).write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='closure'):
        delivery.windows_directory(source, tmp_path / 'out-dir')
    assert not (tmp_path / 'out-dir').exists()



@pytest.mark.parametrize('change', ['extra_file', 'missing_entry', 'wrong_windows_release', 'different_entrypoint'])
def test_outer_package_rejects_inventory_and_descriptor_mismatches(delivery, tmp_path, change):
    output = tmp_path / 'package'
    manifest = delivery.export_plugin(ROOT, output, include_ui=False)
    if change == 'extra_file':
        (output / 'unexpected.txt').write_text('extra')
    elif change == 'missing_entry':
        del manifest['files']['plugin.py']
    elif change == 'wrong_windows_release':
        manifest['windows']['release'] = '0' * 64
    else:
        launcher = output / 'plugin.py'
        launcher.write_text('# different launcher')
        manifest['files']['plugin.py'] = delivery.sha(launcher.read_bytes())
    (output / delivery.PACKAGE).write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='package'):
        delivery.verify_plugin(output)



def test_verified_package_can_be_reused_after_regular_python_import(delivery, tmp_path):
    output = tmp_path / 'package'
    delivery.export_plugin(ROOT, output, include_ui=False)
    code = """
import sys
sys.path.insert(0, sys.argv[1])
import backend.gui_test.standalone.server
"""
    subprocess.run([sys.executable, '-I', '-c', code, str(output / 'agent-monitor')],
                   cwd=tmp_path, check=True)
    cache = output / 'agent-monitor/backend/gui_test/standalone/__pycache__'
    assert list(cache.glob('server.cpython-*.pyc'))
    command = [sys.executable, '-I', str(output / 'plugin.py'), 'verify', str(output)]
    subprocess.run(command, cwd=tmp_path, check=True)
    assert subprocess.run(command + ['--pristine'], cwd=tmp_path).returncode == 1
    (cache / 'not_in_manifest.cpython-311.pyc').touch()
    assert subprocess.run(command, cwd=tmp_path).returncode == 1



def test_monitor_passes_first_run_custom_runtime_from_status_to_start(delivery, tmp_path, monkeypatch):
    import manage

    spec = importlib.util.spec_from_file_location('portable_plugin_monitor_test', ROOT / 'apps/agent-monitor/plugin.py')
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)
    source = tmp_path / 'source'
    delivery.export(ROOT, source, include_ui=False)
    home, runtime = tmp_path / 'home', tmp_path / 'outside-runtime'
    release = source / 'AGENT_MONITOR_SOURCE.json'
    release_id = json.loads(release.read_text())['release']
    ready = {'state': 'READY', 'url': 'http://127.0.0.1:18766', 'release': release_id}
    calls = []

    def manager_result(action, target, **options):
        calls.append((action, target, options.get('runtime')))
        if action == 'status':
            if len(calls) == 1:
                result = subprocess.run([sys.executable, '-B', str(source / 'apps/agent-monitor/manage.py'),
                                         'status', '--home', str(target), '--runtime', str(options['runtime'])],
                                        cwd=tmp_path, capture_output=True, text=True, check=True)
                assert json.loads(result.stdout)['state'] == 'STOPPED' and not target.exists()
                return {'state': 'STOPPED'}
            return ready
        assert action == 'start' and options['port'] == 18766
        manage.bind_runtime(target, options['runtime'])
        manage.atomic(target / 'current.json', {'release': release_id, 'path': str(source)})
        return ready

    monkeypatch.setattr(plugin, 'manager_result', manager_result)
    original = plugin.subprocess.run
    monkeypatch.setattr(plugin.subprocess, 'run',
                        lambda argv, **opts: type('Fixture', (), {'returncode': 0})()
                        if '--_dispatch' in argv else original(argv, **opts))
    args = ['--home', str(home), '--runtime', str(runtime), '--port', '18766', 'monitor']
    assert plugin.main(args) == 0
    assert calls == [('status', home, runtime), ('start', home, runtime), ('status', home, runtime)]
    assert manage.runtime_path(home) == runtime
