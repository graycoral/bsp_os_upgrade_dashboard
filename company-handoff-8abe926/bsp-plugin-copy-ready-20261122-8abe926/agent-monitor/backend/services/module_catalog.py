"""Plugin-published module choices, separate from selected and frozen job modules."""
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.domain.policy import Conflict
from backend.settings import ModuleSpec, Profile


class PublishedModule(ModuleSpec):
    stable_key: str = Field(min_length=1, max_length=256)


class PublishModules(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_version: int = Field(ge=0)
    modules: list[PublishedModule] = Field(max_length=100)

    @model_validator(mode='after')
    def unique_modules(self):
        for field in ('stable_key', 'name'):
            values = [getattr(module, field) for module in self.modules]
            if any(not value.strip() for value in values) or len(set(values)) != len(values):
                raise ValueError('Module keys and names must be nonempty and unique')
        # Reuse the existing module path and stable-key contract.
        Profile(modules=[module.model_dump() for module in self.modules])
        return self


class ModuleCatalog:
    key = 'plugin_module_catalog'

    def __init__(self, store):
        self.store = store

    def _read(self, connection):
        row = connection.execute('SELECT value FROM meta WHERE key=?', (self.key,)).fetchone()
        return json.loads(row[0]) if row else {'version': 0, 'modules': []}

    def read(self):
        with self.store.connection() as connection:
            return self._read(connection)

    def publish(self, request):
        with self.store.transaction() as connection:
            current = self._read(connection)
            if current['version'] != request.expected_version:
                raise Conflict('플러그인 모듈 목록이 변경되었습니다. 최신 버전을 다시 읽으세요.', 'VERSION_CONFLICT')
            modules = [module.model_dump() for module in request.modules]
            if current['modules'] == modules:
                return current
            result = {'version': current['version'] + 1, 'modules': modules}
            connection.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                               (self.key, json.dumps(result, ensure_ascii=False)))
            return result
