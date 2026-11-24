"""Immutable execution slots separate planned repetitions from recovery attempts."""
def integration_decision(states):
    """Logical verdict for a single plugin TC; raw Attempts remain immutable."""
    if not states:
        return 'RETRY'
    if any(state not in {'PASS', 'FAIL'} for state in states) or len(states) > 3:
        return 'ABORT'
    if states[0] == 'PASS':
        return 'PASS'
    if states.count('PASS') >= 2:
        return 'PASS'
    if len(states) >= 3 or states.count('PASS') + 3 - len(states) < 2:
        return 'FAIL'
    return 'RETRY'


def execution_plan(tests, repeats, cycles):
    return [{'tc_id': t['id'], 'cycle': cycle, 'iteration': iteration}
            for cycle in range(1, cycles + 1) for t in tests
            for iteration in range(1, repeats.get(t['id'], 1) + 1)]


def slot_states(run):
    if 'plan' not in run:
        return [run['results'].get(t['id'], 'PENDING') for t in run['tests']]
    return [run.get('slot_results', {}).get(str(i), 'PENDING') for i in range(len(run['plan']))]


def record_result(run, attempt, state):
    tc_id = attempt['tc_id']
    if 'plan' not in run:
        run['results'][tc_id] = state
        return
    run.setdefault('slot_results', {})[str(attempt['slot_index'])] = state
    states = [run['slot_results'].get(str(i), 'PENDING') for i, slot in enumerate(run['plan']) if slot['tc_id'] == tc_id]
    # A later successful repetition cannot erase a previous failed repetition.
    for candidate in ('RUNNING', 'UNKNOWN', 'ERROR', 'TIMEOUT', 'CANCELLED', 'FAIL', 'PENDING'):
        if candidate in states:
            run['results'][tc_id] = candidate
            return
    run['results'][tc_id] = 'PASS'
