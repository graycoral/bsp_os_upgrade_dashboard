import json
import os
import re
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from backend.domain.policy import Conflict


class ModuleSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    group: Literal['boot', 'main']


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    execution: Literal['demo', 'bridge'] = 'demo'
    host: str = ''
    account: str = ''
    workspace: str = '/workspace/bsp-upgrade'
    source_revision: str = 'demo-os-v1'
    old_base: str = ''
    vendor_tree: str = ''
    new_base: str = ''
    build_argv: list[str] = Field(default_factory=list, max_length=40)
    agents: dict[str, list[str]] = Field(default_factory=lambda: {'claude': [], 'opencode': [], 'codex': []})
    modules: list[ModuleSpec] = Field(default_factory=lambda: [ModuleSpec(name=n, group=g) for n, g in [('Bootloader','boot'),('Kernel / BSP','boot'),('Ethernet','main'),('Display','main'),('Camera','main')]], max_length=100)
    max_analysis: int = Field(default=3, ge=1, le=8)
    timeout_seconds: int = Field(default=900, ge=10, le=14400)
    jira_mode: Literal['direct', 'claude_mcp'] = 'direct'
    jira_url: str = ''
    jira_project: str = ''
    jira_auth_env: str = 'BSP_JIRA_TOKEN'
    jira_api_version: Literal['2', '3'] = '2'
    mcp_name: str = ''
    mcp_scope: str = 'project'
    mcp_argv: list[str] = Field(default_factory=list, max_length=40)
    jira_issue_type: str = 'Task'
    jira_fields: dict = Field(default_factory=dict)


def validate_live(profile):
    # Invocation profiles use an explicit bridge contract, never guessed vendor CLI flags.
    if not Path(profile['workspace']).is_dir():
        raise Conflict('실행 관리자와 같은 Linux의 작업 폴더를 설정하세요.', 'ENVIRONMENT', 422)
    if not re.fullmatch('[0-9a-fA-F]{40,64}', profile['source_revision']):
        raise Conflict('고정된 소스 커밋/해시가 필요합니다.', 'ENVIRONMENT', 422)
    for name in ['old_base', 'vendor_tree', 'new_base']:
        if not Path(profile[name]).is_dir() or not profile[name]:
            raise Conflict(f'{name} 소스 경로가 필요합니다.', 'ENVIRONMENT', 422)
    if not profile['agents'].get('claude') or not profile['build_argv']:
        raise Conflict('Claude 및 빌드 JSON 브리지 실행 파일을 설정하세요.', 'ENVIRONMENT', 422)
    for args in [*profile['agents'].values(), profile['build_argv']]:
        if args and (not Path(args[0]).is_absolute() or not os.access(args[0], os.X_OK)):
            raise Conflict('실행 가능한 절대 경로의 브리지를 지정하세요.', 'ENVIRONMENT', 422)


class Settings:
    def __init__(self, store):
        self.store = store
        with store.transaction() as c:
            c.execute('INSERT OR IGNORE INTO config VALUES(1,1,?)', (Profile().model_dump_json(),))

    def get(self):
        with self.store.connection() as c:
            r = c.execute('SELECT * FROM config WHERE id=1').fetchone()
            return {'version': r['version'], 'profile': Profile.model_validate_json(r['data']).model_dump()}

    def save(self, version, profile):
        p = Profile.model_validate(profile)
        if len({m.name for m in p.modules}) != len(p.modules) or not p.modules:
            raise Conflict('모듈 이름은 중복 없이 한 개 이상 필요합니다.', status=422)
        for key in p.agents:
            if key not in {'claude', 'opencode', 'codex'}:
                raise Conflict('지원하는 도구는 Claude/OpenCode/Codex입니다.', status=422)
        if not re.fullmatch(r'[A-Z_][A-Z0-9_]*', p.jira_auth_env):
            raise Conflict('인증은 환경변수 이름으로 지정하세요.', status=422)
        with self.store.transaction() as c:
            r = c.execute('UPDATE config SET version=version+1,data=? WHERE id=1 AND version=?', (p.model_dump_json(), version))
            if r.rowcount != 1:
                raise Conflict('설정이 변경되었습니다. 다시 읽어주세요.', 'VERSION_CONFLICT')
        return self.get()
