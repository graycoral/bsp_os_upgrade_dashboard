"""Pure module membership and dependency ordering for a pinned TC catalog."""
import heapq
from collections import Counter
from pathlib import PurePosixPath
import re
import unicodedata


def _tokens(value):
    return tuple(re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', str(value)).casefold()))


def valid_memberships(value):
    return (isinstance(value, list) and 0 < len(value) <= 100 and
            all(isinstance(name, str) and 0 < len(name) <= 160 and _tokens(name) and
                not any(ord(char) < 32 or ord(char) == 127 for char in name) for name in value) and
            len({_tokens(name) for name in value}) == len(value))


def _path_matches(test, module_name):
    wanted = _tokens(module_name)
    if not wanted:
        return False
    path = PurePosixPath(str(test.get('path', '')).replace('\\', '/'))
    for part in (*path.parts[:-1], path.stem):
        words = _tokens(part)
        if any(words[index:index + len(wanted)] == wanted for index in range(len(words) - len(wanted) + 1)):
            return True
    return False


def belongs_to_module(test, module_name):
    if 'modules' in test:
        return valid_memberships(test['modules']) and _tokens(module_name) in {_tokens(name) for name in test['modules']}
    return _path_matches(test, module_name)


def resolve_module_tests(catalog, module_name, explicit_ids=None):
    """Return candidates only; a failure never falls back to the whole catalog."""
    def blocked(reason):
        return {'tests': [], 'tc_ids': [], 'blocked_reason': reason}

    if not isinstance(catalog, dict) or not isinstance(catalog.get('tests'), list):
        return blocked('TC 카탈로그 형식을 확인하세요.')
    tests = catalog['tests']
    if any(not isinstance(test, dict) or not isinstance(test.get('id'), str) or not test['id'] for test in tests):
        return blocked('TC 식별자 형식을 확인하세요.')
    by_id = {test['id']: test for test in tests}
    duplicate_ids = {identity for identity, count in Counter(test['id'] for test in tests).items() if count > 1}
    if explicit_ids is not None:
        if (not isinstance(explicit_ids, list) or not explicit_ids or len(explicit_ids) > 500 or
                any(not isinstance(identity, str) or not identity for identity in explicit_ids)):
            return blocked('자동 프로파일의 TC 매핑을 확인하세요.')
        ids = list(dict.fromkeys(explicit_ids))
        if any(identity not in by_id for identity in ids):
            return blocked('매핑한 TC가 현재 카탈로그에 없습니다.')
    else:
        for test in tests:
            if 'modules' in test and not valid_memberships(test['modules']):
                hints = test['modules'] if isinstance(test['modules'], list) else [test['modules']]
                if _path_matches(test, module_name) or any(isinstance(name, str) and _tokens(name) == _tokens(module_name) for name in hints):
                    return blocked('모듈 소속 메타데이터가 잘못된 TC가 있습니다.')
        ids = [test['id'] for test in tests if belongs_to_module(test, module_name)]
    if not ids:
        return blocked('이 모듈에 연결된 TC가 없습니다. modules 메타데이터 또는 정확한 모듈 이름의 경로를 확인하세요.')
    if len(ids) > 500:
        return blocked('모듈 TC 목록은 최대 500개입니다.')
    if duplicate_ids.intersection(ids):
        return blocked('모듈 TC 식별자가 중복되었습니다.')
    if any('modules' in by_id[identity] and not valid_memberships(by_id[identity]['modules']) for identity in ids):
        return blocked('모듈 소속 메타데이터가 잘못된 TC가 있습니다.')
    if any(by_id[identity].get('disabled_reason') for identity in ids):
        return blocked('실행할 수 없는 모듈 TC가 있습니다. TC 메타데이터를 확인하세요.')
    chosen = set(ids)
    before, following = {}, {identity: [] for identity in ids}
    for identity in ids:
        dependencies = by_id[identity].get('after', [])
        if (not isinstance(dependencies, list) or
                any(not isinstance(dep, str) or not dep for dep in dependencies) or
                len(dependencies) != len(set(dependencies))):
            return blocked('TC 선행 조건 형식을 확인하세요.')
        for dependency in dependencies:
            if dependency not in by_id:
                return blocked('필수 선행 TC가 카탈로그에 없습니다.')
            if dependency not in chosen:
                return blocked('다른 모듈 또는 매핑 밖의 선행 TC가 필요합니다. 명시적 매핑을 확인하세요.')
            following[dependency].append(identity)
        before[identity] = len(dependencies)
    order = {identity: index for index, identity in enumerate(ids)}
    ready = [(order[identity], identity) for identity in ids if not before[identity]]
    heapq.heapify(ready)
    resolved = []
    while ready:
        _, identity = heapq.heappop(ready)
        resolved.append(identity)
        for child in following[identity]:
            before[child] -= 1
            if not before[child]:
                heapq.heappush(ready, (order[child], child))
    if len(resolved) != len(ids):
        return blocked('TC 선행 조건에 순환이 있습니다.')
    return {'tests': [by_id[identity] for identity in resolved], 'tc_ids': resolved, 'blocked_reason': None}
