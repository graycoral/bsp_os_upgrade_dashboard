"""Offline same-view adapter. No production profile or hardware imports."""
import copy
from pathlib import Path
from .logs import redact


class MockConnector:
    preview = True
    def __init__(self, home):
        self.home = Path(home); self.scenario = '연결'; self.connected = False; self.manual_board = None
        self.profile = {'_setup': {'server': 'company.example', 'account': 'tester', 'ssh_port': 22},
                        'python': 'C:/TC/Python/python.exe', 'serial_transport':'proxy',
                        'boards': [{'board_id': 'board-a', 'host': 'TEST-PC', 'com': 'COM7'}, {'board_id': 'board-b', 'host': 'TEST-PC', 'com': 'COM8'}],
                        'console_observers': {'board-b': {'port': 'COM18', 'rx_only_confirmed': True, 'control_lines_isolated': True}, 'board-a': {'port': 'COM17', 'rx_only_confirmed': True, 'control_lines_isolated': True}}}
    def settings(self): return copy.deepcopy(self.profile)
    def save(self, value): self.profile.update(copy.deepcopy(value)); return self.settings()
    def connect(self): self.connected = True; return self.status()
    def disconnect(self): self.connected = False; return self.status()
    def ports(self): return [{'com': c, 'description': d} for c, d in [('COM7', 'Board control'), ('COM17', 'Splitter RX only'), ('COM8', 'USB serial'), ('COM18', 'Second splitter RX')]]
    def manual(self, board_id, enabled):
        if enabled and self.scenario in {'시험 중','확인 필요'}: raise RuntimeError('시험·확인 필요 작업이 남아 있습니다.')
        self.manual_board = board_id if enabled else None
        return {'owner':'manual' if enabled else None}
    def putty(self, board_id): return {'opened':False, 'preview':True}
    def status(self):
        code = {'연결': 'CONNECTED', '시험 중': 'RUNNING', '오류': 'ERROR', '미연결': 'DISCONNECTED', '확인 필요': 'UNKNOWN'}[self.scenario]
        text = 'U-Boot 2026.11\nStarting kernel ...\nboard login :\n'
        if self.scenario == '시험 중': text += '[board-a] TC UART response received\n'
        if self.scenario == '오류': text += 'Kernel panic: simulated preview evidence\n'
        error = {'event_id': 'preview-error-1', 'code': 'CONSOLE_PANIC', 'board_id': 'board-a', 'run_id': 'preview-run', 'phase': 'TC', 'source': 'board-console', 'evidence_ref': 'preview://console/1'}
        return {'state': 'CONNECTED' if self.connected else 'DISCONNECTED', 'error': '모의 콘솔 오류 · 공통 서버 오류 조회에 저장됨' if self.scenario == '오류' else '',
                'fresh': self.connected and self.scenario not in {'미연결', '확인 필요'},
                'server_paths': {'selected_tc_source': '/srv/tc', 'run': {'id':'preview-run','state':'RUNNING' if self.scenario=='시험 중' else 'COMPLETED','historical':self.scenario!='시험 중','installer':'/srv/images/build-123/install.bat','tc_source':'/srv/tc','batch_id':'preview-batch','execution_ids':['preview-attempt']}} if self.connected else None,
                'execution_paths': [{'id':'preview-prepare','batch_id':'preview-batch','kind':'batch-prepare','working_directory':'C:/BoardConnector/runtime/batch-snapshots/preview-batch/images'}, {'id':'preview-attempt','working_directory':'C:/BoardConnector/runtime/snapshots/preview-attempt'}],
                'dashboard_url': '미리보기 · 실제 서버 연결 없음', 'stages': {k: 'READY' if self.connected else 'WAITING' for k in ('local', 'ssh', 'dashboard', 'roundtrip')},
                'boards': [dict(board, name=self.profile.get('board_names',{}).get(board['board_id'],board['board_id']), state=(code if board['board_id']=='board-a' else 'CONNECTED' if self.scenario not in {'미연결','확인 필요'} else 'UNKNOWN') if self.connected else 'DISCONNECTED', detected=self.scenario != '미연결', serial_proxy={'state':'READY' if self.connected else 'WAITING','owner':'manual' if self.manual_board==board['board_id'] else 'execution' if self.scenario=='시험 중' and board['board_id']=='board-a' else None,'putty_port':None,'putty_connected':False}) for board in self.profile['boards']],
                'console': {'epoch': 'preview-epoch', 'cursor': 1, 'boards': [{'board_id': 'board-a', 'text': text, 'code': 'CONSOLE_PANIC' if self.scenario == '오류' else 'CONSOLE_READY', 'phase': 'TC', 'run_ids': ['preview-run']}], 'errors': [error] if self.scenario == '오류' else []},
                'executions': [{'id': 'preview-attempt', 'state': 'RUNNING' if self.scenario == '시험 중' else 'DONE', 'stdout': 'TC process stdout · separate from board console\n', 'stderr': ''}]}


def install_guard():
    """Fail closed for accidental Python network/child/hardware use in preview."""
    import socket
    import subprocess
    def denied(*args, **kwargs): raise RuntimeError('PREVIEW_GUARD: external operation prohibited')
    socket.socket.connect = denied; socket.socket.connect_ex = denied
    socket.create_connection = denied; subprocess.Popen = denied; subprocess.run = denied
    # Production modules remain unimported: DPAPI, serial, fastboot and TC cannot start.
