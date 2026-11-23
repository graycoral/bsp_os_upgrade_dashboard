"""TC observations cannot schedule, take control, or reuse another source's verdict."""
import os
from types import SimpleNamespace

import pytest

from backend.gui_test.connector.test_status import TestStatus
from backend.gui_test.core.sources import SourceService
from backend.gui_test.core.store import Store


@pytest.fixture
def rig(tmp_path):
    store = Store(tmp_path / 'runs.db')
    sources = SourceService(store)
    folder = tmp_path / 'tc'; folder.mkdir()
    for path in ('Single/pass.py', 'Single/fail.py', 'Single/running.py', 'Single/pending.py', 'Single/unused.py', 'Dual/link.py'):
        file = folder / path; file.parent.mkdir(exist_ok=True)
        file.write_text('raise RuntimeError("scripts must never be imported")\n')
    inspection = sources.inspect('server-folder', str(folder))
    sources.apply(inspection['inspection_id'], None, 0)
    manager = SimpleNamespace(store=store, sources=sources)
    return TestStatus(manager), manager


def run(manager, identity='run-one', **changes):
    tests = manager.sources.catalog()['tests']
    value = {'id': identity, 'version': 0, 'simulation': False, 'state': 'RUNNING',
             'created_at': '2026-11-17T01:00:00Z', 'source_revision': manager.sources.descriptor()['source_revision'],
             'source_snapshot': manager.sources.descriptor(), 'runner_id_snapshot': 'runner-one',
             'connection_snapshot': {'a': {'board_id': 'A'}, 'b': {'board_id': 'B'}},
             'tests': [test for test in tests if not test['path'].endswith('unused.py')],
             'results': {'Single/pass.py': 'PASS', 'Single/fail.py': 'FAIL', 'Single/running.py': 'RUNNING'},
             'attempts': []}
    value.update(changes)
    with manager.store.transaction() as connection:
        manager.store.save(connection, value, 'FIXTURE')
    return value


def indexed(projection):
    return {row['path']: row for row in projection['rows']}


def test_all_scripts_and_structured_states_without_writes_or_control(rig):
    projection, manager = rig
    run(manager)
    before = manager.store.all()
    value = projection.snapshot('runner-one'); rows = indexed(value)
    assert len(rows) == 6 and not value['stale']
    assert [rows['Single/' + name + '.py']['boards']['A']['state'] for name in ('pass', 'fail', 'running', 'pending', 'unused')] == [
        'PASS', 'FAIL', 'RUNNING', 'PENDING', 'NOT_SELECTED']
    assert rows['Dual/link.py']['boards']['B']['state'] == 'PENDING'
    assert rows['Single/pass.py']['boards']['B']['state'] == 'NOT_SELECTED'
    assert manager.store.all() == before
    with manager.store.connection() as connection:
        assert connection.execute('SELECT count(*) FROM reservations').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM commands').fetchone()[0] == 0


@pytest.mark.parametrize('changes', [
    {'simulation': True}, {'runner_id_snapshot': 'other-runner'}, {'source_revision': 'other-source'},
    {'source_snapshot': {'snapshot_id': 'other-snapshot', 'location': '/other'}},
])
def test_unrelated_run_cannot_supply_pass(rig, changes):
    projection, manager = rig; run(manager, **changes)
    assert all(not row['boards'] for row in projection.snapshot('runner-one')['rows'])


def test_source_switch_clears_previous_results_and_catalog_is_cached(rig, tmp_path, monkeypatch):
    projection, manager = rig; run(manager)
    original = manager.sources.catalog; calls = []
    def catalog():
        calls.append(True); return original()
    monkeypatch.setattr(manager.sources, 'catalog', catalog)
    projection.snapshot('runner-one'); projection.snapshot('runner-one')
    assert len(calls) == 1
    folder = tmp_path / 'new-tc'; folder.mkdir(); (folder / 'different.py').write_text('print("new")')
    inspection = manager.sources.inspect('server-folder', str(folder))
    manager.sources.apply(inspection['inspection_id'], None, 1)
    value = projection.snapshot('runner-one')
    assert list(indexed(value)) == ['different.py'] and not value['rows'][0]['boards']
    assert value['source']['location'] == str(folder)
    assert len(calls) == 2


def test_latest_run_per_board_and_running_run_precedes_history(rig):
    projection, manager = rig
    active = run(manager)
    run(manager, 'later-history', state='COMPLETED', created_at='2026-11-17T02:00:00Z', results={'Single/pass.py': 'FAIL'})
    assert indexed(projection.snapshot('runner-one'))['Single/pass.py']['boards']['A']['run_id'] == active['id']
    active['state'] = 'COMPLETED'
    with manager.store.transaction() as connection:
        manager.store.save(connection, active, 'FIXTURE')
    state = indexed(projection.snapshot('runner-one'))['Single/pass.py']['boards']['A']
    assert state['run_id'] == 'later-history' and state['state'] == 'FAIL' and state['historical']


def test_timeout_unknown_cancel_and_repetitions_keep_server_meaning(rig):
    projection, manager = rig
    run(manager, state='CANCELLED', results={'Single/pass.py': 'PENDING', 'Single/fail.py': 'TIMEOUT',
        'Single/running.py': 'UNKNOWN'}, attempts=[{'tc_id': 'Single/pass.py', 'state': 'PASS'}])
    rows = indexed(projection.snapshot('runner-one'))
    assert rows['Single/pass.py']['boards']['A']['state'] == 'CANCELLED'
    assert rows['Single/fail.py']['boards']['A']['label'] == 'FAIL · 시간 초과'
    assert rows['Single/running.py']['boards']['A']['label'] == '확인 필요'


def test_legacy_source_never_calls_remote_catalog(tmp_path):
    def forbidden(): raise AssertionError('remote catalog must not run')
    projection = TestStatus(SimpleNamespace(sources=SimpleNamespace(descriptor=lambda: None, catalog=forbidden)))
    assert projection.snapshot('runner-one')['rows'] == []


def test_plugin_configured_path_and_frozen_receipt_work_without_active_source(rig, tmp_path):
    from backend.gui_test.core.discovery import discover
    from backend.gui_test.execution.source import read_source
    from backend.gui_test.execution.source_snapshots import manifest
    projection, manager = rig
    folder = tmp_path / 'plugin-tc'; folder.mkdir(); (folder / 'plugin_test.py').write_bytes(b'raise RuntimeError("never import")\r\n')
    metadata = {}; config = {'tc_root': str(folder), 'runner_id': 'runner-one', 'metadata': metadata}
    manager.shared_settings = SimpleNamespace(integration_config=lambda: config)
    files = read_source(folder)
    frozen = manifest(files, {'kind': 'integration-folder', 'location': str(folder)}, metadata)
    catalog = discover(folder, metadata) | {'revision': frozen['source_revision']}
    run(manager, source_revision=catalog['revision'], tests=catalog['tests'], source_snapshot={},
        results={'plugin_test.py': 'PASS'}, integration={'config': config.copy(), 'receipt': {
            'catalog': catalog, 'source_snapshot': {'snapshot_id': frozen['snapshot_id'], 'source_revision': frozen['source_revision']}}})
    value = projection.snapshot('runner-one')
    assert value['source']['location'] == str(folder)
    assert value['rows'][0]['boards']['A']['state'] == 'PASS'
    (folder / 'plugin_test.py').write_text('print("changed source")')
    projection.checked -= 11
    assert not projection.snapshot('runner-one')['rows'][0]['boards']
    other = tmp_path / 'empty-tc'; other.mkdir(); config['tc_root'] = str(other)
    assert projection.snapshot('runner-one')['rows'] == []


def test_shared_path_matches_dashboard_full_frozen_tree_and_cannot_reuse_changed_dependencies(rig):
    projection, manager = rig; saved = run(manager)
    config = {'tc_root': saved['source_snapshot']['location'], 'metadata': {}}
    manager.shared_settings = SimpleNamespace(integration_config=lambda: config)
    assert indexed(projection.snapshot('runner-one'))['Single/pass.py']['boards']['A']['state'] == 'PASS'
    from pathlib import Path
    (Path(config['tc_root']) / 'dependency.json').write_text('{"changed": true}')
    projection.checked -= 11
    assert not indexed(projection.snapshot('runner-one'))['Single/pass.py']['boards']


def test_source_change_during_read_cannot_show_stale_pass(rig, monkeypatch):
    projection, manager = rig; run(manager)
    descriptor = manager.sources.descriptor(); changed = dict(descriptor, version=999)
    calls = []
    def selected():
        calls.append(True); return descriptor if len(calls) == 1 else changed
    monkeypatch.setattr(manager.sources, 'descriptor', selected)
    value = projection.snapshot('runner-one')
    assert value['stale'] and value['rows'] == []


def test_qt_status_table_is_read_only_and_switches_boards(tmp_path, monkeypatch):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication, QAbstractItemView
    from backend.gui_test.connector.gui import ConnectorWindow
    from backend.gui_test.connector.preview import MockConnector
    monkeypatch.setattr(ConnectorWindow, 'operation', lambda *args: None)
    app = QApplication.instance() or QApplication([])
    adapter = MockConnector(tmp_path); adapter.connect(); adapter.scenario = '시험 중'
    window = ConnectorWindow(adapter); window.timer.stop()
    try:
        window.render(adapter.status())
        assert window.tc_table.rowCount() == 5
        assert window.tc_table.editTriggers() == QAbstractItemView.NoEditTriggers
        assert window.tc_table.item(2, 1).text() == '진행 중'
        window.board_list.setCurrentRow(1)
        assert window.tc_table.item(2, 1).text() == '미실행'
        adapter.scenario = '확인 필요'; window.render(adapter.status())
        assert '과거 수신 정보' in window.tc_note.text()
    finally:
        window.close(); app.processEvents()


def test_manager_polls_read_only_tc_status_and_marks_lost_response_stale(tmp_path, monkeypatch):
    import httpx
    import time
    from backend.gui_test.connector.supervisor import Manager
    from backend.gui_test.execution import launch
    from backend.gui_test.connector import shared_control
    manager = Manager.__new__(Manager)
    manager.home = tmp_path; manager.settings = SimpleNamespace(read=lambda: {})
    manager.error = ''; manager.thread = None; manager.console_cursor = 0; manager.console_epoch = None
    manager.storage_cache = {}; manager.storage_checked = time.monotonic(); manager.cached = {}
    receipt = {'runner_id': 'runner', 'runner_url': 'http://127.0.0.1:1',
               'dashboard_url': 'http://127.0.0.1:2', 'phase': 'ssh_running', 'remote_runner_port': 3}
    monkeypatch.setattr(launch, 'read_active', lambda _: receipt)
    calls = []; lost = [False]
    def response(request):
        calls.append((request.method, request.url.path))
        path = request.url.path
        if path == '/v1/inventory':
            value = {'runner_id': 'runner', 'boards': [], 'checked_at': time.time(), 'host_busy': False, 'reserved': False}
        elif path == '/v1/console': value = {'boards': []}
        elif path == '/v1/recent-executions': value = {'executions': []}
        elif path.endswith('/register'): value = {'runner_id': 'runner'}
        elif path.endswith('/test-status'):
            if lost[0]: return httpx.Response(503)
            value = {'rows': [{'id': 'tc.py', 'path': 'tc.py', 'boards': {}}], 'source': {'location': '/tc'}, 'stale': False}
        else: raise AssertionError(path)
        return httpx.Response(200, json=value)
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **options: real_client(transport=httpx.MockTransport(response), **options))
    monkeypatch.setattr(shared_control, 'request', lambda *args: (_ for _ in ()).throw(RuntimeError('settings fixture unavailable')))
    manager.cached = manager.probe()
    assert manager.cached['test_status']['rows'][0]['path'] == 'tc.py'
    lost[0] = True
    status = manager.probe()
    assert status['state'] == 'CONNECTED'
    assert status['test_status']['stale'] and status['test_status']['rows'][0]['path'] == 'tc.py'
    assert '과거 수신 정보' in status['test_status']['message']
    assert set(method for method, path in calls if path.endswith('/test-status')) == {'GET'}


def test_unknown_run_does_not_look_like_queued_work(rig):
    projection, manager = rig
    run(manager, state='UNKNOWN', results={'Single/pass.py': 'PASS'})
    rows = indexed(projection.snapshot('runner-one'))
    assert rows['Single/pending.py']['boards']['A']['state'] == 'UNKNOWN'
    assert rows['Single/pass.py']['boards']['A']['state'] == 'PASS'
