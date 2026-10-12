import json
import os
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from backend.domain.policy import Conflict


def bridge_defaults(workspace):
    """Project conventions, not a claim that the external wrappers are installed."""
    folder = Path(workspace) / '.bsp-dashboard' / 'bridges'
    if not Path(workspace).is_absolute():
        raise Conflict('브리지 기본 경로에는 절대 경로의 프로젝트 작업 폴더가 필요합니다.', 'ENVIRONMENT', 422)
    return {'agents': {tool: [str(folder / tool)] for tool in ('claude', 'opencode', 'codex')},
            'build_argv': [str(folder / 'build')]}


def executable_status(argv):
    if not argv:
        return 'NOT_CONFIGURED', '실행 브리지 미설정'
    if not all(isinstance(arg, str) and arg and '\x00' not in arg for arg in argv):
        return 'INVALID', '실행 배열에는 비어 있지 않은 문자열만 사용하세요.'
    path = Path(argv[0])
    if not path.is_absolute():
        return 'INVALID', '브리지 실행 파일은 절대 경로여야 합니다.'
    if not path.is_file():
        return 'MISSING', f'브리지 파일이 없습니다: {path}'
    if not os.access(path, os.X_OK):
        return 'NOT_EXECUTABLE', f'실행 권한이 없습니다: {path}'
    return 'FILE_READY', '실행 파일 확인 · JSON 계약/도구 인증/실제 동작은 미검증'


def resolve_source_revision(profile):
    explicit = profile.get('source_revision', '').strip()
    if explicit:
        if not re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', explicit):
            raise Conflict('소스 기준은 비워 두면 자동 기록합니다. 직접 지정할 때는 40자리 커밋 또는 64자리 스냅샷 해시를 입력하세요.', 'ENVIRONMENT', 422)
        return explicit.lower()
    source = profile.get('new_base', '')
    if not source or not Path(source).is_dir():
        raise Conflict('소스 기준 자동 기록을 위해 신규 OS 원본 경로를 지정하세요.', 'ENVIRONMENT', 422)
    # Never checkout, commit, clean or execute a project hook to resolve a base.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    def git(*args):
        return subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(Path(source).resolve()), *args], env=env,
                              capture_output=True, timeout=10, check=True).stdout.strip()
    try:
        revision = git('rev-parse', '--verify', 'HEAD^{commit}').decode('ascii')
        dirty = git('status', '--porcelain', '--untracked-files=normal')
        unchanged = git('rev-parse', '--verify', 'HEAD^{commit}').decode('ascii')
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise Conflict('신규 OS 원본에서 Git 커밋을 읽지 못했습니다. Git 저장소 경로를 확인하거나 고정 스냅샷 해시를 직접 지정하세요.', 'ENVIRONMENT', 422) from None
    if dirty or revision != unchanged:
        raise Conflict('신규 OS 원본에 미커밋 변경이 있거나 커밋이 바뀌었습니다. 기준을 확정한 후 다시 시작하세요. 파일은 변경하지 않았습니다.', 'ENVIRONMENT', 422)
    if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', revision):
        raise Conflict('Git에서 유효한 소스 기준을 읽지 못했습니다.', 'ENVIRONMENT', 422)
    return revision


class ModuleSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    group: Literal['boot', 'main']


class Profile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    execution: Literal['demo', 'bridge'] = 'demo'
    runner: Literal['native', 'bridge'] = 'native'
    tool_paths: dict[str, str] = Field(default_factory=lambda: dict.fromkeys(('claude', 'opencode', 'codex'), ''))
    disabled_tools: list[Literal['opencode', 'codex']] = Field(default_factory=list)
    models: dict[str, str] = Field(default_factory=dict)
    agent_instructions: str = ''
    role_instructions: dict[str, str] = Field(default_factory=dict)
    build_command: str = Field(default='', max_length=8000)
    build_env_script: str = ''
    artifact_path: str = ''
    verification_command: str = Field(default='', max_length=8000)
    integration_command: str = Field(default='', max_length=8000)
    host: str = ''
    account: str = ''
    workspace: str = '/workspace/bsp-upgrade'
    source_revision: str = ''
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

    @model_validator(mode='before')
    @classmethod
    def legacy_profile(cls, data):
        # Old JSON with explicit invocation arrays keeps its original contract.
        if isinstance(data, dict) and 'runner' not in data and ('agents' in data or 'build_argv' in data):
            data = dict(data, runner='bridge')
        return data

    @model_validator(mode='after')
    def validate_native_fields(self):
        tools = {'claude', 'opencode', 'codex'}
        if any(set(value) - tools for value in (self.tool_paths, self.models, self.agents)):
            raise ValueError('지원하는 도구는 Claude/OpenCode/Codex입니다.')
        if set(self.role_instructions) - {'analysis', 'design', 'code', 'review', 'coordinate', 'question'}:
            raise ValueError('지원하지 않는 역할 지침입니다.')
        for value in [*self.tool_paths.values(), *self.models.values(), *self.role_instructions.values(),
                      self.workspace, self.agent_instructions, self.artifact_path, self.build_env_script,
                      self.build_command, self.verification_command, self.integration_command]:
            if '\x00' in value:
                raise ValueError('설정에 NUL 문자를 사용할 수 없습니다.')
        return self


def validate_live(profile):
    workspace = Path(profile['workspace'])
    if not workspace.is_absolute() or not workspace.is_dir():
        raise Conflict('실행 관리자와 같은 Linux의 작업 폴더를 절대 경로로 설정하세요.', 'ENVIRONMENT', 422)
    for name in ['old_base', 'vendor_tree', 'new_base']:
        path = Path(profile[name])
        if not profile[name] or not path.is_absolute() or not path.is_dir():
            raise Conflict(f'{name} 소스 절대 경로가 필요합니다.', 'ENVIRONMENT', 422)
    if profile.get('runner', 'bridge') == 'native':
        from backend.adapters.native import instruction_bundle
        for key in ('build_command', 'artifact_path', 'verification_command', 'integration_command'):
            if not profile.get(key, '').strip():
                raise Conflict(f'{key} 설정이 필요합니다. 프로젝트의 기존 빌드/시험 명령을 등록하세요.', 'ENVIRONMENT', 422)
        if profile.get('agent_instructions') and not Path(profile['agent_instructions']).is_absolute():
            raise Conflict('에이전트 지침 폴더는 절대 경로로 지정하세요.', 'ENVIRONMENT', 422)
        if profile.get('build_env_script') and (not Path(profile['build_env_script']).is_absolute() or not Path(profile['build_env_script']).is_file()):
            raise Conflict('빌드 환경 초기화 파일이 없습니다.', 'ENVIRONMENT', 422)
        try:
            artifact = (workspace / profile['artifact_path'].format(job_id='job', module_id='module', attempt_id='attempt')).resolve()
            if not artifact.is_relative_to(workspace.resolve()) or artifact == workspace.resolve():
                raise ValueError('산출물은 작업 폴더 안의 파일이어야 합니다.')
            for stage in ('analysis', 'design', 'code', 'review', 'coordinate', 'question'):
                instruction_bundle(profile, stage)
        except (OSError, UnicodeError, ValueError, KeyError) as e:
            raise Conflict('산출물/역할 지침 경로를 확인하세요. 지침은 지정 폴더 안에 있어야 합니다.', 'ENVIRONMENT', 422) from None
        for key in ('old_base', 'vendor_tree', 'new_base'):
            if workspace.resolve().is_relative_to(Path(profile[key]).resolve()):
                raise Conflict('수정할 작업 폴더와 읽기 전용 원본 소스 폴더를 분리하세요.', 'ENVIRONMENT', 422)
    else:
        if not profile['agents'].get('claude') or not profile['build_argv']:
            raise Conflict('Claude 및 빌드 JSON 브리지 실행 파일을 설정하세요.', 'ENVIRONMENT', 422)
        for name, args in [*profile['agents'].items(), ('build', profile['build_argv'])]:
            status, detail = executable_status(args)
            if args and status != 'FILE_READY':
                raise Conflict(f'{name}: {detail}', 'ENVIRONMENT', 422)
    return resolve_source_revision(profile)


def prepare_job_profile(profile):
    resolved = deepcopy(profile)
    if resolved['execution'] == 'bridge':
        resolved['source_revision'] = validate_live(resolved)
        resolved['workspace'] = str(Path(resolved['workspace']).resolve())
        if resolved.get('runner', 'bridge') == 'native':
            from backend.adapters.native import resolve_tools
            resolved['agents'], resolved['tool_checks'] = resolve_tools(resolved)
            from backend.adapters.native import instruction_bundle, ROLES
            resolved['instruction_snapshots'] = {role: instruction_bundle(resolved, role) for role in sorted(ROLES)}
    elif not resolved['source_revision'].strip():
        resolved['source_revision'] = 'demo-os-v1'
    return resolved


class Settings:
    def __init__(self, store):
        self.store = store
        with store.transaction() as c:
            c.execute('INSERT OR IGNORE INTO config VALUES(1,1,?)', (Profile().model_dump_json(),))

    def get(self):
        with self.store.connection() as c:
            r = c.execute('SELECT * FROM config WHERE id=1').fetchone()
            data = json.loads(r['data'])
            # Only migrate the exact generated, uninstalled placeholder profile.
            # Custom/installed wrappers and all existing job snapshots remain unchanged.
            if 'runner' not in data and Path(data.get('workspace', '')).is_absolute():
                defaults = bridge_defaults(data['workspace'])
                arrays = [*defaults['agents'].values(), defaults['build_argv']]
                if all(data.get(k) == value for k, value in defaults.items()) and not any(Path(a[0]).exists() for a in arrays):
                    data['runner'] = 'native'
            return {'version': r['version'], 'profile': Profile.model_validate(data).model_dump()}

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
