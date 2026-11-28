"""Read the reverse connector port before the managed interpreter is available."""

from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3


DEFAULT_CONNECTOR_PORT = 8771


def valid_port(port):
    return type(port) is int and 1 <= port <= 65535


def legacy_connector_port(settings):
    if not isinstance(settings, dict):
        return None
    match = re.fullmatch(r'http://127\.0\.0\.1:([0-9]+)', str(settings.get('url', '')).rstrip('/'))
    if match:
        port = int(match[1])
        if valid_port(port):
            return port
    return None


def configured_connector_port(runtime):
    runtime = Path(runtime)
    database = runtime / 'shared-settings.db'
    if database.is_symlink():
        raise ValueError('The shared settings database path is a symlink.')
    if database.exists():
        try:
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
                db.execute('PRAGMA trusted_schema=OFF')
                row = db.execute('SELECT data_json FROM connector_preferences WHERE id=1').fetchone()
        except sqlite3.Error as exc:
            raise ValueError('The shared connector settings could not be read.') from exc
        document = json.loads(row[0]) if row else None
        port = document.get('preferred_connector_port') if isinstance(document, dict) else None
        if not valid_port(port):
            raise ValueError('The saved reverse connector port is invalid.')
        return port
    legacy = runtime / 'gui-test.json'
    if legacy.is_file() and not legacy.is_symlink():
        try:
            port = legacy_connector_port(json.loads(legacy.read_text(encoding='utf-8-sig')))
            if port is not None:
                return port
        except (OSError, ValueError):
            pass
    return DEFAULT_CONNECTOR_PORT
