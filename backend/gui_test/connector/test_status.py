"""Read-only TC projection from the selected frozen source and Linux Run records.

No adapter calls, control leases, source selection, or scheduling belong here.
"""
import threading
import time

from ..core.models import TestError, now
from .paths import display_path


LABELS = {'PENDING': '대기 중', 'RUNNING': '진행 중', 'PASS': 'PASS', 'FAIL': 'FAIL',
          'ERROR': 'FAIL · 실행 오류', 'TIMEOUT': 'FAIL · 시간 초과',
          'UNKNOWN': '확인 필요', 'CANCELLED': '취소됨', 'NOT_SELECTED': '미선택',
          'NOT_RUN': '미실행'}


class TestStatus:
    __test__ = False

    def __init__(self, manager):
        self.manager = manager
        self.lock = threading.Lock()
        self.descriptor = None
        self.catalog = None
        self.checked = 0
        self.manifest = None
        self.catalog_checked_at = None

    def selection(self):
        shared = getattr(self.manager, 'shared_settings', None)
        config = shared.integration_config() if shared is not None else {}
        if config.get('tc_root'):
            return {'kind': 'integration-folder', 'location': config['tc_root'], 'metadata': config.get('metadata', {})}
        return self.manager.sources.descriptor()

    def acquire(self, descriptor):
        if descriptor['kind'] != 'integration-folder':
            self.manifest = None
            return self.manager.sources.catalog()
        from ..core.discovery import discover_contents
        from ..execution.source import read_source
        from ..execution.source_snapshots import manifest
        metadata = descriptor.get('metadata', {})
        if (not isinstance(metadata, dict) or any(not isinstance(value, dict) or
                ('id' in value and not isinstance(value['id'], str)) for value in metadata.values())):
            raise TestError('TC metadata entries must be objects with string identities', 'TC_METADATA_INVALID', 422)
        location = self.manager.sources.location('server-folder', descriptor['location'])
        files = read_source(location)
        value = manifest(files, {'kind': 'integration-folder', 'location': location}, descriptor['metadata'])
        # Match Path.read_text's universal-newline behavior in discover(), while
        # retaining original bytes for the execution snapshot identity.
        texts = {name: data.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
                 for name, data in files.items() if name.endswith('.py')}
        catalog = discover_contents(texts, descriptor['metadata'], value['source_revision'])
        self.manifest = value
        return catalog

    def snapshot(self, runner_id):
        manager = self.manager
        descriptor = self.selection()
        result = {'source': None, 'rows': [], 'checked_at': now(), 'stale': False,
                  'message': '공통 설정에서 서버 TC 경로를 선택하세요.'}
        if descriptor is None:
            return result  # Never query a legacy remote catalog or invent Mock TCs.
        result['source'] = {'location': display_path(descriptor['location']), 'kind': descriptor['kind']}
        try:
            with self.lock:
                if self.descriptor != descriptor or (descriptor['kind'] == 'integration-folder' and time.monotonic() - self.checked >= 10):
                    catalog = self.acquire(descriptor)
                    if self.selection() != descriptor:
                        raise TestError('TC 경로가 변경되었습니다. 다음 조회에서 갱신합니다.', 'SOURCE_CHANGED')
                    self.descriptor, self.catalog = descriptor, catalog
                    self.checked = time.monotonic()
                    self.catalog_checked_at = now()
                tests = self.catalog['tests']
                revision = self.catalog['revision']
                source_manifest = self.manifest
                result['source']['revision'] = revision
                result['source']['checked_at'] = self.catalog_checked_at
        except (TestError, OSError, UnicodeError) as exc:
            return result | {'stale': True, 'message': 'TC 목록을 확인할 수 없습니다. 서버 소스 설정을 확인하세요.',
                             'code': getattr(exc, 'code', 'SOURCE_UNAVAILABLE')}

        # A board's current Run takes precedence over its latest completed Run.
        # Source identity and runner pin prevent unrelated historical PASS leakage.
        runs = {}
        candidates = sorted(manager.store.all(), key=lambda run: (
            run['state'] not in {'COMPLETED', 'CANCELLED'}, run.get('created_at') or '', run['id']), reverse=True)
        for run in candidates:
            integration = run.get('integration') or {}
            pinned = run.get('runner_id_snapshot') or integration.get('config', {}).get('runner_id')
            if run.get('simulation') or not runner_id or pinned != runner_id:
                continue
            frozen = run.get('source_snapshot') or {}
            receipt = integration.get('receipt') or {}
            if descriptor['kind'] == 'integration-folder':
                matching = (integration.get('config', {}).get('tc_root') == descriptor['location'] and
                            run.get('source_revision') == revision and
                            receipt.get('source_snapshot', {}).get('snapshot_id') == (source_manifest or {}).get('snapshot_id'))
                # Dashboard Runs use a different manifest source identity. Compare
                # the full frozen file tree, never just a reused TC path/name.
                if not integration and frozen.get('location') == descriptor['location']:
                    from ..execution.source_snapshots import load_manifest
                    try:
                        frozen_manifest = load_manifest(manager.sources.directory(frozen), frozen['snapshot_id'])
                        matching = (frozen_manifest['files'] == source_manifest['files'] and
                                    frozen_manifest['metadata'] == source_manifest['metadata'] and
                                    run.get('source_revision') == frozen['source_revision'])
                    except (TestError, OSError, KeyError):
                        matching = False
            else:
                matching = (run.get('source_revision') == descriptor['source_revision'] and
                            frozen.get('snapshot_id') == descriptor['snapshot_id'] and
                            frozen.get('location') == descriptor['location'])
            if not matching:
                continue
            connection = run.get('connection_snapshot') or {}
            for slot in ('a', 'b'):
                if slot == 'b' and not any(test['kind'] == 'Dual' for test in run['tests']):
                    continue
                board = connection.get(slot)
                if board and board['board_id'] not in runs:
                    runs[board['board_id']] = (run, slot, {test['id']: test for test in run['tests']})

        for test in tests:
            row = {'id': display_path(test['id']), 'path': display_path(test['path']),
                   'name': display_path(test['name']), 'boards': {}}
            for board_id, (run, slot, selected_tests) in runs.items():
                selected = selected_tests.get(test['id'])
                if selected and selected.get('content_hash') != test.get('content_hash'):
                    selected = None
                selected = selected if slot == 'a' or (selected and selected['kind'] == 'Dual') else None
                state = run.get('results', {}).get(test['id'], 'PENDING') if selected else 'NOT_SELECTED'
                if state not in LABELS:
                    state = 'UNKNOWN'
                if selected and state == 'PENDING' and run['state'] in {'CANCELLED', 'UNKNOWN'}:
                    state = run['state']
                row['boards'][board_id] = {'state': state, 'label': LABELS[state],
                    'run_id': run['id'], 'run_state': run['state'],
                    'historical': run['state'] in {'COMPLETED', 'CANCELLED'}}
            result['rows'].append(row)
        if self.selection() != descriptor:
            return result | {'rows': [], 'stale': True, 'message': 'TC 경로가 변경되었습니다. 다음 조회에서 갱신합니다.'}
        return result | {'message': '' if tests else '선택한 경로에 테스트 스크립트가 없습니다.'}
