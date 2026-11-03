"""Optional configuration only: no console, fastboot, batch or test is executed."""
import copy
import hashlib
from pathlib import Path, PurePosixPath
import re

from scripts.setup_runtime import ask, checked_path, number, read_json, runner_get, validate_boards, yes


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
    profile['fastboot'] = checked_path('fastboot.exe 절대 경로', profile.get('fastboot', ''))
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
    for board in draft['boards']:
        if not yes(f"{board['board_id']} ({board['com']}) 콘솔/퓨징 설정", board['board_id'] in console or len(draft['boards']) == 1):
            continue
        cfg = console.setdefault(board['board_id'], {})
        cfg['com'] = board['com']
        cfg['baudrate'] = number('확인한 baud rate', cfg.get('baudrate', ''), 1, 4000000)
        cfg['line_ending'] = ask('콘솔 개행 (cr / lf / crlf)', cfg.get('line_ending', ''), check=lambda x: x in ('cr', 'lf', 'crlf'))
        cfg['lkshell_prompt'] = ask('lkshell 준비 시 출력되는 정확한 문구', cfg.get('lkshell_prompt', ''))
        cfg['boot_marker'] = ask('정상 부팅/TC 준비 완료 시 출력되는 정확한 문구', cfg.get('boot_marker', ''))
        cfg['serial'] = ask('fastboot serial', cfg.get('serial', ''), check=lambda x: bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,160}', x)))
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
    token = wizard.tokens.load()
    boards = runner_get('/boards', token)['boards']
    tests = runner_get('/catalog', token)['tests']
    if not boards or not tests:
        raise ValueError('Windows 실행기/SSH 연결 후 등록 보드와 TC 목록을 먼저 확인하세요.')
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
    draft['url'] = 'http://127.0.0.1:8771'
    wizard.preview_save(path, draft)


def configure(wizard):
    print('이미지 퓨징 설정입니다. 설정만 저장하며 배치/보드/TC는 실행하지 않습니다.')
    if wizard.windows:
        windows(wizard)
    else:
        linux(wizard)
