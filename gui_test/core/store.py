import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from gui_test.core.models import TestError, now


class Store:
    """Separate DB for each mode; reservations and commands commit with run state."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO meta VALUES('schema_version','1');
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reservations(resource TEXT PRIMARY KEY, run_id TEXT NOT NULL, token TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY, hash TEXT NOT NULL, result TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, type TEXT, data TEXT, at TEXT);
            CREATE TABLE IF NOT EXISTS documents(kind TEXT, name TEXT, data TEXT, PRIMARY KEY(kind,name));
            CREATE TABLE IF NOT EXISTS outbox(run_id TEXT PRIMARY KEY, data TEXT NOT NULL);
            ''')
            if c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] != '1':
                raise RuntimeError('Unsupported GUI Test database version')

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    @contextmanager
    def transaction(self):
        with self.connection() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise

    def get(self, c, run_id):
        row = c.execute('SELECT data FROM runs WHERE id=?', (run_id,)).fetchone()
        if not row:
            raise TestError('Run not found', 'NOT_FOUND', 404)
        return json.loads(row[0])

    def save(self, c, run, event, data=None):
        run['version'] += 1
        run['updated_at'] = now()
        c.execute('INSERT INTO runs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                  (run['id'], json.dumps(run, ensure_ascii=False)))
        c.execute('INSERT INTO events(run_id,type,data,at) VALUES(?,?,?,?)',
                  (run['id'], event, json.dumps(data or {}), now()))

    def snapshot(self, run_id):
        with self.connection() as c:
            return self.get(c, run_id)

    def all(self):
        with self.connection() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT data FROM runs ORDER BY rowid DESC')]

    def events(self, run_id):
        with self.connection() as c:
            self.get(c, run_id)
            return [dict(r) | {'data': json.loads(r['data'])} for r in c.execute('SELECT * FROM events WHERE run_id=? ORDER BY seq', (run_id,))]

    def documents(self, kind):
        with self.connection() as c:
            return [{'name': r[0], **json.loads(r[1])} for r in c.execute('SELECT name,data FROM documents WHERE kind=? ORDER BY name', (kind,))]

    def backup(self, path):
        with self.connection() as c, sqlite3.connect(path) as target:
            c.backup(target)
