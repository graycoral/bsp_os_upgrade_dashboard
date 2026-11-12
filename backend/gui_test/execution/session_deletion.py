"""Delete private execution copies; never traverse caller-provided filesystem paths."""
import json
import os
import shutil
import sqlite3

from pydantic import Field
from ..core.models import StrictModel, TestError, now
from .installer_snapshots import regular


class DeleteSession(StrictModel):
    runner_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    execution_ids: list[str] = Field(max_length=256)
    batch_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')


def remove_private(root, directory):
    if not directory.exists() and not directory.is_symlink(): return
    regular(root, directory=True)
    regular(directory.parent, directory=True)
    regular(directory, directory=True)
    if not directory.resolve().is_relative_to(root.resolve()):
        raise TestError('실행 사본 경로를 확인할 수 없습니다.', 'DELETE_PATH')
    for base, dirs, files in os.walk(directory, followlinks=False):
        from pathlib import Path
        for name in dirs: regular(Path(base) / name, directory=True)
        for name in files: regular(Path(base) / name)
    shutil.rmtree(directory)


def delete_session(host, payload):
    from .host import valid_identity
    value = DeleteSession.model_validate(payload)
    if value.runner_id != host.identity:
        raise TestError('커넥터 실행 저장소가 바뀌었습니다.', 'RUNNER_CHANGED')
    ids = list(dict.fromkeys(value.execution_ids))
    for identity in ids: valid_identity(identity)
    with host.lock, sqlite3.connect(host.db) as c:
        if any(json.loads(row[0]).get('state') in {'RUNNING', 'UNKNOWN'} for row in c.execute('SELECT data FROM jobs')):
            raise TestError('커넥터의 다른 실행이 끝나고 종료가 확인된 후 삭제하세요.', 'SESSION_ACTIVE')
        jobs = []
        for identity in ids:
            row = c.execute('SELECT data FROM jobs WHERE id=?', (identity,)).fetchone()
            item = json.loads(row[0]) if row else None
            if item and (item.get('state') not in {'DONE', 'DELETED'} or item.get('terminated') is not True):
                raise TestError('실행 중·종료 불명 기록은 삭제할 수 없습니다.', 'SESSION_ACTIVE')
            if item and item.get('batch_id') and item['batch_id'] != value.batch_id:
                raise TestError('상위 세션 소유권이 다릅니다.', 'DELETE_OWNER')
            if not item and any((host.runtime / key / identity).exists() for key in ('snapshots', 'flash-snapshots')):
                raise TestError('소유 실행 기록이 없는 사본은 자동 삭제하지 않습니다.', 'DELETE_OWNER')
            jobs.append((identity, item))
        batch = None
        if value.batch_id:
            row = c.execute('SELECT data FROM batches WHERE id=?', (value.batch_id,)).fetchone()
            batch = json.loads(row[0]) if row else None
            if not batch or batch['state'] != 'RELEASED':
                raise TestError('상위 장비 예약이 해제되지 않았습니다.', 'SESSION_ACTIVE')
            linked = [(key, json.loads(data)) for key, data in c.execute('SELECT id,data FROM jobs')]
            if any(item.get('batch_id') == value.batch_id and (item.get('state') not in {'DONE', 'DELETED'} or item.get('terminated') is not True) for _, item in linked):
                raise TestError('상위 세션의 실행이 종료되지 않았습니다.', 'SESSION_ACTIVE')
            jobs.extend((key, item) for key, item in linked if item.get('batch_id') == value.batch_id and key not in ids)
        # Console errors are durable connector evidence; purge this authorized session's references too.
        table=c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='connector_console_errors'").fetchone()
        if table:
            owned={identity for identity,item in jobs}
            for seq,data in c.execute('SELECT seq,data FROM connector_console_errors').fetchall():
                if owned.intersection(json.loads(data).get('run_ids',[])):
                    c.execute('DELETE FROM connector_console_errors WHERE seq=?',(seq,))
        for identity, item in jobs:
            if item:
                for key in ('snapshots', 'flash-snapshots'):
                    remove_private(host.runtime, host.runtime / key / identity)
                tombstone = {'id': identity, 'state': 'DELETED', 'terminated': True, 'deleted_at': now(),
                             'request_hash': item.get('request_hash')}
                c.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(tombstone), identity))
        if batch:
            remove_private(host.runtime, host.runtime / 'batch-snapshots' / value.batch_id)
            c.execute('UPDATE batches SET data=? WHERE id=?', (json.dumps({'id': value.batch_id, 'state': 'RELEASED', 'deleted': True, 'epoch': batch['epoch']}), value.batch_id))
    return {'deleted': True, 'execution_ids': ids, 'runner_id': host.identity}
