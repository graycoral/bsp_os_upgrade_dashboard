"""Shared Qt Widgets view/controller, production IPC or isolated mock injected."""
import copy
import json
from pathlib import Path
import socket
import time

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Qt, QUrl, QUrlQuery
from PySide6.QtGui import QDesktopServices, QColor, QTextCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QTabBar, QFormLayout, QLineEdit, QComboBox, QGroupBox, QPlainTextEdit,
    QCheckBox, QFileDialog, QMessageBox, QScrollArea, QSpinBox, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView)
from .logs import redact
from .paths import path_text


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Task(QRunnable):
    def __init__(self, operation): super().__init__(); self.operation = operation; self.signals = Signals()
    def run(self):
        try: self.signals.done.emit(self.operation())
        except Exception as exc: self.signals.failed.emit(redact(str(exc)))


class ConnectorWindow(QMainWindow):
    def __init__(self, adapter):
        super().__init__(); self.adapter = adapter; self.profile = {}; self.pending = False; self.snapshot = {}; self.tasks = set()
        self.setWindowTitle('보드 커넥터' + (' · 미리보기' if adapter.preview else ''))
        self.resize(760, 520); self.setMinimumSize(620, 460)
        base = QWidget(); self.setCentralWidget(base); layout = QVBoxLayout(base); layout.setContentsMargins(20, 16, 20, 14)
        title = QLabel('보드 커넥터'); title.setStyleSheet('font-size:20px;font-weight:700;')
        layout.addWidget(title)
        subtitle = QLabel('보드 연결과 콘솔을 한곳에서 확인하세요.' + ('   ·   안전한 모의 미리보기' if adapter.preview else ''))
        subtitle.setStyleSheet('color:#68788b;'); layout.addWidget(subtitle)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs, 1)
        connect = QWidget(); cv = QVBoxLayout(connect); self.tabs.addTab(connect, '연결')
        top = QHBoxLayout(); self.state = QLabel('● 미연결'); top.addWidget(self.state); top.addStretch()
        self.connect_button = QPushButton('연결'); self.disconnect_button = QPushButton('연결 종료'); self.verify_button = QPushButton('연결 확인'); self.reconnect_ssh_button = QPushButton('SSH 재연결'); self.dashboard_button = QPushButton('Agent Monitor 열기')
        for button in (self.connect_button, self.disconnect_button, self.verify_button, self.reconnect_ssh_button, self.dashboard_button): top.addWidget(button)
        self.dashboard_button.hide()
        self.monitor_task = QComboBox()
        self.monitor_task.setAccessibleName('Agent Monitor 작업 선택')
        self.monitor_task.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.monitor_task.setMinimumContentsLength(9)
        self.monitor_task.setMaximumWidth(220)
        self.monitor_task.hide()
        top.insertWidget(max(0, top.count() - 1), self.monitor_task)
        self.monitor_selection = None
        self.monitor_choices = []
        self.monitor_opening = False
        self.monitor_task.activated.connect(self.select_monitor_task)
        cv.addLayout(top)
        self.stage = QLabel('로컬 Host  —     SSH -R  —     직결  —     모니터(선택)  —'); self.stage.setWordWrap(True); cv.addWidget(self.stage)
        plugin_row = QHBoxLayout()
        self.plugin_status = QLabel('플러그인 연결 보고 대기')
        self.plugin_status.setTextFormat(Qt.TextFormat.PlainText)
        self.plugin_status.setWordWrap(True)
        plugin_row.addWidget(self.plugin_status, 1)
        self.plugin_toggle = QPushButton('플러그인이 보낸 설정')
        self.plugin_toggle.setCheckable(True)
        plugin_row.addWidget(self.plugin_toggle)
        cv.addLayout(plugin_row)
        self.plugin_values = QPlainTextEdit()
        self.plugin_values.setReadOnly(True)
        self.plugin_values.setMaximumHeight(90)
        self.plugin_values.hide()
        self.plugin_toggle.toggled.connect(self.plugin_values.setVisible)
        cv.addWidget(self.plugin_values)
        self.board_box = QGroupBox('보드'); self.board_layout = QVBoxLayout(self.board_box); cv.addWidget(self.board_box)
        self.board_labels = []; self.board_items = {}
        self.board_list = QListWidget(); self.board_list.setMinimumHeight(65); self.board_list.setMaximumHeight(115)
        self.board_layout.addWidget(self.board_list); self.board_list.currentItemChanged.connect(self.select_board)
        controls = QHBoxLayout(); self.putty_button = QPushButton('PuTTY 열기')
        controls.addWidget(self.putty_button); controls.addStretch(); cv.addLayout(controls)
        self.putty_button.clicked.connect(self.open_putty)
        self.board_summary=QLabel('등록 0대 · 감지 0대 · 시험 중 0대'); controls.addWidget(self.board_summary)
        self.error = QLabel(''); self.error.setWordWrap(True); self.error.setStyleSheet('color:#b63d3d;'); cv.addWidget(self.error); self.error.hide()
        self.space = QLabel('환경설정에서 서버 경로와 TC 제한시간을 변경할 수 있습니다.'); self.space.setWordWrap(True); cv.addWidget(self.space)
        self.tc_note = QLabel('테스트 스크립트 · 서버 연결 후 조회'); self.tc_note.setWordWrap(True); cv.addWidget(self.tc_note)
        self.tc_table = QTableWidget(0, 2); self.tc_table.setHorizontalHeaderLabels(['테스트 스크립트', '상태'])
        self.tc_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tc_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.tc_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tc_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tc_table.setMaximumHeight(170); cv.addWidget(self.tc_table)
        self.paths_toggle = QPushButton('▸ 경로 보기'); self.paths_toggle.setCheckable(True)
        self.paths_text = QPlainTextEdit(); self.paths_text.setReadOnly(True); self.paths_text.setMaximumHeight(145)
        self.paths_text.setPlaceholderText('서버 경로 미수신'); self.paths_text.hide(); cv.addWidget(self.paths_text)
        self.paths_toggle.toggled.connect(self.paths_text.setVisible)
        self.paths_toggle.toggled.connect(lambda value: self.log_toggle.setChecked(False) if value else None)
        self.paths_toggle.toggled.connect(lambda value: self.paths_toggle.setText('▾ 경로 닫기' if value else '▸ 경로 보기'))
        if adapter.preview:
            row = QHBoxLayout(); row.addWidget(QLabel('미리보기 상태')); self.scenario = QComboBox(); self.scenario.addItems(['연결', '시험 중', '오류', '미연결', '확인 필요']); row.addWidget(self.scenario); row.addStretch(); cv.addLayout(row)
            self.scenario.currentTextChanged.connect(self.change_scenario)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); settings = QWidget(); form = QFormLayout(settings); scroll.setWidget(settings); self.tabs.addTab(scroll, '환경설정')
        self.server = QLineEdit(); self.account = QLineEdit(); self.ssh_port = QSpinBox(); self.ssh_port.setRange(1, 65535); self.ssh_port.setValue(22)
        self.dashboard_port = QSpinBox(); self.dashboard_port.setRange(1, 65535); self.dashboard_port.setValue(8766)
        form.addRow('Linux SSH 서버', self.server); form.addRow('계정', self.account); form.addRow('Agent Monitor 서버 포트', self.dashboard_port)
        self.python_path = QLineEdit(); form.addRow('TC Python', self.path_row(self.python_path, 'TC Python 선택'))
        self.ssh_key = QLineEdit(); self.putty_path = QLineEdit(); advanced=QWidget(); af=QFormLayout(advanced); af.setContentsMargins(0,0,0,0); af.addRow('SSH 포트',self.ssh_port); af.addRow('SSH 키 (선택)',self.path_row(self.ssh_key,'SSH 개인 키 선택')); af.addRow('PuTTY (자동 검색)',self.path_row(self.putty_path,'putty.exe 선택')); advanced.hide(); toggle=QPushButton('고급 연결 설정'); toggle.setCheckable(True); toggle.toggled.connect(advanced.setVisible); form.addRow('',toggle); form.addRow(advanced)
        self.board_count = QSpinBox(); self.board_count.setRange(1,32); self.board_count.setValue(1)
        self.serial_status = QLabel('자동 COM 공유'); form.addRow('통신 방식', self.serial_status)
        form.addRow('연결할 보드 수', self.board_count)
        self.board_editor = QTabWidget(); self.board_editor.setUsesScrollButtons(True)
        form.addRow(self.board_editor)
        self.board_rows = []; self.board_drafts = []; self.port_choices = []
        self.refresh_button = QPushButton('COM 새로고침'); form.addRow('', self.refresh_button)
        self.board_count.valueChanged.connect(self.resize_boards)
        self.resize_boards(1)
        note = QLabel('실제 보드 COM과 통신 속도를 선택하세요. 커넥터가 TC·콘솔·PuTTY 연결을 자동으로 공유합니다.\nTC 폴더는 공통 서버에서 한 번 선택합니다.\nSSH는 사전 인증된 키/agent를 사용합니다. 암호·host key 확인은 OpenSSH 콘솔에서 먼저 완료하세요.'); note.setWordWrap(True); note.setStyleSheet('color:#68788b;'); form.addRow(note)
        from .shared_settings_ui import SharedSettingsPanel, StorageSettingsPanel
        self.shared_panel = SharedSettingsPanel(self); form.addRow(self.shared_panel)
        self.storage_panel = StorageSettingsPanel(self); form.addRow(self.storage_panel)
        self.save_button = QPushButton('장비 설정 저장'); self.cancel_button=QPushButton('변경 취소'); save_row=QWidget(); sv=QHBoxLayout(save_row); sv.setContentsMargins(0,0,0,0); sv.addWidget(self.save_button); sv.addWidget(self.cancel_button); form.addRow('', save_row)
        self.cancel_button.clicked.connect(lambda: self.load_settings(copy.deepcopy(self.profile)))
        loghead = QHBoxLayout(); self.log_toggle = QPushButton('▸ 로그 보기'); self.log_toggle.setCheckable(True); loghead.addWidget(self.log_toggle); loghead.addStretch(); loghead.addWidget(self.paths_toggle); self.log_source = QTabBar(); [self.log_source.addTab(label) for label in ['보드 콘솔','TC 실행','연결','플러그인 오류']]; cv.addLayout(loghead)
        self.log_panel = QWidget(); lp = QVBoxLayout(self.log_panel); lp.setContentsMargins(0, 0, 0, 0); lp.addWidget(self.log_source); filterrow = QHBoxLayout(); self.errors_only = QCheckBox('오류만'); self.search = QLineEdit(); self.search.setPlaceholderText('로그 검색'); self.copy = QPushButton('복사'); self.open_logs = QPushButton('로그 열기')
        for w in (self.errors_only, self.search, self.copy, self.open_logs): filterrow.addWidget(w)
        lp.addLayout(filterrow); self.log_text = QPlainTextEdit(); self.log_text.setReadOnly(True); self.log_text.setMaximumBlockCount(1000); self.log_text.setMinimumHeight(80); lp.addWidget(self.log_text); cv.addWidget(self.log_panel,1); self.log_panel.hide()
        self.log_toggle.toggled.connect(self.toggle_logs); self.log_source.currentChanged.connect(self.render_logs); self.search.textChanged.connect(self.render_logs); self.errors_only.toggled.connect(self.render_logs)
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(redact(self.log_text.textCursor().selectedText() or self.log_text.toPlainText())))
        self.open_logs.clicked.connect(self.open_log_folder); self.dashboard_button.clicked.connect(self.open_dashboard)
        self.connect_button.clicked.connect(lambda: self.operation(adapter.connect)); self.disconnect_button.clicked.connect(lambda: self.connection_operation(adapter.disconnect))
        self.verify_button.clicked.connect(lambda: self.operation(getattr(adapter, 'verify_connection', lambda: {'verified': True}), lambda _: self.poll()))
        self.reconnect_ssh_button.clicked.connect(lambda: self.connection_operation(getattr(adapter, 'reconnect_ssh', lambda: {'reconnected': True})))
        self.refresh_button.clicked.connect(self.refresh_ports); self.save_button.clicked.connect(self.save_settings)
        self.connection_lines = []; self.last_connection_error=''; self.last_connection_state=''; self.error_repeats=0
        self.operation(adapter.settings, self.load_settings); self.refresh_ports()
        self.timer = QTimer(self); self.timer.setInterval(1200); self.timer.timeout.connect(self.poll); self.timer.start(); self.poll()
        self.connect_button.setObjectName('primary')
        self.setStyleSheet('''
            QMainWindow{background:#f3f5f8;} QWidget{color:#243247;font-size:12px;}
            QTabWidget::pane{background:#fff;border:1px solid #dce3ec;border-radius:8px;}
            QTabBar::tab{padding:7px 13px;background:transparent;color:#64748b;}
            QTabBar::tab:selected{color:#245bd6;background:#eaf0ff;border-radius:5px;}
            QGroupBox{border:0;margin-top:12px;padding:5px;} QGroupBox::title{subcontrol-origin:margin;left:5px;font-weight:600;}
            QPushButton{background:#fff;border:1px solid #d8e0ea;border-radius:6px;padding:5px 10px;}
            QPushButton:hover{background:#edf2fc;border-color:#9db6ed;} QPushButton:disabled{color:#9ba7b8;background:#f7f9fc;}
            QPushButton#primary{background:#2d62df;color:white;border-color:#2d62df;}
            QLineEdit,QComboBox,QSpinBox{background:white;border:1px solid #d8e0ea;border-radius:5px;min-height:25px;padding:0 5px;}
            QListWidget{border:1px solid #e2e8f0;border-radius:6px;background:#fafbfd;outline:0;}
            QListWidget::item{padding:7px 9px;border-bottom:1px solid #eef2f6;}
            QListWidget::item:selected{background:#eaf0ff;color:#245bd6;}
            QPlainTextEdit{border:1px solid #dce3ec;border-radius:6px;background:#fafbfd;font-family:Consolas,Menlo,monospace;font-size:11px;}
        ''')

    def path_row(self, field, title):
        row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0,0,0,0); layout.addWidget(field, 1); button = QPushButton('찾아보기…'); layout.addWidget(button)
        def choose():
            path, _ = QFileDialog.getOpenFileName(self, title, field.text() if field.text() else str(self.adapter.home))
            if path: field.setText(path)
        button.clicked.connect(choose); return row

    def operation(self, fn, done=None, failed=None):
        task = Task(fn); self.tasks.add(task)
        def finished(value):
            if done: done(value)
            self.tasks.discard(task)
        task.signals.done.connect(finished); task.signals.failed.connect(self.show_error); task.signals.failed.connect(lambda _: self.tasks.discard(task))
        if failed:
            task.signals.failed.connect(failed)
        QThreadPool.globalInstance().start(task)

    def connection_operation(self, operation):
        self.clear_dashboard_link()
        self.operation(operation, lambda _: self.poll())

    def show_error(self, text):
        self.pending = False; self.error.setText(redact(text)); self.error.setVisible(bool(text)); self.connection_lines.append('ERROR ' + redact(text)); self.connection_lines = self.connection_lines[-300:]; self.render_logs()

    def poll(self):
        checked = self.snapshot.get('last_checked_at') or 0
        if not 0 <= time.time() - checked <= 15:
            self.clear_dashboard_link()
        if self.snapshot.get('plugin_receipt') and not 0 <= time.time() - checked <= 15:
            self.plugin_status.setText('플러그인 현재 상태 확인 필요 · 커넥터 응답 대기')
        if self.pending: return
        self.pending = True; self.operation(self.adapter.status, self.render, self.clear_dashboard_link)

    def render(self, value):
        import datetime
        error=redact(value.get('error',''))
        if error:
            if error==self.last_connection_error and self.connection_lines:
                self.error_repeats+=1; self.connection_lines[-1]=self.connection_lines[-1].split(' · 반복 ')[0]+f' · 반복 {self.error_repeats}'
            else:
                self.error_repeats=1; self.connection_lines.append(datetime.datetime.now().strftime('%H:%M:%S')+' ERROR '+error)
            self.last_connection_error=error
        else:
            self.last_connection_error=''
            if value['state']!=self.last_connection_state:self.connection_lines.append(datetime.datetime.now().strftime('%H:%M:%S')+' INFO '+value['state'])
        self.last_connection_state=value['state'];self.connection_lines=self.connection_lines[-300:]
        self.shared_panel.connection(value)
        self.pending = False; self.snapshot = value; self.state.setText('● ' + {'CONNECTED':'연결됨', 'CONNECTING':'연결 중', 'DISCONNECTED':'미연결', 'ERROR':'오류'}.get(value['state'], value['state']))
        if value.get('shared_monitor') is None and self.dashboard_link() is not None:
            self.monitor_task.hide()
            self.dashboard_button.setEnabled(True)
            self.dashboard_button.show()
        elif value.get('shared_monitor') is None:
            self.clear_dashboard_link()
        self.error.setText(redact(value.get('error', ''))); self.error.setVisible(bool(value.get('error')))
        self.space.setText('공통 설정은 플러그인·Agent Monitor·ACON과 동기화됩니다.' if value.get('source_ready',True) else '연결은 정상입니다. 환경설정에서 서버의 TC 소스를 선택하세요.')
        analyses=value.get('analyses', [])
        analyses=value.get('analyses') or value.get('pending_analyses') or []
        if isinstance(analyses, dict): analyses=analyses.get('analyses', [])
        active_run = value.get('active_run')
        if active_run:
            self.space.setText(self.space.text() + f" · 실행 {active_run.get('run_id','')[:8]} {active_run.get('state','')}" + (' (분석 래치)' if active_run.get('analysis_latched') else ''))
        if analyses:
            self.space.setText(self.space.text()+' · 분석 '+str(analyses[0].get('status','대기')))
        storage=value.get('storage')
        if storage: self.space.setText(self.space.text()+f" · 로컬 {storage['runtime_bytes']/1024**2:.1f} MiB"+(' 이상 · 일부 집계' if storage.get('partial') else '')+(' · 진행 작업 보호' if storage['protected'] else ''))
        labels = {'local':'로컬 Host', 'ssh':'SSH -R', 'overall':'직결', 'agent_monitor':'모니터(선택)'}
        stage_map = {'READY':'정상','CONNECTED':'연결됨','WAITING':'대기','OPTIONAL_OFFLINE':'선택(미연결)','runner_ready':'준비 중','ssh_starting':'연결 중','ssh_running':'연결 중','AUTH_OR_CONFIG_ERROR':'인증/설정 오류','RECONNECTING':'재연결 중','REGISTRATION_FAILED':'실패'}
        self.stage.setText('   ·   '.join(labels[k] + ' ' + stage_map.get(value.get('stages',{}).get(k), '—') for k in labels))
        receipt = value.get('plugin_receipt')
        self.plugin_toggle.setVisible(bool(receipt))
        if receipt:
            labels = {'CONNECTED': '연동 확인', 'STALE': '마지막 보고 만료', 'MISMATCH': '연결 정보 불일치'}
            live = (value.get('fresh') and value.get('state') == 'CONNECTED' and not value.get('stale')
                    and 0 <= time.time() - (value.get('last_checked_at') or 0) <= 15)
            label = labels.get(receipt['state'], '확인 필요') if live else '현재 상태 확인 필요'
            seen = datetime.datetime.fromtimestamp(receipt['observed_at']).strftime('%Y-%m-%d %H:%M:%S')
            self.plugin_status.setText(f"플러그인 {label} · 마지막 수신 {seen} · {receipt['linux_host']}:{receipt['port']}")
            settings = receipt.get('settings')
            text = json.dumps(settings, indent=2, ensure_ascii=False) if settings else '이 보고에서 확인할 수 있는 설정값이 없습니다.'
            if self.plugin_values.toPlainText() != text:
                self.plugin_values.setPlainText(text)
        else:
            self.plugin_status.setText('플러그인 연결 보고 대기')
            self.plugin_toggle.setChecked(False)
            self.plugin_values.clear()
        if value.get('shared_monitor') is not None:
            self.render_monitor_tasks(value)
        peer_warnings = value.get('peer_warnings') or (value.get('diagnostics') or {}).get('peer_warnings') or []
        if peer_warnings and not value.get('error'):
            self.error.setText('피어 연결 불일치 경고: ' + ', '.join(f"{w.get('peer_type','peer')} ({(w.get('client_issue') or {}).get('code') or w.get('client_status')})" for w in peer_warnings))
            self.error.setVisible(True)
        rd = value.get('readiness') or (value.get('diagnostics') or {}).get('readiness') or {}
        if value.get('state') == 'CONNECTED' and rd and not rd.get('execution_ready', True):
            self.space.setText(self.space.text() + ' · 실행 준비 확인 필요(COM/Python)')
        colors = {'CONNECTED':'#258557', 'RUNNING':'#ac7813', 'ERROR':'#c44242', 'UNKNOWN':'#ac7813', 'RESERVED':'#ac7813', 'DISCONNECTED':'#929ba5'}
        texts = {'CONNECTED':'연결', 'RUNNING':'시험 중', 'ERROR':'오류', 'UNKNOWN':'확인 필요', 'RESERVED':'예약', 'DISCONNECTED':'미연결'}
        boards=value.get('boards', [])
        self.serial_status.setText('자동 COM 공유 적용됨' if value.get('state')=='CONNECTED' and value.get('fresh') is True and boards and all(b.get('serial_proxy') and not b.get('stale') for b in boards) else '다음 연결 시 자동 적용')
        self.board_summary.setText(f"등록 {len(boards)}대 · 감지 {sum(bool(b.get('detected')) for b in boards)}대 · 시험 중 {sum(b.get('state')=='RUNNING' for b in boards)}대")
        ids = {b['board_id'] for b in boards}
        for identity in list(self.board_items):
            if identity not in ids:
                self.board_list.takeItem(self.board_list.row(self.board_items.pop(identity)))
        for board in boards:
            identity = board['board_id']; state = board.get('state','UNKNOWN')
            if identity not in self.board_items:
                item = QListWidgetItem(); item.setData(Qt.UserRole,identity); self.board_list.addItem(item); self.board_items[identity] = item
            item = self.board_items[identity]
            label = '●  ' + board.get('name',identity) + '    ' + board['com'] + '    ' + ('수동 제어' if board.get('serial_proxy',{}).get('owner')=='manual' else texts.get(state,state))
            if item.text() != label: item.setText(label); item.setForeground(QColor(colors.get(state,'#929ba5')))
        self.board_labels = list(self.board_items.values())
        if self.board_list.currentItem() is None and self.board_list.count(): self.board_list.setCurrentRow(0)
        self.select_board()
        text = path_text(value)
        if self.paths_text.toPlainText() != text: self.paths_text.setPlainText(text)
        self.render_logs()

    def capture_board_drafts(self):
        for index, row in enumerate(self.board_rows):
            data=self.board_drafts[index]; data['name']=row['name'].text(); data['board']['com']=row['com'].currentData() or ''
            node=row['node'].text().strip()
            if node: data['board']['node']=node
            else: data['board'].pop('node',None)
            data['baudrate']=row['baud'].value()

    def resize_boards(self,count):
        import secrets
        self.capture_board_drafts()
        while len(self.board_drafts)<count:
            index=len(self.board_drafts)+1
            self.board_drafts.append({'board':{'board_id':'board-'+secrets.token_hex(4),'host':self.profile.get('boards',[{}])[0].get('host','TEST-PC') if self.profile.get('boards') else 'TEST-PC','com':''},'name':f'보드 {index}','observer':{}})
        for row in self.board_rows: row['widget'].deleteLater(); self.board_editor.removeTab(self.board_editor.indexOf(row['widget']))
        self.board_rows=[]
        for index,data in enumerate(self.board_drafts[:count]):
            widget=QWidget(); form=QFormLayout(widget); name=QLineEdit(data['name']); node=QLineEdit(data['board'].get('node','')); com=QComboBox()
            for combo,selected in ((com,data['board'].get('com','')),):
                combo.addItem('미설정','')
                for port in self.port_choices: combo.addItem(port['com']+' · '+port.get('description',''),port['com'])
                if selected and combo.findData(selected)<0: combo.addItem(selected+' · 미연결',selected)
                combo.setCurrentIndex(max(0,combo.findData(selected)))
            baud=QSpinBox(); baud.setRange(1,12000000); baud.setValue(data.get('baudrate',115200))
            form.addRow('이름',name); form.addRow('보드 COM',com); form.addRow('통신 속도',baud); form.addRow('노드 (선택)',node)
            self.board_editor.addTab(widget,f'보드 {index+1}'); self.board_rows.append(dict(widget=widget,name=name,node=node,com=com,baud=baud))
        self.com=self.board_rows[0]['com']

    def load_settings(self, profile):
        self.profile = copy.deepcopy(profile); state = profile.get('_setup', {}); self.server.setText(state.get('server','')); self.account.setText(state.get('account','')); self.ssh_port.setValue(state.get('ssh_port',22)); self.dashboard_port.setValue(state.get('remote_dashboard_port',8766)); self.ssh_key.setText(state.get('ssh_key','')); self.python_path.setText(profile.get('python','')); self.putty_path.setText(profile.get('putty_path','')); self.serial_status.setText('다음 연결 시 자동 적용')
        # Replace the draft only; discard/reduce never deletes execution history.
        for row in self.board_rows: self.board_editor.removeTab(self.board_editor.indexOf(row['widget'])); row['widget'].deleteLater()
        self.board_rows=[]; self.board_drafts=[]
        for board in profile.get('boards',[]):
            self.board_drafts.append({'board':copy.deepcopy(board),'name':profile.get('board_names',{}).get(board['board_id'],board['board_id']),'baudrate':profile.get('serial_settings',{}).get(board['board_id'],{}).get('baudrate',115200),'observer':copy.deepcopy(profile.get('console_observers',{}).get(board['board_id'],{}))})
        count=max(1,len(self.board_drafts)); self.board_drafts.extend(copy.deepcopy(profile.get('connector_inactive_boards',[]))); self.board_count.blockSignals(True); self.board_count.setValue(count); self.board_count.blockSignals(False); self.resize_boards(count); self.refresh_ports()

    def refresh_ports(self):
        def fill(ports):
            self.capture_board_drafts(); self.port_choices=ports; self.resize_boards(self.board_count.value())
        self.operation(self.adapter.ports, fill)

    def save_settings(self):
        self.capture_board_drafts(); count=self.board_count.value()
        boards=[copy.deepcopy(data['board']) for data in self.board_drafts[:count]]
        controls=[b['com'].upper() for b in boards]
        if not all(controls) or len(set(controls))!=len(controls):
            self.show_error('보드별 COM을 선택하고 중복을 해소하세요.'); return
        observers=copy.deepcopy(self.profile.get('console_observers',{}))
        observers.update({data['board']['board_id']:copy.deepcopy(data['observer']) for data in self.board_drafts[:count] if data.get('observer')})
        names={data['board']['board_id']:data['name'] for data in self.board_drafts[:count]}
        setup = dict(self.profile.get('_setup', {}), server=self.server.text().strip(), account=self.account.text().strip(), ssh_port=self.ssh_port.value(), remote_dashboard_port=self.dashboard_port.value(), ssh_key=self.ssh_key.text().strip())
        inactive=copy.deepcopy(self.board_drafts[count:])
        patch={'_setup':setup,'python':self.python_path.text().strip(),'boards':boards,'console_observers':observers,'board_names':names,'connector_inactive_boards':inactive,'serial_transport':'proxy','putty_path':self.putty_path.text().strip(), 'serial_settings':{d['board']['board_id']:dict(self.profile.get('serial_settings',{}).get(d['board']['board_id'],{}),baudrate=d.get('baudrate',115200)) for d in self.board_drafts[:count]}}
        self.operation(lambda: self.adapter.save(patch), self.saved)

    def saved(self,value): self.profile=value; self.connection_lines.append('INFO 설정 저장 완료'); self.error.setText('설정을 저장했습니다.'); self.render_logs()
    def change_scenario(self,value): self.adapter.scenario=value; self.poll()
    def toggle_logs(self,value):
        self.log_panel.setVisible(value); self.log_toggle.setText('▾ 로그 닫기' if value else '▸ 로그 보기')
        self.space.setVisible(not value)
        if value: self.paths_toggle.setChecked(False)
        self.render_logs()
    def render_logs(self,*args):
        source = self.log_source.currentIndex(); value = self.snapshot
        if source == 0: lines = ['[' + row['board_id'] + ' · ' + row.get('phase','') + ' · ' + row.get('code','') + ']\n' + row.get('text','') for row in value.get('console',{}).get('boards',[]) if row['board_id']==self.selected_board()]
        elif source == 1: lines = ['[' + row['id'] + ' · ' + row['state'] + ']\n' + row.get('stdout','') + row.get('stderr','') for row in value.get('executions',[]) if not row.get('board_ids') or self.selected_board() in row['board_ids']]
        elif source == 2: lines = self.connection_lines
        else: lines = [str(row) for row in value.get('console',{}).get('errors',[]) if not row.get('board_id') or row['board_id']==self.selected_board()]
        text = redact('\n'.join(lines))[-65536:]
        if source==0 and value.get('console',{}).get('stale'): text='[과거 로그 · 연결 상태 확인 필요]\n'+text
        if self.errors_only.isChecked(): text='\n'.join(line for line in text.splitlines() if any(word in line.upper() for word in ('ERROR','PANIC','FAIL','GAP','UNKNOWN','오류')))
        needle = self.search.text().casefold()
        if needle: text='\n'.join(line for line in text.splitlines() if needle in line.casefold())
        previous = self.log_text.toPlainText()
        if previous == text: return
        bar = self.log_text.verticalScrollBar(); following = bar.value() >= bar.maximum()-2; scroll = bar.value()
        cursor = self.log_text.textCursor(); position = cursor.position(); anchor = cursor.anchor()
        if previous and text.startswith(previous):
            end = QTextCursor(self.log_text.document()); end.movePosition(QTextCursor.End); end.insertText(text[len(previous):])
        else: self.log_text.setPlainText(text)
        maximum = self.log_text.document().characterCount()-1
        cursor.setPosition(min(anchor,maximum)); cursor.setPosition(min(position,maximum),QTextCursor.KeepAnchor); self.log_text.setTextCursor(cursor)
        bar.setValue(bar.maximum() if following else scroll)
    def selected_board(self):
        item = self.board_list.currentItem()
        return item.data(Qt.UserRole) if item else None
    def render_tests(self):
        data = self.snapshot.get('test_status') or {}
        run = data.get('active_run')
        if run and data.get('steps') and (run.get('active') or not data.get('has_projection')):
            label = '현재 실행' if run.get('active') else '최근 실행'
            data = dict(data, source={'location': f"{label} · {run['run_id']}"}, projection_stale=False,
                        message='플러그인이 지정한 실행 순서',
                        items=[{'path': step['path'], 'run_step': step} for step in data['steps']])
        stale = self.snapshot.get('state') != 'CONNECTED' or self.snapshot.get('fresh') is not True or data.get('stale') or data.get('projection_stale')
        self.tc_note.setText(' · '.join(filter(None, ['테스트 스크립트', (data.get('source') or {}).get('location') or data.get('tc_root'),
            '과거 수신 정보 · 현재 상태 확인 필요' if stale and data else '', data.get('message'), '상태 조회 전용'])))
        if 'items' in data:
            signature = [(item['path'], {'label': (item.get('run_step') or {}).get('state', '미실행'), 'historical': False, 'run_id': (item.get('run_step') or {}).get('run_id', ''), 'run_state': (item.get('run_step') or {}).get('state', '')} if item.get('run_step') else None) for item in data.get('items', [])]
        else:
            rows = data.get('rows', [])
            signature = [(row['path'], row.get('boards', {}).get(self.selected_board())) for row in rows]
        if getattr(self, 'tc_signature', None) == signature:
            return
        self.tc_signature = signature
        self.tc_table.setRowCount(len(signature))
        for index, (path, status) in enumerate(signature):
            self.tc_table.setItem(index, 0, QTableWidgetItem(path))
            item = QTableWidgetItem(status['label'] if status else '미실행')
            if status:
                item.setToolTip(('이전 실행' if status.get('historical') else '현재 실행') + ' · ' + str(status.get('run_id', '')) + ' · ' + str(status.get('run_state', '')))
            self.tc_table.setItem(index, 1, item)
    def select_board(self, *args):
        board = next((b for b in self.snapshot.get('boards',[]) if b['board_id']==self.selected_board()), {})
        proxy = board.get('serial_proxy',{})
        ready = self.snapshot.get('state')=='CONNECTED' and proxy.get('state')=='READY' and not board.get('stale')
        busy = any(b.get('state') in {'RUNNING','UNKNOWN','RESERVED'} and b.get('serial_proxy',{}).get('owner')!='manual' for b in self.snapshot.get('boards',[]))
        cleanup = any(r.get('board_id')==self.selected_board() for r in self.snapshot.get('putty_cleanup',[]))
        self.putty_button.setText('제어권 반환 중' if cleanup else 'PuTTY 열림' if proxy.get('putty_connected') else 'PuTTY 여는 중' if proxy.get('owner')=='manual' else 'PuTTY 열기')
        self.putty_button.setToolTip('입력 제어권 반환 재시도 중' if cleanup else '')
        self.putty_button.setEnabled(ready and self.snapshot.get('fresh') is True and not cleanup and not busy and not proxy.get('owner') and not proxy.get('putty_connected'))
        if hasattr(self,'log_text'): self.render_logs()
        if hasattr(self,'tc_table'): self.render_tests()
    def open_putty(self):
        board = self.selected_board()
        if board: self.operation(lambda:self.adapter.putty(board), lambda _:self.poll())
    def clear_dashboard_link(self, *_):
        self.snapshot['dashboard_url'] = ''
        if self.snapshot.get('shared_monitor'):
            self.render_monitor_tasks(dict(self.snapshot, fresh=False))
        else:
            self.monitor_task.hide()
            self.dashboard_button.hide()

    def select_monitor_task(self, index):
        self.monitor_selection = self.monitor_task.itemData(index)
        self.render_monitor_tasks(self.snapshot)

    def render_monitor_tasks(self, value):
        import datetime
        monitor = value['shared_monitor']
        tasks = monitor.get('tasks', [])
        owner = next((row for row in tasks if row['task_id'] == monitor.get('active_task_id')), None)
        owner_blocked = bool(monitor.get('active_task_id') and owner is None)
        latest = max(tasks, key=lambda row: row.get('last_seen_at') or 0, default=None)
        checked = value.get('last_checked_at') or 0
        ready = (value.get('fresh') is True and not value.get('stale') and 0 <= time.time() - checked <= 15
                 and monitor.get('state') == 'READY')

        def label(row):
            return f"{row.get('project') or row['task_id']} · {row.get('account') or ''}"

        report = []
        if monitor.get('state') == 'ACCESS_DENIED':
            report.append('작업 조회 권한을 확인하세요.')
        elif not ready:
            report.append('SSH 또는 작업 조회 서버가 오프라인입니다.')
        elif not tasks:
            report.append('등록된 플러그인 작업이 없습니다.')
        if latest:
            seen = datetime.datetime.fromtimestamp(latest.get('last_seen_at') or 0).strftime('%Y-%m-%d %H:%M:%S')
            report.append('마지막 보고 ' + label(latest) + ' · ' + seen)
        report.append('Run 소유 작업 ' + (label(owner) if owner else '조회 권한 확인 필요' if owner_blocked else '없음'))

        states = {'UNREGISTERED': ' · 목적지 미등록', 'OFFLINE': ' · 오프라인'}
        choices = [(row['task_id'], label(row) + states.get(row.get('monitor_state'), '')) for row in tasks]
        if choices != self.monitor_choices:
            self.monitor_choices = choices
            self.monitor_task.clear()
            self.monitor_task.addItem('작업 선택', None)
            for task_id, text in choices:
                self.monitor_task.addItem(text, task_id)
        if not any(task_id == self.monitor_selection for task_id, _ in choices):
            self.monitor_selection = None
        selected = self.monitor_selection or monitor.get('default_task_id')
        selected_row = next((row for row in tasks if row['task_id'] == selected), {})
        if selected_row.get('monitor_state') == 'UNREGISTERED':
            report.append('선택한 작업의 Monitor 목적지가 등록되지 않았습니다.')
        self.plugin_status.setText(' | '.join(report))
        index = self.monitor_task.findData(selected)
        self.monitor_task.setCurrentIndex(max(index, 0))
        self.monitor_task.setVisible(len(tasks) > 1 or owner_blocked)
        self.monitor_task.setEnabled(ready and not self.monitor_opening)
        self.dashboard_button.setVisible(True)
        self.dashboard_button.setEnabled(ready and index > 0 and not self.monitor_opening)

    def dashboard_link(self):
        value = self.snapshot
        checked = value.get('last_checked_at') or 0
        if (self.adapter.preview or value.get('fresh') is not True or value.get('stale')
                or not 0 <= time.time() - checked <= 15
                or (value.get('state') != 'CONNECTED' and value.get('connection_mode') != 'legacy')):
            return None
        url = QUrl(value.get('dashboard_url') or '')
        if url.isValid() and url.scheme() == 'http' and url.host() == '127.0.0.1' and not url.userInfo():
            return url

    def open_dashboard(self):
        if self.snapshot.get('shared_monitor') is not None:
            self.render_monitor_tasks(self.snapshot)
            task_id = self.monitor_task.currentData()
            if not task_id or not self.dashboard_button.isEnabled():
                return
            self.monitor_opening = True
            self.dashboard_button.setEnabled(False)

            def finished(value=None):
                self.monitor_opening = False
                if self.snapshot.get('shared_monitor') is not None:
                    self.render_monitor_tasks(self.snapshot)
                if not value:
                    return
                url = QUrl(value.get('url', ''))
                task = QUrlQuery(url).queryItemValue('task')
                if (url.isValid() and url.scheme() == 'http' and url.host() == '127.0.0.1'
                        and not url.userInfo() and url.path() == '/plugin-task/'
                        and task == task_id and url.fragment().startswith('ticket=')):
                    if QDesktopServices.openUrl(url):
                        return
                self.show_error('연결된 작업 Monitor를 열 수 없습니다.')

            self.operation(lambda: self.adapter.open_task_monitor(task_id), finished, lambda _: finished())
            return
        url = self.dashboard_link()
        if url is not None:
            QDesktopServices.openUrl(url)
    def open_log_folder(self):
        if self.adapter.preview: self.error.setText('미리보기 로그는 격리된 임시 프로파일에만 있습니다.'); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.adapter.home/'logs')))
    def closeEvent(self,event): self.timer.stop(); event.accept()  # detach; never disconnect/kill
