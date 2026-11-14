"""Compact shared execution settings; server paths are browsed on Linux."""
import copy
from PySide6.QtWidgets import (QGroupBox, QFormLayout, QHBoxLayout, QWidget, QLineEdit,
    QSpinBox, QCheckBox, QPushButton, QLabel, QDialog, QVBoxLayout, QListWidget, QListWidgetItem)
from PySide6.QtCore import Qt


class SharedSettingsPanel(QGroupBox):
    def __init__(self, owner):
        super().__init__('공통 실행 설정'); self.owner = owner; self.value = None; self.dirty = False; self.edit_generation = 0
        form = QFormLayout(self)
        self.installer = QLineEdit(); self.source = QLineEdit(); self.patterns = QLineEdit(); self.profile = QLineEdit()
        self.installer.setPlaceholderText('/srv/images/build/install.bat')
        self.source.setPlaceholderText('/srv/tc'); self.patterns.setPlaceholderText('**/*.py')
        for label, field, kind in [('설치 BAT', self.installer, 'installer'), ('TC 폴더', self.source, 'source')]:
            row = QWidget(); box = QHBoxLayout(row); box.setContentsMargins(0,0,0,0); box.addWidget(field)
            button = QPushButton('서버에서 선택'); box.addWidget(button)
            button.clicked.connect(lambda checked=False, f=field, k=kind: self.browse(f, k)); form.addRow(label, row)
        form.addRow('TC 패턴 (쉼표 구분)', self.patterns); form.addRow('플래싱 프로파일', self.profile)
        self.use_default = QCheckBox('모든 TC에 공통값 적용')
        self.seconds = QSpinBox(); self.seconds.setRange(1,86400); self.seconds.setValue(600); self.seconds.setSuffix(' 초')
        timeout = QWidget(); row = QHBoxLayout(timeout); row.setContentsMargins(0,0,0,0); row.addWidget(self.use_default); row.addWidget(self.seconds)
        form.addRow('TC 제한시간', timeout)
        self.status = QLabel('서버 연결 후 불러옵니다. 기본 제한시간 600초'); self.status.setWordWrap(True); form.addRow(self.status)
        buttons = QWidget(); row = QHBoxLayout(buttons); row.setContentsMargins(0,0,0,0)
        load = QPushButton('다시 불러오기'); save = QPushButton('공통 설정 저장'); row.addWidget(load); row.addWidget(save); form.addRow(buttons)
        load.clicked.connect(self.reload); save.clicked.connect(self.save)
        for field in (self.installer,self.source,self.patterns,self.profile): field.textEdited.connect(self.mark_dirty)
        self.seconds.valueChanged.connect(self.mark_dirty); self.use_default.toggled.connect(self.mark_dirty)

    def mark_dirty(self, *args): self.dirty = True; self.edit_generation += 1

    def reload(self):
        if hasattr(self.owner.adapter, 'shared_settings'):
            generation = self.edit_generation
            self.owner.operation(self.owner.adapter.shared_settings, lambda v: self.received(v, generation))

    def received(self, value, generation):
        if generation != self.edit_generation:
            self.value = copy.deepcopy(value)
            self.status.setText('서버 반영됨 · 응답 대기 중 수정한 내용은 아직 저장하지 않았습니다.')
            return
        self.accept(value, force=True)

    def accept(self, value, force=False):
        if not value: return
        application = value.get('connector_application', {})
        self.status.setText(('미저장 변경 있음' if self.dirty and not force else '공통 설정 반영됨') + ' · 장비 설정 ' + {'APPLIED':'적용됨','PENDING':'적용 대기','BLOCKED':'연결 재시작 대기'}.get(application.get('state'), '변경 없음'))
        if self.value is not None:
            self.value['connector_application'] = copy.deepcopy(application)
        if self.dirty and not force: return
        if self.value and self.value.get('revision') == value.get('revision') and not force:
            return
        self.value = copy.deepcopy(value); cfg = value.get('integration', {})
        self.installer.setText(cfg.get('installer_path') or ''); self.source.setText(cfg.get('tc_root') or '')
        self.patterns.setText(', '.join(cfg.get('global_defaults', []))); self.profile.setText(cfg.get('flash_profile') or '')
        timeout = value.get('timeouts', {}).get('default_seconds')
        self.use_default.setChecked(timeout is not None); self.seconds.setValue(timeout or 600)
        application = value.get('connector_application', {})
        self.status.setText('공통 설정 반영됨 · 장비 설정 ' + {'APPLIED':'적용됨','PENDING':'적용 대기','BLOCKED':'연결 재시작 대기'}.get(application.get('state'), '변경 없음'))
        self.dirty = False

    def save(self):
        if self.value is None:
            self.owner.show_error('공통 설정을 먼저 불러오세요.'); return
        cfg = copy.deepcopy(self.value['integration']); cfg.update(
            installer_path=self.installer.text().strip(), tc_root=self.source.text().strip(),
            flash_profile=self.profile.text().strip(), global_defaults=[p.strip() for p in self.patterns.text().split(',') if p.strip()])
        limits = {k:v for k,v in self.value['timeouts'].items() if k in {'default_seconds','source_revision','overrides'}}
        limits['default_seconds'] = self.seconds.value() if self.use_default.isChecked() else None
        payload = {'expected_revision':self.value['revision'], 'integration':cfg, 'timeouts':limits}
        generation = self.edit_generation
        self.owner.operation(lambda: self.owner.adapter.save_shared_settings(payload), lambda v: self.received(v, generation))

    def browse(self, field, kind):
        dialog = QDialog(self); dialog.setWindowTitle('Linux 서버 ' + ('설치 BAT' if kind == 'installer' else 'TC 폴더')); dialog.resize(540,360)
        layout = QVBoxLayout(dialog); path = QLineEdit(); layout.addWidget(path); listing = QListWidget(); layout.addWidget(listing)
        row = QHBoxLayout(); back=QPushButton('허용 폴더'); choose=QPushButton('선택'); row.addWidget(back); row.addWidget(choose); layout.addLayout(row)
        current = {'path':'', 'directory':True}
        def render(value):
            listing.clear(); path.setText(value.get('path') or ''); current['path']=value.get('path') or ''
            rows = value.get('entries', [])
            if not current['path']:
                rows = [{'name':p,'path':p,'directory':True} for p in value.get('roots', [])]
            for entry in rows:
                item=QListWidgetItem(('▸ ' if entry.get('directory') else '')+entry['name']); item.setData(Qt.UserRole,entry); listing.addItem(item)
        def load(location):
            self.owner.operation(lambda:self.owner.adapter.server_paths(kind,location),render)
        def selected():
            item=listing.currentItem(); entry=item.data(Qt.UserRole) if item else current
            if kind=='installer' and entry.get('directory',True): return
            if kind=='source' and not entry.get('directory',True): return
            if entry.get('path'):
                field.setText(entry['path']); self.mark_dirty(); dialog.accept()
        def opened(item):
            entry=item.data(Qt.UserRole)
            if entry.get('directory'): load(entry['path'])
            else: selected()
        listing.itemDoubleClicked.connect(opened); choose.clicked.connect(selected); back.clicked.connect(lambda:load(''))
        path.returnPressed.connect(lambda:load(path.text().strip())); load(''); dialog.exec()


class StorageSettingsPanel(QGroupBox):
    """The connector edits the same central policy as the plugin and monitor."""
    def __init__(self, owner):
        super().__init__('스냅샷 저장 공간'); self.owner=owner; self.value=None; self.generation=0
        from PySide6.QtWidgets import QDoubleSpinBox
        layout=QVBoxLayout(self); row=QHBoxLayout(); layout.addLayout(row)
        self.enabled=QCheckBox('자동 정리'); self.enabled.setChecked(True)
        self.hours=QSpinBox(); self.hours.setRange(1,3650*24); self.hours.setValue(168); self.hours.setSuffix(' 시간')
        self.gib=QDoubleSpinBox(); self.gib.setRange(.001,1024*1024); self.gib.setDecimals(3); self.gib.setValue(20); self.gib.setSuffix(' GiB')
        for field in (self.enabled,self.hours,self.gib): row.addWidget(field)
        self.status=QLabel('서버 연결 후 정책을 불러오세요. 실행 중인 작업과 실패 근거는 보존합니다.');self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        for text, action in [('불러오기',self.reload),('저장',self.save),('정리 예상 보기',self.preview)]:
            button=QPushButton(text);button.clicked.connect(action);buttons.addWidget(button)
        self.enabled.toggled.connect(self.edited);self.hours.valueChanged.connect(self.edited);self.gib.valueChanged.connect(self.edited)
        self.displayed=None

    def edited(self,*args): self.generation+=1

    def reload(self):
        generation=self.generation
        self.owner.operation(self.owner.adapter.storage_policy,lambda value:self.accept(value,generation))

    def accept(self,value,generation):
        self.value=copy.deepcopy(value)
        if generation!=self.generation:
            self.status.setText('정책을 확인했습니다. 대기 중 수정한 값은 아직 저장하지 않았습니다.');return
        self.enabled.setChecked(value['enabled']);self.hours.setValue(max(1,round(value['max_age_seconds']/3600)));self.gib.setValue(value['max_bytes']/1024**3)
        self.displayed=(self.hours.value(),self.gib.value())
        state=value.get('connector_sync',{}).get('state')
        self.status.setText('정책 반영됨'+(' · 커넥터 적용 대기' if state=='SYNC_PENDING' else ' · 커넥터 적용됨' if state=='APPLIED' else ''))

    def save(self):
        if self.value is None:
            self.owner.show_error('저장 공간 정책을 먼저 불러오세요.');return
        payload={k:self.value[k] for k in ('enabled','max_age_seconds','max_bytes')}
        payload.update(enabled=self.enabled.isChecked(),expected_revision=self.value['revision'])
        if self.displayed is None or self.hours.value()!=self.displayed[0]: payload['max_age_seconds']=self.hours.value()*3600
        if self.displayed is None or self.gib.value()!=self.displayed[1]: payload['max_bytes']=int(self.gib.value()*1024**3)
        generation=self.generation
        self.owner.operation(lambda:self.owner.adapter.save_storage_policy(payload),lambda value:self.accept(value,generation))

    def preview(self):
        def render(value):
            def summary(report):
                if report.get('skipped_reason'): return '작업 중 · 정리 대기'
                text=f"예상 정리 {report.get('planned_bytes',0)/1024**2:.1f} MiB · 보호 {report.get('protected_bytes',0)/1024**2:.1f} MiB"
                if report.get('over_budget'): text+=' · 용량 목표 초과'
                if report.get('batch_limited'): text+=' · 다음 주기에 계속 정리'
                if report.get('measurement_complete') is False: text+=' · 일부 경로 제외'
                return text
            remote=value.get('connector_cleanup',{})
            self.status.setText('서버: '+summary(value)+'\n커넥터: '+(summary(remote['report']) if remote.get('state')=='CHECKED' else '연결 확인 필요'))
        self.owner.operation(lambda:self.owner.adapter.cleanup_snapshots(dry_run=True),render)
