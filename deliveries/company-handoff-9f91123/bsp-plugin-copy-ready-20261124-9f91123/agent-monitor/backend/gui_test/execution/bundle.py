"""Small frozen-runtime boundary shared by setup and contained children.

Keep this module standard-library-only: the contained child must wait for its
parent's Job Object before importing or executing any external TC code.
"""
from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys


def is_frozen():
    return bool(getattr(sys, 'frozen', False))


def editable_root():
    """Recognize the distribution only when interpreter, marker and source agree."""
    if is_frozen():
        return None
    executable = Path(sys.executable).resolve()
    candidate = executable.parent.parent
    source = Path(__file__).resolve()
    source_candidate = source.parents[4] if len(source.parents) > 4 else None
    roots = [candidate]
    if source_candidate is not None and source_candidate not in roots:
        roots.append(source_candidate)
    for root in roots:
        marker = root / 'bundle.json'
        if not marker.exists():
            continue
        try:
            value = json.loads(marker.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as exc:
            raise ValueError('Invalid editable Runner marker') from exc
        expected = {'version': 1, 'mode': 'editable', 'python': 'runtime/python.exe',
                    'source': 'src', 'dependencies': 'deps', 'python_version': '3.12.10',
                    'platform': 'win_amd64'}
        if (not isinstance(value, dict) or value != expected or type(value.get('version')) is not int or
                executable != (root / 'runtime/python.exe').resolve() or
                source != (root / 'src/backend/gui_test/execution/bundle.py').resolve()):
            raise ValueError('Editable Runner marker does not match this interpreter and source')
        return root
    return None


def runtime_mode():
    return 'frozen' if is_frozen() else 'editable' if editable_root() is not None else 'source'


def bundle_roots():
    if not is_frozen():
        root = editable_root()
        return (root,) if root is not None else ()
    roots = [Path(sys.executable).resolve().parent]
    internal = getattr(sys, '_MEIPASS', None)
    if internal:
        root = Path(internal).resolve()
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def validate_external_python(value):
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise ValueError('Configure an external TC Python executable (not the portable Runner).')
    try:
        requested = Path(value).expanduser()
        if not requested.is_absolute():
            raise ValueError('TC Python must be an absolute path.')
        path = requested.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError('TC Python must be an existing external executable file.') from exc
    if not path.is_file() or path.samefile(sys.executable) or any(
            path.is_relative_to(root) for root in bundle_roots()):
        raise ValueError('TC Python must be outside the portable Runner bundle and cannot be the Runner itself.')
    return str(path)


def external_environment(env=None):
    """Remove runner credentials and bootloader state without losing TC overlays."""
    result = {}
    roots = bundle_roots()
    for key, value in (os.environ if env is None else env).items():
        upper = key.upper()
        if (upper in {'GUI_TEST_RUNNER_TOKEN', 'GUI_TEST_CONNECTOR_REGISTRATION_TOKEN', 'GUI_TEST_INTEGRATION_TOKEN'} or upper.startswith('_PYI_') or
                upper.startswith(('GUI_TEST_BUNDLE_', 'BSP_RUNNER_', 'BSP_EDITABLE_'))):
            continue
        if upper in {'PATH', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONUSERBASE'} and roots:
            parts = []
            for part in value.split(os.pathsep):
                try:
                    bundled = any(Path(part.strip('"')).resolve().is_relative_to(root) for root in roots) if part else False
                except (OSError, RuntimeError, ValueError):
                    bundled = False
                if not bundled:
                    parts.append(part)
            value = os.pathsep.join(parts)
            if not value and upper != 'PATH':
                continue
        result[key] = value
    return result


@contextmanager
def external_dll_search():
    """Temporarily undo PyInstaller's DLL directory for an external executable.

    Used only in a contained child or the single-threaded setup SSH spawn;
    never change the multithreaded Runner parent's process-wide DLL state.
    """
    if not is_frozen() or os.name != 'nt':
        yield
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDllDirectoryW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    kernel.GetDllDirectoryW.restype = wintypes.DWORD
    kernel.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    kernel.SetDllDirectoryW.restype = wintypes.BOOL
    size = kernel.GetDllDirectoryW(0, None)
    buffer = ctypes.create_unicode_buffer(size + 1)
    if size and not kernel.GetDllDirectoryW(len(buffer), buffer):
        raise OSError('Cannot read the current DLL search directory')
    previous = buffer.value if size else None
    if not kernel.SetDllDirectoryW(None):
        raise OSError('Cannot reset the external executable DLL search directory')
    try:
        yield
    finally:
        if not kernel.SetDllDirectoryW(previous):
            raise OSError('Cannot restore the Runner DLL search directory')


def contained_child(argv):
    if not argv:
        return 2
    if sys.stdin.buffer.read(1) != b'!':
        return 125
    with external_dll_search():
        return subprocess.call(list(argv), shell=False, stdin=subprocess.DEVNULL,
                               env=external_environment())
