"""Windows source launcher: provision once, then run the native connector.

Only standard-library imports are allowed before the managed environment is ready.
No source, TC, board profile, or running environment is modified by provisioning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.gui_test.execution.launch import LaunchLock
from backend.gui_test.connector.logs import logger

LOCKFILES = ('apps/gui-test/requirements.lock', 'apps/board-connector/requirements.lock')

# The child verifies installed bytes through normal imports as well as pinned versions.
CHECK = '''import importlib.metadata as m, json, sys, struct
assert list(sys.version_info[:2])==json.loads(sys.argv[2]) and struct.calcsize("P")==8
expected=json.loads(sys.argv[1])
assert all(m.version(name)==version for name,version in expected.items())
from PySide6.QtWidgets import QApplication
import fastapi, httpx, serial, uvicorn
from backend.gui_test.connector.gui import ConnectorWindow
'''


def supported_python(version, bits):
    return (3, 11) <= tuple(version) < (3, 14) and bits == 64


def browser_files(root):
    for name in ('index.html', 'host.mjs', 'view.mjs', 'style.css'):
        file = root / 'backend/gui_test/connector/web_assets' / name
        if not file.is_file() and name in {'view.mjs', 'style.css'}:
            file = root / 'packages/gui-test-ui/src/connector_web' / name
        if not file.is_file():
            raise RuntimeError('[BC-55] 웹 화면 파일 누락: ' + name + '. 전체 소스/배포본을 갱신하세요. pip 재설치로 해결되지 않습니다.')
        file.read_bytes()


def requirements(root, ui='browser'):
    pins = {}
    digest = hashlib.sha256(b'board-connector-bootstrap-v1\0')
    digest.update(f'{sys.version_info.major}.{sys.version_info.minor}-{struct.calcsize("P")}'.encode())
    if ui == 'browser':
        digest.update(b'browser\0')
    for relative in (LOCKFILES[:1] if ui == 'browser' else LOCKFILES):
        data = (root / relative).read_bytes()
        for line in data.decode('utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)', line)
            if not match:
                raise ValueError('Unsupported requirement in ' + relative)
            name, version = match.groups()
            name = re.sub(r'[-_.]+', '-', name).lower()
            if name in pins and pins[name] != version:
                raise ValueError('Conflicting dependency pin: ' + name)
            pins[name] = version
    digest.update(json.dumps(pins, sort_keys=True).encode())
    return pins, digest.hexdigest()


def child_env():
    # Keep company pip configuration/proxies; never copy connection secrets to children.
    from backend.gui_test.execution.bundle import external_environment
    env = external_environment()
    for key in list(env):
        if key.upper() in {'PYTHONPATH', 'PYTHONHOME'}:
            env.pop(key)
    env['PYTHONUTF8'] = '1'
    return env


def healthy(python, pins, root, ui='browser'):
    if not python.is_file():
        return False
    try:
        check = CHECK if ui == 'qt' else CHECK.replace('from PySide6.QtWidgets import QApplication\n', '').replace(
            'from backend.gui_test.connector.gui import ConnectorWindow', 'from backend.gui_test.connector.web import BrowserUI')
        return subprocess.run([str(python), '-X', 'utf8', '-c', check, json.dumps(pins), json.dumps(list(sys.version_info[:2]))],
                              cwd=root, env=child_env(), stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_step(argv, root, log, stage):
    print(stage, flush=True)
    log.info('%s', stage)
    # pip progress goes to this console. Do not persist raw index URLs/credentials.
    result = subprocess.run([str(value) for value in argv], cwd=root, env=child_env())
    if result.returncode:
        log.error('%s failed: exit=%s', stage, result.returncode)
        raise RuntimeError(stage + ' 실패. 위 오류를 확인하고 같은 실행 파일로 다시 시도하세요.')


def prepare(root, home, log, ui='browser'):
    pins, fingerprint = requirements(root, ui)
    def ready(python):
        return healthy(python, pins, root, ui=ui)
    cache = home / 'connector-environments'
    cache.mkdir(parents=True, exist_ok=True)
    # Installation and publication are serialized; GUI/Host lifetime is independent.
    with LaunchLock(cache / 'install.lock'):
        record = cache / (fingerprint + '.json')
        try:
            name = json.loads(record.read_text(encoding='utf-8'))['directory']
        except (OSError, ValueError, KeyError, TypeError):
            name = ''
        if isinstance(name, str) and re.fullmatch(r'env-[a-f0-9]{32}', name):
            python = cache / name / 'Scripts' / 'python.exe'
            if ready(python):
                log.info('Using prepared connector environment')
                return python
        # Reuse a previously installed source environment without changing its packages.
        existing = root / '.venv' / 'Scripts' / 'python.exe'
        if ready(existing):
            log.info('Using existing source environment')
            return existing
        # Build at its final path: virtual environments cannot safely be renamed.
        directory = cache / ('env-' + uuid.uuid4().hex)
        try:
            run_step([sys.executable, '-m', 'venv', directory], root, log, '커넥터 실행 환경을 준비합니다.')
            python = directory / 'Scripts' / 'python.exe'
            lock_args = [arg for name in (LOCKFILES[:1] if ui == 'browser' else LOCKFILES) for arg in ('-r', root / name)]
            run_step([python, '-m', 'pip', 'install', '--disable-pip-version-check', *lock_args],
                     root, log, '필요한 패키지를 설치합니다. 최초 설치에는 시간이 걸릴 수 있습니다.')
            if not ready(python):
                raise RuntimeError('설치 후 패키지 확인에 실패했습니다. Python 3.13 64비트(3.11/3.12 호환)와 설치 오류를 확인하세요.')
            temporary = record.with_suffix('.tmp')
            temporary.write_text(json.dumps({'directory': directory.name}) + '\n', encoding='utf-8')
            os.replace(temporary, record)
            log.info('Prepared connector environment')
            return python
        except BaseException:
            # This attempt's unpublished directory only. Never remove earlier environments.
            shutil.rmtree(directory, ignore_errors=True)
            raise


def diagnose(root, home, ui='browser'):
    """Read files and test imports only; never install, start a manager, or open hardware."""
    print('[BC-50] 읽기 전용 진단 · 설치/GUI/SSH/COM을 시작하지 않습니다.')
    print('Python:', sys.executable)
    print('Version:', sys.version.split()[0], str(struct.calcsize('P') * 8) + '-bit')
    print('Source:', root)
    print('Profile home:', home)
    try:
        required = ('scripts/board_connector.py', 'backend/gui_test/connector/__main__.py', *(LOCKFILES if ui == 'qt' else LOCKFILES[:1]))
        for relative in required:
            with (root / relative).open('rb') as stream:
                stream.read(1)
        pins, fingerprint = requirements(root, ui)
        if ui == 'browser':
            browser_files(root)
    except (OSError, ValueError, RuntimeError) as exc:
        print('[BC-51] 소스/고정 의존성 파일을 읽을 수 없습니다:', type(exc).__name__)
        print('조치: CMD 하나가 아닌 전체 소스를 같은 폴더에 갱신하고 Z: 접근을 확인하세요.')
        return 2
    candidates = [root / '.venv' / 'Scripts' / 'python.exe']
    record = home / 'connector-environments' / (fingerprint + '.json')
    try:
        name = json.loads(record.read_text(encoding='utf-8'))['directory']
        if isinstance(name, str) and re.fullmatch(r'env-[a-f0-9]{32}', name):
            candidates.insert(0, record.parent / name / 'Scripts' / 'python.exe')
    except (OSError, ValueError, KeyError, TypeError):
        pass
    for python in candidates:
        if healthy(python, pins, root, ui=ui):
            print('[BC-52] 기존 실행 환경 정상:', python)
            break
    else:
        print('[BC-53] 재사용 가능한 실행 환경 없음. 일반 실행에서 최초 준비가 필요합니다.')
    print('[BC-54] CMD만 실패하면 CMD 시작 설정/호출 경로를 확인하세요.')
    print('PowerShell: cmd.exe /d /c .\\board-connector.cmd --diagnose')
    print('직접 성공한 python.exe는 BOARD_CONNECTOR_PYTHON으로 지정할 수 있습니다.')
    print('AutoRun 오류가 BC-00 전에 나오는 경우 CMD 내부 재시작으로 최초 오류까지 제거할 수 없습니다.')
    return 0



def prepare_public_tools(root, home, log):
    """Windows package-manager setup, separate from Python/GUI package locks."""
    if shutil.which('ssh') and shutil.which('fastboot'):
        return
    script = root / 'scripts/bootstrap-prerequisites.ps1'
    if not script.is_file():
        raise RuntimeError('[BC-56] 공개 필수 도구 설치 스크립트가 없습니다. 전체 소스를 갱신하세요.')
    powershell = shutil.which('powershell.exe')
    if not powershell:
        raise RuntimeError('[BC-56] Windows PowerShell을 찾을 수 없습니다.')
    # Serialize first setup; do not expose package-manager output/credentials in
    # diagnostic records. Full output remains in the local prerequisite log.
    logs = home / 'logs'; logs.mkdir(parents=True, exist_ok=True)
    output = logs / ('prerequisites-' + uuid.uuid4().hex + '.log')
    receipt = logs / ('prerequisite-paths-' + uuid.uuid4().hex + '.json')
    with LaunchLock(home / 'prerequisites.lock'), output.open('wb') as stream:
        result = subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), '-ReceiptPath', str(receipt)],
                                cwd=root, env=child_env(), stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, shell=False)
    if result.returncode:
        log.error('Public prerequisite preparation failed: %s', output)
        raise RuntimeError('[BC-56] 공개 필수 도구를 준비하지 못했습니다. 로컬 로그: ' + str(output))
    if receipt.is_file():
        values = json.loads(receipt.read_text(encoding='utf-8-sig')).get('tools', {})
        directories = [str(Path(path).parent) for name, path in values.items()
                       if name in {'ssh.exe', 'fastboot.exe'} and isinstance(path,str) and Path(path).is_file()]
        if directories:
            os.environ['PATH'] = os.pathsep.join(directories + [os.environ.get('PATH','')])

def main(argv=None):
    parser = argparse.ArgumentParser(description='보드 커넥터 설치 확인 및 실행')
    parser.add_argument('--home', type=Path, default=Path.home() / '.bsp-dashboard' / 'windows')
    parser.add_argument('--install-only', action='store_true', help='설치 확인만 하고 종료')
    parser.add_argument('--diagnose', action='store_true', help='설치/장비 실행 없는 읽기 전용 진단')
    parser.add_argument('--ui', choices=('browser', 'qt'), default='browser', help='기본 브라우저 화면 또는 Qt 호환 화면')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--import-profile', type=Path, help='플러그인 연결 JSON 가져오기')
    source.add_argument('--choose-profile', action='store_true', help='플러그인 연결 JSON 파일 선택')
    parser.add_argument('--import-only', action='store_true', help='가져오기 후 관리자/SSH 시작 없이 종료')
    args = parser.parse_args(argv)
    importing = args.import_profile is not None or args.choose_profile
    if args.import_only and not importing:
        parser.error('--import-only requires a connection profile')
    if importing and (args.install_only or args.diagnose):
        parser.error('connection import cannot be combined with install-only/diagnose')
    if os.name != 'nt':
        print('이 실행기는 Windows용입니다. Mac 미리보기는 --preview 모듈 실행을 사용하세요.', file=sys.stderr)
        return 2
    if not supported_python(sys.version_info[:2], struct.calcsize('P') * 8):
        print('Python 3.13 64비트를 설치하세요. 3.11/3.12도 호환됩니다.', file=sys.stderr)
        return 2
    home = args.home.expanduser().absolute() if importing else args.home.expanduser().resolve()
    if args.diagnose:
        return diagnose(ROOT, home, ui=args.ui)
    log = None
    try:
        log = logger(home)
        if args.ui == 'browser':
            browser_files(ROOT)
        prepare_public_tools(ROOT, home, log)
        python = prepare(ROOT, home, log, ui=args.ui)
        if args.install_only:
            print('설치 확인 완료.', flush=True)
            return 0
        print('보드 커넥터를 실행합니다.', flush=True)
        # Keep the console until GUI exit so startup failures remain visible.
        # Closing the GUI still leaves the existing manager/Host lifetime unchanged.
        ui_args = ['--ui', args.ui]
        if args.import_profile is not None:
            ui_args += ['--import-profile', str(args.import_profile.expanduser().absolute())]
        if args.choose_profile:
            ui_args += ['--choose-profile']
        if args.import_only:
            ui_args += ['--import-only']
        result = subprocess.run([str(python), '-X', 'utf8', '-B', '-m', 'backend.gui_test.connector',
                                 '--home', str(home), *ui_args], cwd=ROOT, env=child_env())
        if result.returncode:
            raise RuntimeError('GUI 실행에 실패했습니다. 로그를 확인하세요.')
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        if log:
            log.error('LAUNCH_FAILED %s', type(exc).__name__)
        print(str(exc) + '\n로그: ' + str(home / 'logs' / 'connector.log'), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('실행 준비를 취소했습니다. 같은 실행 파일로 다시 시작할 수 있습니다.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
