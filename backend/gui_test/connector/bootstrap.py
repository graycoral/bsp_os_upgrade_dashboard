"""Offline bootstrap import; no manager, SSH, TC, or device is started here."""
import copy
import json
import sqlite3
from contextlib import ExitStack

from ..core.connector_bootstrap import load_profile, plain_path, ConnectorBootstrap
from ..core.models import TestError
from ..execution.launch import LaunchLock
from .settings import Settings


def import_profile(home, path):
    profile = load_profile(path)
    home = plain_path(home)
    runtime = home / 'runtime'
    target = plain_path(home / 'windows-runner.json')
    # Reject any running manager, even if disconnected. Its settings/control and
    # offline launchers must never race an out-of-band file replacement.
    with ExitStack() as stack:
        try:
            for name in ('connector-manager.lock', 'setup-launch.lock', 'runner.lock'):
                stack.enter_context(LaunchLock(runtime / name))
        except RuntimeError as exc:
            raise TestError('관리자와 연결을 안전하게 종료한 뒤 연결 파일을 가져오세요.', 'CONNECTOR_BUSY', 409) from exc
        db = plain_path(runtime / 'executions.db')
        if db.exists():
            try:
                connection = stack.enter_context(sqlite3.connect(db.as_uri() + '?mode=rw', uri=True, timeout=0))
                connection.execute('BEGIN IMMEDIATE')
                jobs = [json.loads(row[0]) for row in connection.execute('SELECT data FROM jobs')]
                batches = [json.loads(row[0]) for row in connection.execute('SELECT data FROM batches')]
                if any(job.get('state') not in {'DONE', 'DELETED'} or job.get('terminated') is not True for job in jobs) or any(
                        batch.get('state') != 'RELEASED' for batch in batches):
                    raise TestError('진행·예약·종료 불명 작업이 있어 연결 설정을 유지합니다.', 'CONNECTOR_BUSY', 409)
            except (sqlite3.Error, ValueError, TypeError, AttributeError) as exc:
                raise TestError('장비 실행 기록을 확인할 수 없어 연결 설정을 유지합니다.', 'CONNECTOR_BUSY', 409) from exc
        current = Settings(home).read()
        value = copy.deepcopy(current)
        setup = value.setdefault('_setup', {})
        if not isinstance(setup, dict):
            raise ValueError('Invalid local connection settings')
        previous = setup.get('connector_bootstrap')
        if previous is not None:
            try:
                previous_identity = ConnectorBootstrap.model_validate(previous).identity
            except ValueError:
                raise ValueError('Existing imported connection profile is malformed') from None
            if previous_identity != profile.identity:
                raise TestError('기존 Linux 서비스 식별자와 다른 연결 파일입니다.', 'SERVICE_IDENTITY_MISMATCH', 409)
        setup.update(profile.endpoint.model_dump())
        setup['connector_bootstrap'] = profile.model_dump()
        # Do not use Settings.save: first connection legitimately has no COM/TC
        # configuration yet. Only the validated narrow endpoint fields change.
        from scripts.setup_runtime import save_json
        plain_path(target)
        save_json(target, value)
        return {'state': 'IMPORTED', 'format': profile.format, 'identity': profile.identity.model_dump(),
                'endpoint': profile.endpoint.model_dump()}
