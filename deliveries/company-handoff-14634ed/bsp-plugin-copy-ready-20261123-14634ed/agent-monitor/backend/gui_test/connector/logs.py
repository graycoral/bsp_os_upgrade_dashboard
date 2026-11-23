"""Identical redaction for file, GUI and clipboard; bounded rotating files."""
import logging
from logging.handlers import RotatingFileHandler
import re


def redact(text):
    text = str(text)
    text = re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+', r'\1[REDACTED]', text)
    return re.sub(r'(?im)((?:token|password|secret|authorization)[\w-]*\s*[:=]\s*)[^\r\n,}]+', r'\1[REDACTED]', text)


class SafeFormatter(logging.Formatter):
    def format(self, record): return redact(super().format(record))


def logger(home):
    from pathlib import Path
    folder = Path(home) / 'logs'; folder.mkdir(parents=True, exist_ok=True)
    value = logging.getLogger('connector.' + str(folder))
    if not value.handlers:
        handler = RotatingFileHandler(folder / 'connector.log', maxBytes=1024 * 1024, backupCount=3, encoding='utf-8')
        handler.setFormatter(SafeFormatter('%(asctime)s %(levelname)s %(message)s'))
        value.addHandler(handler); value.setLevel(logging.INFO); value.propagate = False
    return value
