"""BSP plugin contract over the existing GUI Run engine.

Acceptance freezes configuration, not producer bytes. Only the worker prepares
immutable trees and the Windows parent reservation; no API request touches COM.
"""
import fnmatch
import hashlib
import hmac
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import time

from pydantic import Field, model_validator
from .retention import snapshot_operation
from .models import StrictModel, Connection, TestError, digest, uid, now
from .discovery import select
from .repetition import execution_plan
from .failure_analysis import POLICY, blocked, supported
from ..adapters.runner import resolve_argv, validate_windows_command

CONTRACT_VERSION = 'bsp-upgrade-integration-v1'
RETRY_POLICY = POLICY


def validate_patterns(patterns):
    if not isinstance(patterns, list) or not 1 <= len(patterns) <= 100:
        raise TestError('Provide 1 to 100 TC patterns', 'PATTERN_INVALID', 422)
    for pattern in patterns:
        if (not isinstance(pattern, str) or not 1 <= len(pattern) <= 1024 or
                pattern.startswith('/') or '\\' in pattern or ':' in pattern or
                any(part in {'', '.', '..'} for part in pattern.split('/')) or
                any(ord(c) < 32 or ord(c) == 127 for c in pattern) or
                any(c in pattern for c in ('$','`','~','{','}',';','|','&','<','>'))):
            raise TestError('TC patterns must be safe root-relative POSIX globs', 'PATTERN_INVALID', 422)
    return list(patterns)


def resolve_patterns(module_key, module_defaults, global_defaults, override=None):
    value = override if override is not None else module_defaults[module_key] if module_key in module_defaults else global_defaults
    return validate_patterns(value)


def _matches(path, pattern):
    # Unlike fnmatch(path, pattern), * must not cross a slash. ** may match zero
    # or more full path components, including a root-level test.
    parts, globs = path.split('/'), pattern.split('/')
    reachable = {0}
    for pattern_part in globs:
        if pattern_part == '**':
            reachable = set(range(min(reachable), len(parts) + 1)) if reachable else set()
        else:
            reachable = {index + 1 for index in reachable if index < len(parts) and fnmatch.fnmatchcase(parts[index], pattern_part)}
    return len(parts) in reachable


def select_patterns(catalog, patterns):
    patterns = validate_patterns(patterns)
    selected = {t['id']: t for t in catalog['tests'] if any(_matches(t['path'], p) for p in patterns)}
    if not selected or len(selected) > 500:
        raise TestError('TC patterns must select 1 to 500 catalog tests', 'TC_SELECTION', 422)
    ordered, pending = [], list(selected)
    while pending:
        ready = [identity for identity in pending if all(dep in ordered for dep in selected[identity].get('after', []))]
        if not ready:
            raise TestError('Selected TC predecessor is missing or cyclic', 'TC_SELECTION', 422)
        ordered.extend(ready)
        pending = [identity for identity in pending if identity not in ready]
    return select(catalog, ordered)


class IntegrationRequest(StrictModel):
    installer_path: str = Field(min_length=1, max_length=4096)
    tc_patterns: list[str] = Field(min_length=1, max_length=100)
    prepared_token: str | None = Field(default=None, min_length=32, max_length=256)

    @model_validator(mode='after')
    def safe(self):
        if not self.installer_path.startswith('/') or '\\' in self.installer_path or any(ord(c) < 32 for c in self.installer_path):
            raise ValueError('Installer must be an absolute Linux BAT path')
        if PurePosixPath(self.installer_path).suffix.lower() != '.bat' or '..' in self.installer_path.split('/'):
            raise ValueError('Installer must identify a BAT without traversal')
        validate_patterns(self.tc_patterns)
        return self


class IntegrationService:
    def __init__(self, manager, config, *, clock=time.time, preparer=None, controller_resolver=None):
        self.manager, self.config, self.clock = manager, config, clock
        self.preparer = preparer or self._prepare
        # An injected host may explicitly resolve authenticated control identities.
        # The bundled one-principal service supports no arbitrary target handoff.
        self.controller_resolver = controller_resolver
        manager.integration = self
        with manager.store.transaction() as c:
            c.execute("INSERT OR IGNORE INTO meta VALUES('integration_token_key',?)", (secrets.token_hex(32),))
            self._token_key = bytes.fromhex(c.execute("SELECT value FROM meta WHERE key='integration_token_key'").fetchone()[0])

    def _token_value(self, identity):
        return hmac.new(self._token_key, identity.encode(), hashlib.sha256).hexdigest()

    def _read(self, kind, identity, c=None):
        if c is None:
            with self.manager.store.connection() as connection:
                return self._read(kind, identity, connection)
        row = c.execute('SELECT data FROM documents WHERE kind=? AND name=?', (kind, identity)).fetchone()
        if row is None:
            raise TestError('Integration record not found', 'NOT_FOUND', 404)
        return json.loads(row[0])

    @staticmethod
    def _write(c, kind, identity, value):
        c.execute('INSERT INTO documents VALUES(?,?,?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data',
                  (kind, identity, json.dumps(value)))

    def frozen_config(self):
        # Credentials belong to the adapter environment, never to a Run or token.
        cfg = self.config() if callable(self.config) else self.config
        allowed = {'installer_roots', 'tc_root', 'connection', 'command_profile', 'command_revision',
                   'runner_id', 'flash_profile', 'flash_profile_revision', 'metadata', 'max_bundle_bytes', 'module_defaults', 'global_defaults'}
        value = json.loads(json.dumps({k: v for k, v in cfg.items() if k in allowed}))
        registry = getattr(self.manager.runner, 'registry', None)
        registration = registry.read() if registry is not None else None
        if registration:
            # Installation selects the registered connector; clients never copy COM/URL settings.
            if not value.get('runner_id'):
                value['runner_id'] = registration['runner_id']
            if not value.get('connection'):
                boards = registration['inventory']['boards']
                selected = [{k: b[k] for k in ('board_id','host','com','node') if k in b} for b in boards]
                if selected: value['connection'] = {'a':selected[0], 'b':selected[1] if len(selected)>1 else None}
        if not value.get('tc_root'):
            active = self.manager.sources.state()['active']
            if active['kind'] == 'server-folder': value['tc_root'] = active['location']
            elif active.get('snapshot_id'):
                value['tc_root'] = str(self.manager.sources.directory(self.manager.sources.descriptor()))
        required = ('installer_roots', 'tc_root', 'connection', 'command_profile', 'command_revision', 'runner_id', 'flash_profile')
        if any(not value.get(k) for k in required):
            raise TestError('Integration defaults are incomplete', 'INTEGRATION_NOT_CONFIGURED', 422)
        if not isinstance(value['installer_roots'], list) or any(not str(p).startswith('/') for p in value['installer_roots']) or not str(value['tc_root']).startswith('/'):
            raise TestError('Configure absolute Linux installer and TC roots', 'INTEGRATION_NOT_CONFIGURED', 422)
        value['connection'] = Connection.model_validate(value['connection']).model_dump()
        value['command_snapshot'] = self.manager.command_snapshot(value['command_profile'], value['command_revision'])
        if not self.manager.simulation:
            validate_windows_command(value['command_snapshot']['template'])
        value['retry_policy'] = POLICY
        value['config_revision'] = digest(value)
        return value

    def acceptance_config(self):
        """Read-only Runner profile probe, always outside the acceptance DB lock."""
        frozen = self.frozen_config()
        if self.manager.simulation:
            revision = frozen.get('flash_profile_revision') or digest({'simulation': True, 'profile': frozen['flash_profile']})
        else:
            probe = getattr(self.manager.runner, 'integration_profile', None)
            if probe is None:
                raise TestError('Runner cannot pin the registered flash profile', 'FLASH_PROFILE_UNSUPPORTED', 503)
            profile = probe(frozen['flash_profile'])
            revision = profile.get('revision') if isinstance(profile, dict) else None
            if not isinstance(revision, str) or not re.fullmatch('[a-f0-9]{64}', revision):
                raise TestError('Runner flash profile revision is invalid', 'FLASH_PROFILE_UNSUPPORTED', 503)
            if frozen.get('flash_profile_revision') not in {None, revision}:
                raise TestError('Registered flash profile changed', 'FLASH_PROFILE_CHANGED')
        frozen['flash_profile_revision'] = revision
        return frozen

    @staticmethod
    def base_request(request):
        return {k: request[k] for k in ('installer_path', 'tc_patterns')}

    @staticmethod
    def request_value(request):
        return IntegrationRequest.model_validate(request).model_dump(exclude_none=True)

    @snapshot_operation
    def preview(self, principal, request):
        req = self.request_value(request)
        if req.get('prepared_token'):
            raise TestError('Preview does not consume a prepared token', status=422)
        frozen = self.acceptance_config()
        item = {'preparation_id': uid(), 'principal': principal, 'request': req, 'request_hash': digest(req),
                'config': frozen, 'state': 'PREPARING', 'created_at': now(), 'reason': '',
                'timeout_settings_snapshot': self.manager.timeouts.read()}
        with self.manager.store.transaction() as c:
            self.manager.timeouts.require_revision(item['timeout_settings_snapshot']['revision'], c)
            self._write(c, 'integration-preparation', item['preparation_id'], item)
        return {'preparation_id': item['preparation_id'], 'state': item['state']}

    def preparation(self, identity, principal):
        item = self._read('integration-preparation', identity)
        if item['principal'] != principal:
            raise TestError('Preparation belongs to another principal', 'CONTROL_REQUIRED', 403)
        public = {k: item[k] for k in ('preparation_id', 'state', 'reason')}
        if item['state'] == 'READY':
            public.update(tests=item['receipt']['tests'], tc_ids=[t['id'] for t in item['receipt']['tests']],
                          catalog_revision=item['receipt']['catalog']['revision'], prepared_token=self._token_value(identity))
        return public

    @snapshot_operation
    def prepare_one(self):
        items = self.manager.store.documents('integration-preparation')
        item = next((v for v in items if v['state'] == 'PREPARING'), None)
        if item is None:
            return False
        try:
            receipt = self.preparer(item['request'], item['config'])
            catalog = self.manager.timeouts.apply(receipt['catalog'], item['timeout_settings_snapshot']) if item.get('timeout_settings_snapshot') else receipt['catalog']
            receipt['tests'] = select_patterns(catalog, item['request']['tc_patterns'])
            token = self._token_value(item['preparation_id'])
            item.update(state='READY', receipt=receipt, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                        expires_at=self.clock() + 1800, consumed_by=None)
        except Exception as exc:
            item.update(state='FAILED', reason=exc.code if isinstance(exc, TestError) else 'PREPARATION_FAILED')
        with self.manager.store.transaction() as c:
            self._write(c, 'integration-preparation', item['preparation_id'], {k: v for k, v in item.items() if k != 'name'})
        return True

    def _token(self, token, req, principal, frozen, c):
        hashed = hashlib.sha256(token.encode()).hexdigest()
        rows = c.execute("SELECT data FROM documents WHERE kind='integration-preparation'").fetchall()
        item = next((json.loads(r[0]) for r in rows if json.loads(r[0]).get('token_hash') == hashed), None)
        if (not item or item['state'] != 'READY' or item['principal'] != principal or
                item['request_hash'] != digest(self.base_request(req)) or item['config']['config_revision'] != frozen['config_revision'] or
                item['config'].get('flash_profile_revision') != frozen.get('flash_profile_revision') or
                self.clock() >= item['expires_at']):
            raise TestError('Prepared input is expired or does not match this request/configuration', 'PREPARED_TOKEN_STALE')
        if item['consumed_by']:
            raise TestError('Prepared token has already been consumed', 'PREPARED_TOKEN_USED')
        if item.get('timeout_settings_snapshot'):
            self.manager.timeouts.require_revision(item['timeout_settings_snapshot']['revision'], c)
        elif self.manager.timeouts.read(c)['default_seconds'] is not None or self.manager.timeouts.read(c)['overrides']:
            raise TestError('TC 제한시간이 변경되었습니다. 새 미리 보기를 준비하세요.', 'TC_TIMEOUT_CHANGED')
        return item

    @snapshot_operation
    def start(self, key, principal, request):
        # Manager.command reads the ledger BEFORE configuration, token or source
        # access and rechecks atomically inside the acceptance transaction.
        prepared_request = prepared_config = prepared_timeouts = None
        def prepare():
            nonlocal prepared_request, prepared_config, prepared_timeouts
            prepared_request = self.request_value(request)
            prepared_config = self.acceptance_config()
            prepared_timeouts = self.manager.timeouts.read()
            if not self.manager.simulation and (prepared_timeouts['default_seconds'] is not None or prepared_timeouts['overrides']):
                self.manager.runner.require_timeout_support()

        def operation(c):
            req, frozen = prepared_request, prepared_config
            self.manager.timeouts.require_revision(prepared_timeouts['revision'], c)
            if self.frozen_config()['config_revision'] != frozen['config_revision']:
                raise TestError('Integration configuration changed before acceptance', 'CONFIG_CHANGED')
            prepared = self._token(req['prepared_token'], req, principal, frozen, c) if req.get('prepared_token') else None
            identity = uid()
            run = {'id': identity, 'mode': self.manager.mode, 'simulation': self.manager.simulation,
                   'state': 'QUEUED', 'overall_result': 'INCOMPLETE', 'version': 0, 'created_at': now(),
                   'started_at': None, 'ended_at': None, 'source_revision': '', 'metadata_revision': '', 'suite_revision': '',
                   'connection_snapshot': frozen['connection'], 'command_snapshot': frozen['command_snapshot'],
                   'tests': [], 'tc_repeats': {}, 'cycles': 1, 'plan': [], 'slot_results': {}, 'results': {}, 'attempts': [], 'index': 0,
                   'controller': principal, 'controller_seen_at': now(), 'control_request': None, 'scenario': 'pass', 'speed': 1,
                   'injected_fault': None, 'environment_ready': False, 'link': None, 'sync': {'status': 'NOT_LINKED'},
                   'parent_run_id': None, 'lease_token': uid(), 'reason': '', 'execution_policy': POLICY,
                   'timeout_settings_snapshot': prepared_timeouts,
                   'integration': {'contract_version': CONTRACT_VERSION, 'request_hash': digest(req),
                       'config_revision': frozen['config_revision'], 'config': frozen, 'principal': principal,
                       'request': self.base_request(req), 'retry_policy': POLICY, 'phase': 'PREPARING',
                       'preparation_id': prepared['preparation_id'] if prepared else None}}
            if prepared:
                run['integration']['receipt'] = prepared['receipt']
                prepared['consumed_by'] = identity
                self._write(c, 'integration-preparation', prepared['preparation_id'], prepared)
            self.manager.store.save(c, run, 'INTEGRATION_ACCEPTED')
            return self.manager.decorate(run)
        return self.manager.command(key, {'principal': principal, 'integration_request': request}, operation, prepare=prepare)

    @snapshot_operation
    def prepare_run(self, run_id):
        run = self.manager.store.snapshot(run_id)
        meta = run.get('integration')
        if not meta or not supported(run) or blocked(run) or run['state'] != 'QUEUED' or meta['phase'] != 'PREPARING':
            return False
        try:
            receipt = meta.get('receipt') or self.preparer(meta['request'], meta['config'])
            catalog = self.manager.timeouts.apply(receipt['catalog'], run['timeout_settings_snapshot']) if run.get('timeout_settings_snapshot') else receipt['catalog']
            tests = select_patterns(catalog, meta['request']['tc_patterns'])
            for tc in tests:
                resolve_argv(run['command_snapshot']['template'][tc['kind'].lower()], tc, run['connection_snapshot'])
            resources = self.manager.resources(run['connection_snapshot'], any(t['kind'] == 'Dual' for t in tests))
            with self.manager.store.transaction() as c:
                current = self.manager.store.get(c, run_id)
                if current['state'] != 'QUEUED' or not supported(current) or blocked(current):
                    return False
                if any(c.execute('SELECT 1 FROM reservations WHERE resource=? AND run_id<>?', (r, run_id)).fetchone() for r in resources):
                    raise TestError('Board/COM already reserved', 'RESERVATION_CONFLICT')
                for resource in resources:
                    c.execute('INSERT OR IGNORE INTO reservations VALUES(?,?,?)', (resource, run_id, current['lease_token']))
                current.update(tests=tests, plan=execution_plan(tests, {}, 1), source_revision=receipt['catalog']['revision'],
                               metadata_revision=receipt['catalog']['metadata_revision'])
                current['timeout_override'] = catalog.get('timeout_settings_active', False)
                current['integration'].update(receipt=receipt, phase='FLASHING')
                # Durable request ID is committed BEFORE calling the Windows runner.
                self.manager.store.save(c, current, 'INTEGRATION_PREPARED')
                run = current
            result = self.manager.runner.begin_integration(receipt, {'run_id': run_id, 'connection': run['connection_snapshot'],
                'command_template': run['command_snapshot']['template'], 'config': meta['config'],
                'timeout_override': run.get('timeout_override', False),
                'save_batch': lambda batch: self.record_batch(run_id, batch)})
            self.record_batch(run_id, result)
        except Exception as exc:
            with self.manager.store.transaction() as c:
                current = self.manager.store.get(c, run_id)
                if current['state'] in {'COMPLETED', 'CANCELLED'}:
                    return True  # A late source failure cannot reopen a cancelled preparation.
                uncertain = current['integration']['phase'] != 'PREPARING'
                current.update(state='UNKNOWN' if uncertain else 'PAUSED', environment_ready=False,
                               reason=exc.code if isinstance(exc, TestError) else 'PREPARATION_FAILED')
                if getattr(exc, 'diagnostic', None):
                    current['integration']['diagnostic'] = exc.diagnostic
                current['integration']['phase'] = 'UNKNOWN' if uncertain else 'FAILED'
                self.manager.analysis.enqueue(c, current, phase=current['integration']['phase'])
                self.manager.store.save(c, current, 'INTEGRATION_BLOCKED')
        return True

    @staticmethod
    def _attempts_stopped(run):
        return all(attempt.get('terminated') is True and attempt['state'] not in {'RUNNING', 'UNKNOWN'}
                   for attempt in run['attempts'])

    @staticmethod
    def _failed_batch_stopped(receipt):
        return bool(receipt and receipt.get('state') in {'FAILED', 'DONE'} and
                    (receipt.get('terminated') is True or receipt.get('not_started') is True))

    def record_batch(self, run_id, result):
        with self.manager.store.transaction() as c:
            run = self.manager.store.get(c, run_id)
            meta = run['integration']
            if meta.get('batch') == result and not meta.get('cancel_requested'):
                return
            had_analysis_latch = blocked(run)
            meta['batch'] = result
            meta['batch_id'] = result.get('batch_id', result.get('id'))
            meta['phase'] = result.get('phase', result.get('state', 'UNKNOWN'))
            safe_cancel = (meta.get('cancel_requested') and self._attempts_stopped(run) and
                           (result.get('state') == 'READY' or self._failed_batch_stopped(result)))
            if safe_cancel:
                self.manager.end(c, run, 'CANCELLED')
                run['environment_ready'] = False
                if run['state'] == 'CANCELLED':
                    meta['phase'] = 'CANCELLED'
            elif result.get('state') == 'READY':
                # A verified preparation receipt can resolve a pre-TC transport
                # UNKNOWN. It is not termination evidence for an existing TC.
                pre_tc = not run['attempts']
                if pre_tc and blocked(run) and run['state'] == 'UNKNOWN':
                    run.update(state='PAUSED', environment_ready=False)
                if pre_tc and not blocked(run) and run['state'] not in {'COMPLETED', 'CANCELLED'}:
                    if run['state'] == 'UNKNOWN':
                        resume = meta.get('preparation_resume_state', 'QUEUED')
                        run['state'] = 'PAUSED' if resume in {'PAUSED', 'PAUSE_REQUESTED'} else 'QUEUED'
                        run['reason'] = ''
                    run['environment_ready'] = True
                    meta['phase'] = 'TESTING'
            elif result.get('state') == 'RUNNING':
                meta['phase'] = 'WAITING_BATCH'
                run['environment_ready'] = False
            elif result.get('state') == 'UNKNOWN':
                if not run['attempts'] and run['state'] in {'QUEUED', 'PAUSED', 'PAUSE_REQUESTED'}:
                    meta['preparation_resume_state'] = run['state']
                run.update(state='UNKNOWN', reason=result.get('reason', 'Batch preparation is unresolved'), environment_ready=False)
            else:
                run.update(state='UNKNOWN' if meta.get('cancel_requested') else 'PAUSED',
                           reason=result.get('reason', 'Batch preparation failed'), environment_ready=False)
            if result.get('state') not in {'READY', 'RUNNING'} and not meta.get('cancel_requested') and run['state'] not in {'COMPLETED', 'CANCELLED'}:
                self.manager.analysis.enqueue(c, run, phase=meta['phase'])
            if had_analysis_latch and not meta.get('cancel_requested'):
                self.manager.analysis.refresh(c, run)
            self.manager.store.save(c, run, 'INTEGRATION_BATCH_RECEIPT')
            cancelled = meta.get('cancel_requested') and result.get('state') == 'RUNNING'
        if cancelled:
            # The ownership receipt is durable, but a cancellation that raced
            # reservation must prevent the wrapper's next hardware command.
            raise TestError('Batch cancellation requested before preparation', 'BATCH_CANCELLED')

    def poll_batch(self, run_id):
        run = self.manager.store.snapshot(run_id)
        try:
            if run['integration'].get('cancel_requested') and run['integration'].get('batch'):
                self.manager.runner.cancel_batch(run['integration']['batch'])
            result = self.manager.runner.reconcile_integration(run_id, run['integration'].get('batch'))
        except Exception:
            result = {'state': 'UNKNOWN', 'phase': run['integration']['phase'], 'terminated': False,
                      'reason': 'RUNNER_UNAVAILABLE', **run['integration'].get('batch', {})}
            result['state'] = 'UNKNOWN'
        self.record_batch(run_id, result)

    def release_batch(self, run_id):
        run = self.manager.store.snapshot(run_id)
        batch = run['integration'].get('batch')
        if not batch or run['state'] not in {'COMPLETED', 'CANCELLED'} or run['integration'].get('batch_released'):
            return
        self.manager.runner.finish_integration(batch)
        with self.manager.store.transaction() as c:
            run = self.manager.store.get(c, run_id)
            run['integration']['batch_released'] = True
            self.manager.store.save(c, run, 'INTEGRATION_BATCH_RELEASED')

    def finalize_run(self, run_id):
        run = self.manager.store.snapshot(run_id)
        meta = run['integration']
        if not meta.get('pending_terminal_state') or meta.get('batch_released'):
            return False
        try:
            # Idempotent release returns the same positive receipt if the worker
            # died after remote finalization but before committing locally.
            proof = self.manager.runner.finish_integration(meta['batch'])
            batch = meta['batch']
            if (not isinstance(proof, dict) or proof.get('state') != 'RELEASED' or
                    proof.get('batch_id', proof.get('id')) != batch.get('batch_id', batch.get('id')) or
                    any(proof.get(key) != batch[key] for key in ('epoch', 'runner_id') if key in batch)):
                raise TestError('Final batch release receipt is not verified', 'FINALIZATION_UNCONFIRMED')
        except Exception as exc:
            with self.manager.store.transaction() as c:
                current = self.manager.store.get(c, run_id)
                current.update(state='UNKNOWN', environment_ready=False, overall_result='INCOMPLETE',
                               reason=exc.code if isinstance(exc, TestError) else 'FINALIZATION_UNCONFIRMED')
                current['integration']['phase'] = 'FINALIZING'
                retries = current['integration'].get('finalization_retries', 0) + 1
                current['integration'].update(finalization_retries=retries,
                    finalization_retry_at=self.clock() + min(30, 2 ** min(retries, 5)))
                if getattr(exc, 'diagnostic', None):
                    current['integration']['diagnostic'] = exc.diagnostic
                self.manager.store.save(c, current, 'INTEGRATION_FINALIZATION_UNCONFIRMED')
            return False
        with self.manager.store.transaction() as c:
            current = self.manager.store.get(c, run_id)
            meta = current['integration']
            meta['batch_released'] = True
            meta['finalization_receipt'] = {key: proof[key] for key in ('id', 'batch_id', 'state', 'epoch', 'runner_id', 'updated_at') if key in proof}
            target = 'CANCELLED' if meta.get('cancel_requested') else meta['pending_terminal_state']
            meta['phase'] = target
            current['reason'] = '' if target == 'CANCELLED' else meta.get('terminal_reason', '')
            self.manager.end(c, current, target)
            self.manager.store.save(c, current, 'INTEGRATION_FINALIZED')
        return True

    def act(self, run_id, key, principal, expected, action, data=None):
        data = data or {}
        if action == 'cancel':
            def operation(c):
                run = self.manager.store.get(c, run_id)
                if run['version'] != expected or run['controller'] != principal:
                    raise TestError('Controller/version changed', 'VERSION_CONFLICT')
                if run['state'] in {'COMPLETED', 'CANCELLED'}:
                    raise TestError('Finished run is immutable')
                run['integration']['cancel_requested'] = True
                meta = run['integration']
                no_hardware = (not meta.get('batch') and not run['attempts'] and
                               meta['phase'] in {'PREPARING', 'FAILED'})
                failed_stopped = self._failed_batch_stopped(meta.get('batch')) and self._attempts_stopped(run)
                if no_hardware or failed_stopped or (meta.get('batch_released') and self._attempts_stopped(run)):
                    self.manager.end(c, run, 'CANCELLED')
                    run['environment_ready'] = False
                    if run['state'] == 'CANCELLED':
                        meta['phase'] = 'CANCELLED'
                elif self.manager.active_attempt(run):
                    run['state'] = 'CANCEL_REQUESTED'
                elif run['environment_ready'] and self._attempts_stopped(run):
                    self.manager.end(c, run, 'CANCELLED')
                else:
                    # No child Attempt does not establish that BAT is stopped.
                    run.update(state='UNKNOWN', reason='Cancellation pending physical batch reconciliation')
                self.manager.store.save(c, run, 'INTEGRATION_CANCEL_REQUESTED')
                return self.manager.decorate(run)
            return self.manager.command(key, {'run_id': run_id, 'principal': principal, 'expected': expected, 'action': action}, operation)
        if action == 'transfer-control':
            target = data.get('controller')
            if not isinstance(target, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', target):
                raise TestError('Explicit target controller required', status=422)
            def operation(c):
                run = self.manager.store.get(c, run_id)
                if run['version'] != expected or run['controller'] != principal or data.get('expected_controller') != principal:
                    raise TestError('Controller/version changed', 'VERSION_CONFLICT')
                if target != principal and not (self.controller_resolver and self.controller_resolver(target) is True):
                    raise TestError('Target controller cannot authenticate through this host', 'CONTROL_TARGET_UNAVAILABLE', 422)
                run.update(controller=target, controller_seen_at=now(), control_request=None)
                self.manager.store.save(c, run, 'INTEGRATION_CONTROL_TRANSFERRED')
                return self.manager.decorate(run)
            return self.manager.command(key, {'run_id': run_id, 'principal': principal, 'expected': expected, 'action': action, 'data': data}, operation)
        if action == 'reconcile':
            # Record intent only; the worker owns network/hardware interaction.
            def operation(c):
                run = self.manager.store.get(c, run_id)
                if run['version'] != expected or run['controller'] != principal:
                    raise TestError('Controller/version changed', 'VERSION_CONFLICT')
                run['integration']['reconcile_requested'] = True
                if run['integration'].get('pending_terminal_state'):
                    run['integration']['finalization_retry_at'] = 0
                self.manager.store.save(c, run, 'INTEGRATION_RECONCILE_REQUESTED')
                return self.manager.decorate(run)
            return self.manager.command(key, {'run_id': run_id, 'principal': principal, 'expected': expected, 'action': action}, operation)
        if action not in {'pause', 'resume'}:
            raise TestError('Unsupported integration action', status=422)
        previous = self.manager.store.snapshot(run_id)
        if previous['integration']['phase'] == 'PREPARING':
            def operation(c):
                run = self.manager.store.get(c, run_id)
                if run['version'] != expected or run['controller'] != principal:
                    raise TestError('Controller/version changed', 'VERSION_CONFLICT')
                if run['integration']['phase'] != 'PREPARING' or run['state'] not in {'QUEUED', 'PAUSED'}:
                    raise TestError('Preparation phase changed', 'VERSION_CONFLICT')
                if action == 'resume' and blocked(run):
                    raise TestError('Failure analysis latch requires verified remediation', 'ANALYSIS_REQUIRED')
                if action == 'pause' and blocked(run):
                    run['analysis_manual_hold'] = True
                run['state'] = 'PAUSED' if action == 'pause' else 'QUEUED'
                self.manager.store.save(c, run, 'INTEGRATION_' + action.upper())
                return self.manager.decorate(run)
            return self.manager.command(key, {'run_id': run_id, 'principal': principal, 'expected': expected, 'action': action}, operation)
        return self.manager.act(run_id, key, principal, expected, action, data)

    def recover(self):
        for run in self.manager.store.all():
            meta = run.get('integration')
            if not meta or run['state'] in {'COMPLETED', 'CANCELLED'} or meta['phase'] == 'PREPARING':
                continue
            # Never begin again after the durable FLASHING boundary. The original
            # runner must reconcile/tombstone the same parent request first.
            try:
                result = self.manager.runner.reconcile_integration(run['id'], meta.get('batch'))
            except Exception:
                result = {'state': 'UNKNOWN', 'phase': meta['phase'], 'terminated': False, 'reason': 'RUNNER_UNAVAILABLE'}
            if self.manager.active_attempt(run):
                continue  # Manager.recover reconciles the existing child separately.
            self.record_batch(run['id'], result)

    def _prepare(self, request, config):
        # The disk-stream installer implementation and source snapshot rules are
        # shared with the authenticated Windows transport.
        from .integration_sources import prepare_inputs
        return prepare_inputs(request, config, self.manager.store.path.parent / 'integration-inputs')
