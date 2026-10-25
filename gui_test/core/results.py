"""Never infer a verdict from an arbitrary PASS word or from a running process."""
import re

PARSER_REVISION = 'strict-result-line-v1'
LINE = re.compile(r'^Test Result: (PASS|FAIL)$', re.MULTILINE)


def parse_result(stdout, stderr, exit_code, *, terminated=True, allowed_codes=(0,), allow_repeated=False):
    if not terminated:
        return 'UNKNOWN', 'Process termination is unverified', None
    matches = LINE.findall((stdout + '\n' + stderr).replace('\r\n', '\n'))
    if exit_code not in allowed_codes:
        return 'ERROR', f'Unexpected exit code: {exit_code}', None
    if not matches or len(set(matches)) != 1 or (len(matches) != 1 and not allow_repeated):
        return 'ERROR', 'Expected exactly one unambiguous Test Result: PASS|FAIL line', None
    return matches[-1], 'Verified final result line and exit code', 'Test Result: ' + matches[-1]


def aggregate(states):
    if not states or any(s not in {'PASS', 'FAIL'} for s in states):
        return 'INCOMPLETE'
    return 'FAIL' if 'FAIL' in states else 'PASS'


def progress(run):
    states = [run['results'].get(tc['id'], 'PENDING') for tc in run['tests']]
    counts = {s: states.count(s) for s in ('PASS', 'FAIL', 'RUNNING', 'PENDING', 'ERROR', 'TIMEOUT', 'UNKNOWN', 'CANCELLED')}
    done = counts['PASS'] + counts['FAIL']
    return {'done': done, 'total': len(states), 'percent': round(100 * done / len(states), 1), 'counts': counts}


def module_results(run, mapping):
    if run['state'] != 'COMPLETED' or run['overall_result'] not in {'PASS', 'FAIL'}:
        return {}, 'Entire run must have a final PASS/FAIL verdict'
    result = {}
    for module in mapping['modules']:
        cases = {}
        for case, tc_ids in module['required_cases'].items():
            if not tc_ids or len(set(tc_ids)) != len(tc_ids):
                break
            state = aggregate([run['results'].get(tc_id, 'PENDING') for tc_id in tc_ids])
            if state == 'INCOMPLETE':
                break
            cases[case] = state
        if len(cases) == len(module['required_cases']) and cases:
            result[module['module_key']] = cases
    return result, '' if result else 'Required mapped cases are missing or invalid'
