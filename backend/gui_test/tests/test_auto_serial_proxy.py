"""Unchanged company-style pySerial consumers in real isolated child Python."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest
import serial

from backend.gui_test.connector.multiplexer import Multiplexers, PortMultiplexer
from backend.gui_test.core.models import TestError
from backend.gui_test.tests.test_serial_multiplexer import BOARD, FakePort, wait_for


@pytest.fixture
def endpoint():
    port = FakePort()
    port.echo = True
    mux = PortMultiplexer(BOARD, factory=lambda *_: port)
    mux.start()
    mapping = {'COM7': mux.acquire('automatic-tc')}
    observer = mux.subscribe()
    try:
        yield mux, port, mapping, observer
    finally:
        observer.close()
        mux.close()


def launch(script, runtime, mapping, *, python=sys.executable, extra_env=None):
    original = [str(Path(python).absolute()), str(script.absolute()), '-p', 'COM7']
    command = Multiplexers.command(original, runtime)
    env = dict(os.environ) | Multiplexers.environment(mapping, runtime) | (extra_env or {})
    result = subprocess.run(command, cwd=script.parent, env=env, capture_output=True, timeout=12)
    assert original == [str(Path(python).absolute()), str(script.absolute()), '-p', 'COM7']
    return result


@pytest.mark.parametrize('imports,expression', [
    ('import serial', 'serial.Serial'),
    ('from serial import Serial', 'Serial'),
    ('import serial', 'serial.serial_for_url'),
    pytest.param('from serial.serialposix import Serial', 'Serial', marks=pytest.mark.skipif(os.name == 'nt', reason='POSIX backend')),
    pytest.param('from serial.serialwin32 import Serial', 'Serial', marks=pytest.mark.skipif(os.name != 'nt', reason='Windows backend')),
])
def test_unchanged_common_module_uses_managed_serial(tmp_path, endpoint, imports, expression):
    mux, physical, mapping, observer = endpoint
    (tmp_path / 'common.py').write_text(imports + '\nconnect = ' + expression + '\n')
    script = tmp_path / 'company_tc.py'
    script.write_text("""import os, sys
from common import connect
assert sys.argv[1:] == ['-p', 'COM7']
assert os.getcwd() == os.path.dirname(__file__)
with connect(sys.argv[2], 115200, timeout=1) as port:
    assert port.write(b'unchanged TC\\n') == 13
    assert port.readline() == b'unchanged TC\\n'
print('Test Result: PASS')
""")
    original = script.read_bytes()
    result = launch(script, tmp_path / 'runtime', mapping)
    assert result.returncode == 0, result.stderr
    assert result.stdout == b'Test Result: PASS' + os.linesep.encode('ascii')
    assert script.read_bytes() == original
    assert physical.written == [b'unchanged TC\n']
    assert observer.read() == b'unchanged TC\n'
    wait_for(lambda: mux.control is None)


def test_preserves_pth_pythonpath_and_existing_sitecustomize_after_install(tmp_path, endpoint):
    _, physical, mapping, _ = endpoint
    home = tmp_path / 'python'
    venv.EnvBuilder(with_pip=False).create(home)
    python = home / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    packages = home / ('Lib/site-packages' if os.name == 'nt' else 'lib/python%d.%d/site-packages' % sys.version_info[:2])
    shutil.copytree(Path(serial.__file__).parent, packages / 'serial')
    dependency = tmp_path / 'dependency'
    dependency.mkdir()
    (dependency / 'pth_dependency.py').write_text('VALUE = "pth dependency"\n')
    (packages / 'company.pth').write_text(str(dependency) + '\nimport pth_hook\nimport builtins; builtins.PROXY_PTH_COUNT = getattr(builtins, "PROXY_PTH_COUNT", 0) + 1\n')
    (packages / 'pth_hook.py').write_text('from serial import Serial\nassert Serial.__module__ == "serial_proxy"\n')
    pythonpath = tmp_path / 'company-startup'
    pythonpath.mkdir()
    (pythonpath / 'sitecustomize.py').write_text('from serial import Serial as captured\nMARKER = "existing startup"\n')
    script = tmp_path / 'company_tc.py'
    script.write_text("""import sitecustomize, pth_dependency, pth_hook, builtins
assert builtins.PROXY_PTH_COUNT == 1
assert sitecustomize.MARKER == 'existing startup'
assert pth_dependency.VALUE == 'pth dependency'
assert pth_hook.Serial is sitecustomize.captured
with sitecustomize.captured('COM7', timeout=1) as port:
    port.write(b'startup preserved')
    assert port.read(17) == b'startup preserved'
""")
    result = launch(script, tmp_path / 'runtime', mapping, python=python,
                    extra_env={'PYTHONPATH': str(pythonpath)})
    assert result.returncode == 0, result.stderr
    assert physical.written == [b'startup preserved']


@pytest.mark.parametrize('mapping_value', [{}, {'COM7': {'port': 0, 'lease': 'do-not-print'}}])
def test_invalid_bootstrap_mapping_fails_before_tc_without_secret(tmp_path, mapping_value):
    script = tmp_path / 'tc.py'
    marker = tmp_path / 'tc-ran'
    script.write_text("from pathlib import Path\nPath('tc-ran').write_text('unsafe')\n")
    result = launch(script, tmp_path / 'runtime', mapping_value)
    assert result.returncode == 125
    assert b'BOOTSTRAP_FAILED' in result.stderr
    assert b'do-not-print' not in result.stderr
    assert not marker.exists()


def test_startup_hook_failure_prevents_tc(tmp_path, endpoint):
    _, _, mapping, _ = endpoint
    (tmp_path / 'sitecustomize.py').write_text("raise RuntimeError('startup failed')\n")
    script = tmp_path / 'tc.py'
    script.write_text("from pathlib import Path\nPath('tc-ran').touch()\n")
    result = launch(script, tmp_path / 'runtime', mapping)
    assert result.returncode == 125
    assert not (tmp_path / 'tc-ran').exists()


def test_startup_hook_system_exit_cannot_report_success(tmp_path, endpoint):
    _, _, mapping, _ = endpoint
    (tmp_path / 'sitecustomize.py').write_text('raise SystemExit(0)\n')
    script = tmp_path / 'tc.py'
    script.write_text("from pathlib import Path\nPath('tc-ran').touch()\n")
    result = launch(script, tmp_path / 'runtime', mapping)
    assert result.returncode == 125
    assert not (tmp_path / 'tc-ran').exists()


def test_missing_pyserial_in_external_python_prevents_tc(tmp_path, endpoint):
    _, _, mapping, _ = endpoint
    home = tmp_path / 'empty-python'
    venv.EnvBuilder(with_pip=False).create(home)
    python = home / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    script = tmp_path / 'tc.py'
    script.write_text("from pathlib import Path\nPath('tc-ran').touch()\n")
    result = launch(script, tmp_path / 'runtime', mapping, python=python)
    assert result.returncode == 125
    assert not (tmp_path / 'tc-ran').exists()


def test_system_site_venv_preserves_inherited_pyserial(tmp_path, endpoint):
    _, physical, mapping, _ = endpoint
    home = tmp_path / 'system-site-python'
    venv.EnvBuilder(with_pip=False, system_site_packages=True).create(home)
    python = home / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    userbase = tmp_path / 'inherited-user-packages'
    env = dict(os.environ) | {'PYTHONUSERBASE': str(userbase), 'PYTHONNOUSERSITE': ''}
    # A --system-site-packages venv also inherits enabled user packages. Keep the
    # package outside the venv, without installing into or modifying the machine.
    location = subprocess.run([str(python), '-S', '-c', 'import site; print(site.getusersitepackages())'],
                              env=env, capture_output=True, check=True, text=True)
    packages = Path(location.stdout.strip())
    packages.mkdir(parents=True)
    shutil.copytree(Path(serial.__file__).parent, packages / 'serial')
    normal = subprocess.run([str(python), '-c', 'import serial; print(serial.__file__)'],
                            env=env, capture_output=True, check=True, text=True)
    assert str(userbase) in normal.stdout
    script = tmp_path / 'tc.py'
    script.write_text("""from serial import Serial
with Serial('COM7', timeout=1) as port:
    port.write(b'inherited')
    assert port.read(9) == b'inherited'
""")
    result = launch(script, tmp_path / 'runtime', mapping, python=python,
                    extra_env={'PYTHONUSERBASE': str(userbase), 'PYTHONNOUSERSITE': ''})
    assert result.returncode == 0, result.stderr
    assert physical.written == [b'inherited']


@pytest.mark.parametrize('include_system', [False, True])
def test_venv_prefixes_match_normal_python_in_hooks_and_tc(tmp_path, endpoint, include_system):
    _, physical, mapping, _ = endpoint
    home = tmp_path / 'prefix-python'
    venv.EnvBuilder(with_pip=False, system_site_packages=include_system).create(home)
    python = home / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    packages = home / ('Lib/site-packages' if os.name == 'nt' else 'lib/python%d.%d/site-packages' % sys.version_info[:2])
    shutil.copytree(Path(serial.__file__).parent, packages / 'serial')
    (packages / 'prefix_state.py').write_text("""import site, sys, sysconfig
def snapshot():
    return dict(prefix=sys.prefix, exec_prefix=sys.exec_prefix,
                base_prefix=sys.base_prefix, base_exec_prefix=sys.base_exec_prefix,
                site_prefixes=site.PREFIXES, purelib=sysconfig.get_path('purelib'))
""")
    startup = tmp_path / 'prefix-startup'
    startup.mkdir()
    (startup / 'sitecustomize.py').write_text('from prefix_state import snapshot\nVALUE = snapshot()\n')
    environment = dict(os.environ) | {'PYTHONPATH': str(startup)}
    normal = subprocess.run([str(python), '-c', 'import json, prefix_state; print(json.dumps(prefix_state.snapshot()))'],
                            env=environment, capture_output=True, check=True, text=True)
    expected = json.loads(normal.stdout)
    assert expected['prefix'] == str(home)
    (packages / 'prefix_hook.py').write_text('from prefix_state import snapshot\nVALUE = snapshot()\n')
    (packages / 'prefix.pth').write_text('import prefix_hook\n')
    script = tmp_path / 'tc.py'
    script.write_text("""import prefix_hook, prefix_state, sitecustomize
from serial import Serial
expected = """ + repr(expected) + """
assert {k:v for k,v in prefix_hook.VALUE.items() if k != 'site_prefixes'} == {k:v for k,v in expected.items() if k != 'site_prefixes'}, (prefix_hook.VALUE, expected)
assert sitecustomize.VALUE == expected, (sitecustomize.VALUE, expected)
assert prefix_state.snapshot() == expected, (prefix_state.snapshot(), expected)
with Serial('COM7', timeout=1) as port:
    port.write(b'venv prefixes')
    assert port.read(13) == b'venv prefixes'
""")
    result = launch(script, tmp_path / 'runtime', mapping, python=python,
                    extra_env={'PYTHONPATH': str(startup)})
    assert result.returncode == 0, result.stderr
    assert physical.written == [b'venv prefixes']


def test_unmapped_com_and_url_never_fall_back_to_physical(tmp_path, endpoint):
    _, physical, mapping, _ = endpoint
    script = tmp_path / 'tc.py'
    script.write_text("""import serial
for name in ('COM99', 'socket://127.0.0.1:1', 'loop://'):
    try:
        serial.serial_for_url(name, timeout=.1)
    except serial.SerialException:
        pass
    else:
        raise AssertionError('Unmanaged port opened')
port = serial.serial_for_url('COM7', do_not_open=True)
assert not port.is_open
port.open()
port.close()
""")
    result = launch(script, tmp_path / 'runtime', mapping)
    assert result.returncode == 0, result.stderr
    assert physical.written == []


def test_tc_local_serial_modules_cannot_shadow_trusted_bootstrap(tmp_path, endpoint):
    _, physical, mapping, _ = endpoint
    for name in ('serial.py', 'serial_proxy.py'):
        (tmp_path / name).write_text("raise RuntimeError('TC shadow module executed')\n")
    script = tmp_path / 'tc.py'
    script.write_text("""from serial import Serial
with Serial('COM7', timeout=1) as port:
    port.write(b'trusted')
    assert port.read(7) == b'trusted'
""")
    result = launch(script, tmp_path / 'runtime', mapping)
    assert result.returncode == 0, result.stderr
    assert physical.written == [b'trusted']


def test_managed_helper_integrity_failure_prevents_tc(tmp_path, endpoint):
    _, _, mapping, _ = endpoint
    script = tmp_path / 'tc.py'
    script.write_text("from pathlib import Path\nPath('tc-ran').touch()\n")
    runtime = tmp_path / 'runtime'
    command = Multiplexers.command([sys.executable, str(script)], runtime)
    env = dict(os.environ) | Multiplexers.environment(mapping, runtime)
    folder = Path(command[3]).parent
    (folder / 'serial_proxy.py').write_text("raise RuntimeError('tampered helper')\n")
    result = subprocess.run(command, env=env, cwd=tmp_path, capture_output=True, timeout=8)
    assert result.returncode == 125
    assert not (tmp_path / 'tc-ran').exists()


def test_command_refuses_python_options_and_relative_launch(tmp_path):
    for command in ([sys.executable, '-c', 'pass'], ['python', 'tc.py'], [sys.executable, '-m', 'module']):
        with pytest.raises(TestError):
            Multiplexers.command(command, tmp_path)
