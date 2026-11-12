"""Persistent execution limits, separate from source bytes and catalog I/O limits."""
import json
from typing import Annotated

from pydantic import Field, StrictInt, model_validator

from .models import StrictModel, TestError, digest

Seconds = Annotated[StrictInt, Field(ge=1, le=86400)]


class TimeoutValues(StrictModel):
    default_seconds: Seconds | None = None
    source_revision: str = Field(default='', max_length=256)
    overrides: dict[str, Seconds] = Field(default_factory=dict, max_length=10000)

    @model_validator(mode='after')
    def valid_overrides(self):
        if self.overrides and not self.source_revision:
            raise ValueError('TC overrides require a source revision')
        if any(not key.strip() or len(key) > 1024 for key in self.overrides):
            raise ValueError('Invalid TC identifier')
        return self


class TimeoutUpdate(TimeoutValues):
    expected_revision: str = Field(pattern=r'^[a-f0-9]{64}$')


class TimeoutSettings:
    def __init__(self, store):
        self.store = store

    def read(self, connection=None):
        if connection is None:
            with self.store.connection() as c:
                return self.read(c)
        row = connection.execute("SELECT data FROM documents WHERE kind='execution-timeouts' AND name='current'").fetchone()
        values = TimeoutValues.model_validate(json.loads(row[0]) if row else {}).model_dump()
        return values | {'revision': digest(values)}

    def save(self, value):
        update = TimeoutUpdate.model_validate(value)
        values = TimeoutValues.model_validate(update.model_dump(exclude={'expected_revision'})).model_dump()
        with self.store.transaction() as c:
            self.require_revision(update.expected_revision, c)
            c.execute("INSERT INTO documents VALUES('execution-timeouts','current',?) "
                      "ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data", (json.dumps(values),))
        return values | {'revision': digest(values)}

    def require_revision(self, revision, connection=None):
        if self.read(connection)['revision'] != revision:
            raise TestError('TC 제한시간 설정이 변경되었습니다. 다시 불러오고 Preflight를 검사하세요.', 'TC_TIMEOUT_CHANGED')

    @staticmethod
    def active(values, source_revision):
        return values['default_seconds'] is not None or bool(values['overrides'] and values['source_revision'] == source_revision)

    def apply(self, catalog, values=None):
        values = values if values is not None else self.read()
        overrides = values['overrides'] if values['source_revision'] == catalog['revision'] else {}
        tests = [test | {'source_timeout': test.get('source_timeout', test['timeout']),
                         'timeout': overrides.get(test['id'], values['default_seconds'] if values['default_seconds'] is not None else test.get('source_timeout', test['timeout']))}
                 for test in catalog['tests']]
        return catalog | {'tests': tests, 'timeout_settings_revision': values['revision'],
                          'timeout_settings_active': self.active(values, catalog['revision'])}
