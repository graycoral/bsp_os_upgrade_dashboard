"""Optional configuration; only read-only fastboot devices discovery is executed."""
import copy
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

from scripts.setup_runtime import ask, checked_path, number, read_json, runner_get, validate_boards, yes
from backend.gui_test.execution.bundle import external_environment, external_dll_search


CONSOLE_FIELDS = ('baudrate', 'line_ending', 'lkshell_prompt', 'boot_marker', 'login_prompt')


def lkshell_marker(value):
    return bool(value.strip()) and value.strip().lower() not in ('reboot lkshell', 'fast', 'fastboot init success')


def find_fastboot(saved=''):
    """Reuse the configured executable, then search PATH and standard SDK locations."""
    candidates = [saved, shutil.which('fastboot.exe'), shutil.which('fastboot')]
    for key in ('ANDROID_SDK_ROOT', 'ANDROID_HOME'):
        if os.environ.get(key):
            candidates.append(Path(os.environ[key]) / 'platform-tools' / 'fastboot.exe')
    if os.environ.get('LOCALAPPDATA'):
        candidates.append(Path(os.environ['LOCALAPPDATA']) / 'Android' / 'Sdk' / 'platform-tools' / 'fastboot.exe')
    for value in candidates:
        if value:
            path = Path(value).expanduser()
            if path.suffix.lower() == '.exe' and path.is_file():
                return str(path.resolve())
    return ''


def fastboot_devices(executable):
    """Never switch modes, wipe, flash or reboot during setup."""
    env = {key: value for key, value in external_environment().items() if key.upper() != 'ANDROID_SERIAL'}
    try:
        with external_dll_search():
            result = subprocess.run([executable, 'devices'], shell=False, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=10, env=env)
    except (OSError, subprocess.TimeoutExpired):
        print('fastboot 장치 조회 실패/시간 초과. 드라이버·USB·fastboot 모드를 확인하거나 serial을 직접 입력하세요.')
        return []
    if result.returncode or len(result.stdout) > 65536:
        print('fastboot 장치 조회 실패. serial을 직접 입력할 수 있습니다.')
        return []
    devices = []
    for line in result.stdout.decode('utf-8', errors='replace').splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == 'fastboot' and re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', fields[0]):
            if fields[0] not in devices:
                devices.append(fields[0])
    print('조회된 fastboot 장치:', ', '.join(devices) or '(없음: fastboot 모드에서만 조회됩니다)')
    return devices


def console_settings(previous):
    print('공통 콘솔 설정: 명령은 reboot lkshell → 준비 출력 확인 → fast 순서로 고정되어 있습니다.\n'
          '권장 개행 cr은 Enter에 해당합니다. 기존 저장값은 유지하며 필요하면 lf/crlf로 변경하세요.\n'
          'lkshell 준비 문구에는 명령어가 아니라 명령 실행 후 나타나는 프롬프트를 입력하세요.\n'
          'fastboot init success는 fast 이후 출력입니다. 실제 fastboot 장치/serial로 진입을 확인합니다.\n'
          '자동 리부팅 후 **** login : 출력은 login : 부분으로 확인합니다. 마지막 줄일 필요는 없습니다.\n'
          '퓨징 후 root 로그인은 TC가 담당합니다. Runner가 먼저 로그인하지 않습니다.')
    prompt = previous.get('lkshell_prompt', '')
    if prompt and not lkshell_marker(prompt):
        print('기존 lkshell 준비 문구가 명령어 또는 fast 이후 출력입니다. fast 이전의 실제 출력으로 바로잡아 주세요.')
        prompt = ''
    return {
        'baudrate': number('공통 baud rate (기존 콘솔 설정 확인)', previous.get('baudrate') or 115200, 1, 4000000),
        'line_ending': ask('공통 콘솔 개행 (cr / lf / crlf)', previous.get('line_ending') or 'cr',
                           check=lambda x: x in ('cr', 'lf', 'crlf')),
        'lkshell_prompt': ask('lkshell 진입 후 실제 출력되는 준비 문구 (명령어 아님)', prompt,
                             check=lkshell_marker),
        'boot_marker': ask('정상 부팅/TC 준비 완료 시 실제 출력되는 문구', previous.get('boot_marker') or 'login :'),
        'login_prompt': previous.get('login_prompt') or 'login :',
    }


def board_serial(board, previous, devices, single):
    if single and len(devices) == 1 and (not previous or previous == devices[0]):
        print(f"{board['board_id']} fastboot serial 자동 선택: {devices[0]}")
        return devices[0]
    if devices:
        print('여러 보드의 COM↔USB 대응은 목록 순서로 추정하지 않습니다. 대상 보드의 serial을 선택하세요.')
        for index, serial in enumerate(devices, 1):
            print(f'{index}. {serial}')
        if yes('조회 목록에서 serial을 선택할까요?', True):
            default = devices.index(previous) + 1 if previous in devices else 1
            return devices[number('대상 보드의 fastboot 장치 번호', default, 1, len(devices)) - 1]
    return ask('fastboot serial (기존값 유지 또는 직접 입력)', previous,
               check=lambda x: bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', x)))


def relative(value):
    if not value or '\\' in value or ':' in value or PurePosixPath(value).is_absolute():
        return False
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(10)), *('LPT'+str(i) for i in range(10))}
    return all(part not in ('', '.', '..') and bool(re.fullmatch(r'[A-Za-z0-9_ .-]+', part)) and
               not part.endswith((' ', '.')) and part.split('.')[0].upper() not in reserved for part in value.split('/'))


def windows(wizard):
    draft = read_json(wizard.config)
    if not draft.get('boards'):
        raise ValueError('먼저 연결 설정에서 보드를 등록하세요.')
    profiles = draft.setdefault('flashing', {}).setdefault('profiles', {})
    print('기존 프로파일:', ', '.join(profiles) or '(없음)')
    name = ask('퓨징 프로파일 이름', next(iter(profiles), 'board-flash'), check=lambda x: bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', x)))
    profile = copy.deepcopy(profiles.get(name, {}))
    if profile and yes('이 프로파일을 비활성화할까요?'):
        profile['enabled'] = False
        profiles[name] = profile
        wizard.preview_save(wizard.config, draft)
        return
    profile['image_root'] = checked_path('Windows에서 여는 공유 이미지 루트', profile.get('image_root', ''), True)
    image_root = Path(profile['image_root'])
    if image_root.is_relative_to(wizard.runtime.resolve()) or wizard.runtime.resolve().is_relative_to(image_root):
        raise ValueError('이미지 루트와 실행 기록 폴더는 분리해야 합니다.')
    profile['fastboot'] = find_fastboot(profile.get('fastboot', ''))
    if profile['fastboot']:
        print('사용할 fastboot:', profile['fastboot'])
    else:
        profile['fastboot'] = checked_path('fastboot.exe 경로 (자동 탐색 실패)', '')
    if Path(profile['fastboot']).suffix.lower() != '.exe':
        raise ValueError('장치 조회에는 fastboot.exe 실행 파일이 필요합니다. 배치/셸 파일은 사용할 수 없습니다.')
    devices = fastboot_devices(profile['fastboot'])
    batch = checked_path('검토한 .bat 파일 경로 (해시만 계산)', profile.get('_setup_batch', ''))
    if Path(batch).suffix.lower() != '.bat':
        raise ValueError('.bat 파일을 지정하세요.')
    profile['_setup_batch'] = batch
    with open(batch, 'rb') as stream:
        profile['batch_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    profile['success_marker'] = ask('배치 전체 성공 시 출력되는 정확한 문구', profile.get('success_marker', ''))
    markers = ask('실패 문구 목록 (|로 구분)', '|'.join(profile.get('failure_markers', ['FAILED', 'fastboot: error:'])))
    profile['failure_markers'] = [part.strip() for part in markers.split('|') if part.strip()]
    if not profile['failure_markers']:
        raise ValueError('실패 문구를 하나 이상 입력하세요.')
    console = copy.deepcopy(profile.get('boards', {}))
    registered = {board['board_id'] for board in draft['boards']}
    removed = set(console) - registered
    if removed:
        print('현재 등록에서 제거된 콘솔 매핑을 정리합니다:', ', '.join(sorted(removed)))
        console = {key: value for key, value in console.items() if key in registered}
    previous = profile.get('console_defaults') or next(iter(console.values()), {})
    common = console_settings(previous)
    profile['console_defaults'] = common
    for board in draft['boards']:
        if not yes(f"{board['board_id']} ({board['com']}) 콘솔/퓨징 설정", board['board_id'] in console or len(draft['boards']) == 1):
            continue
        cfg = console.setdefault(board['board_id'], {})
        cfg['com'] = board['com']
        if any(key in cfg and cfg[key] != common[key] for key in CONSOLE_FIELDS):
            print(f"{board['board_id']}: 기존 보드별 콘솔 값이 공통값과 다릅니다.")
            if yes('이 보드에도 새 공통값을 적용할까요?', True):
                cfg.update(common)
            else:
                cfg.update(console_settings(cfg))
        else:
            cfg.update(common)
        cfg['serial'] = board_serial(board, cfg.get('serial', ''), devices, len(draft['boards']) == 1)
    if not console:
        raise ValueError('콘솔 보드를 하나 이상 설정하세요.')
    serials = [cfg['serial'] for cfg in console.values()]
    if len(serials) != len(set(serials)):
        raise ValueError('fastboot serial이 중복되었습니다.')
    profile['boards'] = console
    for key, label, default in [('console_timeout', '콘솔 준비', 120), ('fastboot_timeout', 'fastboot 준비', 60),
                                ('flash_timeout', '배치 퓨징', 1800), ('boot_timeout', '부팅 준비', 180)]:
        profile[key] = number(label + ' 제한 시간(초)', profile.get(key, default), 1, 7200)
    print('배치는 고정 대상(ANDROID_SERIAL)과 도구(BSP_FASTBOOT)를 사용하고, 실패를 종료 코드로 전달해야 합니다.\n'
          '대화형 pause/start나 공유 폴더의 미고정 외부 파일 의존성이 있으면 먼저 배치를 조정하세요.')
    profile['enabled'] = yes('배치 검토와 실제 콘솔 값을 확인했으며, 이 프로파일의 자동 실행을 허용할까요?')
    profiles[name] = profile
    wizard.preview_save(wizard.config, draft)


def choose_board(boards, label, old=None):
    for i, board in enumerate(boards, 1):
        print(f"{i}. {board['board_id']} / {board['host']} / {board['com']} / {board.get('node', '-')}")
    default = next((i for i, board in enumerate(boards, 1) if board == old), 1)
    return boards[number(label, default, 1, len(boards)) - 1]


def check_cases(cases, tests, connection, template=None):
    selected = list(dict.fromkeys(tc for group in cases.values() for tc in group))
    available = {t['id']: t for t in tests}
    if not cases or any(not group for group in cases.values()):
        raise ValueError('모든 필수 사례에 TC가 필요합니다.')
    if len(cases) > 100 or len(selected) > 100:
        raise ValueError('자동 시험은 최대 100개 사례/고유 TC를 지원합니다.')
    dual = template['dual'] if template else ['{node_a}', '{node_b}']
    needs_nodes = any('{node_a}' in arg or '{node_b}' in arg for arg in dual)
    for index, tc in enumerate(selected):
        if tc not in available or available[tc].get('disabled_reason'):
            raise ValueError('실행 가능한 TC를 선택하세요: ' + tc)
        test = available[tc]
        if any(dep not in selected[:index] for dep in test.get('after', [])):
            raise ValueError('선행 TC를 앞에 배치하세요: ' + tc)
        if test['kind'] == 'Dual' and (not connection.get('b') or (needs_nodes and (not connection['a'].get('node') or not connection['b'].get('node')))):
            raise ValueError('Dual TC에는 서로 다른 두 보드와 각 노드명이 필요합니다.')


def linux(wizard):
    path = wizard.runtime / 'device-test.json'
    draft = read_json(path)
    modules = draft.setdefault('modules', {})
    print('기존 모듈:', ', '.join(modules) or '(없음)')
    name = ask('BSP에 등록한 정확한 모듈 이름', next(iter(modules), ''))
    module = copy.deepcopy(modules.get(name, {}))
    if module and yes('이 모듈의 자동 퓨징/TC를 비활성화할까요?'):
        module['enabled'] = False
        modules[name] = module
        wizard.preview_save(path, draft)
        return
    token = None
    def query(route):
        if wizard.effective_runner_port == 8771:
            return runner_get(route, token)
        return runner_get(route, token, wizard.effective_runner_port)
    boards = query('/boards')['boards']
    tests = query('/catalog')['tests']
    if not boards or not tests:
        raise ValueError('TEST BOARD CONNECTOR/SSH 연결 후 등록 보드와 TC 목록을 먼저 확인하세요.')
    module['profile'] = ask('Windows에 저장한 퓨징 프로파일 이름', module.get('profile', 'board-flash'), check=lambda x: bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', x)))
    module['bundle'] = ask('image_root 아래 빌드 이미지 상대 폴더', module.get('bundle', ''), check=relative)
    connection = module.get('connection', {})
    a = choose_board(boards, '보드 A 번호', connection.get('a'))
    b = None
    if yes('Dual 보드인가요?', bool(connection.get('b'))):
        remaining = [board for board in boards if board != a]
        if not remaining:
            raise ValueError('두 번째 등록 보드가 없습니다.')
        b = choose_board(remaining, '보드 B 번호', connection.get('b'))
    validate_boards([a] + ([b] if b else []))
    module['connection'] = {'a': a, 'b': b}
    previous = module.get('cases', {})
    names = [part.strip() for part in ask('필수 사례 이름 (쉼표로 구분, BSP 시험 계획과 일치)', ','.join(previous) or 'boot,functional').split(',')]
    if not all(names) or len(names) != len(set(names)):
        raise ValueError('사례 이름은 비어 있거나 중복되면 안 됩니다.')
    for i, test in enumerate(tests, 1):
        print(f"{i}. {test['id']} [{test['kind']}] {test.get('disabled_reason', '')}")
    cases = {}
    for case in names:
        default = ','.join(str(i) for tc in previous.get(case, []) for i, test in enumerate(tests, 1) if test['id'] == tc)
        indices = ask(f'{case}의 TC 번호 (실행 순서대로 쉼표 구분)', default)
        if not all(part.strip().isdecimal() and 1 <= int(part.strip()) <= len(tests) for part in indices.split(',')):
            raise ValueError('목록에 있는 TC 번호를 입력하세요.')
        cases[case] = list(dict.fromkeys(tests[int(part.strip())-1]['id'] for part in indices.split(',')))
    module['cases'] = cases
    module.setdefault('template', {'single': ['python3', '{tc_path}', '-p', '{com_a}'],
                                   'dual': ['python3', '{tc_path}', '-n', '{node_a}', '-n2', '{node_b}']})
    check_cases(cases, tests, module['connection'], module['template'])
    print('이미지 manifest는 빌드 산출물로 등록해야 합니다. 저장만으로 이미지를 생성하거나 보드에 쓰지는 않습니다.\n'
          '활성화 후 worker를 다시 시작하면 조건을 충족한 대기 작업에도 퓨징/TC가 배정될 수 있습니다.')
    module['enabled'] = yes('이 모듈의 자동 퓨징/TC를 활성화할까요?')
    modules[name] = module
    # Do not implicitly activate previously dormant enabled modules under a disabled master.
    if module['enabled'] and draft.get('enabled') is not True:
        other = [key for key, value in modules.items() if key != name and value.get('enabled') is True]
        if other:
            print('전체 활성화 시 함께 동작할 기존 모듈:', ', '.join(other))
            if not yes('나열한 기존 모듈까지 활성화할까요?'):
                print('변경하지 않았습니다.')
                return
        draft['enabled'] = True
    draft.setdefault('enabled', False)
    draft['url'] = wizard.runner_url
    wizard.preview_save(path, draft)


def configure(wizard):
    print('이미지 퓨징 설정입니다. Windows에서 fastboot devices로 장치 목록만 조회하며, 콘솔 명령/배치/TC는 실행하지 않습니다.')
    if wizard.windows:
        windows(wizard)
    else:
        linux(wizard)
