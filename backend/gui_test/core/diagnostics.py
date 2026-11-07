"""Bounded connection diagnostics, independent of Run acceptance and hardware."""
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit
from uuid import uuid4


def safe_target(value):
    try:
        parsed = urlsplit(str(value))
        host = parsed.hostname
        if parsed.scheme not in {'http', 'https'} or not host:
            return 'configured-service'
        port = parsed.port
        return parsed.scheme + '://' + ('[' + host + ']' if ':' in host else host) + (':' + str(port) if port else '')
    except (ValueError, TypeError):
        return 'configured-service'


def scrub(value):
    text = str(value)[:2048]
    # Defense in depth: callers use fixed causes/hints rather than exception repr.
    text = re.sub(r'(?i)\b(?:Bearer|Basic)\s+[^\s,;]+', '[REDACTED]', text)
    text = re.sub(r'(?i)(?:https?://)[^\s<>"\']+', lambda match: safe_target(match.group()), text)
    text = re.sub(r'(?i)\b(token|password|passwd|secret|authorization|credential|api[_-]?key)\b\s*[=:]\s*(?:"[^"]*"|\'[^\']*\'|[^\s,;]+)', r'\1=[REDACTED]', text)
    return ''.join(c if ord(c) >= 32 else ' ' for c in text)


class _RaisingHandler(RotatingFileHandler):
    def handleError(self, record):
        raise OSError('Diagnostic log write failed')


class DiagnosticRecorder:
    def __init__(self, log_dir=None, callback=None, *, max_bytes=8 * 1024**2, backups=7):
        self.directory = Path(log_dir) if log_dir is not None else Path.home() / '.bsp-upgrade' / 'gui-test-logs'
        self.path = self.directory / 'connections.jsonl'
        self.callback = callback
        self.max_bytes, self.backups = max_bytes, backups
        self.lock = threading.Lock()

    def record(self, phase, target, code, cause, hint, *, attempt=1, duration_ms=0, correlation_id=None):
        event = {'correlation_id': correlation_id or uuid4().hex,
                 'at': datetime.now(timezone.utc).isoformat(), 'phase': scrub(phase),
                 'attempt': max(1, int(attempt)), 'duration_ms': max(0, round(duration_ms, 2)),
                 'target': safe_target(target), 'code': scrub(code), 'cause': scrub(cause), 'hint': scrub(hint),
                 'log_path': str(self.path)}
        try:
            with self.lock:
                self.directory.mkdir(parents=True, exist_ok=True)
                handler = _RaisingHandler(self.path, maxBytes=self.max_bytes, backupCount=self.backups, encoding='utf-8')
                try:
                    handler.setFormatter(logging.Formatter('%(message)s'))
                    handler.emit(logging.LogRecord('gui-test-connection', logging.INFO, '', 0,
                                                  json.dumps(event, ensure_ascii=False), (), None))
                finally:
                    handler.close()
        except Exception:
            # Surface storage failure without replacing the original connection
            # cause or exposing OS errors that may contain credential paths.
            event['log_error'] = 'DIAGNOSTIC_LOG_UNAVAILABLE'
            event['log_hint'] = 'Check the configured diagnostic directory permissions and free space.'
        if self.callback:
            try:
                self.callback(dict(event))
            except Exception:
                event['callback_error'] = 'DIAGNOSTIC_CALLBACK_FAILED'
        return event
