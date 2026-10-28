import time
from pathlib import Path
from gui_test.core.discovery import discover
from gui_test.core.models import Connection, TestError
from gui_test.adapters.runner import resolve_argv


class MockBoards:
    simulation = True

    def boards(self):
        return [{'board_id': 'demo-board-a', 'host': 'demo-windows', 'com': 'COM3'},
                {'board_id': 'demo-board-b', 'host': 'demo-windows', 'com': 'COM4'}]

    def verify(self, connection, dual):
        c = Connection.model_validate(connection)
        selected = [c.a] + ([c.b] if dual else [])
        if any(board is None or board.model_dump() not in self.boards() for board in selected):
            raise TestError('Board identity/host/COM does not match the mock directory', 'BOARD_MISMATCH')


def demo_catalog(branch='demo/main'):
    if branch not in ('demo/main', 'demo/next'):
        raise TestError('Unknown demo branch', status=422)
    catalog = discover(Path(__file__).resolve().parents[1] / 'demo' / 'tc')
    catalog['revision'] += '-' + branch.split('/')[-1]
    catalog['branch'] = branch
    return catalog


class MockRunner:
    simulation = True

    def probe(self, process_ref):
        return 'STOPPED' if process_ref.startswith('mock:') else 'UNKNOWN'

    def execute(self, tc, connections, timeout, context, emit, cancelled):
        # The template is evidence only: Mock never invokes a subprocess.
        argv = context.get('resolved_command_argv')
        if argv is None:
            argv = resolve_argv(['mock-tc', '{tc_path}', '{com_a}'] + (['{com_b}'] if tc['kind'] == 'Dual' else []), tc, connections)
        emit('stdout', 'MOCK ONLY · ' + repr(argv) + '\n')
        start = time.monotonic()
        duration = .6 / context['speed']
        while time.monotonic() - start < duration:
            if cancelled():
                return {'exit_code': -1, 'terminated': True, 'forced_state': 'CANCELLED'}
            if time.monotonic() - start >= timeout:
                return {'exit_code': -1, 'terminated': True, 'forced_state': 'TIMEOUT'}
            time.sleep(.01)
        fault = context['fault']
        if fault in {'disconnect', 'timeout', 'unknown'}:
            emit('stderr', 'Injected mock ' + fault + '\n')
            return {'exit_code': None, 'terminated': fault != 'unknown',
                    'forced_state': {'disconnect': 'ERROR', 'timeout': 'TIMEOUT', 'unknown': 'UNKNOWN'}[fault]}
        emit('stdout', 'Test Result: ' + ('FAIL' if fault == 'fail' else 'PASS') + '\n')
        return {'exit_code': 0, 'terminated': True}
