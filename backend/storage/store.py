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
            version = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
            if version not in {'1', '2'}:
                raise RuntimeError('Unsupported database schema')
        if version == '1':
            self._migrate_v2()

    def _migrate_v2(self):
        """Add tables atomically without rewriting any frozen v1 JSON."""
        statements = [
            'CREATE TABLE IF NOT EXISTS agent_reports(report_id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), attempt_id TEXT NOT NULL, module_id TEXT, stage TEXT NOT NULL, sha256 TEXT NOT NULL, disposition TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS report_receipts(id TEXT PRIMARY KEY, report_id TEXT NOT NULL, job_id TEXT NOT NULL REFERENCES jobs(id), sha256 TEXT NOT NULL, disposition TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS decision_candidates(id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), report_id TEXT NOT NULL REFERENCES agent_reports(report_id), candidate_key TEXT NOT NULL, module_id TEXT NOT NULL, status TEXT NOT NULL, decision_id TEXT, data TEXT NOT NULL, UNIQUE(job_id,module_id,candidate_key))',
            'CREATE TABLE IF NOT EXISTS scope_holds(id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), candidate_id TEXT NOT NULL REFERENCES decision_candidates(id), status TEXT NOT NULL, data TEXT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS orchestration_triggers(id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), event_id TEXT NOT NULL, type TEXT NOT NULL, plan_version INTEGER NOT NULL, status TEXT NOT NULL, run_id TEXT, root_id TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(job_id,event_id,type))',
            'CREATE TABLE IF NOT EXISTS orchestration_runs(id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), status TEXT NOT NULL, root_id TEXT NOT NULL, request TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL)',
            'CREATE UNIQUE INDEX IF NOT EXISTS one_active_orchestration ON orchestration_runs(job_id) WHERE status IN (\'PENDING\',\'RUNNING\',\'UNKNOWN\')',
            'CREATE TABLE IF NOT EXISTS orchestration_proposals(id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), run_id TEXT NOT NULL REFERENCES orchestration_runs(id), proposal_key TEXT NOT NULL, sha256 TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(job_id,run_id,proposal_key))',
            'CREATE TABLE IF NOT EXISTS coordinator_lanes(job_id TEXT PRIMARY KEY REFERENCES jobs(id), owner_id TEXT NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL)',
            'CREATE TABLE IF NOT EXISTS launch_receipts(id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), owner_id TEXT NOT NULL, kind TEXT NOT NULL, nonce TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(owner_id,kind))',
            'CREATE INDEX IF NOT EXISTS reports_by_job ON agent_reports(job_id,created_at)',
            'CREATE INDEX IF NOT EXISTS pending_triggers ON orchestration_triggers(job_id,status)',
        ]
        with self.transaction() as c:
            for statement in statements:
                c.execute(statement)
            c.execute("UPDATE meta SET value='2' WHERE key='schema_version'")

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
        job = json.loads(row['data'])
        job['scope_holds'] = [json.loads(r[0]) for r in c.execute("SELECT data FROM scope_holds WHERE job_id=? AND status='ACTIVE'", (job_id,))]
        return job

    @staticmethod
    def _encoded(job):
        return json.dumps({k: v for k, v in job.items() if k != 'scope_holds'}, ensure_ascii=False)

    def audit(self, c, job, event, detail=None):
        """Persist audit/session transport metadata without invalidating execution CAS."""
        c.execute('UPDATE jobs SET data=? WHERE id=?', (self._encoded(job), job['id']))
        c.execute('INSERT INTO events(job_id,type,data,created_at) VALUES(?,?,?,?)', (job['id'], event, json.dumps(detail or {}, ensure_ascii=False), now()))

    def save(self, c, job, event, detail=None):
        job['version'] += 1
        job['updated_at'] = now()
        c.execute('INSERT INTO jobs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,data=excluded.data', (job['id'], job['version'], self._encoded(job)))
        c.execute('INSERT INTO events(job_id,type,data,created_at) VALUES(?,?,?,?)', (job['id'], event, json.dumps(detail or {}, ensure_ascii=False), now()))

    def snapshot(self, job_id):
        with self.connection() as c:
            return self.get(c, job_id)

    def all(self):
        with self.connection() as c:
            return [self.get(c, r[0]) for r in c.execute('SELECT id FROM jobs ORDER BY rowid DESC').fetchall()]

    def events(self, job_id, after=0):
        with self.connection() as c:
            return [dict(r) | {'data': json.loads(r['data'])} for r in c.execute('SELECT * FROM events WHERE job_id=? AND seq>? ORDER BY seq LIMIT 300', (job_id, after))]

    def backup(self, destination):
        with self.connection() as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
