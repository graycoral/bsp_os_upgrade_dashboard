"""RQ-60 / T-202, T-206: plugin selection and trial policy; synthetic catalogs only."""
import copy

import pytest

from backend.gui_test.core.integration import resolve_patterns, select_patterns, validate_patterns
from backend.gui_test.core.models import TestError
from backend.gui_test.core.repetition import integration_decision


def case(identity, path=None, **changes):
    return {'id': identity, 'path': path or identity, 'name': identity, 'kind': 'Single',
            'timeout': 10, 'after': [], 'disabled_reason': '', **changes}


def catalog(*tests):
    return {'revision': 'fixed-fixture', 'tests': list(tests)}


def test_exact_module_defaults_and_user_edits_are_distinct_from_global_fallback():
    modules = {'ethernet': ['test/network/*.py']}
    global_defaults = ['test/global/*.py']
    before = copy.deepcopy(modules)
    assert resolve_patterns('ethernet', modules, global_defaults) == modules['ethernet']
    assert resolve_patterns('Ethernet', modules, global_defaults) == global_defaults
    assert resolve_patterns('ethernet', modules, global_defaults, ['test/edited/*.py']) == ['test/edited/*.py']
    assert modules == before


@pytest.mark.parametrize('patterns', [[], [''], ['../escape.py'], ['/root/case.py'],
    ['C:/case.py'], ['test\\case.py'], ['test/../case.py'], ['$(whoami).py'],
    ['`whoami`.py'], ['test/\x00.py'], ['test/\n.py'], ['x' * 1025], ['*.py'] * 101])
def test_unsafe_or_unbounded_patterns_are_rejected(patterns):
    with pytest.raises(TestError):
        validate_patterns(patterns)


@pytest.mark.parametrize('mapped', [[], ['../escape.py']])
def test_invalid_explicit_module_mapping_never_silently_uses_global_defaults(mapped):
    with pytest.raises(TestError):
        resolve_patterns('ethernet', {'ethernet': mapped}, ['*.py'])


def test_globs_filter_catalog_paths_with_linux_case_and_component_semantics():
    source = catalog(case('root-id', 'test/root.py'), case('nested-id', 'test/sub/deep.py'),
                     case('case-sensitive-id', 'Test/upper.py'), case('text-id', 'test/data.txt'))
    before = copy.deepcopy(source)
    assert [t['id'] for t in select_patterns(source, ['test/*.py'])] == ['root-id']
    assert {t['id'] for t in select_patterns(source, ['test/**/*.py'])} == {'root-id', 'nested-id'}
    assert source == before


def test_union_deduplicates_identity_and_sorts_dependencies_without_expanding_scope():
    source = catalog(case('dependent', 'test/network/link.py', after=['setup']),
                     case('setup', 'test/shared/setup.py'), case('unrelated', 'video.py'))
    chosen = select_patterns(source, ['test/**/*.py', 'test/network/*.py'])
    assert [t['id'] for t in chosen] == ['setup', 'dependent']
    with pytest.raises(TestError):
        select_patterns(source, ['test/network/*.py'])


@pytest.mark.parametrize('source,patterns', [
    (catalog(case('a.py')), ['no-match/*.py']),
    (catalog(case('a.py', disabled_reason='Not runnable')), ['*.py']),
    (catalog(case('a.py', after=['missing.py'])), ['*.py']),
    (catalog(case('a.py', after=['b.py']), case('b.py', after=['a.py'])), ['*.py']),
])
def test_empty_disabled_and_invalid_dependency_selections_fail_closed(source, patterns):
    with pytest.raises(TestError):
        select_patterns(source, patterns)


@pytest.mark.parametrize('states,expected', [
    ([], 'RETRY'), (['PASS'], 'PASS'), (['FAIL'], 'RETRY'),
    (['FAIL', 'PASS'], 'RETRY'), (['FAIL', 'PASS', 'PASS'], 'PASS'),
    (['FAIL', 'PASS', 'FAIL'], 'FAIL'), (['FAIL', 'FAIL'], 'FAIL'),
    (['ERROR'], 'ABORT'), (['TIMEOUT'], 'ABORT'), (['UNKNOWN'], 'ABORT'),
    (['FAIL', 'UNKNOWN'], 'ABORT'),
])
def test_trial_policy_first_pass_or_two_of_three_and_non_retryable_uncertainty(states, expected):
    before = states[:]
    assert integration_decision(states) == expected
    assert states == before
