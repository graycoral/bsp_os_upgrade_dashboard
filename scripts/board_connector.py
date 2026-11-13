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
CHECK = '''import importlib.metadata as m, json, sys
expected=json.loads(sys.argv[1])
assert all(m.version(name)==version for name,version in expected.items())
from PySide6.QtWidgets import QApplication
import fastapi, httpx, serial, uvicorn
from backend.gui_test.connector.gui import ConnectorWindow
'''


def requirements(root):
    pins = {}
    digest = hashlib.sha256(b'board-connector-bootstrap-v1\0')
    digest.update(f'{sys.version_info.major}.{sys.version_info.minor}-{struct.calcsize("P")}'.encode())
    for relative in LOCKFILES:
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


def healthy(python, pins, root):
    if not python.is_file():
        return False
    try:
        return subprocess.run([str(python), '-X', 'utf8', '-c', CHECK, json.dumps(pins)],
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


def prepare(root, home, log):
    pins, fingerprint = requirements(root)
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
            if healthy(python, pins, root):
                log.info('Using prepared connector environment')
                return python
        # Reuse a previously installed source environment without changing its packages.
        existing = root / '.venv' / 'Scripts' / 'python.exe'
        if healthy(existing, pins, root):
            log.info('Using existing source environment')
            return existing
        # Build at its final path: virtual environments cannot safely be renamed.
        directory = cache / ('env-' + uuid.uuid4().hex)
        try:
            run_step([sys.executable, '-m', 'venv', directory], root, log, '커넥터 실행 환경을 준비합니다.')
            python = directory / 'Scripts' / 'python.exe'
            run_step([python, '-m', 'pip', 'install', '--disable-pip-version-check',
                      '-r', root / LOCKFILES[0], '-r', root / LOCKFILES[1]],
                     root, log, '필요한 패키지를 설치합니다. 최초 설치에는 시간이 걸릴 수 있습니다.')
            if not healthy(python, pins, root):
                raise RuntimeError('설치 후 패키지 확인에 실패했습니다. Python 3.11/3.12 64비트와 설치 오류를 확인하세요.')
            temporary = record.with_suffix('.tmp')
            temporary.write_text(json.dumps({'directory': directory.name}) + '\n', encoding='utf-8')
            os.replace(temporary, record)
            log.info('Prepared connector environment')
            return python
        except BaseException:
            # This attempt's unpublished directory only. Never remove earlier environments.
            shutil.rmtree(directory, ignore_errors=True)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description='보드 커넥터 설치 확인 및 실행')
    parser.add_argument('--home', type=Path, default=Path.home() / '.bsp-dashboard' / 'windows')
    parser.add_argument('--install-only', action='store_true', help='설치 확인만 하고 종료')
    args = parser.parse_args(argv)
    if os.name != 'nt':
        print('이 실행기는 Windows용입니다. Mac 미리보기는 --preview 모듈 실행을 사용하세요.', file=sys.stderr)
        return 2
    if not (3, 11) <= sys.version_info[:2] < (3, 13) or struct.calcsize('P') != 8:
        print('Python 3.11 또는 3.12 64비트를 설치하세요.', file=sys.stderr)
        return 2
    home = args.home.expanduser().resolve()
    log = None
    try:
        log = logger(home)
        python = prepare(ROOT, home, log)
        if args.install_only:
            print('설치 확인 완료.', flush=True)
            return 0
        print('보드 커넥터를 실행합니다.', flush=True)
        # Keep the console until GUI exit so startup failures remain visible.
        # Closing the GUI still leaves the existing manager/Host lifetime unchanged.
        result = subprocess.run([str(python), '-X', 'utf8', '-B', '-m', 'backend.gui_test.connector',
                                 '--home', str(home)], cwd=ROOT, env=child_env())
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
