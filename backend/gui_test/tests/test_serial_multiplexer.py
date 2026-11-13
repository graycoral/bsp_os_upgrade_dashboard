import json
import queue
import socket
import threading
import time

import pytest

from backend.gui_test.connector.multiplexer import PortMultiplexer, Subscription
from backend.gui_test.connector.serial_proxy import Serial, SerialException
from backend.gui_test.core.models import TestError

BOARD = {'board_id':'board-a', 'host':'TEST-PC', 'com':'COM7'}


class FakePort:
    def __init__(self):
        self.input = queue.Queue(); self.written = []; self.opened = True
        self.cts = self.dsr = True; self.cd = self.ri = False; self.out_waiting = 0
        self.dtr = self.rts = False
    def read(self, size):
        if not self.opened: raise OSError('unplugged')
        try: return self.input.get(timeout=.01)
        except queue.Empty: return b''
    @property
    def in_waiting(self):
        with self.input.mutex: return sum(len(data) for data in self.input.queue)
    def write(self, data):
        self.written.append(data)
        if getattr(self,'echo',False): self.input.put(data)
        return len(data)
    def flush(self): pass
    def reset_output_buffer(self): pass
    def close(self): self.opened = False


@pytest.fixture
def mux(monkeypatch):
    port = FakePort(); calls=[]
    def factory(*args): calls.append(args); return port
    value = PortMultiplexer(BOARD, factory=factory); value.start()
    yield value, port, calls
    value.close()


def wait_for(fn):
    end=time.monotonic()+3
    while time.monotonic()<end:
        if fn(): return
        time.sleep(.01)
    assert fn()


def test_one_physical_open_fanout_and_independent_reset(mux,monkeypatch):
    m,p,calls=mux; observer=m.subscribe()
    target=m.acquire('tc-1'); monkeypatch.setenv('BOARD_CONNECTOR_SERIAL_MAP',json.dumps({'COM7':target}))
    with Serial('COM7',115200,timeout=.3) as serial, socket.create_connection(('127.0.0.1',m.raw_port)) as putty:
        putty.settimeout(2); wait_for(lambda:m.raw_client is not None)
        p.input.put(b'boot login :\n'); assert serial.readline()==b'boot login :\n'
        assert observer.read()==b'boot login :\n'; assert putty.recv(99)==b'boot login :\n'
        p.input.put(b'next\n'); wait_for(lambda:observer.pending_bytes()>0)
        serial.reset_input_buffer(); assert observer.read()==b'next\n'
        serial.write(b'root\r'); assert p.written==[b'root\r']
        putty.sendall(b'blocked\r'); time.sleep(.1); assert p.written==[b'root\r']
        assert not p.dtr and not p.rts  # opening a viewer/TC does not pulse control lines
        serial.dtr=True; assert p.dtr
    m.release('tc-1'); observer.close(); assert len(calls)==1


def test_lease_rejects_second_writer_and_stale_endpoint(mux,monkeypatch):
    m,p,_=mux; old=m.acquire('first')
    with pytest.raises(TestError):m.acquire('manual')
    monkeypatch.setenv('BOARD_CONNECTOR_SERIAL_MAP',json.dumps({'COM7':old}))
    with Serial('COM7',timeout=.1):
        with pytest.raises(SerialException):Serial('COM7',timeout=.1)
    m.release('first'); new=m.acquire('second')
    assert new['lease']!=old['lease']
    with pytest.raises(SerialException):Serial('COM7',timeout=.1)
    assert not p.written


def test_manual_only_owner_disconnect_releases_without_replaying(mux):
    m,p,_=mux
    with socket.create_connection(('127.0.0.1',m.raw_port)) as putty:
        wait_for(lambda:m.raw_client is not None)
        putty.sendall(b'ignored'); time.sleep(.1)
        m.acquire('manual')
        assert putty.recv(1)==b''  # read-only session is not silently promoted
        with socket.create_connection(('127.0.0.1',m.raw_port)) as manual:
            wait_for(lambda:m.manual_client is not None)
            manual.sendall(b'help\r'); wait_for(lambda:p.written)
            assert p.written==[b'help\r']
    wait_for(lambda:m.owner is None)


def test_slow_reader_isolated_and_unplug_reported(mux):
    m,p,_=mux; slow=Subscription(m,limit=4); m.readers.add(slow); normal=m.subscribe()
    p.input.put(b'12345');wait_for(lambda:normal.pending_bytes()==5)
    with pytest.raises(OSError,match='OVERFLOW'):slow.read()
    assert normal.read()==b'12345'
    p.opened=False;wait_for(lambda:bool(m.error))
    with pytest.raises(OSError,match='DISCONNECTED'):normal.read()
    assert m.snapshot()['state']=='ERROR'


def test_read_ahead_readline_timeout_and_close_reopen(mux,monkeypatch):
    m,p,_=mux;target=m.acquire('tc');monkeypatch.setenv('BOARD_CONNECTOR_SERIAL_MAP',json.dumps({'COM7':target}))
    serial=Serial('COM7',timeout=.1)
    p.input.put(b'one\ntwo\n');assert serial.readline()==b'one\n';assert serial.readline()==b'two\n'
    assert serial.read(2)==b''
    serial.close();wait_for(lambda:m.control is None)
    serial.open();serial.write(b'reopened');serial.close();assert p.written==[b'reopened']


def test_no_mapping_never_opens_physical_port(monkeypatch):
    monkeypatch.delenv('BOARD_CONNECTOR_SERIAL_MAP',raising=False)
    with pytest.raises(SerialException,match='매핑'):Serial('COM7')


def test_host_tc_common_module_and_manual_gate(tmp_path):
    import sys
    from fastapi.testclient import TestClient
    from backend.gui_test.execution.host import Host, create_app
    source=tmp_path/'source';source.mkdir()
    (source/'common.py').write_text('from serial_proxy import Serial\n')
    (source/'single.py').write_text("import sys\nfrom common import Serial\nwith Serial(sys.argv[2],115200,timeout=2) as port:\n port.write(b'proxy response\\n')\n assert port.readline()==b'proxy response\\n'\nprint('Test Result: PASS')\n")
    host=Host({'source_root':str(source),'python':sys.executable,'boards':[BOARD],'serial_transport':'proxy'},tmp_path/'runtime',ports=lambda:{'COM7'})
    port=FakePort();port.echo=True
    host.multiplexers.ports['board-a'].factory=lambda *_:port
    host.recover()
    client=TestClient(create_app(host),client=('127.0.0.1',123))
    try:
        catalog=host.catalog()
        payload={'id':'a'*32,'source_revision':catalog['revision'],'tc_id':'single.py','connection':{'a':BOARD},
                 'template':{'single':['python','{tc_path}','-p','{com_a}'],'dual':['python','{tc_path}','-p','{com_a}','-p2','{com_b}']}}
        assert client.post('/v1/serial-control',json={'board_id':'board-a','manual':True}).status_code==200
        with pytest.raises(TestError,match='수동'):host.start(payload)
        assert client.post('/v1/serial-control',json={'board_id':'board-a','manual':False}).status_code==200
        host.start(payload)
        assert client.post('/v1/serial-control',json={'board_id':'board-a','manual':True}).status_code==409
        end=time.monotonic()+8
        while time.monotonic()<end:
            result=host.poll(payload['id'])
            if result['state']!='RUNNING':break
            time.sleep(.02)
        assert result['state']=='DONE' and result['exit_code']==0, result
        assert 'Test Result: PASS' in result['stdout']
        assert port.written==[b'proxy response\n']
        host.console.refresh();projection=host.console.projection()
        assert 'proxy response' in projection['boards'][0]['text']
        assert host.multiplexers.ports['board-a'].owner is None
        assert host.catalog()['revision']==catalog['revision']
        assert client.get('/v1/recent-executions').json()['executions'][0]['board_ids']==['board-a']
        assert client.post('/v1/serial-control',json={'board_id':'board-a','manual':True},headers={'Origin':'http://localhost'}).status_code==403
    finally:host.close()


def test_flash_console_uses_same_physical_port_and_reader_fence(mux):
    from backend.gui_test.connector.multiplexer import ControlPort
    from backend.gui_test.execution.flashing import SerialConsole
    m,p,calls=mux;observer=m.subscribe()
    p.input.put(b'old boot marker\n')
    console=SerialConsole({'baudrate':115200,'line_ending':'cr'},ControlPort(m,'flash:1',115200))
    try:
        console.command('reboot lkshell')
        assert b'old boot marker' in observer.read()
        assert b'old boot marker' not in console.buffer
        p.input.put(b'lkshell>');console.wait('lkshell>',1)
    finally:console.close();observer.close()
    assert len(calls)==1 and m.owner is None and p.opened


def test_gui_updates_existing_rows_filters_board_and_preserves_selection(tmp_path):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QThreadPool
    from backend.gui_test.connector.gui import ConnectorWindow
    from backend.gui_test.connector.preview import MockConnector
    app=QApplication.instance() or QApplication([])
    adapter=MockConnector(tmp_path);adapter.connect();window=ConnectorWindow(adapter);window.timer.stop()
    QThreadPool.globalInstance().waitForDone(5000);app.processEvents()
    try:
        window.render(adapter.status());first=window.board_list.item(0)
        for _ in range(100):window.render(adapter.status())
        assert window.board_list.item(0) is first
        window.log_toggle.setChecked(True);assert 'Starting kernel' in window.log_text.toPlainText()
        window.board_list.setCurrentRow(1);assert window.log_text.toPlainText()==''
        window.board_list.setCurrentRow(0)
        cursor=window.log_text.textCursor();cursor.setPosition(5);window.log_text.setTextCursor(cursor)
        window.render(adapter.status());assert window.log_text.textCursor().position()==5
        assert window.transport.currentData()=='proxy' and window.board_rows[0]['legacy'].isHidden()
        window.show();app.processEvents()
        assert window.width()==760 and window.height()==520
        assert window.log_text.height()>=80
    finally:window.close();QThreadPool.globalInstance().waitForDone(5000);app.processEvents()


def test_control_overflow_blocks_success_without_waiting_for_tc_read(mux,monkeypatch):
    m,p,_=mux;mapping=m.acquire('tc');monkeypatch.setenv('BOARD_CONNECTOR_SERIAL_MAP',json.dumps({'COM7':mapping}))
    observer=m.subscribe()
    with Serial('COM7',timeout=.1):
        m.control_reader.limit=4;p.input.put(b'overflow\n')
        wait_for(lambda:bool(m.failure()))
        assert m.snapshot()['code']=='SERIAL_READER_OVERFLOW'
        assert observer.read()==b'overflow\n'
    assert m.failure()
    observer.close()


def test_proxy_settings_preserve_legacy_and_validate_before_write(tmp_path):
    from backend.gui_test.connector.settings import Settings
    settings=Settings(tmp_path)
    assert settings.read()['serial_transport']=='proxy'
    settings.path.write_text(json.dumps({'boards':[BOARD],'_setup':{'server':'linux','account':'tester'},'console_observers':{'board-a':{'port':'COM17'}}}))
    assert settings.read().get('serial_transport','native')=='native'
    saved=settings.save({'serial_transport':'proxy','serial_settings':{'board-a':{'baudrate':115200}}})
    assert saved['console_observers']['board-a']['port']=='COM17'
    original=settings.path.read_bytes()
    with pytest.raises(TestError):settings.save({'serial_settings':{'board-a':{'baudrate':0}}})
    assert settings.path.read_bytes()==original
