"""Isolated child entry point: install managed pySerial before importing a TC.

Executed by the configured external Python with -I -S. No TC source, PYTHONPATH,
sitecustomize or .pth file runs before installation. This is process-local API
adaptation, not a sandbox against deliberately hostile TC code.
"""
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import runpy
import site
import sys


def dependency_paths():
    """Restore this CPython's venv semantics without executing startup hooks.

    Before 3.14, -S also suppresses venv prefix initialization. Let the selected
    Python's stdlib restore prefixes/PREFIXES/_home and parse pyvenv.cfg, but defer
    .pth processing until after the proxy is installed. This also avoids caching
    sysconfig against base prefixes before company hooks or TC code imports it.
    """
    addsitepackages = site.addsitepackages
    try:
        site.addsitepackages = lambda known_paths, prefixes=None: known_paths
        site.venv(set())
    finally:
        site.addsitepackages = addsitepackages
    paths = list(dict.fromkeys(Path(path) for path in site.getsitepackages()))
    venv_paths = (site.getsitepackages([sys.prefix])
                  if sys.prefix != sys.base_prefix or sys.exec_prefix != sys.base_exec_prefix else [])
    return paths, site.ENABLE_USER_SITE is not False, len(venv_paths)


def install():
    folder = Path(__file__).absolute().parent
    digest = hashlib.sha256()
    for name in ('serial_bootstrap.py', 'serial_proxy.py'):
        digest.update(name.encode() + b'\0' + (folder / name).read_bytes())
    if digest.hexdigest() != folder.name:
        raise RuntimeError('Managed serial support integrity check failed')
    mapping = json.loads(os.environ.get('BOARD_CONNECTOR_SERIAL_MAP', '{}'))
    if not isinstance(mapping, dict) or not mapping:
        raise RuntimeError('Managed serial mapping is missing')
    for com, endpoint in mapping.items():
        if (not isinstance(com, str) or not isinstance(endpoint, dict) or
                type(endpoint.get('port')) is not int or not 1 <= endpoint['port'] <= 65535 or
                not isinstance(endpoint.get('lease'), str) or not endpoint['lease']):
            raise RuntimeError('Managed serial mapping is invalid')
    paths, enable_user, user_index = dependency_paths()
    enable_user = (enable_user and not os.environ.get('PYTHONNOUSERSITE') and
                   (not hasattr(os, 'getuid') or os.getuid() == os.geteuid()) and
                   (not hasattr(os, 'getgid') or os.getgid() == os.getegid()))
    if enable_user:
        paths.insert(user_index, Path(site.getusersitepackages()))
    for path in paths:
        if path.is_dir() and str(path) not in sys.path:
            sys.path.append(str(path))
    import serial
    if not hasattr(serial, 'SerialBase') or not hasattr(serial, 'SerialException'):
        raise RuntimeError('The configured TC Python requires pySerial')
    spec = importlib.util.spec_from_file_location('serial_proxy', folder / 'serial_proxy.py')
    proxy = importlib.util.module_from_spec(spec)
    sys.modules['serial_proxy'] = proxy
    spec.loader.exec_module(proxy)

    def serial_for_url(url, *args, **kwargs):
        do_open = not kwargs.pop('do_not_open', False)
        instance = proxy.Serial(None, *args, **kwargs)
        instance.port = url
        if do_open:
            instance.open()
        return instance

    def patch():
        if sys.modules.get('serial') is not serial:
            raise RuntimeError('Startup hook replaced the managed serial package')
        # Patch platform backend aliases too, including aliases imported by hooks.
        for name, module in tuple(sys.modules.items()):
            if name == 'serial' or name.startswith('serial.serial'):
                for attribute in ('Serial', 'PosixPollSerial', 'VTIMESerial'):
                    if hasattr(module, attribute):
                        setattr(module, attribute, proxy.Serial)
        serial.Serial = proxy.Serial
        serial.serial_for_url = serial_for_url

    patch()
    # Restore ordinary dependency lookup and startup hooks only after installing
    # the proxy. Hook/common-module imports can safely capture Serial aliases.
    script_directory = str(Path(sys.argv[1]).absolute().parent)
    python_paths = [os.path.abspath(value) for value in os.environ.get('PYTHONPATH', '').split(os.pathsep)] if 'PYTHONPATH' in os.environ else []
    sys.path[:0] = [script_directory, *python_paths]
    site.ENABLE_USER_SITE = bool(enable_user)
    for path in paths:
        if path.is_dir():
            site.addsitedir(str(path))
    for name in ('sitecustomize', 'usercustomize') if enable_user else ('sitecustomize',):
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name != name:
                raise
    patch()


def main():
    try:
        if len(sys.argv) < 2 or not Path(sys.argv[1]).is_file():
            raise RuntimeError('Managed TC script is missing')
        install()
    except BaseException:
        # Never print endpoint credentials or execute a TC after partial setup.
        sys.stderr.write('BOARD_CONNECTOR_SERIAL_BOOTSTRAP_FAILED: check TC Python pySerial and managed support files\n')
        return 125
    script = str(Path(sys.argv[1]).absolute())
    sys.argv = [script, *sys.argv[2:]]
    sys.path.insert(0, str(Path(script).parent))
    runpy.run_path(script, run_name='__main__')
    return 0


if __name__ == '__main__':
    sys.exit(main())
