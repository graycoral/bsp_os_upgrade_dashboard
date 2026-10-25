"""The company's existing CLI supports COM arguments; its syntax is not invented here."""
from typing import Protocol, Callable
from gui_test.core.models import Connection, TestError


class Runner(Protocol):
    simulation: bool

    def execute(self, tc: dict, connections: dict, timeout: float, context: dict,
                emit: Callable, cancelled: Callable) -> dict: ...

    def probe(self, process_ref: str) -> str: ...


def resolve_argv(template, tc, connections):
    connection = Connection.model_validate(connections)
    dual = tc['kind'] == 'Dual'
    if dual and not connection.b:
        raise TestError('Dual TC requires Board B', status=422)
    required = {'{tc_path}', '{com_a}'} | ({'{com_b}'} if dual else set())
    if not template or any(template.count(slot) != 1 for slot in required):
        raise TestError('Register one complete argv slot per TC path and COM argument', status=422)
    values = {'{tc_path}': tc['path'], '{com_a}': connection.a.com}
    if dual:
        values['{com_b}'] = connection.b.com
    resolved = []
    for arg in template:
        if not isinstance(arg, str) or '\0' in arg or ('{' in arg and arg not in values):
            raise TestError('Unknown or embedded command placeholder', status=422)
        resolved.append(values.get(arg, arg))
    return resolved


class UnconfiguredRunner:
    simulation = False

    def execute(self, *args, **kwargs):
        raise TestError('Hardware execution disabled: register and verify the existing Single/Dual command adapter')

    def probe(self, process_ref):
        return 'UNKNOWN'
