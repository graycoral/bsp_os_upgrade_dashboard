"""Interactive real-run setup. Standard library only; never executes a TC/flash itself."""
from __future__ import annotations

import argparse
import copy
import ctypes
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
TOKEN_ENV = 'GUI_TEST_RUNNER_TOKEN'


def read_json(path):
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'JSON 객체가 필요합니다: {path}')
    return value


def atomic_write(path, data, backup=False):
    """Private temporary + replace; failed edits leave the original and backup intact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f'링크 파일에는 저장하지 않습니다: {path}')
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if backup and path.exists():
            # Never replace an earlier backup (including several saves in one second).
            previous = path.with_name(path.name + '.' + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3) + '.bak')
            with previous.open('xb') as stream:
                stream.write(path.read_bytes())
            if os.name != 'nt':
                previous.chmod(0o600)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save_json(path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'), backup=True)


def dpapi(data, decrypt=False):
    """Windows user-bound encryption; no third-party module or plaintext temp file."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise OSError('Windows 사용자 토큰 보호/복원 실패. 같은 계정에서 토큰을 다시 등록하세요.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


class TokenStore:
    def __init__(self, home, windows):
        self.home, self.windows = Path(home), windows
        self.path = self.home / ('runner-token.dpapi' if windows else 'runner-token')

    def prepare(self):
        if self.home.is_symlink() or self.path.is_symlink():
            raise ValueError('토큰 경로에 링크를 사용할 수 없습니다.')
        self.home.mkdir(parents=True, exist_ok=True)
        if not self.windows:
            if self.home.stat().st_uid != os.getuid():
                raise ValueError('토큰 폴더 소유자가 현재 사용자와 다릅니다.')
            self.home.chmod(0o700)

    @staticmethod
    def validate(token):
        if not 32 <= len(token) <= 4096 or any(c.isspace() for c in token) or not token.isascii():
            raise ValueError('공백 없는 ASCII 토큰 32~4096자가 필요합니다.')
        return token

    def load(self):
        self.prepare()
        if not self.path.exists():
            raise ValueError('먼저 연결 설정에서 양쪽에 동일한 토큰을 등록하세요.')
        if not self.windows:
            info = self.path.stat()
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('토큰 파일은 현재 사용자 소유, 권한 600이어야 합니다.')
        data = self.path.read_bytes()
        return self.validate((dpapi(data, True) if self.windows else data).decode('ascii'))

    def save(self, token):
        self.validate(token)
        self.prepare()
        raw = token.encode('ascii')
        atomic_write(self.path, dpapi(raw) if self.windows else raw)


def ask(label, default='', optional=False, check=None):
    while True:
        value = input(f'{label}' + (f' [{default}]' if default != '' else '') + ': ').strip()
        value = value or str(default)
        if optional and value == '-':
            value = ''
        if not value and not optional:
            print('값을 입력하세요. Ctrl+C는 이번 단계 취소입니다.')
            continue
        if check and not check(value):
            print('형식 또는 경로가 올바르지 않습니다.')
            continue
        return value


def yes(label, default=False):
    return ask(label + ' (y/n)', 'y' if default else 'n', check=lambda x: x.lower() in ('y', 'n')).lower() == 'y'


def number(label, default, low=1, high=65535):
    return int(ask(label, default, check=lambda x: x.isdecimal() and low <= int(x) <= high))


def checked_path(label, default='', directory=False):
    value = ask(label, default, check=lambda x: Path(x).expanduser().is_dir() if directory else Path(x).expanduser().is_file())
    return str(Path(value).expanduser().resolve())


def valid_name(value):
    return bool(re.fullmatch(r'[\w.-]{1,80}', value))


def validate_boards(boards):
    if not boards or any(not valid_name(b['host']) or not valid_name(b['board_id']) or
                         not re.fullmatch(r'COM[1-9][0-9]{0,3}', b['com']) or
                         (b.get('node') and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', b['node'])) for b in boards):
        raise ValueError('보드/COM/노드 설정이 올바르지 않습니다.')
    for key in ('board_id', 'com', 'node'):
        values = [b[key].casefold() for b in boards if b.get(key)]
        if len(values) != len(set(values)):
            raise ValueError(f'중복 보드 설정: {key}')
    if len({b['host'].casefold() for b in boards}) != 1:
        raise ValueError('모든 보드는 같은 Windows PC에 있어야 합니다.')


def ssh_argv(settings):
    host, account = settings['server'], settings['account']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', host) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', account):
        raise ValueError('SSH 서버/계정 형식이 올바르지 않습니다.')
    port = settings.get('ssh_port', 22)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('SSH 포트가 올바르지 않습니다.')
    return ['ssh', '-NT', '-o', 'ExitOnForwardFailure=yes', '-o', 'ServerAliveInterval=15',
            '-o', 'ServerAliveCountMax=3', '-L', '127.0.0.1:8766:127.0.0.1:8766',
            '-R', '127.0.0.1:8771:127.0.0.1:8771', '-p', str(port), '-l', account, host]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('실행기 리다이렉트는 허용하지 않습니다.')


def runner_get(path, token):
    # Fixed loopback endpoint, no environment proxy and no credential-bearing redirect.
    request = Request('http://127.0.0.1:8771/v1' + path, headers={'Authorization': 'Bearer ' + token})
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=5) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('실행기 응답이 너무 큽니다.')
    return json.loads(raw)


def require_free(port):
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', port))


class Wizard:
    def __init__(self, root=ROOT, windows=None, home=None):
        self.root = Path(root)
        self.windows = os.name == 'nt' if windows is None else windows
        self.home = Path(home) if home else Path.home() / '.bsp-dashboard' / ('windows' if self.windows else 'linux')
        self.tokens = TokenStore(self.home, self.windows)
        self.runtime = self.home / 'runtime' if self.windows else self.root / '.runtime'
        self.config = self.home / 'windows-runner.json' if self.windows else self.runtime / 'gui-test.json'
        self.state = read_json(self.config).get('_setup', {})
        self.python = self.home / 'venv' / 'Scripts' / 'python.exe' if self.windows else self.root / '.venv' / 'bin' / 'python'

    def command(self, argv, env=None):
        # Paths/answers are argv elements, never evaluated as shell code.
        result = subprocess.run([str(x) for x in argv], cwd=self.root, env=env, check=False)
        if result.returncode:
            raise RuntimeError(f'명령 실패 (종료 코드 {result.returncode}). 위 출력을 확인하세요.')

    def preview_save(self, path, value):
        print(f'\n저장할 파일: {path}\n' + json.dumps(value, ensure_ascii=False, indent=2))
        if yes('이 설정을 저장할까요?'):
            save_json(path, value)
            print('저장했습니다. 기존 파일은 같은 폴더의 .bak으로 보존했습니다. 실행 중 서비스에는 재시작 후 적용됩니다.')
            return True
        print('변경하지 않았습니다.')
        return False

    def token_setup(self):
        print('양쪽에 같은 토큰을 한 번 등록하면 다음 실행부터 자동으로 사용합니다.')
        choice = ask('1 다른 PC의 토큰 입력 / 2 새 토큰 생성', '1', check=lambda x: x in ('1', '2'))
        if choice == '2':
            token = secrets.token_hex(32)
            print('다른 PC의 설정 메뉴에 옮길 토큰 (저장소/채팅에 붙여넣지 마세요):\n' + token)
        else:
            token = getpass.getpass('토큰 (화면에 표시하지 않음): ').strip()
        self.tokens.validate(token)
        if yes('이 토큰을 로컬에 보호하여 저장할까요?'):
            self.tokens.save(token)
            print('토큰 저장 완료. Windows는 현재 사용자 DPAPI, Linux는 소유자 전용 파일(600)을 사용합니다.')

    def connection(self):
        if self.windows:
            draft = copy.deepcopy(read_json(self.config))
            draft['source_root'] = checked_path('탐색기로 열던 TC 공유 폴더', draft.get('source_root', ''), True)
            source = Path(draft['source_root'])
            if self.runtime.resolve().is_relative_to(source) or source.is_relative_to(self.runtime.resolve()):
                raise ValueError('TC 공유 폴더와 실행 기록 폴더는 서로 분리해야 합니다.')
            draft['python'] = checked_path('TC 실행에 성공했던 Windows python.exe', draft.get('python', sys.executable))
            boards = draft.get('boards', [])
            host = ask('Windows PC 이름', boards[0]['host'] if boards else socket.gethostname(), check=valid_name)
            count = number('등록할 보드 수', len(boards) or 1, 1, 32)
            result = []
            for i in range(count):
                old = boards[i] if i < len(boards) else {}
                print(f'\n보드 {i + 1}/{count}')
                board = {'host': host, 'board_id': ask('보드 ID', old.get('board_id', f'board-{i+1}'), check=valid_name),
                         'com': ask('실제 COM 번호 (예: COM7)', old.get('com', ''), check=lambda x: bool(re.fullmatch(r'COM[1-9][0-9]{0,3}', x)))}
                node = ask('노드명 (Single만 쓰면 빈칸, 기존 값 삭제는 -)', old.get('node', ''), optional=True,
                           check=lambda x: not x or bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', x)))
                if node:
                    board['node'] = node
                result.append(board)
            validate_boards(result)
            draft['boards'] = result
            draft.setdefault('metadata', {})
            while yes('TC별 제한 시간을 추가/변경할까요? (기본 10초)'):
                name = ask('TC 공유 폴더 기준 상대 파일 경로 (예: single/tc1.py)')
                entry = draft['metadata'].setdefault(name, {})
                entry['timeout'] = number('제한 시간(초)', entry.get('timeout', 120), 1, 86400)
            state = copy.deepcopy(self.state)
            state['server'] = ask('Linux SSH 서버 주소', state.get('server', ''), check=lambda x: bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', x)))
            state['account'] = ask('Linux SSH 계정', state.get('account', ''), check=lambda x: bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', x)))
            state['ssh_port'] = number('SSH 포트', state.get('ssh_port', 22))
            # One authoritative file makes runner + tunnel edits one atomic replacement.
            draft['_setup'] = state
            if self.preview_save(self.config, draft):
                self.state = state
        else:
            draft = read_json(self.config)
            draft.update(runner='windows-http', url='http://127.0.0.1:8771')
            self.preview_save(self.config, draft)
        if not self.tokens.path.exists():
            self.token_setup()

    def install(self):
        print('Python 의존성을 전용 가상환경에 설치합니다.' + ('' if self.windows else ' Linux 웹 화면도 빌드합니다.'))
        if not yes('설치/빌드를 진행할까요?'):
            return
        if not self.python.is_file():
            destination = self.python.parents[1]
            self.command([sys.executable, '-m', 'venv', destination])
        lock = self.root / ('gui_test/requirements.lock' if self.windows else 'requirements.lock')
        self.command([self.python, '-m', 'pip', 'install', '-r', lock])
        if not self.windows:
            self.command(['bash', self.root / 'scripts/build.sh', 'dashboard'])
        print('설치 완료. 회사 TC용 패키지는 등록한 TC Python 환경의 기존 설치를 사용합니다.')

    def environment(self):
        env = os.environ.copy()
        env[TOKEN_ENV] = self.tokens.load()
        return env

    def check(self):
        if not self.config.exists():
            raise ValueError('연결 설정이 없습니다. 메뉴 1을 먼저 진행하세요.')
        token = self.tokens.load()
        identity = runner_get('/identity', token)
        boards = runner_get('/boards', token)
        catalog = runner_get('/catalog', token)
        print('Windows 실행기 인증/조회 성공. 장비 시험 성공을 의미하지 않습니다.')
        print('실행기 ID:', identity['runner_id'])
        print('사용 가능한 보드:', json.dumps(boards, ensure_ascii=False))
        print('TC 소스 기준:', catalog['revision'])

    @staticmethod
    def stop_owned(process, windows=False):
        if process.poll() is not None:
            return
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT if windows else signal.SIGINT)
        except ProcessLookupError:
            return
        print('정상 종료 대기 중입니다. 진행 중 작업은 강제 종료하지 않습니다.')
        while process.poll() is None:
            try:
                process.wait(timeout=1)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                pass

    def linux_start(self, env):
        if not (self.root / 'apps/web/dist/index.html').is_file():
            raise ValueError('화면 빌드가 없습니다. 메뉴 2를 진행하세요.')
        processes = []
        try:
            # Start under Python (not Bash's asynchronous SIGINT-ignore disposition).
            # Separate sessions isolate terminal Ctrl+C; send one graceful SIGINT ourselves.
            for argv in ([self.python, self.root / 'scripts/serve.py', '--runtime', self.runtime, '--port', '8766'],
                         [self.python, '-m', 'backend.worker.main', '--runtime', self.runtime]):
                processes.append(subprocess.Popen([str(x) for x in argv], cwd=self.root, env=env, start_new_session=True))
            while all(p.poll() is None for p in processes):
                time.sleep(.2)
            failed = next(p.returncode for p in processes if p.poll() is not None)
            raise RuntimeError(f'API 또는 worker가 종료됐습니다 (코드 {failed}). 위 오류를 확인하세요.')
        finally:
            # Stop scheduling before closing the API. Keep waiting for active work to finish.
            for process in reversed(processes):
                self.stop_owned(process)

    def start(self):
        if not self.python.is_file():
            raise ValueError('먼저 메뉴 2에서 의존성을 설치하세요.')
        if not self.config.exists():
            raise ValueError('먼저 메뉴 1에서 실제 연결을 설정하세요. Mock로 시작하지 않습니다.')
        env = self.environment()
        if not self.windows:
            config = read_json(self.config)
            if config.get('runner') != 'windows-http' or config.get('url') != 'http://127.0.0.1:8771':
                raise ValueError('이 마법사는 loopback 8771의 windows-http 설정을 사용합니다. 메뉴 1에서 확인하세요.')
            require_free(8766)
            print('저장한 설정으로 Linux API/worker를 시작합니다. 종료: Ctrl+C. 실제 BSP 설정은 웹의 환경 설정에서 변경합니다.')
            self.linux_start(env)
            return
        tunnel = ssh_argv(self.state)
        if not shutil.which('ssh'):
            raise ValueError('Windows OpenSSH 클라이언트가 필요합니다.')
        require_free(8771)
        require_free(8766)
        self.runtime.mkdir(parents=True, exist_ok=True)
        log_path = self.runtime / 'setup-runner.log'
        print(f'Windows 실행기 로그: {log_path}')
        # The script owns only this child, never an already-running service.
        with log_path.open('ab') as log:
            process = subprocess.Popen([str(self.python), '-m', 'gui_test.execution.host', '--config', str(self.config),
                                        '--runtime', str(self.runtime), '--port', '8771'], cwd=self.root, env=env,
                                       stdout=log, stderr=log, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            try:
                for _ in range(50):
                    if process.poll() is not None:
                        raise RuntimeError(f'실행기 시작 실패. 로그를 확인하세요: {log_path}')
                    try:
                        runner_get('/identity', env[TOKEN_ENV])
                        break
                    except (OSError, ValueError):
                        time.sleep(.1)
                else:
                    raise RuntimeError('실행기 준비 시간 초과. 로그를 확인하세요.')
                print('SSH 연결 후 브라우저에서 http://127.0.0.1:8766 을 여세요. 종료: Ctrl+C.')
                # SSH authentication remains OpenSSH's responsibility (key/agent/password).
                ssh_env = os.environ.copy()
                ssh_env.pop(TOKEN_ENV, None)
                transport = subprocess.Popen(tunnel, cwd=self.root, env=ssh_env,
                                             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                try:
                    while process.poll() is None and transport.poll() is None:
                        time.sleep(.2)
                    if process.poll() is not None:
                        raise RuntimeError(f'Windows 실행기가 종료됐습니다. 로그를 확인하세요: {log_path}')
                    if transport.returncode:
                        raise RuntimeError(f'SSH 연결이 종료됐습니다 (코드 {transport.returncode}). 서버/계정/포트 포워딩을 확인하세요.')
                finally:
                    if transport.poll() is None:
                        # Only the SSH transport can be forcibly closed; never the hardware runner.
                        transport.terminate()
                        try:
                            transport.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            transport.kill()
                            transport.wait()
            finally:
                self.stop_owned(process, windows=True)

    def menu(self):
        print('\nBSP 실제 연결 설정 — ' + ('Windows 보드 실행기' if self.windows else 'Linux 대시보드'))
        print(f'설정: {self.config}\n기록: {self.runtime}')
        print('처음에는 1 → 2 → 3. 다음에는 3만 선택합니다. 설정/토큰은 재입력하지 않습니다.')
        while True:
            print('\n1 연결 설정 / 변경\n2 의존성 설치' + ('' if self.windows else ' + 화면 빌드') +
                  '\n3 저장한 설정으로 실행\n4 실행기 연결 점검 (읽기 전용)\n5 인증 토큰 변경 / 확인\n6 이미지 자동 퓨징 설정\n0 종료')
            if not self.windows:
                print('7 빌드 이미지 manifest 생성 (파일 해시만 계산)')
            try:
                default = '1' if not self.config.exists() else ('2' if not self.python.is_file() else '3')
                choice = ask('선택', default, check=lambda x: x in ('0123456' if self.windows else '01234567') and len(x) == 1)
                if choice == '0':
                    return
                if choice == '5':
                    if self.tokens.path.exists() and yes('다른 PC에 옮기기 위해 저장한 토큰을 화면에 표시할까요?'):
                        print(self.tokens.load())
                    elif yes('토큰을 새로 등록/변경할까요?'):
                        self.token_setup()
                else:
                    {'1': self.connection, '2': self.install, '3': self.start, '4': self.check,
                     '6': self.flashing, '7': self.manifest}[choice]()
            except KeyboardInterrupt:
                print('\n이번 단계를 취소했습니다. 저장한 설정/실행 이력은 유지합니다.')
            except (OSError, ValueError, RuntimeError, KeyError) as error:
                # Do not echo authenticated HTTP response bodies or token contents.
                print(f'완료하지 못했습니다: {error}')

    def flashing(self):
        from scripts.setup_flashing import configure
        configure(self)

    def manifest(self):
        from scripts.setup_flashing import relative
        if not self.python.is_file():
            raise ValueError('먼저 메뉴 2에서 의존성을 설치하세요.')
        draft = read_json(self.config)
        if draft.get('runner') != 'windows-http':
            raise ValueError('먼저 메뉴 1에서 실제 연결을 설정하세요.')
        values = copy.deepcopy(draft.get('_setup', {}).get('manifest', {}))
        values['root'] = checked_path('Linux의 빌드 완료 이미지 폴더', values.get('root', ''), True)
        values['batch'] = ask('이미지 폴더 내 배치 상대 경로', values.get('batch', ''), check=relative)
        values['output'] = ask('새 manifest JSON의 절대 경로 (이미지 폴더 밖)', values.get('output', ''),
                               check=lambda x: Path(x).is_absolute() and not Path(x).exists() and
                               not Path(x).resolve().is_relative_to(Path(values['root'])))
        print(json.dumps(values, ensure_ascii=False, indent=2))
        if not yes('파일 해시를 계산해 새 manifest를 만들까요?'):
            return
        self.command([self.python, '-m', 'scripts.create_flash_manifest', '--root', values['root'],
                      '--batch', values['batch'], '--output', values['output']])
        draft.setdefault('_setup', {})['manifest'] = values
        save_json(self.config, draft)
        print('생성했습니다. BSP 환경 설정의 빌드 산출물 경로에 이 manifest를 등록하세요.\n'
              '빌드마다 새 manifest를 생성하도록 빌드 명령에 기존 생성기를 연결할 수 있습니다. 장비는 실행하지 않았습니다.')


def main():
    parser = argparse.ArgumentParser(description='Linux Dashboard / Windows runner interactive setup')
    parser.add_argument('--home', type=Path, help='Local setup/token directory (default: ~/.bsp-dashboard/<OS>)')
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error('Python 3.11 이상이 필요합니다.')
    if os.name != 'nt' and not sys.platform.startswith('linux'):
        parser.error('이 마법사는 Linux와 Windows를 지원합니다.')
    home = args.home.expanduser().resolve() if args.home else None
    if home and home.is_relative_to(ROOT):
        parser.error('토큰/개인 설정 폴더는 저장소 밖을 지정하세요.')
    try:
        if os.name != 'nt':
            def interrupted(signum, frame):
                raise KeyboardInterrupt
            signal.signal(signal.SIGTERM, interrupted)
            signal.signal(signal.SIGHUP, interrupted)
        Wizard(home=home).menu()
    except (KeyboardInterrupt, EOFError):
        print('\n종료했습니다.')
    return 0


if __name__ == '__main__':
    # Direct launch and python -m share the same repository imports.
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
