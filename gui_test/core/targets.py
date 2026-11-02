"""Execution destination comes from the runner, never the currently selected UI profile."""
def normalize_target(value, connection, dual):
    if not isinstance(value, dict):
        raise ValueError('Execution target must be an object')
    if value.get('kind') == 'local':
        if value.get('boards'):
            raise ValueError('Local execution cannot report connected boards')
        return {'kind': 'local'}
    if value.get('kind') != 'board' or not isinstance(value.get('boards'), list):
        raise ValueError('Unknown execution target')
    roles = ['a', 'b'] if dual else ['a']
    if len(value['boards']) != len(roles):
        raise ValueError('Execution target must cover the actual Single/Dual boards')
    boards = []
    for role, board in zip(roles, value['boards']):
        pinned = connection.get(role)
        if not isinstance(board, dict) or board.get('role') != role or not pinned:
            raise ValueError('Unexpected board role')
        if any(board.get(field) != pinned[field] for field in ('board_id', 'host', 'com')):
            raise ValueError('Execution board differs from the pinned connection')
        name = board.get('board_name')
        if not isinstance(name, str) or not name.strip() or len(name) > 160 or any(ord(c) < 32 for c in name):
            raise ValueError('Verified board name required')
        boards.append({'role': role, 'board_name': name, **{field: pinned[field] for field in ('board_id', 'host', 'com')}})
    return {'kind': 'board', 'boards': boards}


def target_summary(attempts):
    labels = []
    for attempt in attempts:
        target = attempt.get('execution_target')
        if not target:
            continue
        label = 'local' if target['kind'] == 'local' else ' / '.join(b['role'].upper()+': '+b['board_name'] for b in target['boards'])
        if label not in labels:
            labels.append(label)
    return {'labels': labels, 'incomplete': not attempts or any(not a.get('execution_target') for a in attempts)}
