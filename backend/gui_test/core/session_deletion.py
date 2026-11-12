"""Explicit permanent deletion, only after both managers confirm stopped work."""
import json

from .models import TestError, TERMINAL, digest, now


class SessionDeletion:
    def __init__(self, manager):
        self.manager = manager
        self.store = manager.store

    def check(self, c, run, session, expected):
        if run['controller'] != session:
            raise TestError('현재 세션의 제어권이 필요합니다.', 'CONTROL_REQUIRED', 403)
        if run['version'] != expected:
            raise TestError('세션 상태를 새로 확인한 후 삭제하세요.', 'VERSION_CONFLICT')
        if run['state'] not in TERMINAL or any(a.get('terminated') is False for a in run['attempts']):
            raise TestError('완료·취소되고 종료가 확인된 세션만 영구 삭제할 수 있습니다.', 'SESSION_ACTIVE')
        if c.execute('SELECT 1 FROM reservations WHERE run_id=?', (run['id'],)).fetchone() or c.execute('SELECT 1 FROM outbox WHERE run_id=?', (run['id'],)).fetchone():
            raise TestError('예약 해제와 결과 동기화를 확인한 후 삭제하세요.', 'SESSION_ACTIVE')
        for row in c.execute('SELECT data FROM runs'):
            child = json.loads(row[0])
            if child.get('parent_run_id') == run['id'] and child['state'] not in TERMINAL:
                raise TestError('이 세션에서 시작한 재실행이 아직 진행 중입니다.', 'SESSION_REFERENCED')

    def delete(self, run_id, session, expected):
        fingerprint = digest({'id': run_id, 'session': session, 'version': expected})
        with self.store.transaction() as c:
            run = self.store.get(c, run_id)
            self.check(c, run, session, expected)
            row = c.execute("SELECT data FROM documents WHERE kind='session-deletion' AND name=?", (run_id,)).fetchone()
            if row and json.loads(row[0])['fingerprint'] != fingerprint:
                raise TestError('진행 중인 세션 삭제 요청과 다릅니다.', 'DELETE_CONFLICT')
            c.execute("INSERT OR IGNORE INTO documents VALUES('session-deletion',?,?)", (run_id, json.dumps({'fingerprint': fingerprint, 'started_at': now()})))
        if not run['simulation']:
            self.manager.runner.delete_session(run)
        registry=getattr(self.manager.runner,'registry',None)
        if registry is not None: registry.delete_run_events(run_id)
        with self.store.transaction() as c:
            try: current = self.store.get(c, run_id)
            except TestError as exc:
                if exc.code == 'RUN_DELETED': return {'id': run_id, 'deleted': True}
                raise
            self.check(c, current, session, expected)
            # Old command keys must never replay full deleted evidence or recreate work.
            for row in c.execute('SELECT id,result FROM commands').fetchall():
                result = json.loads(row['result'])
                if isinstance(result, dict) and result.get('id') == run_id:
                    c.execute('UPDATE commands SET result=? WHERE id=?', (json.dumps({'_deleted_run': run_id}), row['id']))
            for row in c.execute("SELECT name,data FROM documents WHERE kind='integration-preparation'").fetchall():
                if json.loads(row['data']).get('consumed_by') == run_id:
                    c.execute("DELETE FROM documents WHERE kind='integration-preparation' AND name=?", (row['name'],))
            c.execute('DELETE FROM events WHERE run_id=?', (run_id,))
            c.execute('DELETE FROM runs WHERE id=?', (run_id,))
            c.execute("DELETE FROM documents WHERE kind='session-deletion' AND name=?", (run_id,))
            c.execute("INSERT OR REPLACE INTO documents VALUES('deleted-run',?,?)", (run_id, json.dumps({'deleted_at': now()})))
        return {'id': run_id, 'deleted': True}
