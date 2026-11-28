"""Resolve a path in a frozen Linux source on the Windows board connector."""
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Literal
import re
import shutil

from pydantic import Field

from ..core.models import Connection, StrictModel, TestError, digest
from .source_snapshots import load_manifest, safe_name


class PathRunRequest(StrictModel):
    tc_path: str = Field(min_length=1, max_length=1024)
    source_snapshot_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_revision: str = Field(min_length=1, max_length=256)
    expected_plan_revision: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    execution_mode: Literal['tc_only', 'flash_and_test'] = 'tc_only'
    installer: dict | None = None
    connection: Connection | None = None
    origin: dict = Field(default_factory=dict)


def suite_group(name):
    group, separator, _ = name.partition('/')
    return group if separator and group in {'python3', 'dual_board', 'linux'} else None


def is_adb_tc(name):
    return suite_group(name) == 'linux' and name.endswith(('.sh', '.py'))


def plan_path(host, request):
    manifest = load_manifest(host.runtime / 'source-snapshots' / request.source_snapshot_id,
                             request.source_snapshot_id)
    if manifest['source_revision'] != request.source_revision:
        raise TestError('TC source revision changed', 'SOURCE_CHANGED', 409)
    target = request.tc_path
    if target != '.':
        safe_name(target)
    paths = sorted(name for name in manifest['files']
                   if (target == '.' or name == target or name.startswith(target + '/'))
                   and (is_adb_tc(name) or (suite_group(name) and name.endswith('.py')))
                   and Path(name).name != '__init__.py')
    if not 1 <= len(paths) <= 2000:
        raise TestError('테스트 경로에서 1~2000개의 .py 또는 .sh TC를 지정하세요.', 'TC_SELECTION', 422)
    settings = host.path_run
    boards = {b['board_id']: b for b in host.configured_boards}
    primary = settings.get('board_a') or (next(iter(boards)) if len(boards) == 1 else None)
    if primary not in boards:
        raise TestError('커넥터의 path_run.board_a에서 대상 보드를 지정하세요.', 'BOARD_MISMATCH', 422)
    connection = {'a': boards[primary]}
    tests = []
    for path in paths:
        meta = manifest['metadata'].get(path, {})
        kind = 'Dual' if suite_group(path) == 'dual_board' else 'Single'
        if kind == 'Dual':
            secondary = settings.get('board_b')
            if secondary not in boards or secondary == primary:
                raise TestError('Dual TC에는 서로 다른 board_a와 board_b가 필요합니다.', 'BOARD_MISMATCH', 422)
            connection['b'] = boards[secondary]
        tests.append({'tc_id': meta.get('id', path), 'path': path, 'kind': kind,
                      'after': meta.get('after', [])})
    # Within this path execute prerequisites first. Never expand to an unrequested path.
    ordered = TopologicalSorter()
    by_id = {tc['tc_id']: tc for tc in tests}
    if len(by_id) != len(tests):
        raise TestError('Duplicate TC identity in path', 'TC_NOT_FOUND', 422)
    for tc in tests:
        if any(dep not in by_id for dep in tc['after']):
            raise TestError('선택한 경로에 선행 TC가 없습니다.', 'INVALID_TC_ORDER', 422)
        ordered.add(tc['tc_id'], *tc['after'])
    try:
        steps = [by_id[key] | {'step_index': i} for i, key in enumerate(ordered.static_order())]
    except CycleError as exc:
        raise TestError('선행 TC 순환 의존성입니다.', 'INVALID_TC_ORDER', 422) from exc
    template = settings.get('python_command') or {
        'single': ['python', '{tc_path}', '--com', '{com_a}'],
        'dual': ['python', '{tc_path}', '--a', '{com_a}', '--b', '{com_b}'],
    }
    return {'execution_mode': 'tc_only', 'tests': steps, 'connection': connection,
            'command_snapshot': {'name': 'connector', 'revision': digest(template), 'template': template},
            'source_snapshot_id': request.source_snapshot_id, 'source_revision': request.source_revision,
            'origin': request.origin}


def adb_target(host, board_id):
    settings = host.path_run
    mapping = settings.get('adb_serials') or {}
    serial = mapping.get(board_id)
    if not isinstance(serial, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:\-]{0,159}', serial) or list(mapping.values()).count(serial) != 1:
        raise TestError('보드에 고유한 ADB serial을 설정하세요.', 'ADB_SERIAL_REQUIRED', 422)
    adb = shutil.which(settings.get('adb_path') or 'adb')
    if not adb:
        raise TestError('Windows 커넥터에서 adb 실행 파일을 찾을 수 없습니다.', 'ADB_NOT_CONFIGURED', 422)
    return str(Path(adb).resolve()), serial
