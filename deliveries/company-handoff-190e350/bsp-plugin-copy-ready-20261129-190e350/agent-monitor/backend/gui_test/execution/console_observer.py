"""Independent RX-only console evidence; disk backpressure never blocks the writer COM."""
import codecs
import json
import os
from pathlib import Path
import queue
import re
import threading
import time

from ..core.models import TestError, now


class WindowsReadOnlyPort:
    """Open the splitter RX endpoint with GENERIC_READ; never issue modem-control calls."""
    def __init__(self, name):
        if os.name != 'nt': raise TestError('RX console requires Windows', 'WINDOWS_REQUIRED')
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.kernel.CreateFileW.restype = wintypes.HANDLE
        self.kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.SetCommTimeouts.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        self.kernel.ClearCommError.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        self.handle = self.kernel.CreateFileW('\\\\.\\' + name, 0x80000000, 0, None, 3, 0, None)
        if self.handle == wintypes.HANDLE(-1).value:
            raise TestError('Cannot open isolated RX observer', 'OBSERVER_UNAVAILABLE')
        class Timeouts(ctypes.Structure):
            _fields_ = [(key, wintypes.DWORD) for key in ('interval', 'read_multiplier', 'read_constant', 'write_multiplier', 'write_constant')]
        if not self.kernel.SetCommTimeouts(self.handle, ctypes.byref(Timeouts(0xFFFFFFFF, 0, 100, 0, 0))):
            self.close(); raise TestError('Cannot configure RX observation timeout', 'OBSERVER_UNAVAILABLE')

    def read(self, size=4096):
        buffer = self.ctypes.create_string_buffer(size); count = self.wintypes.DWORD()
        if not self.kernel.ReadFile(self.handle, buffer, size, self.ctypes.byref(count), None):
            raise OSError('RX observer disconnected')
        return buffer.raw[:count.value]

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle); self.handle = None

    def pending_bytes(self):
        class ComStat(self.ctypes.Structure):
            _fields_ = [('flags', self.wintypes.DWORD), ('incoming', self.wintypes.DWORD), ('outgoing', self.wintypes.DWORD)]
        errors = self.wintypes.DWORD(); status = ComStat()
        if not self.kernel.ClearCommError(self.handle, self.ctypes.byref(errors), self.ctypes.byref(status)) or errors.value:
            raise OSError('RX queue state is not established')
        return status.incoming


class ConsoleObserver:
    def __init__(self, directory, config, source=None):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)
        self.config = config
        self.tail_limit = config.get('tail_bytes', 65536)
        self.rotate_bytes = config.get('rotate_bytes', 8 * 1024**2)
        self.rotate_count = config.get('rotate_count', 8)
        self.queue_bytes = config.get('queue_bytes', 1024**2)
        for value in (self.tail_limit, self.rotate_bytes, self.rotate_count, self.queue_bytes):
            if type(value) is not int or value < 1: raise TestError('Invalid console log limits', 'OBSERVER_CONFIG')
        self.markers = {key: config.get(key, []) for key in ('panic_signatures', 'boot_signatures', 'login_markers')}
        for key, values in self.markers.items():
            if not isinstance(values, list) or any(not isinstance(v, str) or not 1 <= len(v.encode('utf-8')) <= 1024 for v in values):
                raise TestError('Invalid console signatures', 'OBSERVER_CONFIG')
        self.lock = threading.RLock(); self.stopping = threading.Event(); self.read_stopping = threading.Event()
        self.ingress_lock = threading.Lock()
        self.queue = queue.Queue(maxsize=max(1, self.queue_bytes // 4096))
        self.decoder = codecs.getincrementaldecoder('utf-8')('strict')
        self.partial = ''; self.tail = ''; self.offset = 0; self.phase_epoch = 0; self.boot_epoch = 0
        self.stage_offset = 0; self.expected_boot = False; self.phase = 'INIT'
        self.events = []; self.gaps = []; self.rotations = 0; self.retained_from = 0
        self.evidence_overflow = False; self.log_pending = ''; self.omitting_line = False
        self.source = source; self.reader = None; self.writer_error = False
        self.writer = threading.Thread(target=self._write, name='console-log-writer', daemon=True); self.writer.start()

    def start(self):
        if self.reader: return
        if self.source is None:
            if self.config.get('rx_only_confirmed') is not True or self.config.get('control_lines_isolated') is not True:
                raise TestError('Validated RX-only splitter/control-line isolation required', 'OBSERVER_CONFIG')
            name = self.config.get('port', '')
            if not isinstance(name, str) or not name.upper().startswith('COM'):
                raise TestError('Configure an RX virtual COM', 'OBSERVER_CONFIG')
            self.source = WindowsReadOnlyPort(name)
        self.reader = threading.Thread(target=self._read, name='console-rx', daemon=True); self.reader.start()

    def _read(self):
        try:
            while not self.read_stopping.is_set():
                with self.ingress_lock:
                    data = self.source.read(4096)
                    if data: self.feed(data)
                if not data: time.sleep(.005)
        except Exception:
            self.gap('DISCONNECTED', self.offset, self.offset + 1)

    def gap(self, reason, start=None, end=None):
        with self.lock:
            if len(self.gaps) < 2048:
                self.gaps.append({'start': self.offset if start is None else start, 'end': self.offset + 1 if end is None else end,
                                  'reason': reason, 'boot_epoch': self.boot_epoch, 'phase_epoch': self.phase_epoch, 'at': now()})
            else: self.evidence_overflow = True
            self.partial = ''; self.decoder.reset()

    def redact(self, text):
        for secret in self.config.get('redact_values', []):
            if secret: text = text.replace(secret, '[REDACTED]')
        return re.sub(r'(?im)(token|password|secret|authorization)([ \t]*[:=][ \t]*)[^\r\n]*', r'\1\2[REDACTED]', text)

    def log_text(self, text):
        """Delay incomplete lines so credentials split across serial chunks never reach disk/tail."""
        combined = self.log_pending + text
        lines = combined.splitlines(keepends=True)
        self.log_pending = ''
        output = []
        for line in lines:
            complete = line.endswith(('\r', '\n'))
            if self.omitting_line:
                if complete: self.omitting_line = False
                continue
            if len(line) > 4096:
                output.append('[long console line omitted]\n'); self.omitting_line = not complete
            elif complete: output.append(self.redact(line))
            else: self.log_pending = line
        return ''.join(output)

    def boundary(self, phase, boot=False, expected_boot=False):
        with self.lock:
            self.phase = phase; self.phase_epoch += 1
            if boot: self.boot_epoch += 1
            self.stage_offset = self.offset; self.expected_boot = expected_boot
            self.partial = ''; self.decoder.reset()
            return self.position()

    def position(self):
        with self.lock:
            return {'offset': self.offset, 'boot_epoch': self.boot_epoch, 'phase_epoch': self.phase_epoch, 'phase': self.phase}

    def feed(self, data):
        if not isinstance(data, bytes): raise TypeError('Console bytes required')
        # Bound individual ingress records too; callers may supply larger transport chunks.
        if len(data) > 4096:
            for index in range(0, len(data), 4096): self.feed(data[index:index + 4096])
            return
        with self.lock:
            start = self.offset; self.offset += len(data)
            try: text = self.decoder.decode(data)
            except UnicodeDecodeError:
                self.gap('DECODE_ERROR', start, self.offset); text = ''
            old_length = len(self.partial)
            combined = self.partial + text
            for kind, values in self.markers.items():
                for marker in values:
                    index = combined.find(marker)
                    while index >= 0:
                        if index + len(marker) > old_length:
                            match_offset = self.offset - len(combined.encode('utf-8')) + len(combined[:index + len(marker)].encode('utf-8'))
                            event = {'kind': kind, 'signature': marker, 'offset': match_offset, 'boot_epoch': self.boot_epoch,
                                     'phase_epoch': self.phase_epoch, 'phase': self.phase, 'at': now()}
                            if kind == 'boot_signatures':
                                event['expected'] = self.expected_boot
                            if len(self.events) < 2048: self.events.append(event)
                            else: self.evidence_overflow = True
                        index = combined.find(marker, index + 1)
            self.partial = combined[-4096:]
            logged = self.log_text(text)
            self.tail = (self.tail + logged).encode('utf-8')[-self.tail_limit:].decode('utf-8', errors='ignore')
            record = {'start': start, 'end': self.offset, 'boot_epoch': self.boot_epoch,
                      'phase_epoch': self.phase_epoch, 'phase': self.phase, 'text': logged}
            try: self.queue.put_nowait(record)
            except queue.Full: self.gap('QUEUE_OVERFLOW', start, self.offset)

    def evidence(self, since=None):
        with self.lock:
            since = since or {'offset': self.stage_offset, 'boot_epoch': self.boot_epoch, 'phase_epoch': self.phase_epoch}
            start = since['offset']
            events = [e for e in self.events if e['offset'] > start and e['boot_epoch'] == since['boot_epoch'] and e['phase_epoch'] == since['phase_epoch']]
            gaps = [g for g in self.gaps if g['end'] > start]
            return {**self.position(), 'start_offset': start, 'end_offset': self.offset,
                    'panic': any(e['kind'] == 'panic_signatures' for e in events),
                    'unexpected_boot': any(e['kind'] == 'boot_signatures' and not e['expected'] for e in events),
                    'events': events, 'gaps': gaps, 'complete': not gaps and not self.writer_error and not self.evidence_overflow,
                    'evidence_overflow': self.evidence_overflow,
                    'tail': self.tail, 'log_directory': str(self.directory),
                    'rotations': self.rotations, 'retained_from': self.retained_from}

    def fence(self, timeout=2, closing=False):
        """Ingest the RX queue's current high-water mark, then confirm durable logging.

        The Windows queue count supplies a finite cut even if later console output
        continues. Injected sources without that interface must reach an empty read;
        inability to establish either cut is evidence loss, never permission to PASS.
        """
        deadline = time.monotonic() + timeout
        if not self.ingress_lock.acquire(timeout=max(0, deadline - time.monotonic())):
            self.gap('OBSERVER_FENCE_TIMEOUT'); return self.evidence()
        try:
            if self.source is not None and (closing or not self.read_stopping.is_set()):
                pending = getattr(self.source, 'pending_bytes', None)
                remaining = pending() if pending else None
                while remaining is None or remaining > 0:
                    if time.monotonic() >= deadline:
                        self.gap('OBSERVER_FENCE_TIMEOUT'); break
                    data = self.source.read(min(4096, remaining) if remaining is not None else 4096)
                    if not data:
                        if remaining: self.gap('OBSERVER_FENCE_INCOMPLETE')
                        break
                    self.feed(data)
                    if remaining is not None: remaining -= len(data)
        except Exception:
            self.gap('OBSERVER_FENCE_FAILED')
        finally:
            self.ingress_lock.release()
        while self.queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(.005)
        if self.queue.unfinished_tasks: self.gap('LOG_FENCE_TIMEOUT')
        return self.evidence()

    def _receipt(self):
        with self.lock:
            value = {**self.position(), 'events': self.events, 'gaps': self.gaps, 'rotations': self.rotations,
                     'retained_from': self.retained_from, 'writer_error': self.writer_error, 'evidence_overflow': self.evidence_overflow}
        temp = self.directory / 'receipt.tmp'
        temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, self.directory / 'receipt.json')

    def _write(self):
        path = self.directory / 'console.jsonl'
        while not self.stopping.is_set() or not self.queue.empty():
            try:
                try: record = self.queue.get(timeout=.1)
                except queue.Empty:
                    self._receipt(); continue
                data = (json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8')
                if path.exists() and path.stat().st_size + len(data) > self.rotate_bytes:
                    oldest = self.directory / f'console.{self.rotate_count - 1}.jsonl'
                    if oldest.exists():
                        # Retention is explicit evidence, distinct from acquisition gaps.
                        try:
                            last = json.loads(oldest.read_text(encoding='utf-8').splitlines()[-1])
                            self.retained_from = max(self.retained_from, last['end'])
                        except (ValueError, IndexError): self.writer_error = True
                        oldest.unlink()
                    for index in range(self.rotate_count - 2, 0, -1):
                        previous = self.directory / f'console.{index}.jsonl'
                        if previous.exists(): os.replace(previous, self.directory / f'console.{index + 1}.jsonl')
                    if self.rotate_count > 1: os.replace(path, self.directory / 'console.1.jsonl')
                    else:
                        self.retained_from = record['start']; path.unlink()
                    self.rotations += 1
                with path.open('ab') as out: out.write(data); out.flush()
                self._receipt(); self.queue.task_done()
            except Exception:
                self.writer_error = True; self.gap('LOG_WRITE_FAILED'); time.sleep(.1)
        try: self._receipt()
        except OSError: self.writer_error = True

    def close(self):
        self.read_stopping.set()
        if self.reader: self.reader.join(timeout=1)
        # A final queue cut after the background reader stopped includes bytes
        # arriving between the caller's fence and the handoff to close().
        self.fence(closing=True)
        if self.source: self.source.close()
        with self.lock:
            if self.log_pending:
                record = {**self.position(), 'start': self.offset, 'end': self.offset, 'text': self.redact(self.log_pending)}
                self.log_pending = ''
                try: self.queue.put_nowait(record)
                except queue.Full: self.gap('QUEUE_OVERFLOW')
        self.stopping.set()
        self.writer.join(timeout=3)
        if self.writer.is_alive(): self.gap('LOG_DRAIN_INCOMPLETE')
