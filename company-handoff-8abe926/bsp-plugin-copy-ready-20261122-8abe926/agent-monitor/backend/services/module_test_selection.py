"""Read-only BSP module context for the independent GUI TC workspace."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

from backend.domain.policy import Conflict, gate
from backend.gui_test.core.discovery import select
from backend.gui_test.core.models import TestError
from backend.gui_test.core.module_selection import resolve_module_tests


class ModuleTestSelection:
    def __init__(self, engine, runtime):
        self.engine = engine
        self.configuration_path = Path(runtime) / 'device-test.json'
        self.configuration, self.configuration_revision, self.configuration_error = self._read_configuration()

    def _read_configuration(self):
        try:
            with self.configuration_path.open('rb') as source:
                raw = source.read(1024 * 1024 + 1)
            revision = hashlib.sha256(raw).hexdigest()
            if len(raw) > 1024 * 1024:
                return None, revision, '자동 장비 설정 파일의 크기 제한을 초과했습니다.'
            config = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(config, dict):
                return None, revision, '자동 장비 설정 형식을 확인하세요.'
            return config, revision, None
        except FileNotFoundError:
            return None, 'absent', None
        except (OSError, ValueError, UnicodeError):
            return None, 'unreadable', '자동 장비 설정을 읽을 수 없습니다.'

    def _profile(self, job, module):
        if job['execution'] != 'bridge':
            return None, None
        _, current_revision, current_error = self._read_configuration()
        if current_revision != self.configuration_revision or current_error:
            return {}, '자동 장비 설정이 변경되었거나 읽을 수 없습니다. API와 worker를 함께 재시작하세요.'
        if self.configuration_error:
            return {}, self.configuration_error
        config = self.configuration
        if config is None or config.get('enabled') is None or config.get('enabled') is False:
            return None, None
        if config.get('enabled') is not True or not isinstance(config.get('modules'), dict):
            return {}, '자동 장비 설정의 enabled/modules 형식을 확인하세요.'
        profile = config['modules'].get(module['name'])
        if profile is None:
            return None, None
        if not isinstance(profile, dict):
            return {}, '이 모듈의 자동 장비 프로파일 형식을 확인하세요.'
        if profile.get('enabled') is None or profile.get('enabled') is False:
            return None, None
        if profile.get('enabled') is not True:
            return {}, '이 모듈의 자동 장비 enabled 설정을 확인하세요.'
        return profile, None

    @staticmethod
    def _case_ids(cases, required):
        if (not isinstance(cases, dict) or not cases or set(cases) != set(required) or
                any(not isinstance(items, list) or not items or
                    any(not isinstance(identity, str) or not identity for identity in items)
                    for items in cases.values())):
            return None, '자동 프로파일에 모든 필수 사례의 TC 매핑이 필요합니다.'
        identities = list(dict.fromkeys(identity for items in cases.values() for identity in items))
        if len(identities) > 500:
            return None, '자동 프로파일의 TC 매핑은 최대 500개입니다.'
        return identities, None

    def _load(self, job_id, module_id):
        try:
            job = self.engine.snapshot(job_id)
            return job, self.engine.module(job, module_id)
        except Conflict as exc:
            raise TestError(exc.message, exc.code, exc.status) from None

    @staticmethod
    def _context(job, module, catalog_revision):
        attempts = module['stages']['device_test'].get('attempts', [])
        return {'job_id': job['id'], 'module_id': module['id'],
                'attempt_id': attempts[-1]['id'] if attempts else None,
                'plan_version': job['plan_version'], 'fingerprint': job['fingerprint'],
                'catalog_revision': catalog_revision}

    def _selection(self, manager, job, module, catalog, source_reason=None):
        stage = module['stages']['device_test']
        automation = stage.get('automation')
        frozen = automation is not None
        profile, profile_reason = (None, None) if frozen else self._profile(job, module)
        automatic = frozen or (profile is not None and stage['status'] in {'WAITING_INPUT', 'RUNNING', 'UNKNOWN', 'CANCEL_REQUESTED'})
        revision = catalog.get('revision', '')
        candidates = {'tests': [], 'tc_ids': [], 'blocked_reason': None}
        mapping_reason = None
        if frozen:
            payload = automation.get('payload') if isinstance(automation, dict) else None
            if (not isinstance(payload, dict) or not isinstance(payload.get('tests'), list) or
                    not isinstance(payload.get('source_revision'), str) or not payload['source_revision']):
                mapping_reason = '저장된 자동 시험 TC 구성을 확인하세요.'
            else:
                revision = payload['source_revision']
                ids, mapping_reason = self._case_ids(payload.get('cases'), stage['required_cases'])
                if ids is not None:
                    pinned = {'revision': revision, 'tests': payload['tests']}
                    candidates = resolve_module_tests(pinned, module['name'], ids)
                    if not candidates['blocked_reason'] and [test['id'] for test in payload['tests']] != candidates['tc_ids']:
                        mapping_reason = '저장된 자동 시험 TC 순서와 사례 매핑이 일치하지 않습니다.'
        elif source_reason is None and profile_reason is None:
            if automatic:
                ids, mapping_reason = self._case_ids(profile.get('cases'), stage['required_cases'])
                if ids is not None:
                    candidates = resolve_module_tests(catalog, module['name'], ids)
            else:
                candidates = resolve_module_tests(catalog, module['name'])

        attempts = stage.get('attempts', [])
        latest = attempts[-1] if attempts else None
        stage_reason = None
        if not frozen:
            if stage['status'] != 'WAITING_INPUT' or not latest or latest.get('status') != 'WAITING_INPUT':
                stage_reason = '현재 모듈의 장비 테스트 입력 대기 단계에서 TC를 준비할 수 있습니다.'
            elif latest.get('fingerprint') != job['fingerprint']:
                stage_reason = '모듈 시험 시도의 소스·계획 기준이 변경되었습니다.'
        blocked = source_reason or profile_reason or mapping_reason or candidates['blocked_reason']
        if automatic:
            blocked = blocked or '자동 퓨징·시험 프로파일이 이 모듈을 소유합니다. 일반 TC 실행으로 중복 시작할 수 없습니다.'
        else:
            blocked = blocked or stage_reason or gate(job, module, 'device_test')
        return {'context': self._context(job, module, revision), 'module_name': module['name'],
                'module_status': stage['status'], 'mode': 'automatic' if automatic else 'manual',
                'blocked_reason': blocked, 'tests': candidates['tests'], 'tc_ids': candidates['tc_ids'],
                'catalog_revision': revision, 'frozen': frozen}

    def select(self, manager, job_id, module_id, branch='demo/main', catalog_revision=''):
        if manager.mode != 'dashboard':
            raise TestError('단독 화면은 BSP 모듈 작업에 연결할 수 없습니다.', 'MODULE_CONTEXT_UNAVAILABLE', 422)
        job, module = self._load(job_id, module_id)
        stage = module['stages']['device_test']
        source_reason = None
        catalog = {'revision': catalog_revision, 'tests': []}
        if stage.get('automation') is None:
            if job['execution'] == 'bridge' and manager.simulation:
                source_reason = '실제 BSP 모듈의 TC를 조회하려면 Windows 실행기에 연결하세요. Mock TC로 대체하지 않습니다.'
            elif getattr(manager.runner, 'unavailable', False):
                source_reason = 'Windows 실행기가 연결되지 않았습니다.'
            else:
                try:
                    catalog = manager.catalog(branch)
                except TestError:
                    source_reason = 'TC 카탈로그를 조회할 수 없습니다. 실행기 연결과 소스 설정을 확인하세요.'
                if not isinstance(catalog, dict):
                    catalog = {'revision': catalog_revision, 'tests': []}
                    source_reason = 'TC 카탈로그 응답 형식을 확인하세요.'
                if source_reason is None and catalog.get('revision') != catalog_revision:
                    raise TestError('TC 카탈로그가 변경되었습니다. 새 목록을 조회하세요.', 'SOURCE_CHANGED')
        current, _ = self._load(job_id, module_id)
        if current['version'] != job['version']:
            raise TestError('TC 조회 중 BSP 작업이 변경되었습니다. 다시 조회하세요.', 'MODULE_CONTEXT_CHANGED')
        return self._selection(manager, job, module, catalog, source_reason)

    def _validate(self, manager, context, catalog, tc_ids, job, module):
        current = self._context(job, module, catalog.get('revision', ''))
        if current != context:
            raise TestError('모듈 시험 기준이 변경되었습니다. 모듈 TC를 다시 준비하세요.', 'MODULE_CONTEXT_CHANGED')
        if job['execution'] == 'bridge' and manager.simulation:
            raise TestError('실제 BSP 모듈에 Mock TC를 사용할 수 없습니다.', 'HARDWARE_NOT_CONFIGURED', 422)
        selected = self._selection(manager, job, module, catalog)
        if selected['mode'] == 'automatic':
            raise TestError(selected['blocked_reason'], 'AUTOMATIC_TEST_OWNED', 403)
        if selected['blocked_reason']:
            raise TestError(selected['blocked_reason'], 'MODULE_TEST_BLOCKED')
        if not tc_ids or any(identity not in set(selected['tc_ids']) for identity in tc_ids):
            raise TestError('선택한 TC가 현재 모듈 범위를 벗어났습니다.', 'MODULE_TC_MISMATCH', 422)
        select(catalog, tc_ids)
        return selected

    def validate(self, manager, context, catalog, tc_ids):
        if manager.mode != 'dashboard':
            raise TestError('단독 화면은 BSP 모듈 작업에 연결할 수 없습니다.', 'MODULE_CONTEXT_UNAVAILABLE', 422)
        job, module = self._load(context['job_id'], context['module_id'])
        return self._validate(manager, context, catalog, tc_ids, job, module)

    @staticmethod
    def _retry_binding(parent_context, context):
        # Remediation may advance the current BSP attempt/plan/source. The normal
        # gate must verify those new pins; analysis cannot switch job or module.
        for field in ('job_id', 'module_id'):
            if context.get(field) != parent_context.get(field):
                raise TestError('재시도는 원본 BSP 작업과 모듈 범위를 유지해야 합니다.', 'MODULE_CONTEXT_CHANGED')

    def validate_retry(self, manager, parent_context, context, catalog, tc_ids):
        self._retry_binding(parent_context, context)
        return self.validate(manager, context, catalog, tc_ids)

    @contextmanager
    def retry_guard(self, manager, parent_context, context, catalog, tc_ids):
        self._retry_binding(parent_context, context)
        with self.guard(manager, context, catalog, tc_ids):
            yield

    @contextmanager
    def guard(self, manager, context, catalog, tc_ids):
        # Network/catalog preparation is complete before taking the BSP writer
        # lock. Keep this fast check locked until the GUI run/ledger commits.
        with self.engine.store.transaction() as connection:
            try:
                job = self.engine.store.get(connection, context['job_id'])
                module = self.engine.module(job, context['module_id'])
            except Conflict as exc:
                raise TestError(exc.message, exc.code, exc.status) from None
            self._validate(manager, context, catalog, tc_ids, job, module)
            yield
