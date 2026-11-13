"""Shared Qt Widgets view/controller, production IPC or isolated mock injected."""
import copy
from pathlib import Path
import socket

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QColor, QTextCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QTabBar, QFormLayout, QLineEdit, QComboBox, QGroupBox, QPlainTextEdit,
    QCheckBox, QFileDialog, QMessageBox, QScrollArea, QSpinBox, QListWidget, QListWidgetItem)
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
        self.connect_button = QPushButton('연결'); self.disconnect_button = QPushButton('연결 종료'); self.dashboard_button = QPushButton('대시보드 열기')
        for button in (self.connect_button, self.disconnect_button, self.dashboard_button): top.addWidget(button)
        cv.addLayout(top)
        self.stage = QLabel('로컬 커넥터  —     SSH  —     대시보드  —     역방향 응답  —'); self.stage.setWordWrap(True); cv.addWidget(self.stage)
        self.board_box = QGroupBox('보드'); self.board_layout = QVBoxLayout(self.board_box); cv.addWidget(self.board_box)
        self.board_labels = []; self.board_items = {}
        self.board_list = QListWidget(); self.board_list.setMinimumHeight(65); self.board_list.setMaximumHeight(115)
        self.board_layout.addWidget(self.board_list); self.board_list.currentItemChanged.connect(self.select_board)
        controls = QHBoxLayout(); self.putty_button = QPushButton('PuTTY 열기'); self.manual_button = QPushButton('수동 제어')
        controls.addWidget(self.putty_button); controls.addWidget(self.manual_button); controls.addStretch(); cv.addLayout(controls)
        self.putty_button.clicked.connect(self.open_putty); self.manual_button.clicked.connect(self.manual_control)
        self.board_summary=QLabel('등록 0대 · 감지 0대 · 시험 중 0대'); controls.addWidget(self.board_summary)
        self.error = QLabel(''); self.error.setWordWrap(True); self.error.setStyleSheet('color:#b63d3d;'); cv.addWidget(self.error); self.error.hide()
        self.space = QLabel('TC 소스·제한시간·세션 삭제는 공통 대시보드에서 관리합니다.'); self.space.setWordWrap(True); cv.addWidget(self.space)
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
        form.addRow('Linux SSH 서버', self.server); form.addRow('계정', self.account); form.addRow('대시보드 서버 포트', self.dashboard_port)
        self.python_path = QLineEdit(); form.addRow('TC Python', self.path_row(self.python_path, 'TC Python 선택'))
        self.ssh_key = QLineEdit(); self.putty_path = QLineEdit(); advanced=QWidget(); af=QFormLayout(advanced); af.setContentsMargins(0,0,0,0); af.addRow('SSH 포트',self.ssh_port); af.addRow('SSH 키 (선택)',self.path_row(self.ssh_key,'SSH 개인 키 선택')); af.addRow('PuTTY (자동 검색)',self.path_row(self.putty_path,'putty.exe 선택')); advanced.hide(); toggle=QPushButton('고급 연결 설정'); toggle.setCheckable(True); toggle.toggled.connect(advanced.setVisible); form.addRow('',toggle); form.addRow(advanced)
        self.board_count = QSpinBox(); self.board_count.setRange(1,32); self.board_count.setValue(1)
        self.transport = QComboBox(); self.transport.addItem('포트 멀티플렉서', 'proxy'); self.transport.addItem('기존 COM 직접 연결', 'native')
        form.addRow('통신 방식', self.transport)
        self.transport.currentIndexChanged.connect(self.show_transport_fields)
        form.addRow('연결할 보드 수', self.board_count)
        self.board_editor = QTabWidget(); self.board_editor.setUsesScrollButtons(True)
        form.addRow(self.board_editor)
        self.board_rows = []; self.board_drafts = []; self.port_choices = []
        self.refresh_button = QPushButton('COM 새로고침'); form.addRow('', self.refresh_button)
        self.board_count.valueChanged.connect(self.resize_boards)
        self.resize_boards(1)
        note = QLabel('멀티플렉서는 실제 COM 하나로 TC·PuTTY·로그를 연결합니다. TC 공통 모듈 연동이 필요합니다.\nTC 폴더는 공통 서버에서 한 번 선택합니다.\nSSH는 사전 인증된 키/agent를 사용합니다. 암호·host key 확인은 OpenSSH 콘솔에서 먼저 완료하세요.'); note.setWordWrap(True); note.setStyleSheet('color:#68788b;'); form.addRow(note)
        self.save_button = QPushButton('설정 저장'); self.cancel_button=QPushButton('변경 취소'); save_row=QWidget(); sv=QHBoxLayout(save_row); sv.setContentsMargins(0,0,0,0); sv.addWidget(self.save_button); sv.addWidget(self.cancel_button); form.addRow('', save_row)
        self.cancel_button.clicked.connect(lambda: self.load_settings(copy.deepcopy(self.profile)))
        loghead = QHBoxLayout(); self.log_toggle = QPushButton('▸ 로그 보기'); self.log_toggle.setCheckable(True); loghead.addWidget(self.log_toggle); loghead.addStretch(); loghead.addWidget(self.paths_toggle); self.log_source = QTabBar(); [self.log_source.addTab(label) for label in ['보드 콘솔','TC 실행','연결','플러그인 오류']]; cv.addLayout(loghead)
        self.log_panel = QWidget(); lp = QVBoxLayout(self.log_panel); lp.setContentsMargins(0, 0, 0, 0); lp.addWidget(self.log_source); filterrow = QHBoxLayout(); self.errors_only = QCheckBox('오류만'); self.search = QLineEdit(); self.search.setPlaceholderText('로그 검색'); self.copy = QPushButton('복사'); self.open_logs = QPushButton('로그 열기')
        for w in (self.errors_only, self.search, self.copy, self.open_logs): filterrow.addWidget(w)
        lp.addLayout(filterrow); self.log_text = QPlainTextEdit(); self.log_text.setReadOnly(True); self.log_text.setMaximumBlockCount(1000); self.log_text.setMinimumHeight(80); lp.addWidget(self.log_text); cv.addWidget(self.log_panel,1); self.log_panel.hide()
        self.log_toggle.toggled.connect(self.toggle_logs); self.log_source.currentChanged.connect(self.render_logs); self.search.textChanged.connect(self.render_logs); self.errors_only.toggled.connect(self.render_logs)
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(redact(self.log_text.textCursor().selectedText() or self.log_text.toPlainText())))
        self.open_logs.clicked.connect(self.open_log_folder); self.dashboard_button.clicked.connect(self.open_dashboard)
        self.connect_button.clicked.connect(lambda: self.operation(adapter.connect)); self.disconnect_button.clicked.connect(lambda: self.operation(adapter.disconnect))
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

    def operation(self, fn, done=None):
        task = Task(fn); self.tasks.add(task)
        def finished(value):
            if done: done(value)
            self.tasks.discard(task)
        task.signals.done.connect(finished); task.signals.failed.connect(self.show_error); task.signals.failed.connect(lambda _: self.tasks.discard(task)); QThreadPool.globalInstance().start(task)

    def show_error(self, text):
        self.pending = False; self.error.setText(redact(text)); self.error.setVisible(bool(text)); self.connection_lines.append('ERROR ' + redact(text)); self.connection_lines = self.connection_lines[-300:]; self.render_logs()

    def poll(self):
        if self.pending: return
        self.pending = True; self.operation(self.adapter.status, self.render)

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
        self.pending = False; self.snapshot = value; self.state.setText('● ' + {'CONNECTED':'연결됨', 'CONNECTING':'연결 중', 'DISCONNECTED':'미연결', 'ERROR':'오류'}.get(value['state'], value['state']))
        self.error.setText(redact(value.get('error', ''))); self.error.setVisible(bool(value.get('error')))
        self.space.setText('TC 소스·제한시간·세션은 공통 대시보드에서 관리합니다.' if value.get('source_ready',True) else '연결은 정상입니다. TC 실행 전 대시보드에서 소스를 선택하세요.')
        storage=value.get('storage')
        if storage: self.space.setText(self.space.text()+f" · 로컬 {storage['runtime_bytes']/1024**2:.1f} MiB"+(' 이상 · 일부 집계' if storage.get('partial') else '')+(' · 진행 작업 보호' if storage['protected'] else ''))
        labels = {'local':'로컬', 'ssh':'SSH', 'dashboard':'대시보드', 'roundtrip':'역방향 응답'}
        self.stage.setText('   ·   '.join(labels[k] + ' ' + {'READY':'정상','WAITING':'대기','runner_ready':'준비 중','ssh_starting':'연결 중','ssh_running':'연결 중','REGISTRATION_FAILED':'실패'}.get(value.get('stages',{}).get(k), '—') for k in labels))
        colors = {'CONNECTED':'#258557', 'RUNNING':'#ac7813', 'ERROR':'#c44242', 'UNKNOWN':'#ac7813', 'RESERVED':'#ac7813', 'DISCONNECTED':'#929ba5'}
        texts = {'CONNECTED':'연결', 'RUNNING':'시험 중', 'ERROR':'오류', 'UNKNOWN':'확인 필요', 'RESERVED':'예약', 'DISCONNECTED':'미연결'}
        boards=value.get('boards', [])
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
            data['observer']=dict(data.get('observer',{}),port=row['rx'].currentData() or '',rx_only_confirmed=row['confirm'].isChecked(),control_lines_isolated=row['confirm'].isChecked())

    def resize_boards(self,count):
        import secrets
        self.capture_board_drafts()
        while len(self.board_drafts)<count:
            index=len(self.board_drafts)+1
            self.board_drafts.append({'board':{'board_id':'board-'+secrets.token_hex(4),'host':self.profile.get('boards',[{}])[0].get('host','TEST-PC') if self.profile.get('boards') else 'TEST-PC','com':''},'name':f'보드 {index}','observer':{}})
        for row in self.board_rows: row['widget'].deleteLater(); self.board_editor.removeTab(self.board_editor.indexOf(row['widget']))
        self.board_rows=[]
        for index,data in enumerate(self.board_drafts[:count]):
            widget=QWidget(); form=QFormLayout(widget); name=QLineEdit(data['name']); node=QLineEdit(data['board'].get('node','')); com=QComboBox(); rx=QComboBox(); confirm=QCheckBox('RX 전용·제어선 격리 확인')
            for combo,selected in ((com,data['board'].get('com','')),(rx,data.get('observer',{}).get('port',''))):
                combo.addItem('미설정','')
                for port in self.port_choices: combo.addItem(port['com']+' · '+port.get('description',''),port['com'])
                if selected and combo.findData(selected)<0: combo.addItem(selected+' · 미연결',selected)
                combo.setCurrentIndex(max(0,combo.findData(selected)))
            confirm.setChecked(data.get('observer',{}).get('rx_only_confirmed') is True)
            baud=QSpinBox(); baud.setRange(1,12000000); baud.setValue(data.get('baudrate',115200))
            legacy=QWidget(); lf=QFormLayout(legacy); lf.setContentsMargins(0,0,0,0); lf.addRow('콘솔 RX COM',rx); lf.addRow('',confirm)
            form.addRow('이름',name); form.addRow('보드 COM',com); form.addRow('통신 속도',baud); form.addRow('노드 (선택)',node); form.addRow(legacy)
            legacy.setVisible(self.transport.currentData()=='native')
            self.board_editor.addTab(widget,f'보드 {index+1}'); self.board_rows.append(dict(widget=widget,name=name,node=node,com=com,rx=rx,confirm=confirm,baud=baud,legacy=legacy))
        self.com=self.board_rows[0]['com']; self.rx=self.board_rows[0]['rx']; self.rx_confirm=self.board_rows[0]['confirm']

    def load_settings(self, profile):
        self.profile = copy.deepcopy(profile); state = profile.get('_setup', {}); self.server.setText(state.get('server','')); self.account.setText(state.get('account','')); self.ssh_port.setValue(state.get('ssh_port',22)); self.dashboard_port.setValue(state.get('remote_dashboard_port',8766)); self.ssh_key.setText(state.get('ssh_key','')); self.python_path.setText(profile.get('python','')); self.putty_path.setText(profile.get('putty_path','')); self.transport.setCurrentIndex(0 if profile.get('serial_transport','native')=='proxy' else 1)
        # Replace the draft only; discard/reduce never deletes execution history.
        for row in self.board_rows: self.board_editor.removeTab(self.board_editor.indexOf(row['widget'])); row['widget'].deleteLater()
        self.board_rows=[]; self.board_drafts=[]
        for board in profile.get('boards',[]):
            self.board_drafts.append({'board':copy.deepcopy(board),'name':profile.get('board_names',{}).get(board['board_id'],board['board_id']),'baudrate':profile.get('serial_settings',{}).get(board['board_id'],{}).get('baudrate',115200),'observer':copy.deepcopy(profile.get('console_observers',{}).get(board['board_id'],{}))})
        count=max(1,len(self.board_drafts)); self.board_count.blockSignals(True); self.board_count.setValue(count); self.board_count.blockSignals(False); self.resize_boards(count); self.refresh_ports()

    def refresh_ports(self):
        def fill(ports):
            self.capture_board_drafts(); self.port_choices=ports; self.resize_boards(self.board_count.value())
        self.operation(self.adapter.ports, fill)

    def save_settings(self):
        self.capture_board_drafts(); count=self.board_count.value()
        boards=[copy.deepcopy(data['board']) for data in self.board_drafts[:count]]
        controls=[b['com'] for b in boards]; rx=[data['observer'].get('port') for data in self.board_drafts[:count] if data['observer'].get('port')]
        if not all(controls) or len(set(controls))!=len(controls) or (self.transport.currentData()=='native' and (len(set(rx))!=len(rx) or set(controls)&set(rx))):
            self.show_error('보드별 제어 COM을 선택하고 제어/RX 포트의 중복을 해소하세요.'); return
        observers={data['board']['board_id']:data['observer'] for data in self.board_drafts[:count] if data['observer'].get('port')}
        names={data['board']['board_id']:data['name'] for data in self.board_drafts[:count]}
        setup = dict(self.profile.get('_setup', {}), server=self.server.text().strip(), account=self.account.text().strip(), ssh_port=self.ssh_port.value(), remote_dashboard_port=self.dashboard_port.value(), ssh_key=self.ssh_key.text().strip())
        inactive=copy.deepcopy(self.profile.get('connector_inactive_boards',[]))+copy.deepcopy(self.board_drafts[count:])
        patch={'_setup':setup,'python':self.python_path.text().strip(),'boards':boards,'console_observers':observers,'board_names':names,'connector_inactive_boards':inactive,'serial_transport':self.transport.currentData(),'putty_path':self.putty_path.text().strip(), 'serial_settings':{d['board']['board_id']:dict(self.profile.get('serial_settings',{}).get(d['board']['board_id'],{}),baudrate=d.get('baudrate',115200)) for d in self.board_drafts[:count]}}
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
    def show_transport_fields(self):
        for row in getattr(self,'board_rows',[]): row['legacy'].setVisible(self.transport.currentData()=='native')
    def selected_board(self):
        item = self.board_list.currentItem()
        return item.data(Qt.UserRole) if item else None
    def select_board(self, *args):
        board = next((b for b in self.snapshot.get('boards',[]) if b['board_id']==self.selected_board()), {})
        proxy = board.get('serial_proxy',{})
        ready = self.snapshot.get('state')=='CONNECTED' and proxy.get('state')=='READY' and not board.get('stale')
        self.putty_button.setEnabled(ready and not proxy.get('putty_connected'))
        self.manual_button.setText('수동 제어 종료' if proxy.get('owner')=='manual' else '수동 제어')
        busy = any(b.get('state') in {'RUNNING','UNKNOWN','RESERVED'} and b.get('serial_proxy',{}).get('owner')!='manual' for b in self.snapshot.get('boards',[]))
        self.manual_button.setEnabled(ready and (proxy.get('owner')=='manual' or (not busy and proxy.get('owner') is None)))
        if hasattr(self,'log_text'): self.render_logs()
    def open_putty(self):
        board = self.selected_board()
        if board: self.operation(lambda:self.adapter.putty(board), lambda _:self.poll())
    def manual_control(self):
        identity = self.selected_board()
        board = next((b for b in self.snapshot.get('boards',[]) if b['board_id']==identity),{})
        enabled = board.get('serial_proxy',{}).get('owner')!='manual'
        if identity: self.operation(lambda:self.adapter.manual(identity,enabled), lambda _:self.poll())
    def open_dashboard(self):
        if self.adapter.preview: self.error.setText('미리보기: 실제 브라우저·서버를 열지 않습니다.'); return
        url=self.snapshot.get('dashboard_url','')
        if url.startswith('http://127.0.0.1:'): QDesktopServices.openUrl(QUrl(url))
    def open_log_folder(self):
        if self.adapter.preview: self.error.setText('미리보기 로그는 격리된 임시 프로파일에만 있습니다.'); return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.adapter.home/'logs')))
    def closeEvent(self,event): self.timer.stop(); event.accept()  # detach; never disconnect/kill
