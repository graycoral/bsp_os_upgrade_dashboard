import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from backend.domain.policy import Conflict, now


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO meta VALUES ('schema_version','1');
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, version INTEGER NOT NULL, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS commands(key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, result TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS leases(resource TEXT PRIMARY KEY, attempt TEXT NOT NULL, token TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS config(id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL, data TEXT NOT NULL);
            ''')
            if c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0] != '1':
                raise RuntimeError('Unsupported database schema')

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
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
            except Exception:
                c.rollback()
                raise

    def get(self, c, job_id):
        row = c.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row:
            raise Conflict('작업을 찾을 수 없습니다.', 'NOT_FOUND', 404)
        return json.loads(row['data'])

    def save(self, c, job, event, detail=None):
        job['version'] += 1
        job['updated_at'] = now()
        c.execute('INSERT INTO jobs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,data=excluded.data', (job['id'], job['version'], json.dumps(job, ensure_ascii=False)))
        c.execute('INSERT INTO events(job_id,type,data,created_at) VALUES(?,?,?,?)', (job['id'], event, json.dumps(detail or {}, ensure_ascii=False), now()))

    def snapshot(self, job_id):
        with self.connection() as c:
            return self.get(c, job_id)

    def all(self):
        with self.connection() as c:
            return [json.loads(r[0]) for r in c.execute('SELECT data FROM jobs ORDER BY rowid DESC')]

    def events(self, job_id, after=0):
        with self.connection() as c:
            return [dict(r) | {'data': json.loads(r['data'])} for r in c.execute('SELECT * FROM events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 300', (job_id, after))]

    def backup(self, destination):
        with self.connection() as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
