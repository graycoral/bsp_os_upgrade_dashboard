"""One Windows profile, preserving legacy/unknown fields and atomic backups."""
import copy
import json
import re
from pathlib import Path
from ..core.models import TestError


class Settings:
    def __init__(self, home): self.home = Path(home); self.path = self.home / 'windows-runner.json'

    def read(self):
        return json.loads(self.path.read_text(encoding='utf-8-sig')) if self.path.exists() else {'boards': [], '_setup': {}, 'serial_transport': 'proxy'}

    def save(self, patch, *, migration_checked=False):
        from scripts.setup_runtime import save_json
        value = self.validate(patch)
        if self.read().get('serial_transport', 'native') != 'proxy' and not migration_checked:
            from .automatic_serial import idle_records
            from ..execution.launch import LaunchLock
            with LaunchLock(self.home / 'runtime' / 'setup-launch.lock'), LaunchLock(self.home / 'runtime' / 'runner.lock'):
                with idle_records(self.home):
                    value = self.validate(patch)
                    save_json(self.path, value)
            return value
        save_json(self.path, value)
        return value

    def validate(self, patch):
        """Validate without stopping the live Host or writing a partial profile."""
        value = copy.deepcopy(self.read())
        patch = copy.deepcopy(patch)
        # Inactive boards carry settings for later restoration. Keep private
        # observer fields in Windows when a public mirror edits the board count.
        inactive = {entry.get('board', {}).get('board_id'): entry
                    for entry in value.get('connector_inactive_boards', []) if isinstance(entry, dict)}
        observers = dict(value.get('console_observers', {}))
        observers.update({board: entry.get('observer', {}) for board, entry in inactive.items()})
        if isinstance(patch.get('connector_inactive_boards'), list):
            for entry in patch['connector_inactive_boards']:
                if not isinstance(entry, dict) or not isinstance(entry.get('board'), dict):
                    continue
                board = entry['board'].get('board_id')
                previous = inactive.get(board, {})
                for key, item in previous.items():
                    entry.setdefault(key, copy.deepcopy(item))
                entry['observer'] = dict(observers.get(board, {}), **entry.get('observer', {}))
        if isinstance(patch.get('console_observers'), dict):
            # Browser projections omit redaction values and future private fields.
            # Editing visible observer fields must preserve these on the owner.
            patch = copy.deepcopy(patch)
            previous = observers
            patch['console_observers'] = {
                board: dict(previous.get(board, {}), **cfg) if isinstance(cfg, dict) else cfg
                for board, cfg in patch['console_observers'].items()}
        if isinstance(patch.get('boards'), list):
            active = {b.get('board_id') for b in patch['boards'] if isinstance(b, dict)}
            old_active = {b['board_id'] for b in value.get('boards', [])}
            restored = copy.deepcopy(patch.get('console_observers', value.get('console_observers', {})))
            for board in active - old_active:
                if board not in restored and inactive.get(board, {}).get('observer'):
                    restored[board] = copy.deepcopy(inactive[board]['observer'])
            if 'connector_inactive_boards' in patch:
                restored = {board:cfg for board,cfg in restored.items() if board in active}
            if restored != value.get('console_observers', {}) or 'console_observers' in patch:
                patch['console_observers'] = restored
        if set(patch) - {'_setup', 'python', 'boards', 'console_observers', 'board_names', 'connector_inactive_boards', 'serial_transport', 'serial_settings', 'putty_path', 'flashing'}:
            raise TestError('Unsupported connector settings', 'CONNECTOR_CONFIG')
        value.update({key: item for key, item in patch.items() if key != 'flashing'})
        from .automatic_serial import automatic_transport
        value['serial_transport'] = automatic_transport(value.get('serial_transport', 'native'))
        settings = value.get('serial_settings', {})
        if not isinstance(settings, dict): raise TestError('Invalid serial settings', 'CONNECTOR_CONFIG')
        for cfg in settings.values():
            if (not isinstance(cfg, dict) or set(cfg) - {'baudrate','rts','dtr'} or
                    type(cfg.get('baudrate',115200)) is not int or not 1 <= cfg.get('baudrate',115200) <= 12_000_000 or
                    any(type(cfg[k]) is not bool for k in ('rts','dtr') if k in cfg)):
                raise TestError('Invalid serial settings', 'CONNECTOR_CONFIG')
        state = value.get('_setup', {})
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', state.get('server', '')) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', state.get('account', '')):
            raise TestError('SSH 서버와 계정을 입력하세요.', 'CONNECTOR_CONFIG')
        from ..core.models import Connection
        boards = [Connection.model_validate({'a': b}).a.model_dump() for b in value.get('boards', [])]
        if len({b['com'] for b in boards}) != len(boards): raise TestError('COM mappings must be unique', 'CONNECTOR_CONFIG')
        controls = {b['com'] for b in boards}
        observer_ports = [cfg.get('port') for cfg in value.get('console_observers', {}).values()] if value.get('serial_transport','native') == 'native' else []
        if len(observer_ports) != len(set(observer_ports)): raise TestError('RX COM mappings must be unique', 'OBSERVER_CONFIG')
        if not 1 <= len(boards) <= 32: raise TestError('Configure 1 to 32 boards', 'CONNECTOR_CONFIG')
        for cfg in (value.get('console_observers', {}) if value.get('serial_transport','native') == 'native' else {}).values():
            if cfg.get('port') in controls: raise TestError('RX 포트는 제어 COM과 달라야 합니다.', 'OBSERVER_CONFIG')
        value['boards'] = boards
        if 'flashing' in patch:
            from ..core.integration_profiles import merge_flash_patch
            value['flashing'] = merge_flash_patch(value.get('flashing'), patch['flashing'], boards, self.home / 'runtime',
                                                   serial_transport=value.get('serial_transport','native'),
                                                   console_observers=value.get('console_observers',{}))
        return value
