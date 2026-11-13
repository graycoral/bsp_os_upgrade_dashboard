"""One physical UART owner, bounded independent readers and one writer lease.

Listeners bind loopback only. TC leases are issued by Host, never user configuration.
A failed port is not reopened or commands replayed while a job may still own it.
"""
import base64
import hmac
import json
import secrets
import socket
import threading
import time

from ..core.models import TestError

MAX_FRAME = 100_000


class Subscription:
    def __init__(self, mux, limit=262144):
        self.mux = mux
        self.limit = limit
        self.buffer = bytearray()
        self.condition = threading.Condition()
        self.closed = False
        self.error = ''

    def feed(self, data):
        with self.condition:
            if self.closed or self.error: return
            if len(self.buffer) + len(data) > self.limit:
                self.error = 'SERIAL_READER_OVERFLOW'
                self.buffer.clear()
            else: self.buffer.extend(data)
            self.condition.notify_all()

    def fail(self, reason):
        with self.condition:
            self.error = reason
            self.condition.notify_all()

    def read(self, size=4096, timeout=.1):
        with self.condition:
            if not self.buffer and not self.error and not self.closed:
                self.condition.wait(timeout)
            if self.error: raise OSError(self.error)
            if self.closed: raise OSError('Serial subscription closed')
            data = bytes(self.buffer[:size]); del self.buffer[:size]
            return data

    def pending_bytes(self):
        self.mux.fence_ingress()
        with self.condition:
            if self.error: raise OSError(self.error)
            return len(self.buffer)

    def reset_input_buffer(self):
        self.mux.fence_ingress()
        with self.condition: self.buffer.clear()

    def close(self):
        with self.condition:
            self.closed = True; self.condition.notify_all()
        with self.mux.lock: self.mux.readers.discard(self)


class PortMultiplexer:
    def __init__(self, board, config=None, factory=None):
        self.board = board
        self.config = config or {}
        self.factory = factory
        self.lock = threading.RLock()
        self.ingress_lock = threading.Lock()
        self.readers = set()
        self.port = None
        self.error = ''
        self.owner_error = ''
        self.owner = None
        self.key = ''
        self.control = None
        self.control_reader = None
        self.raw_client = None
        self.manual_client = None
        self.listeners = []
        self.sockets = set()
        self.threads = set()
        self.stop = threading.Event()
        self.epoch = secrets.token_hex(16)
        self.received = 0
        self.rpc_port = self.raw_port = None
        self.started = False

    def start(self):
        with self.lock:
            if self.started: return
            self.started = True
            try:
                if self.factory:
                    self.port = self.factory(self.board, self.config)
                else:
                    import serial
                    port = serial.Serial(port=None, baudrate=self.config.get('baudrate', 115200),
                                         timeout=.05, write_timeout=2)
                    # Do not pulse reset/control lines when a viewer connects.
                    port.dtr = self.config.get('dtr', False)
                    port.rts = self.config.get('rts', False)
                    port.port = self.board['com']; self.port = port; port.open()
                for kind in ('rpc', 'raw'):
                    listener = socket.socket()
                    listener.bind(('127.0.0.1', 0)); listener.listen(4); listener.settimeout(.2)
                    self.listeners.append(listener)
                    setattr(self, kind + '_port', listener.getsockname()[1])
                    self._thread(self._accept, listener, kind)
                self._thread(self._read)
            except Exception:
                self.error = 'SERIAL_OPEN_FAILED'
                if self.port: self.port.close(); self.port = None
                for listener in self.listeners: listener.close()
                self.listeners.clear()

    def _thread(self, fn, *args):
        def run():
            try: fn(*args)
            finally:
                with self.lock: self.threads.discard(thread)
        thread = threading.Thread(target=run, daemon=True, name='serial-multiplexer')
        self.threads.add(thread); thread.start()

    def subscribe(self):
        with self.lock:
            if self.error or not self.port or self.stop.is_set(): raise OSError(self.error or 'SERIAL_NOT_READY')
            if len(self.readers) >= 16: raise OSError('SERIAL_READER_LIMIT')
            reader = Subscription(self); self.readers.add(reader); return reader

    def _read(self):
        try:
            while not self.stop.is_set():
                with self.ingress_lock:
                    data = self.port.read(4096)
                    if data: self._publish(data)
                self.stop.wait(.002)
        except Exception:
            with self.lock:
                self.error = 'SERIAL_DISCONNECTED'
                readers = tuple(self.readers)
            for reader in readers: reader.fail(self.error)

    def _publish(self, data):
        with self.lock:
            self.received += len(data); readers = tuple(self.readers)
        for reader in readers: reader.feed(data)

    def fence_ingress(self):
        if not self.ingress_lock.acquire(timeout=1): raise OSError('SERIAL_FENCE_TIMEOUT')
        try:
            if self.error or not self.port: raise OSError(self.error or 'SERIAL_NOT_READY')
            remaining = self.port.in_waiting
            deadline = time.monotonic()+1
            while remaining:
                if time.monotonic() >= deadline: raise OSError('SERIAL_FENCE_TIMEOUT')
                data = self.port.read(min(4096,remaining))
                if not data: raise OSError('SERIAL_FENCE_INCOMPLETE')
                self._publish(data); remaining -= len(data)
        finally: self.ingress_lock.release()

    def acquire(self, owner):
        with self.lock:
            if self.error or not self.port: raise TestError('보드 COM을 열 수 없습니다.', 'SERIAL_UNAVAILABLE', 409)
            if self.owner is not None: raise TestError('보드 제어권이 사용 중입니다.', 'SERIAL_BUSY', 409)
            if owner == 'manual' and self.raw_client:
                # A fresh connection prevents bytes typed while read-only becoming commands.
                try: self.raw_client.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                self.raw_client.close(); self.raw_client = None
            self.owner = owner; self.owner_error = ''; self.key = secrets.token_urlsafe(32)
            return {'port': self.rpc_port, 'lease': self.key}

    def release(self, owner):
        with self.lock:
            if self.owner != owner: return
            self.owner = None; self.key = ''; self.manual_client = None
            if self.control:
                try: self.control.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                self.control.close(); self.control = None; self.control_reader = None

    def write(self, owner, data):
        with self.lock:
            if self.owner != owner or self.error: raise OSError('SERIAL_LEASE_LOST')
            count = self.port.write(data)
            if count != len(data): raise OSError('SERIAL_PARTIAL_WRITE')
            return count

    def failure(self):
        with self.lock:
            return self.error or self.owner_error or (self.control_reader.error if self.control_reader else '')

    def snapshot(self):
        with self.lock:
            return {'state': 'ERROR' if self.failure() else 'READY' if self.port else 'WAITING',
                    'code': self.failure(), 'owner': 'manual' if self.owner == 'manual' else 'execution' if self.owner else None,
                    'putty_connected': self.raw_client is not None, 'putty_port': self.raw_port,
                    'epoch': self.epoch, 'received_bytes': self.received, 'subscribers': len(self.readers)}

    def _accept(self, listener, kind):
        while not self.stop.is_set():
            try: conn, _ = listener.accept()
            except socket.timeout: continue
            except OSError: break
            conn.settimeout(5)
            with self.lock:
                # Bound even unauthenticated/idle clients and thread creation.
                if len(self.sockets) >= 8:
                    conn.close(); continue
                self.sockets.add(conn)
            self._thread(self._client, conn, kind)

    def _client(self, conn, kind):
        try:
            if kind == 'raw': self._raw(conn)
            else: self._rpc(conn)
        except (OSError, ValueError, KeyError, TypeError, TestError): pass
        finally:
            with self.lock: self.sockets.discard(conn)
            conn.close()

    def _raw(self, conn):
        with self.lock:
            if self.raw_client is not None: return
            self.raw_client = conn
            if self.owner == 'manual': self.manual_client = conn
        reader = None
        try:
            reader = self.subscribe(); conn.settimeout(.05)
            while not self.stop.is_set():
                data = reader.read(4096, .02)
                if data: conn.sendall(data)
                try: incoming = conn.recv(4096)
                except socket.timeout: continue
                if not incoming: break
                # Bytes typed while read-only are discarded, never queued for later replay.
                with self.lock:
                    if self.owner == 'manual' and self.manual_client is conn: self.write('manual', incoming)
        finally:
            if reader: reader.close()
            with self.lock:
                if self.raw_client is conn: self.raw_client = None
                if self.manual_client is conn: self.release('manual')

    def _rpc(self, conn):
        stream = conn.makefile('rb'); reader = None; owner = None
        try:
            line = stream.readline(MAX_FRAME + 1)
            if len(line) > MAX_FRAME: return
            request = json.loads(line)
            if not isinstance(request, dict): return
            with self.lock:
                if (request.get('op') != 'open' or self.owner in (None, 'manual') or self.control is not None or
                        not isinstance(request.get('lease'), str) or not hmac.compare_digest(request['lease'], self.key)):
                    self._reply(conn, error='SERIAL_LEASE_REQUIRED'); return
                owner = self.owner; self.control = conn; reader = self.subscribe(); self.control_reader = reader
            self._reply(conn, value=True)
            conn.settimeout(None)  # release()/close() wakes idle clients without revoking the Host lease.
            while not self.stop.is_set():
                line = stream.readline(MAX_FRAME + 1)
                if not line or len(line) > MAX_FRAME: break
                request = json.loads(line)
                if not isinstance(request, dict): break
                try:
                    with self.lock:
                        if self.owner != owner or self.control is not conn: raise OSError('SERIAL_LEASE_LOST')
                    value = self._request(owner, reader, request)
                    self._reply(conn, value=value)
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    with self.lock:
                        if self.owner == owner and self.control is conn: self.owner_error = 'SERIAL_CONTROL_FAILED'
                    self._reply(conn, error=str(exc)[:160]); break
        finally:
            if reader: reader.close()
            stream.close()
            with self.lock:
                if self.control is conn:
                    if reader and reader.error: self.owner_error = reader.error
                    self.control = None; self.control_reader = None
            # TC can close/reopen its serial object; only Host releases the writer lease.

    @staticmethod
    def _reply(conn, **value): conn.sendall(json.dumps(value).encode() + b'\n')

    def _request(self, owner, reader, request):
        op = request.get('op')
        if op == 'read':
            size = request['size']; timeout = request.get('timeout', .1)
            if type(size) is not int or not 0 <= size <= 65536 or type(timeout) not in (int, float) or not 0 <= timeout <= .2:
                raise ValueError('Invalid serial read')
            return base64.b64encode(reader.read(size, timeout)).decode()
        if op == 'pending': return reader.pending_bytes()
        if op == 'reset_input': reader.reset_input_buffer(); return True
        if op == 'write':
            data = base64.b64decode(request['data'], validate=True)
            if len(data) > 65536: raise ValueError('Serial write too large')
            return self.write(owner, data)
        with self.lock:
            if self.owner != owner or self.error: raise OSError('SERIAL_LEASE_LOST')
            if op == 'configure':
                values = request['settings']
                allowed = {'baudrate', 'bytesize', 'parity', 'stopbits', 'xonxoff', 'rtscts', 'dsrdtr', 'write_timeout'}
                if not isinstance(values, dict) or set(values) - allowed: raise ValueError('Invalid serial settings')
                if not 1 <= values.get('baudrate', 115200) <= 12_000_000: raise ValueError('Invalid baudrate')
                for name, value in values.items():
                    if name == 'write_timeout': value = 2 if value is None else min(2, max(0, value))
                    setattr(self.port, name, value)
                return True
            if op == 'line':
                if request['name'] not in {'dtr', 'rts', 'break_condition'} or type(request['value']) is not bool:
                    raise ValueError('Invalid modem line')
                setattr(self.port, request['name'], request['value']); return True
            if op == 'status':
                if request['name'] not in {'cts', 'dsr', 'ri', 'cd', 'out_waiting'}: raise ValueError('Invalid modem status')
                return getattr(self.port, request['name'])
            if op == 'flush':
                deadline = time.monotonic()+2
                while self.port.out_waiting:
                    if time.monotonic() >= deadline: raise OSError('SERIAL_FLUSH_TIMEOUT')
                    time.sleep(.005)
                return True
            if op == 'reset_output': self.port.reset_output_buffer(); return True
        raise ValueError('Unknown serial operation')

    def close(self):
        self.stop.set()
        with self.lock:
            self.release(self.owner)
            sockets = tuple(self.sockets)
            for reader in tuple(self.readers): reader.fail('SERIAL_CLOSED')
        for conn in sockets:
            try: conn.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            conn.close()
        for listener in self.listeners: listener.close()
        if self.port: self.port.close()
        for thread in tuple(self.threads):
            if thread is not threading.current_thread(): thread.join(timeout=1)


class Multiplexers:
    def __init__(self, boards, settings=None, factory=None):
        self.ports = {b['board_id']: PortMultiplexer(b, (settings or {}).get(b['board_id']), factory) for b in boards}

    def start(self):
        for mux in self.ports.values(): mux.start()

    def close(self):
        for mux in self.ports.values(): mux.close()

    def acquire(self, connection, owner):
        selected = [b for b in connection.values() if b]
        mapping = {}
        try:
            for board in selected: mapping[board['com']] = self.ports[board['board_id']].acquire(owner)
            return mapping
        except Exception:
            self.release(owner); raise

    def failure(self, connection):
        return any(self.ports[b['board_id']].failure() for b in connection.values() if b)

    def release(self, owner):
        for mux in self.ports.values(): mux.release(owner)

    @staticmethod
    def environment(mapping, runtime):
        # Trusted helper is separate from the immutable TC snapshot. Hash-named paths
        # keep an already running TC pinned when connector source is updated.
        import hashlib
        import os
        from pathlib import Path
        source = Path(__file__).with_name('serial_proxy.py').read_bytes()
        folder = Path(runtime) / 'serial-support' / hashlib.sha256(source).hexdigest()
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / 'serial_proxy.py'
        if not target.exists() or target.read_bytes() != source:
            temporary = target.with_suffix('.tmp'); temporary.write_bytes(source); os.replace(temporary, target)
        existing = os.environ.get('PYTHONPATH')
        return {'BOARD_CONNECTOR_SERIAL_MAP':json.dumps(mapping), 'PYTHONPATH':str(folder)+(os.pathsep+existing if existing else '')}

    def observer(self, directory, board_id, config):
        from ..execution.console_observer import ConsoleObserver
        return ConsoleObserver(directory, config, source=self.ports[board_id].subscribe())


class ControlPort:
    """In-process flash client. Closing releases only its view and writer lease."""
    def __init__(self, mux, owner, baudrate):
        self.mux, self.owner = mux, owner
        mux.acquire(owner)
        try:
            with mux.lock: mux.port.baudrate = baudrate
            self.reader = mux.subscribe()
        except Exception:
            mux.release(owner); raise
    def read(self, size): return self.reader.read(size, .05)
    def write(self, data): return self.mux.write(self.owner, data)
    def reset_input_buffer(self): self.reader.reset_input_buffer()
    def flush(self):
        with self.mux.lock:
            if self.mux.owner != self.owner: raise OSError('SERIAL_LEASE_LOST')
            deadline = time.monotonic()+2
            while self.mux.port.out_waiting:
                if time.monotonic() >= deadline: raise OSError('SERIAL_FLUSH_TIMEOUT')
                time.sleep(.005)
    def close(self): self.reader.close(); self.mux.release(self.owner)
