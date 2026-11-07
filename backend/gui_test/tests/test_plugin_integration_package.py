"""T-208: headless source and installed namespace import without a BSP host."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('plugin_packaging', ROOT / 'apps/gui-test/package.py')
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


def test_headless_archive_is_hash_complete_and_imports_from_extracted_tree_without_bsp(tmp_path):
    output = tmp_path / 'plugin-headless.zip'
    result = packaging.build_integration_archive(ROOT, output)
    assert result['mode'] == 'integration'
    extracted = tmp_path / 'extracted'
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert 'backend/gui_test/standalone/integration.py' in names
        assert 'backend/gui_test/standalone/plugin_client.py' in names
        assert 'apps/gui-test/bsp-gui-test.service.example' in names
        assert not any(name.startswith(('backend/worker/', 'backend/domain/', 'backend/services/', 'apps/web/',
                                         'packages/', 'apps/gui-test/static/')) for name in names)
        assert not any('.local-reports' in name or '.local.json' in name or name.endswith('.db') for name in names)
        checksums = json.loads(archive.read('SHA256SUMS.json'))
        assert set(checksums) == names - {'SHA256SUMS.json'}
        for name, checksum in checksums.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum
        manifest = json.loads(archive.read('INTEGRATION.json'))
        assert manifest['include_ui'] is False and manifest['company_acceptance'] == 'NOT_RUN'
        archive.extractall(extracted)
    script = """import sys
from pathlib import Path
import backend.gui_test.standalone.integration as service
from backend.gui_test.core.worker import Worker
assert Path(service.__file__).resolve().is_relative_to(Path.cwd())
assert not any(n.startswith(('backend.worker', 'backend.domain', 'backend.services')) for n in sys.modules)
"""
    result = subprocess.run([sys.executable, '-c', script], cwd=extracted, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_headless_wheel_stage_needs_no_static_ui_and_imports_legacy_namespace(tmp_path):
    stage = packaging.stage_wheel(ROOT, tmp_path / 'wheel-stage', include_ui=False)
    assert (stage / 'gui_test/standalone/integration.py').is_file()
    assert not (stage / 'gui_test/static').exists()
    project = (stage / 'pyproject.toml').read_text(encoding='utf-8')
    assert 'gui-test-integration' in project
    script = """import sys
from pathlib import Path
import gui_test.standalone.integration as service
from gui_test.standalone.plugin_client import PluginClient
assert Path(service.__file__).resolve().is_relative_to(Path.cwd())
assert not any(n.startswith(('backend.worker', 'backend.domain', 'backend.services')) for n in sys.modules)
"""
    result = subprocess.run([sys.executable, '-c', script], cwd=stage, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
