"""Build a portable Runner with an already-installed, strictly pinned environment.

No dependency installation or user settings are read. All subprocess output is
retained locally; the final distributable contains only the frozen app and its
generated launch/provenance files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'BSP-Windows-Runner'
LOCK = ROOT / 'packaging/windows-runner-build.lock'
SOURCE_PATHS = (
    'scripts/windows_runner_entry.py', 'scripts/setup_runtime.py',
    'scripts/setup_flashing.py', 'scripts/build_windows_runner.py',
    'packaging/windows-runner.spec', 'packaging/windows-runner-build.lock',
    'apps/gui-test/requirements.lock',
)

README = '''BSP Windows Runner — 포터블 실행 / Portable launch

1. ZIP 전체를 쓰기 가능한 로컬 폴더에 압축 해제하세요.
   Extract the entire ZIP to a writable local folder. Keep _internal beside the EXE.
2. BSP-Windows-Runner.exe 실행: 처음에는 메뉴 1(연결 설정) → 3(실행).
   Launch the EXE: first use menu 1 (connection setup), then 3 (start).
3. Runner Python/의존성 포함: 회사 PC에서 Runner용 pip/venv 설치 불필요.
   Runner Python and dependencies are included. No Runner pip/venv installation.
4. TC는 별도 Windows Python과 기존 TC 패키지를 명시적으로 지정하세요.
   TC Python must be an existing external interpreter outside this bundle.
   OpenSSH Client, fastboot, board drivers and TC packages are separate prerequisites.
5. 기존 사용자 홈의 .bsp-dashboard/windows 설정, DPAPI 토큰과 기록을 재사용합니다.
   Existing per-user settings, DPAPI token and runtime/UNKNOWN history are preserved.
   --home PATH optionally selects an existing external setup directory.
6. 종료는 Ctrl+C. 진행 중 장비 작업의 정상 종료를 기다리세요.
   Stop with Ctrl+C and wait for active hardware work to finish.

--help shows setup options. --runner --help shows the loopback Runner options.
Actual company/board acceptance is separate from local package verification.
build-info.json records the source revision, scoped dirty state and dependency pins.
SHA256SUMS lists packaged files; the adjacent ZIP.sha256 checks the complete archive.
'''


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pins(path, seen=None):
    seen = set() if seen is None else seen
    path = path.resolve()
    if path in seen:
        return {}
    seen.add(path)
    result = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        if line.startswith('-r '):
            result.update(pins(path.parent / line[3:].strip(), seen))
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)', line)
        if not match:
            raise ValueError(f'Build lock must contain exact pins: {path.name}')
        name, version = match.groups()
        if name in result and result[name] != version:
            raise ValueError(f'Conflicting dependency pin: {name}')
        result[name] = version
    return result


def checked_environment():
    if os.name != 'nt' or struct.calcsize('P') != 8 or platform.machine().upper() not in ('AMD64', 'X86_64'):
        raise ValueError('Build requires Windows x64 (AMD64).')
    if platform.python_version() != '3.12.10':
        raise ValueError('Build requires CPython 3.12.10 x64.')
    if platform.python_implementation() != 'CPython':
        raise ValueError('Build requires CPython.')
    versions = {}
    for name, expected in pins(LOCK).items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ValueError(f'Missing build dependency {name}=={expected}; install the lock in the build environment.') from exc
        if actual != expected:
            raise ValueError(f'Build dependency {name}: expected {expected}, installed {actual}.')
        versions[name] = actual
    return versions


def scoped_sources():
    paths = set(SOURCE_PATHS)
    for directory in ('backend',):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / directory).rglob('*.py')
                     if not any(part.startswith('.') or part == '__pycache__' for part in p.relative_to(ROOT).parts))
    return sorted(paths)


def git_capture(args, log_dir, name):
    output = log_dir / (name + '.stdout.log')
    error = log_dir / (name + '.stderr.log')
    with output.open('wb') as stdout, error.open('wb') as stderr:
        result = subprocess.run(['git', *args], cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
    if result.returncode:
        raise RuntimeError(f'git provenance failed ({result.returncode}); see {error}')
    return output.read_text(encoding='utf-8').strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Build Windows x64 portable Runner; uses installed pinned dependencies only.')
    parser.add_argument('--log-dir', type=Path, default=ROOT / '.local-reports/20261104-portable-runner')
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    log_dir = args.log_dir.expanduser().resolve() / ('build-' + stamp)
    log_dir.mkdir(parents=True, exist_ok=False)
    try:
        versions = checked_environment()
        sources = scoped_sources()
        revision = git_capture(['rev-parse', 'HEAD'], log_dir, 'revision')
        status = git_capture(['status', '--porcelain=v1', '--untracked-files=all', '--', *sources], log_dir, 'scoped-status')
        hashes = {name: digest(ROOT / name) for name in sources}
        target = ROOT / 'dist/windows-runner'
        target.mkdir(parents=True, exist_ok=True)
        # A fresh dist path prevents old/unrelated data from entering the deliverable.
        staging = ROOT / 'apps/gui-test/.build' / ('portable-' + stamp)
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                   '--distpath', str(staging / 'dist'), '--workpath', str(staging / 'work'),
                   str(ROOT / 'packaging/windows-runner.spec')]
        with (log_dir / 'pyinstaller.stdout.log').open('wb') as stdout, (log_dir / 'pyinstaller.stderr.log').open('wb') as stderr:
            result = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, check=False)
        if result.returncode:
            raise RuntimeError(f'PyInstaller failed ({result.returncode}); logs: {log_dir}')
        if sources != scoped_sources() or any(digest(ROOT / name) != hashes[name] for name in sources):
            raise RuntimeError('Source files changed during packaging; rerun with a stable checkout.')
        app = staging / 'dist' / NAME
        if not (app / (NAME + '.exe')).is_file():
            raise RuntimeError('PyInstaller did not create the expected executable.')
        (app / 'README.txt').write_text(README, encoding='utf-8-sig')
        manifest = {'format': 1, 'built_at_utc': stamp, 'python': platform.python_version(),
                    'platform': platform.platform(), 'source_revision': revision,
                    'dirty_scope': sources, 'scoped_dirty': bool(status),
                    'scoped_status': status.splitlines(), 'source_sha256': hashes,
                    'dependencies': versions, 'build_command': command}
        (app / 'build-info.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        checksums = [f'{digest(path)}  {path.relative_to(app).as_posix()}'
                     for path in sorted(app.rglob('*')) if path.is_file()]
        (app / 'SHA256SUMS').write_text('\n'.join(checksums) + '\n', encoding='utf-8')
        destination = target / NAME
        if destination.exists():
            # Keep a previous artifact intact for comparison or recovery.
            destination.rename(target / (NAME + '.previous-' + stamp))
        shutil.copytree(app, destination)
        archive = target / (NAME + '.zip')
        pending = target / (NAME + '.' + stamp + '.zip')
        with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_DEFLATED) as zip_stream:
            for path in sorted(destination.rglob('*')):
                if path.is_file():
                    zip_stream.write(path, path.relative_to(target).as_posix())
        os.replace(pending, archive)
        checksum = digest(archive)
        (target / (NAME + '.zip.sha256')).write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
        print(f'Built: {destination}\nZIP: {archive}\nSHA256: {checksum}\nLogs: {log_dir}')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Build failed: {exc}\nLogs: {log_dir}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
