"""Build and repack the editable Windows Runner using verified offline inputs.

Only the build phase uses pip. Repack is standard-library-only and never calls
the network, pip, a TC, or an external service.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen
import uuid
import zipfile

MARKER = {'version': 1, 'mode': 'editable', 'python': 'runtime/python.exe',
          'source': 'src', 'dependencies': 'deps', 'python_version': '3.12.10',
          'platform': 'win_amd64'}
PTH = 'python312.zip\n.\n../deps\n../src\n'
SCRIPT_NAMES = ('setup_runtime.py', 'setup_ports.py', 'setup_flashing.py', 'build_editable_runner.py')
DATA_FILES = ('apps/gui-test/requirements.lock', 'apps/gui-test/config/windows-runner.example.json')
SOURCE_LOCK = 'packaging/editable-windows-runner-inputs.lock.json'
HEX = re.compile(r'[0-9a-f]{64}')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON field: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique)


def _write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _name(value):
    return re.sub(r'[-_.]+', '-', value).lower()


def _relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError(f'Unsafe relative path: {value!r}')
    path = PurePosixPath(value)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *('COM' + str(i) for i in range(10)),
                *('LPT' + str(i) for i in range(10))}
    if path.is_absolute() or any(p in ('', '.', '..') or p.endswith((' ', '.')) or
                               p.split('.')[0].upper() in reserved or
                               any(c in p for c in '<>"|?*\x00') for p in value.split('/')):
        raise ValueError(f'Unsafe relative path: {value!r}')
    return path


def _artifact(value):
    if not isinstance(value, dict):
        raise ValueError('Artifact must be an object')
    name = value.get('filename')
    if not isinstance(name, str) or len(_relative(name).parts) != 1:
        raise ValueError('Artifact filename must be a basename')
    url = urlsplit(value.get('url', ''))
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
        raise ValueError(f'Artifact needs a public HTTPS URL: {name}')
    if not isinstance(value.get('sha256'), str) or not HEX.fullmatch(value['sha256']):
        raise ValueError(f'Invalid SHA256: {name}')
    if type(value.get('size')) is not int or value['size'] <= 0:
        raise ValueError(f'Invalid artifact size: {name}')


def load_input_lock(path) -> dict:
    """Validate the fixed platform and artifact manifest (no network)."""
    value = _json(path)
    if (not isinstance(value, dict) or type(value.get('version')) is not int or
            value.get('version') != 1 or value.get('python_version') != '3.12.10' or
            value.get('platform') != 'win_amd64' or
            not isinstance(value.get('requirements_sha256'), str) or
            not HEX.fullmatch(value['requirements_sha256'])):
        raise ValueError('Unsupported input lock; expected v1 CPython 3.12.10 win_amd64')
    for key in ('runtime', 'pip'):
        _artifact(value.get(key))
    if (value['runtime']['filename'] != 'python-3.12.10-embed-amd64.zip' or
            value['runtime']['sha256'] != '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3' or
            value['pip']['filename'] != 'pip-25.0.1-py3-none-any.whl' or
            value['pip']['sha256'] != 'c46efd13b6aa8279f33f2864459c8ce587ea6a1a59ee20de055868d8f7688f7f'):
        raise ValueError('Runtime/pip identity differs from the approved inputs')
    wheels = value.get('wheels')
    if not isinstance(wheels, list) or not wheels:
        raise ValueError('Input lock needs exact wheels')
    names, filenames = set(), set()
    for wheel in wheels:
        _artifact(wheel)
        if (not isinstance(wheel.get('name'), str) or not wheel['name'] or
                not isinstance(wheel.get('version'), str) or not wheel['version'] or
                not isinstance(wheel.get('tags'), list) or not wheel['tags'] or
                not any(_compatible(tag) for tag in wheel['tags']) or
                not wheel['filename'].endswith('.whl')):
            raise ValueError(f'Invalid wheel identity/tags: {wheel.get("filename")}')
        name = _name(wheel['name'])
        if name in names or wheel['filename'].casefold() in filenames:
            raise ValueError(f'Duplicate wheel: {wheel["filename"]}')
        names.add(name)
        filenames.add(wheel['filename'].casefold())
    return value


def _compatible(tag):
    if not isinstance(tag, str) or len(tag.split('-')) != 3:
        return False
    interpreter, abi, platform = tag.split('-')
    return ((platform == 'any' and abi == 'none' and interpreter in {'py3', 'py312'}) or
            (platform == 'win_amd64' and interpreter == 'cp312' and abi in {'cp312', 'abi3', 'none'}) or
            (platform == 'win_amd64' and interpreter.startswith('cp3') and
             interpreter[2:].isdigit() and 32 <= int(interpreter[2:]) <= 312 and abi == 'abi3'))


def _archive_members(archive):
    seen = set()
    for member in archive.infolist():
        name = member.filename.rstrip('/') if member.is_dir() else member.filename
        _relative(name)
        if name.casefold() in seen:
            raise ValueError(f'Duplicate/case-colliding ZIP member: {name}')
        seen.add(name.casefold())
        mode = member.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
            raise ValueError(f'ZIP links/special files are forbidden: {name}')
        if member.flag_bits & 1:
            raise ValueError(f'Encrypted ZIP member: {name}')
        yield member


def _verify_bytes(path, artifact):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Missing/linked input: {path}; prepare a complete verified cache')
    if path.stat().st_size != artifact['size'] or digest(path) != artifact['sha256']:
        raise ValueError(f'Input size/SHA256 mismatch: {path}; replace it from the fixed HTTPS URL')


def _wheel(path, artifact, *, pip=False):
    with zipfile.ZipFile(path) as archive:
        members = [m.filename for m in _archive_members(archive) if not m.is_dir()]
        metadata = [n for n in members if n.count('/') == 1 and n.endswith('.dist-info/METADATA')]
        wheelfile = [n for n in members if n.count('/') == 1 and n.endswith('.dist-info/WHEEL')]
        if len(metadata) != 1 or len(wheelfile) != 1 or metadata[0].rsplit('/', 1)[0] != wheelfile[0].rsplit('/', 1)[0]:
            raise ValueError(f'Invalid wheel metadata: {path.name}')
        data = BytesParser().parsebytes(archive.read(metadata[0]))
        expected_name, expected_version = ('pip', '25.0.1') if pip else (artifact['name'], artifact['version'])
        tags = [line[5:].strip() for line in archive.read(wheelfile[0]).decode('utf-8').splitlines() if line.startswith('Tag: ')]
        if (_name(data.get('Name', '')) != _name(expected_name) or data.get('Version') != expected_version or
                not tags or not any(_compatible(t) for t in tags) or
                (not pip and sorted(tags) != sorted(artifact['tags']))):
            raise ValueError(f'Wheel name/version/ABI mismatch: {path.name}')


def _runtime(path):
    with zipfile.ZipFile(path) as archive:
        members = {m.filename for m in _archive_members(archive) if not m.is_dir()}
        if not {'python.exe', 'python312.dll', 'python312.zip', 'python312._pth', 'LICENSE.txt'} <= members:
            raise ValueError('Incomplete embedded Python runtime')
        blob = archive.read('python.exe')
        if len(blob) < 64 or blob[:2] != b'MZ':
            raise ValueError('Python runtime is not a Windows PE executable')
        offset = struct.unpack_from('<I', blob, 60)[0]
        if blob[offset:offset + 6] != b'PE\x00\x00d\x86':
            raise ValueError('Python runtime is not Windows AMD64')


def verify_cache(cache, manifest) -> dict:
    """Read-only verification. Return exact artifact filename -> validated Path."""
    cache = Path(cache)
    if cache.is_symlink() or getattr(cache, 'is_junction', lambda: False)():
        raise ValueError('Linked cache roots are forbidden')
    cache = cache.resolve()
    if _json(cache / 'inputs.lock.json') != manifest:
        raise ValueError('Cache inputs.lock.json differs from the repository input lock')
    result = {}
    for directory, artifacts in (('runtime', [manifest['runtime']]), ('bootstrap', [manifest['pip']]),
                                 ('wheels', manifest['wheels'])):
        folder = cache / directory
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError(f'Missing/linked cache directory: {folder}')
        expected = {a['filename'] for a in artifacts}
        if {p.name for p in folder.iterdir()} != expected:
            raise ValueError(f'Unexpected/missing input files in {folder}; expected the fixed artifact set')
        for artifact in artifacts:
            path = folder / artifact['filename']
            _verify_bytes(path, artifact)
            if directory == 'runtime':
                _runtime(path)
            else:
                _wheel(path, artifact, pip=directory == 'bootstrap')
            result[artifact['filename']] = path
    return result


@contextmanager
def _lock(path, *, byte=0):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() < byte + 1:
            stream.write(b'\0' * (byte + 1 - stream.tell()))
            stream.flush()
        stream.seek(byte)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f'Build/output is already locked: {path}') from exc
        try:
            yield
        finally:
            stream.seek(byte)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _prepare(cache, manifest, *, offline):
    lock = cache / 'inputs.lock.json'
    if lock.exists():
        if _json(lock) != manifest:
            raise ValueError('Cache manifest mismatch; use a separate cache for these inputs')
    elif offline:
        raise ValueError(f'Offline cache manifest missing: {lock}')
    else:
        _write_json(lock, manifest)
    for directory, artifacts in (('runtime', [manifest['runtime']]), ('bootstrap', [manifest['pip']]),
                                 ('wheels', manifest['wheels'])):
        folder = cache / directory
        if folder.is_symlink():
            raise ValueError(f'Linked cache directory: {folder}')
        if not offline:
            folder.mkdir(exist_ok=True)
        for artifact in artifacts:
            target = folder / artifact['filename']
            if target.exists():
                _verify_bytes(target, artifact)
                continue
            if offline:
                raise ValueError(f'Offline input missing: {target}; network fallback is disabled')
            pending = folder / (artifact['filename'] + '.' + uuid.uuid4().hex + '.download')
            try:
                with urlopen(artifact['url'], timeout=60) as response, pending.open('xb') as stream:
                    if urlsplit(response.url).scheme != 'https':
                        raise ValueError('Artifact redirect must remain HTTPS')
                    shutil.copyfileobj(response, stream)
                _verify_bytes(pending, artifact)
                os.replace(pending, target)
            finally:
                pending.unlink(missing_ok=True)


def _requirements(path, manifest):
    text = path.read_text(encoding='utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != manifest['requirements_sha256']:
        raise ValueError('requirements.lock canonical UTF-8/LF SHA256 mismatch')
    pins = {}
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)', line)
        if not match or _name(match[1]) in pins:
            raise ValueError('requirements.lock requires unique exact name==version pins')
        pins[_name(match[1])] = match[2]
    if pins != {_name(w['name']): w['version'] for w in manifest['wheels']}:
        raise ValueError('Input wheels do not match the exact requirements pin set')


def _files(root):
    """All regular files, rejecting symlinks/junctions and Windows collisions."""
    result, seen = {}, set()
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in [*dirs, *files]:
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            _relative(relative)
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ValueError(f'Linked bundle/source entry: {relative}')
            if relative.casefold() in seen:
                raise ValueError(f'Case-colliding bundle/source entry: {relative}')
            seen.add(relative.casefold())
        for name in files:
            path = Path(folder) / name
            if not path.is_file():
                raise ValueError(f'Nonregular bundle/source entry: {path}')
            result[path.relative_to(root).as_posix()] = path
    return result


def _source_files(root):
    result = {'backend/__init__.py': root / 'backend/__init__.py'}
    package = root / 'backend/gui_test'
    for name, path in _files(package).items():
        if path.suffix == '.py' and not any(p.startswith('.') or p in {'tests', '__pycache__'} for p in Path(name).parts):
            if name != 'demo/browser_e2e.py':
                result['backend/gui_test/' + name] = path
    for name in SCRIPT_NAMES:
        result['scripts/' + name] = root / 'scripts' / name
    for name in DATA_FILES:
        result[name] = root / name
    for name, path in result.items():
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Missing/linked allowlisted source: {name}')
    return result


def _launcher(module, action=''):
    return ('@echo off\r\nsetlocal\r\n"%~dp0runtime\\python.exe" -B -X utf8 -m ' + module +
            (' ' + action if action else '') + ' %*\r\nexit /b %errorlevel%\r\n').encode('ascii')


def _provenance(root, paths, logs):
    revision, dirty = None, None
    try:
        with (logs / 'git.stderr.log').open('wb') as error:
            rev = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, stdout=subprocess.PIPE, stderr=error, check=False)
            status = subprocess.run(['git', 'status', '--porcelain=v1', '--untracked-files=all', '--', *paths],
                                    cwd=root, stdout=subprocess.PIPE, stderr=error, check=False)
        if rev.returncode == status.returncode == 0 and re.fullmatch(rb'[0-9a-f]{40}\s*', rev.stdout):
            revision, dirty = rev.stdout.decode('ascii').strip(), bool(status.stdout.strip())
    except OSError:
        pass
    return revision, dirty


def _run(command, logs, name, *, env=None):
    with (logs / (name + '.stdout.log')).open('wb') as out, (logs / (name + '.stderr.log')).open('wb') as err:
        result = subprocess.run(command, stdout=out, stderr=err, env=env, check=False)
    if result.returncode:
        raise RuntimeError(f'{name} failed (exit {result.returncode}); see {logs / (name + ".stderr.log")}')


def _logs(root):
    path = root / '.local-reports' / ('editable-runner-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8])
    path.mkdir(parents=True, exist_ok=False)
    return path


@contextmanager
def _stage(logs, prefix):
    """Delete only our newly allocated, resolved direct child of this log dir."""
    base = logs.resolve(strict=True)
    temporary = Path(tempfile.mkdtemp(prefix=prefix, dir=base))
    if temporary.resolve(strict=True).parent != base:
        raise ValueError('Staging directory escaped its designated log directory')
    try:
        yield temporary
    finally:
        if temporary.exists():
            if (temporary.is_symlink() or getattr(temporary, 'is_junction', lambda: False)() or
                    temporary.resolve(strict=True).parent != base):
                raise ValueError('Refusing recursive cleanup outside the designated staging directory')
            shutil.rmtree(_extended_path(temporary))


def _hashes(root, predicate=lambda n: True):
    return {name: digest(path) for name, path in sorted(_files(root).items()) if predicate(name)}


def _extended_path(path):
    """Windows copy staging must also work with legacy MAX_PATH policy."""
    value = str(path)
    if os.name == 'nt' and not value.startswith('\\\\?\\'):
        return Path('\\\\?\\UNC\\' + value[2:] if value.startswith('\\\\') else '\\\\?\\' + value)
    return path


def _info(root, *, source_revision, source_dirty, inputs_sha, original=None, parent=None):
    sources = _hashes(root, lambda n: n.startswith('src/'))
    original = sources if original is None else original
    return {'version': 1, 'bundle_id': str(uuid.uuid4()), 'parent_bundle_id': parent,
            'source_revision': source_revision, 'source_dirty': source_dirty,
            'modified': sources != original, 'built_at': datetime.now(timezone.utc).isoformat(),
            'inputs_lock_sha256': inputs_sha, 'original_source_hashes': original,
            'source_hashes': sources,
            'immutable_hashes': _hashes(root, lambda n: n.startswith(('runtime/', 'deps/')) or n == 'bundle.json')}


def _publish(stage, output, info, *, overwrite):
    _write_json(stage / 'build-info.json', info)
    (stage / 'SHA256SUMS').write_text(''.join(f'{sha}  {name}\n' for name, sha in _hashes(stage).items() if name != 'SHA256SUMS'), encoding='utf-8')
    output.parent.mkdir(parents=True, exist_ok=True)
    with _lock(output.with_name(output.name + '.lock')):
        if not overwrite and output.exists():
            raise ValueError(f'Repack output already exists: {output}; choose a new ZIP path')
        fd, pending_name = tempfile.mkstemp(prefix=output.stem + '.', suffix='.pending', dir=output.parent)
        os.close(fd)
        pending = Path(pending_name)
        checksum_pending = pending.with_suffix('.sha256.pending')
        old_zip = pending.with_suffix('.previous-zip')
        old_sha = pending.with_suffix('.previous-sha')
        sidecar = output.with_name(output.name + '.sha256')
        keep_backups = False
        try:
            with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                for name, path in sorted(_files(stage).items()):
                    archive.write(path, name)
            with zipfile.ZipFile(pending) as archive:
                list(_archive_members(archive))
                bad = archive.testzip()
                if bad:
                    raise ValueError(f'ZIP CRC failure: {bad}')
            checksum_pending.write_text(f'{digest(pending)}  {output.name}\n', encoding='utf-8')
            # Keep rollback bytes until BOTH replacements succeed. This also
            # preserves the previous valid ZIP if a locked sidecar cannot move.
            if output.exists():
                shutil.copyfile(output, old_zip)
            if sidecar.exists():
                shutil.copyfile(sidecar, old_sha)
            os.replace(pending, output)
            try:
                os.replace(checksum_pending, sidecar)
            except OSError as publish_error:
                # A scanner/policy may also block rollback. Until restoration
                # finishes, these are the only recoverable approved bytes.
                keep_backups = True
                try:
                    if old_zip.exists():
                        os.replace(old_zip, output)
                    else:
                        output.unlink(missing_ok=True)
                    if old_sha.exists() and (not sidecar.exists() or digest(sidecar) != digest(old_sha)):
                        os.replace(old_sha, sidecar)
                except OSError as rollback_error:
                    recovery = ', '.join(str(p) for p in (old_zip, old_sha) if p.exists())
                    raise OSError(f'ZIP/checksum publication failed ({publish_error}); rollback failed '
                                  f'({rollback_error}); retained previous artifacts for manual recovery: '
                                  f'{recovery or "none; no previous artifacts existed"}') from rollback_error
                keep_backups = False
                raise
        finally:
            pending.unlink(missing_ok=True)
            checksum_pending.unlink(missing_ok=True)
            if not keep_backups:
                old_zip.unlink(missing_ok=True)
                old_sha.unlink(missing_ok=True)
    return output


def _environment():
    env = os.environ.copy()
    for key in list(env):
        if key.upper().startswith(('PYTHON', 'PIP_', 'GUI_TEST_', 'BSP_EDITABLE_')):
            env.pop(key)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def build(source_root, cache, output, *, offline=False) -> Path:
    if Path(cache).is_symlink() or getattr(Path(cache), 'is_junction', lambda: False)():
        raise ValueError('Linked cache roots are forbidden')
    source_root, cache, output = (Path(p).expanduser().resolve() for p in (source_root, cache, output))
    logs = _logs(source_root)
    phase = 'inputs'
    print(f'Build logs: {logs}', flush=True)
    try:
        manifest = load_input_lock(source_root / SOURCE_LOCK)
        _requirements(source_root / DATA_FILES[0], manifest)
        cache.mkdir(parents=True, exist_ok=True)
        # The PowerShell bootstrap holds byte 0 for the full parent/child lifetime.
        # Direct helper callers take byte 0 themselves; byte 1 serializes children.
        parent_lock = os.environ.get('BSP_EDITABLE_BOOTSTRAP_OWNER') == str(os.getppid())
        with ExitStack() as locks:
            if not parent_lock:
                locks.enter_context(_lock(cache / 'build.lock', byte=0))
            locks.enter_context(_lock(cache / 'build.lock', byte=1))
            _prepare(cache, manifest, offline=offline)
            inputs = verify_cache(cache, manifest)
            phase = 'stage'
            sources = _source_files(source_root)
            initial = {n: digest(p) for n, p in sources.items()}
            build_paths = [SOURCE_LOCK, 'docs/gui_test/WINDOWS_RUNNER_EDITABLE.md',
                           'scripts/build-editable-runner.cmd', 'scripts/build-editable-runner.ps1']
            build_hashes = {n: digest(source_root / n) for n in build_paths}
            revision, dirty = _provenance(source_root, [*sources, *build_paths], logs)
            with _stage(logs, 'stage-') as stage:
                runtime = stage / 'runtime'
                runtime.mkdir()
                with zipfile.ZipFile(inputs[manifest['runtime']['filename']]) as archive:
                    archive.extractall(runtime)  # paths/links/collisions already checked
                (runtime / 'python312._pth').write_text(PTH, encoding='ascii')
                python = runtime / 'python.exe'
                phase = 'dependencies'
                pip_script = logs / 'install-deps.py'
                pip_script.write_text('import runpy,sys\nsys.path.insert(0,sys.argv.pop(1))\nrunpy.run_module("pip",run_name="__main__")\n', encoding='ascii')
                _run([str(python), '-B', '-X', 'utf8', str(pip_script), str(inputs[manifest['pip']['filename']]),
                      'install', '--isolated', '--disable-pip-version-check', '--no-index', '--no-deps', '--no-compile',
                      '--only-binary=:all:', '--no-warn-script-location', '--target', str(stage / 'deps'),
                      *(str(inputs[w['filename']]) for w in manifest['wheels'])], logs, 'pip-install', env=_environment())
                for name, path in sources.items():
                    target = stage / 'src' / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, target)
                (stage / 'src/scripts/__init__.py').write_text('', encoding='ascii')
                _write_json(stage / 'bundle.json', MARKER)
                shutil.copyfile(source_root / SOURCE_LOCK, stage / 'inputs.lock.json')
                shutil.copyfile(source_root / 'docs/gui_test/WINDOWS_RUNNER_EDITABLE.md', stage / 'GUIDE.md')
                (stage / 'README.txt').write_text(README, encoding='utf-8-sig')
                for filename, action in (('setup.cmd', ''), ('launch.cmd', 'run'), ('diagnose.cmd', 'doctor')):
                    (stage / filename).write_bytes(_launcher('scripts.setup_runtime', action))
                (stage / 'repack.cmd').write_bytes(_launcher('scripts.build_editable_runner', 'repack --bundle-root "%~dp0."'))
                phase = 'smoke'
                smoke = ('import sys,platform,struct; assert platform.python_version()=="3.12.10"; '
                         'assert struct.calcsize("P")==8; import fastapi,uvicorn,pydantic_core,PIL._imaging,serial,httpx; '
                         'from backend.gui_test.execution.bundle import runtime_mode; assert runtime_mode()=="editable"; '
                         'import scripts.setup_runtime; print("editable import smoke OK",sys.executable)')
                _run([str(python), '-B', '-X', 'utf8', '-c', smoke], logs, 'import-smoke', env=_environment())
                _run([str(python), '-B', '-X', 'utf8', '-m', 'scripts.setup_runtime', '--help'], logs, 'setup-help', env=_environment())
                if (initial != {n: digest(p) for n, p in _source_files(source_root).items()} or
                        build_hashes != {n: digest(source_root / n) for n in build_paths}):
                    raise RuntimeError('Allowlisted source changed during build; rebuild from a stable source freeze')
                phase = 'publish'
                info = _info(stage, source_revision=revision, source_dirty=dirty, inputs_sha=digest(source_root / SOURCE_LOCK))
                result = _publish(stage, output, info, overwrite=True)
        _write_json(logs / 'result.json', {'status': 'PASS', 'output': str(result), 'sha256': digest(result), 'bundle_id': info['bundle_id'],
                                          'source_revision': revision, 'source_dirty': dirty})
        print(f'Built: {result}\nSHA256: {digest(result)}\nLogs: {logs}', flush=True)
        return result
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        _write_json(logs / 'result.json', {'status': 'FAIL', 'phase': phase, 'error': str(exc)})
        raise RuntimeError(f'Build phase {phase}: {exc}; action: correct the indicated fixed input/source and rerun; logs: {logs}') from exc


def _editable_source(name):
    return (name.startswith('src/backend/gui_test/') and name.endswith('.py') and
            not any(p.startswith('.') or p in {'tests', '__pycache__'} for p in PurePosixPath(name).parts)) or name == 'src/backend/__init__.py' or name in {
                'src/scripts/' + n for n in (*SCRIPT_NAMES, '__init__.py')}


def _hash_map(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid build-info hash map')
    for name, sha in value.items():
        _relative(name)
        if not isinstance(sha, str) or not HEX.fullmatch(sha):
            raise ValueError(f'Invalid build-info SHA256: {name}')
    return value


def _repack(bundle_root, output, logs) -> Path:
    """Package edited .py files, retaining validated original runtime/deps."""
    root = Path(bundle_root).expanduser().resolve(strict=True)
    if _json(root / 'bundle.json') != MARKER:
        raise ValueError('Invalid editable bundle marker')
    previous = _json(root / 'build-info.json')
    if not isinstance(previous, dict) or previous.get('version') != 1:
        raise ValueError('Unsupported build-info schema')
    try:
        uuid.UUID(previous['bundle_id'])
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError('Invalid parent bundle ID') from exc
    originals = _hash_map(previous.get('original_source_hashes'))
    prior_sources = _hash_map(previous.get('source_hashes'))
    immutable = _hash_map(previous.get('immutable_hashes'))
    files = _files(root)
    actual_immutable = {n: digest(p) for n, p in files.items() if n.startswith(('runtime/', 'deps/')) or n == 'bundle.json'}
    if not immutable or immutable != actual_immutable:
        raise ValueError('Immutable runtime/deps/marker added, missing or changed; restore the original bundle')
    checksums = {}
    for line in (root / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        if not re.fullmatch(r'[0-9a-f]{64}  .+', line):
            raise ValueError('Invalid SHA256SUMS')
        sha, name = line.split('  ', 1)
        _relative(name)
        if name in checksums:
            raise ValueError('Duplicate checksum entry')
        checksums[name] = sha
    if checksums.get('build-info.json') != digest(root / 'build-info.json'):
        raise ValueError('Build-info metadata checksum mismatch')
    allowed = set(checksums) | {'SHA256SUMS'}
    selected = {}
    for name, path in files.items():
        if name in {'SHA256SUMS', 'build-info.json'}:
            continue
        if _editable_source(name):
            selected[name] = path
        elif name in allowed:
            if digest(path) != checksums[name]:
                raise ValueError(f'Non-source bundle file changed: {name}')
            selected[name] = path
        else:
            raise ValueError(f'Unexpected bundle file: {name}; keep user configuration/logs outside the bundle')
    if any(name not in files for name in checksums):
        raise ValueError('Original bundle file missing; source deletion is not supported')
    if any(not n.startswith('src/') for n in originals) or set(prior_sources) != {n for n in checksums if n.startswith('src/')}:
        raise ValueError('Build-info source maps differ from the bundle inventory')
    # Compile without importing or executing edited code; never create bytecode.
    for name, path in selected.items():
        if name.startswith('src/') and name.endswith('.py'):
            try:
                compile(path.read_bytes(), name, 'exec')
            except (SyntaxError, ValueError) as exc:
                raise ValueError(f'Edited Python syntax invalid: {name}: {exc}') from exc
    result_info = None
    try:
        with _stage(logs, 'repack-') as stage:
            stage = _extended_path(stage)
            baseline = {n: digest(p) for n, p in selected.items()}
            for name, path in selected.items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            if baseline != {n: digest(p) for n, p in selected.items()} or baseline != _hashes(stage):
                raise RuntimeError('Bundle changed during repack; stop Runner/editing and retry')
            result_info = _info(stage, source_revision=previous.get('source_revision'), source_dirty=previous.get('source_dirty'),
                                inputs_sha=previous.get('inputs_lock_sha256'), original=originals, parent=previous['bundle_id'])
            destination = Path(output).expanduser().resolve() if output else root.parent / ('BSP-Windows-Runner-Editable-' + result_info['bundle_id'] + '.zip')
            if destination.is_relative_to(root):
                raise ValueError('Repack output must be outside the running bundle')
            result = _publish(stage, destination, result_info, overwrite=False)
        _write_json(logs / 'result.json', {'status': 'PASS', 'output': str(result), 'sha256': digest(result), 'bundle_id': result_info['bundle_id'],
                                          'modified': result_info['modified'], 'product_tests': 'NOT_RUN'})
        print(f'Repacked: {result}\nModified: {result_info["modified"]}\nSHA256: {digest(result)}\nLogs: {logs}')
        return result
    except (OSError, ValueError, RuntimeError) as exc:
        _write_json(logs / 'result.json', {'status': 'FAIL', 'error': str(exc)})
        raise


def repack(bundle_root, output=None) -> Path:
    """Repack with a unique full validation/result log, including early errors."""
    root = Path(bundle_root).expanduser().resolve()
    logs = _logs(root.parent)
    print(f'Repack logs: {logs}', flush=True)
    try:
        return _repack(root, output, logs)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        _write_json(logs / 'result.json', {'status': 'FAIL', 'phase': 'repack', 'error': str(exc)})
        raise ValueError(f'Repack phase validation/publish: {exc}; action: restore immutable files or correct edited source/output; logs: {logs}') from exc


README = '''BSP Windows Runner - editable offline bundle

Extract the COMPLETE ZIP to a writable local folder. No Runner Python/pip install.
First use: setup.cmd (connection settings, external TC Python and token).
Daily start: launch.cmd. Diagnosis: diagnose.cmd. Stop cleanly with Ctrl+C.
Existing user home/settings/DPAPI/runtime are reused; --home selects an external home.
Edit src/**/*.py only after stopping Runner; restart to read the edited source.
Repack edits without pip/cache/network: repack.cmd --output "C:\\delivery\\edited.zip"
Repack verifies runtime/deps and syntax. It does not execute or certify product tests.
Keep settings, tokens, TC environments, logs and database OUTSIDE this folder.
OpenSSH, external TC Python/packages, board drivers and fastboot are separate.
Windows defaults: Runner 8771, browser 8766. Saved ports override defaults.
CLI ports override saved ports and remain fixed. Other local conflicts can select
a temporary free loopback port; use the URL printed by launch/diagnose.
Remote Runner/API/SSH ports and saved settings never change automatically.
ports --save explicitly saves preferred ports. See GUIDE.md for commands/recovery.
build-info.json records original revision, scoped dirty state and edited source hashes.
SHA256SUMS covers files; adjacent ZIP.sha256 covers the complete archive.
Actual company SSH/COM/TC/hardware acceptance remains separate.
'''


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build_parser = commands.add_parser('build')
    root = Path(__file__).resolve().parents[1]
    build_parser.add_argument('--source-root', type=Path, default=root)
    build_parser.add_argument('--cache-path', type=Path, default=root / '.local-reports/editable-runner-cache')
    build_parser.add_argument('--output', type=Path, default=root / 'dist/editable-windows-runner/BSP-Windows-Runner-Editable.zip')
    build_parser.add_argument('--offline', action='store_true')
    repack_parser = commands.add_parser('repack')
    repack_parser.add_argument('--bundle-root', required=True, type=Path)
    repack_parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'build':
            build(args.source_root, args.cache_path, args.output, offline=args.offline)
        else:
            repack(args.bundle_root, args.output)
        return 0
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f'{args.command} failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
