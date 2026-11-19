"""Offline bootstrap import; no manager, SSH, TC, or device is started here."""
import copy
import json
import sqlite3
from contextlib import ExitStack

from ..core.connector_bootstrap import (load_profile, plain_path, parse_bootstrap,
                                         ConnectorBootstrap, ConnectorBootstrapV2)
from ..core.models import TestError
from ..execution.launch import LaunchLock
from .settings import Settings


def _active_connector_runs(connection):
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'connector_runs' not in tables:
        return False
    row = connection.execute(
        "SELECT 1 FROM connector_runs WHERE state IN ('QUEUED','FLASHING','RUNNING','PAUSE_REQUESTED','CANCEL_REQUESTED','UNKNOWN') OR analysis_latched=1 LIMIT 1"
    ).fetchone()
    return row is not None


def import_profile(home, path, *, server_port=None):
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
                if (any(job.get('state') not in {'DONE', 'DELETED'} or job.get('terminated') is not True for job in jobs) or
                        any(batch.get('state') != 'RELEASED' for batch in batches) or
                        _active_connector_runs(connection)):
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
                previous_parsed = parse_bootstrap(previous)
            except ValueError:
                raise ValueError('Existing imported connection profile is malformed') from None
            if isinstance(previous_parsed, ConnectorBootstrap) and isinstance(profile, ConnectorBootstrap):
                if previous_parsed.identity != profile.identity:
                    raise TestError('기존 Linux 서비스 식별자와 다른 연결 파일입니다.', 'SERVICE_IDENTITY_MISMATCH', 409)
            elif (isinstance(previous_parsed, ConnectorBootstrapV2) and isinstance(profile, ConnectorBootstrapV2) and
                  previous_parsed.expected_runner_id and profile.expected_runner_id and
                  previous_parsed.expected_runner_id != profile.expected_runner_id):
                raise TestError('기존 보드 커넥터 식별자와 다른 연결 파일입니다.', 'RUNNER_CHANGED', 409)
        endpoint_data = profile.endpoint.model_dump()
        setup.update(endpoint_data)
        setup.setdefault('remote_runner_port', 8771)
        if isinstance(profile, ConnectorBootstrapV2):
            setup['expected_runner_id'] = profile.expected_runner_id
        setup['connector_bootstrap'] = profile.model_dump()
        if server_port is not None:
            from .server_port import set_port
            from scripts.setup_ports import PortsProfile
            value = set_port(value, server_port)
            PortsProfile(home / 'setup-ports.json').resolve({'remote_dashboard_port': server_port})
        elif endpoint_data.get('remote_runner_port') is not None:
            from scripts.setup_ports import PortsProfile
            ports_path = home / 'setup-ports.json'
            if ports_path.exists():
                pp = PortsProfile(ports_path)
                existing_ports = pp.read()
                if existing_ports:
                    existing_ports['remote_runner_port'] = endpoint_data['remote_runner_port']
                    if endpoint_data.get('remote_dashboard_port') is not None:
                        existing_ports['remote_dashboard_port'] = endpoint_data['remote_dashboard_port']
                    pp.save(existing_ports)
        # Do not use Settings.save: first connection legitimately has no COM/TC
        # configuration yet. Only the validated narrow endpoint fields change.
        from scripts.setup_runtime import save_json
        plain_path(target)
        save_json(target, value)
        res = {'state': 'IMPORTED', 'format': profile.format,
               'endpoint': value['_setup']['connector_bootstrap']['endpoint']}
        if isinstance(profile, ConnectorBootstrap):
            res['identity'] = profile.identity.model_dump()
        else:
            res['identity'] = None
            res['expected_runner_id'] = profile.expected_runner_id
        return res


def bootstrap_profile(home, path):
    """First import once; identical later launches may reuse a running Manager."""
    profile = load_profile(path)
    home = plain_path(home)
    current = Settings(home).read()
    setup = current.get('_setup', {})
    saved = setup.get('connector_bootstrap')
    if saved is not None:
        existing = parse_bootstrap(saved)
        if existing == profile and all(setup.get(key) == value for key, value in profile.endpoint.model_dump().items()):
            res = {'state': 'REUSED'}
            if isinstance(profile, ConnectorBootstrap):
                res['identity'] = profile.identity.model_dump()
            else:
                res['identity'] = None
                res['expected_runner_id'] = profile.expected_runner_id
            return res
    # Different endpoints retain all existing busy/UNKNOWN and identity gates.
    return import_profile(home, path)
