"""Bounded in-memory pipe collection. Only redacted text is ever persisted."""
import re
import threading


class Capture:
    def __init__(self, stdout, stderr, limit=65536):
        self.limit = limit
        self.buffers = {'stdout': bytearray(), 'stderr': bytearray()}
        self.total = 0
        self.failed = False
        self.lock = threading.Lock()
        self.threads = [threading.Thread(target=self.read, args=(name, pipe), daemon=True)
                        for name, pipe in [('stdout', stdout), ('stderr', stderr)]]
        for thread in self.threads: thread.start()

    def read(self, name, pipe):
        try:
            while True:
                chunk = pipe.read1(4096)
                if not chunk: break
                with self.lock:
                    self.total = min(self.limit + 1, self.total + len(chunk))
                    space = max(0, self.limit + 1 - len(self.buffers[name]))
                    self.buffers[name].extend(chunk[:space])
        except Exception:
            with self.lock: self.failed = True
        finally: pipe.close()

    def snapshot(self):
        with self.lock:
            texts = {}
            for stream, raw in self.buffers.items():
                # A credential key/value can span pipe writes: publish complete lines only.
                boundary = len(raw) if all(not t.is_alive() for t in self.threads) else raw.rfind(b'\n') + 1
                text = raw[:boundary].decode('utf-8', errors='replace')
                texts[stream] = re.sub(r'(?im)(token|password|secret|authorization)([ \t]*[:=][ \t]*)[^\r\n]*', r'\1\2[REDACTED]', text)
            return texts, self.failed or self.total > self.limit

    def drain(self):
        for thread in self.threads: thread.join(timeout=2)
        return all(not thread.is_alive() for thread in self.threads)
