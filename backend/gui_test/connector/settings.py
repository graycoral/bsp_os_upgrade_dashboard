"""One Windows profile, preserving legacy/unknown fields and atomic backups."""
import copy
import json
import re
from pathlib import Path
from ..core.models import TestError


class Settings:
    def __init__(self, home): self.home = Path(home); self.path = self.home / 'windows-runner.json'

    def read(self):
        return json.loads(self.path.read_text(encoding='utf-8-sig')) if self.path.exists() else {'boards': [], '_setup': {}}

    def save(self, patch):
        from scripts.setup_runtime import save_json
        value = copy.deepcopy(self.read())
        if set(patch) - {'_setup', 'python', 'boards', 'console_observers', 'board_names', 'connector_inactive_boards'}:
            raise TestError('Unsupported connector settings', 'CONNECTOR_CONFIG')
        value.update(patch)
        state = value.get('_setup', {})
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', state.get('server', '')) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', state.get('account', '')):
            raise TestError('SSH 서버와 계정을 입력하세요.', 'CONNECTOR_CONFIG')
        from ..core.models import Connection
        boards = [Connection.model_validate({'a': b}).a.model_dump() for b in value.get('boards', [])]
        if len({b['com'] for b in boards}) != len(boards): raise TestError('COM mappings must be unique', 'CONNECTOR_CONFIG')
        controls = {b['com'] for b in boards}
        observer_ports = [cfg.get('port') for cfg in value.get('console_observers', {}).values()]
        if len(observer_ports) != len(set(observer_ports)): raise TestError('RX COM mappings must be unique', 'OBSERVER_CONFIG')
        if not 1 <= len(boards) <= 32: raise TestError('Configure 1 to 32 boards', 'CONNECTOR_CONFIG')
        for cfg in value.get('console_observers', {}).values():
            if cfg.get('port') in controls: raise TestError('RX 포트는 제어 COM과 달라야 합니다.', 'OBSERVER_CONFIG')
        value['boards'] = boards
        save_json(self.path, value)
        return value
