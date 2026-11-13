"""Host automatically provides this helper to the company's TC process.

Replace `from serial import Serial` with `from serial_proxy import Serial` there.
COM arguments are unchanged. Host supplies BOARD_CONNECTOR_SERIAL_MAP to the TC.
Outside a managed run, opening fails explicitly; physical COM is never a fallback.
Requires the TC's existing pySerial installation, not Qt or the Dashboard package.
"""
import base64
import json
import os
import socket
import threading
import time

from serial import SerialBase, SerialException, PortNotOpenError


class Serial(SerialBase):
    def __init__(self, *args, **kwargs):
        self._socket = None; self._stream = None
        self._rpc_lock = threading.RLock(); self._buffer = bytearray()
        super().__init__(*args, **kwargs)

    def _request(self, op, **payload):
        if self._socket is None: raise PortNotOpenError()
        with self._rpc_lock:
            try:
                self._socket.sendall(json.dumps(dict(op=op, **payload)).encode() + b'\n')
                line = self._stream.readline(100001)
                if not line or len(line) > 100000: raise OSError('Invalid serial proxy response')
                response = json.loads(line)
                if 'error' in response: raise SerialException(response['error'])
                return response['value']
            except (OSError, ValueError, KeyError) as exc:
                self.close()
                raise SerialException('Serial proxy connection lost: ' + str(exc)) from exc

    def open(self):
        if self.is_open: raise SerialException('Port is already open')
        try:
            mapping = json.loads(os.environ.get('BOARD_CONNECTOR_SERIAL_MAP', '{}'))
            target = mapping[self.port.upper()]
            port = target['port']
            if type(port) is not int or not 1 <= port <= 65535: raise ValueError('Invalid endpoint')
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise SerialException('보드 커넥터에서 TC를 시작하세요. 프록시 COM 매핑이 없습니다.') from exc
        try:
            self._socket = socket.create_connection(('127.0.0.1', port), timeout=5)
            self._stream = self._socket.makefile('rb')
            self._request('open', lease=target['lease'])
            self.is_open = True
            self._reconfigure_port()
        except Exception:
            self.close(); raise

    def close(self):
        self.is_open = False
        if self._socket:
            try: self._socket.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        if self._stream: self._stream.close()
        if self._socket: self._socket.close()
        self._socket = self._stream = None; self._buffer.clear()

    def _reconfigure_port(self):
        if not self.is_open: return
        self._request('configure', settings={name: getattr(self, name) for name in (
            'baudrate', 'bytesize', 'parity', 'stopbits', 'xonxoff', 'rtscts', 'dsrdtr', 'write_timeout')})

    def read(self, size=1):
        if not self.is_open: raise PortNotOpenError()
        if size < 0: raise ValueError('Invalid read size')
        end = None if self.timeout is None else time.monotonic() + self.timeout
        result = bytearray()
        while len(result) < size:
            with self._rpc_lock:
                if self._buffer:
                    take = min(size - len(result), len(self._buffer))
                    result.extend(self._buffer[:take]); del self._buffer[:take]
                else:
                    remaining = .2 if end is None else max(0, min(.2, end - time.monotonic()))
                    data = self._request('read', size=min(65536, max(4096, size - len(result))), timeout=remaining)
                    self._buffer.extend(base64.b64decode(data, validate=True))
                    if self._buffer: continue
            if end is not None and time.monotonic() >= end: break
        return bytes(result)

    def write(self, data):
        if not self.is_open: raise PortNotOpenError()
        data = bytes(data); count = 0
        for start in range(0, len(data), 65536):
            count += self._request('write', data=base64.b64encode(data[start:start+65536]).decode())
        return count

    @property
    def in_waiting(self): return len(self._buffer) + self._request('pending')
    @property
    def out_waiting(self): return self._request('status', name='out_waiting')
    def flush(self): self._request('flush')
    def reset_input_buffer(self):
        with self._rpc_lock: self._buffer.clear(); self._request('reset_input')
    def reset_output_buffer(self): self._request('reset_output')
    def _update_dtr_state(self): self._request('line', name='dtr', value=self._dtr_state)
    def _update_rts_state(self): self._request('line', name='rts', value=self._rts_state)
    def _update_break_state(self): self._request('line', name='break_condition', value=self._break_state)
    @property
    def cts(self): return self._request('status', name='cts')
    @property
    def dsr(self): return self._request('status', name='dsr')
    @property
    def ri(self): return self._request('status', name='ri')
    @property
    def cd(self): return self._request('status', name='cd')
