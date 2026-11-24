"""Managed startup upgrades legacy UART profiles without changing live ownership."""
import json
import sqlite3
from pathlib import Path

import pytest

from backend.gui_test.connector.automatic_serial import prepare_locked
from backend.gui_test.connector.settings import Settings
from backend.gui_test.core.models import TestError
from backend.gui_test.core.shared_settings import ConnectorDesired
from backend.gui_test.execution.launch import LaunchLock


def profile(home, mode='native'):
    value = {'boards': [{'host': 'win', 'board_id': 'board-1', 'com': 'COM7'}],
             '_setup': {'server': 'linux', 'account': 'user'},
             'console_observers': {'board-1': {'port': 'COM8', 'redact_values': ['private']}},
             'serial_settings': {'board-1': {'baudrate': 9600, 'dtr': False}},
             'vendor': {'preserve': True}}
    if mode is not None:
        value['serial_transport'] = mode
    (home / 'windows-runner.json').write_text(json.dumps(value))
    return value


def records(home, *, jobs=(), batches=()):
    runtime = home / 'runtime'
    runtime.mkdir(exist_ok=True)
    with sqlite3.connect(runtime / 'executions.db') as db:
        for table, values in [('jobs', jobs), ('batches', batches)]:
            db.execute(f'CREATE TABLE {table}(data TEXT)')
            db.executemany(f'INSERT INTO {table} VALUES(?)', [(json.dumps({'state': v}),) for v in values])


def prepare(home):
    with LaunchLock(home / 'runtime' / 'setup-launch.lock'), LaunchLock(home / 'runtime' / 'runner.lock'):
        prepare_locked(home)


@pytest.mark.parametrize('mode', [None, 'native'])
@pytest.mark.parametrize('existing', [False, True])
def test_legacy_migration_preserves_profile(tmp_path, mode, existing):
    before = profile(tmp_path, mode)
    if existing:
        records(tmp_path, jobs=['PASS', 'FAIL'], batches=['RELEASED'])
    prepare(tmp_path)
    assert Settings(tmp_path).read() == before | {'serial_transport': 'proxy'}
    assert list(tmp_path.glob('windows-runner.json.*.bak'))
    first = (tmp_path / 'windows-runner.json').read_bytes()
    prepare(tmp_path)
    assert (tmp_path / 'windows-runner.json').read_bytes() == first


@pytest.mark.parametrize('jobs,batches', [(['RUNNING'], []), (['UNKNOWN'], []), ([], ['RESERVED'])])
def test_unresolved_ownership_preserves_native(tmp_path, jobs, batches):
    before = profile(tmp_path)
    records(tmp_path, jobs=jobs, batches=batches)
    with pytest.raises(TestError, match='작업'):
        prepare(tmp_path)
    assert Settings(tmp_path).read() == before


def test_live_owner_cannot_be_migrated(tmp_path):
    before = profile(tmp_path)
    with LaunchLock(tmp_path / 'runtime' / 'runner.lock'):
        with pytest.raises(RuntimeError, match="already running"):
            prepare(tmp_path)
    assert Settings(tmp_path).read() == before


def test_corrupt_execution_records_fail_closed(tmp_path):
    before = profile(tmp_path)
    (tmp_path / 'runtime').mkdir()
    (tmp_path / 'runtime' / 'executions.db').write_text('invalid database')
    with pytest.raises(sqlite3.DatabaseError):
        prepare(tmp_path)
    assert Settings(tmp_path).read() == before


def test_save_and_central_desired_use_automatic_transport(tmp_path):
    before = profile(tmp_path)
    saved = Settings(tmp_path).save({'board_names': {'board-1': 'A'}})
    assert saved == before | {'serial_transport': 'proxy', 'board_names': {'board-1': 'A'}}
    desired = ConnectorDesired(expected_revision='a'*64, runner_id='win', settings={'serial_transport': 'native'})
    assert desired.settings['serial_transport'] == 'proxy'
    with pytest.raises(ValueError):
        ConnectorDesired(expected_revision='a'*64, runner_id='win', settings={'serial_transport': 'invalid'})


@pytest.mark.parametrize('jobs,batches', [(['RUNNING'], []), (['UNKNOWN'], []), ([], ['RESERVED'])])
def test_local_save_cannot_bypass_guarded_migration(tmp_path, jobs, batches):
    before = profile(tmp_path)
    records(tmp_path, jobs=jobs, batches=batches)
    with pytest.raises(TestError, match='작업'):
        Settings(tmp_path).save({'serial_transport': 'proxy', 'board_names': {'board-1': 'A'}})
    assert Settings(tmp_path).read() == before


def test_distribution_includes_both_automatic_support_files():
    from scripts.build_connector_bundle import _source_files
    root = Path(__file__).resolve().parents[3]
    files = _source_files(root)
    for name in ('automatic_serial.py', 'serial_bootstrap.py', 'serial_proxy.py'):
        assert files['backend/gui_test/connector/' + name].is_file()
