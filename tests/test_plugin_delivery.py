"""Real source export and copy-only execution, with no install/network/board I/O."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

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
    assert not any('/.runtime/' in name or '/node_modules/' in name or '/.venv/' in name for name in manifest['files'])
    with zipfile.ZipFile(output / delivery.WINDOWS) as archive:
        assert set(delivery.REQUIRED) <= set(archive.namelist())
        assert b'backend.gui_test.connector' in archive.read('scripts/board_connector.py')
        assert 'packaging/board-connector-inputs.lock.json' in archive.namelist()
    env = dict(os.environ); env.pop('PYTHONPATH', None)
    for args in (['help'], ['verify', str(output)]):
        result = subprocess.run([sys.executable, '-I', str(output / 'plugin.py'), *args], cwd=tmp_path, env=env,
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
    # Export from the delivered copy itself, with no original cwd/PYTHONPATH.
    second = tmp_path / 'another-copy'
    result = subprocess.run([sys.executable, '-I', str(output / 'plugin.py'), 'export', '--output', str(second), '--without-ui'],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert delivery.verify_plugin(second)['release'] == manifest['release']
    # The shared facade and both Windows/Linux entry modules resolve from the
    # copied source under isolated Python, without a checkout on sys.path.
    code = 'import sys;sys.path.insert(0,sys.argv[1]);from backend.gui_test.standalone.plugin_runtime import PluginSession;from backend.gui_test.connector.bootstrap import bootstrap_profile'
    result = subprocess.run([sys.executable, '-I', '-c', code, str(second / 'agent-monitor')], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    (output / 'agent-monitor/scripts/board_connector.py').write_text('changed')
    with pytest.raises(ValueError, match='integrity'): delivery.verify_plugin(output)


def test_connection_archive_contains_profile_and_first_import_reuse_launcher(delivery, tmp_path):
    source = tmp_path / 'snapshot'
    delivery.export(ROOT, source, include_ui=False)
    profile = {'format': 'gui-test-connector-bootstrap-v1',
               'endpoint': {'server': 'linux.example', 'account': 'tester', 'ssh_port': 22, 'remote_dashboard_port': 8766},
               'identity': {'runtime_id': 'test', 'package_version': '0.1'}}
    output = tmp_path / 'connection.zip'
    receipt = delivery.windows_archive(source, output, profile=profile)
    assert receipt['sha256'] == delivery.sha(output.read_bytes())
    with zipfile.ZipFile(output) as archive:
        assert json.loads(archive.read('connector-connection.json')) == profile
        assert b'--bootstrap-profile' in archive.read('start-board-connector.bat')
        assert b'--import-profile' not in archive.read('start-board-connector.bat')
        assert 'ssh_key' not in archive.read('connector-connection.json').decode()
    with pytest.raises(ValueError): delivery.windows_archive(source, output)
    with pytest.raises(ValueError): delivery.export_plugin(ROOT, ROOT / 'unsafe-export')
