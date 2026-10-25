from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class Connection(StrictModel):
    a: Board
    b: Board | None = None

    @model_validator(mode='after')
    def distinct(self):
        if self.b and (self.a.host.casefold() != self.b.host.casefold() or
                       self.a.board_id.casefold() == self.b.board_id.casefold() or
                       self.a.com == self.b.com):
            raise ValueError('Dual requires distinct boards/COM ports on the same Windows host')
        return self


class StartRequest(StrictModel):
    tc_ids: list[str] = Field(min_length=1, max_length=500)
    connection: Connection
    source_revision: str
    suite_revision: str = ''
    job_id: str | None = None
    scenario: Literal['pass', 'fail', 'disconnect', 'timeout', 'unknown', 'sync-failure', 'sync-lost-response'] = 'pass'
    speed: float = Field(default=1, ge=.1, le=20)
    execution: Literal['mock', 'hardware'] = 'mock'
    parent_run_id: str | None = None


class Command(StrictModel):
    expected_version: int = Field(ge=0)
    data: dict = Field(default_factory=dict)


TERMINAL = {'COMPLETED', 'CANCELLED'}
ACTIVE = {'RUNNING', 'PAUSE_REQUESTED', 'CANCEL_REQUESTED', 'UNKNOWN'}
