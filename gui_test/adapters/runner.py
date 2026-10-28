"""The company's existing CLI supports COM arguments; its syntax is not invented here."""
from pathlib import PurePosixPath
from typing import Protocol, Callable
from pydantic import ValidationError
from gui_test.core.models import CommandTemplate, Connection, TestError


class Runner(Protocol):
    simulation: bool

    def execute(self, tc: dict, connections: dict, timeout: float, context: dict,
                emit: Callable, cancelled: Callable) -> dict: ...

    def probe(self, process_ref: str) -> str: ...


TC_SLOTS = {'{tc_path}', '{tc_name}', '{tc_file}'}
COM_SLOTS = {'{com_a}', '{com_b}'}


def default_command_template():
    return {'single': ['mock-tc', '{tc_path}', '{com_a}'],
            'dual': ['mock-tc', '{tc_path}', '{com_a}', '{com_b}']}


def validate_argv_template(template, dual):
    if (not isinstance(template, list) or not 3 <= len(template) <= 64 or
            any(not isinstance(arg, str) or not arg or len(arg) > 4096 or
                any(ch in arg for ch in '\0\r\n') for arg in template)):
        raise TestError('Command must be 3–64 nonempty argv entries, at most 4096 characters each, without line breaks/NUL', status=422)
    if sum(map(len, template)) > 16384:
        raise TestError('Command template is too long', status=422)
    if '{' in template[0] or '}' in template[0]:
        raise TestError('Executable must be a fixed argv entry', status=422)
    if sum(template.count(slot) for slot in TC_SLOTS) != 1 or template.count('{com_a}') != 1:
        raise TestError('Register exactly one TC placeholder and one {com_a} argv entry', status=422)
    if template.count('{com_b}') != (1 if dual else 0):
        raise TestError('Dual requires one {com_b}; Single must not contain {com_b}', status=422)
    for arg in template:
        if ('{' in arg or '}' in arg) and arg not in TC_SLOTS | COM_SLOTS:
            raise TestError('Unknown or embedded command placeholder; use one whole argv entry', status=422)
    return list(template)


def validate_command_template(value):
    try:
        result = CommandTemplate.model_validate(value).model_dump()
    except ValidationError as exc:
        raise TestError('Command template requires single and dual argv arrays', status=422) from exc
    for key in ('single', 'dual'):
        result[key] = validate_argv_template(result[key], key == 'dual')
    return result


def resolve_argv(template, tc, connections):
    connection = Connection.model_validate(connections)
    dual = tc['kind'] == 'Dual'
    if dual and not connection.b:
        raise TestError('Dual TC requires Board B', status=422)
    validate_argv_template(template, dual)
    path = PurePosixPath(tc['path'])
    values = {'{tc_path}': tc['path'], '{tc_file}': path.name, '{tc_name}': path.stem,
              '{com_a}': connection.a.com}
    if dual:
        values['{com_b}'] = connection.b.com
    resolved = [values.get(arg, arg) for arg in template]
    if any(any(ch in arg for ch in '\0\r\n') for arg in resolved):
        raise TestError('Resolved command contains an invalid control character', status=422)
    return resolved


class UnconfiguredRunner:
    simulation = False

    def execute(self, *args, **kwargs):
        raise TestError('Hardware execution disabled: register and verify the existing Single/Dual command adapter')

    def probe(self, process_ref):
        return 'UNKNOWN'
