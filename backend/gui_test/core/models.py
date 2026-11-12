from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator, model_serializer


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class TestError(Exception):
    __test__ = False

    def __init__(self, message, code='CONFLICT', status=409):
        self.message, self.code, self.status = message, code, status


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Board(StrictModel):
    board_id: str = Field(min_length=1, max_length=80, pattern=r'^[\w.-]+$')
    host: str = Field(min_length=1, max_length=80, pattern=r'^[\w.-]+$')
    com: str = Field(pattern=r'^COM[1-9][0-9]{0,3}$')
    node: str | None = Field(default=None, min_length=1, max_length=160, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')

    @model_serializer(mode='wrap')
    def serialize(self, handler):
        value = handler(self)
        if self.node is None:
            value.pop('node', None)  # Preserve legacy connection snapshots without node names.
        return value


class Connection(StrictModel):
    a: Board
    b: Board | None = None

    @model_validator(mode='after')
    def distinct(self):
        if self.b and (self.a.host.casefold() != self.b.host.casefold() or
                       self.a.board_id.casefold() == self.b.board_id.casefold() or
                       self.a.com == self.b.com or
                       (self.a.node is not None and self.b.node is not None and
                        self.a.node.casefold() == self.b.node.casefold())):
            raise ValueError('Dual requires distinct boards/COM ports/node names on the same Windows host')
        return self


class CommandTemplate(StrictModel):
    single: list[str] = Field(min_length=3, max_length=64)
    dual: list[str] = Field(min_length=4, max_length=64)


RepeatCount = Annotated[StrictInt, Field(ge=1, le=100)]


class ModuleContext(StrictModel):
    job_id: StrictStr = Field(min_length=1, max_length=160)
    module_id: StrictStr = Field(min_length=1, max_length=160)
    attempt_id: StrictStr = Field(min_length=1, max_length=160)
    plan_version: StrictInt = Field(ge=1)
    fingerprint: StrictStr = Field(min_length=1, max_length=256)
    catalog_revision: StrictStr = Field(min_length=1, max_length=256)


class Selection(StrictModel):
    tc_ids: list[str] = Field(min_length=1, max_length=500)
    tc_repeats: dict[str, RepeatCount] = Field(default_factory=dict)
    cycles: RepeatCount = 1

    @model_validator(mode='after')
    def bounded_repetitions(self):
        if set(self.tc_repeats) - set(self.tc_ids):
            raise ValueError('Repeat counts must refer to selected TC IDs')
        if self.cycles * sum(self.tc_repeats.get(tc_id, 1) for tc_id in self.tc_ids) > 10000:
            raise ValueError('At most 10000 planned TC executions are allowed')
        return self


class StartRequest(Selection):
    connection: Connection
    source_revision: str
    suite_revision: str = ''
    job_id: str | None = None
    scenario: Literal['pass', 'fail', 'disconnect', 'timeout', 'unknown', 'sync-failure', 'sync-lost-response'] = 'pass'
    speed: float = Field(default=1, ge=.1, le=20)
    execution: Literal['mock', 'hardware'] = 'mock'
    parent_run_id: str | None = None
    command_profile: str | None = Field(default=None, min_length=1, max_length=80)
    command_revision: str = Field(default='', max_length=64)
    module_context: ModuleContext | None = None
    timeout_revision: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @model_serializer(mode='wrap')
    def serialize(self, handler):
        value = handler(self)
        if self.module_context is None:
            value.pop('module_context', None)
        if self.timeout_revision is None:
            value.pop('timeout_revision', None)
        return value

    @model_validator(mode='after')
    def validate_module_link(self):
        if self.module_context is not None and self.job_id is not None:
            raise ValueError('Operational module context cannot be mixed with a Demo Dashboard job link')
        return self


class Command(StrictModel):
    expected_version: int = Field(ge=0)
    data: dict = Field(default_factory=dict)


TERMINAL = {'COMPLETED', 'CANCELLED'}
ACTIVE = {'RUNNING', 'PAUSE_REQUESTED', 'CANCEL_REQUESTED', 'UNKNOWN'}
