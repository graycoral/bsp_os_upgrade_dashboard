"""Durable failure outbox and fail-closed remediation gate.

Analyzer output is advisory. Only an injected host verifier may attest remediation;
this module never evaluates commands from analysis text or starts another scheduler.
"""
import json
import re
import time
from contextlib import ExitStack
from typing import Annotated, Literal
from pydantic import Field
from .retention import snapshot_operation
from .models import StrictModel, StartRequest, TestError, digest, uid, now
from .repetition import record_result, slot_states

POLICY = 'fail-stop-analysis-v1'
LEGACY_POLICY = 'initial-pass-else-two-of-three-v1'
FAILURES = {'FAIL', 'ERROR', 'TIMEOUT', 'UNKNOWN'}
KIND = 'failure-analysis'


Reference = Annotated[str, Field(min_length=1, max_length=2048, pattern=r'^[^\x00-\x1f\x7f]+$')]


class AnalysisResult(StrictModel):
    base_revision: int = Field(strict=True, ge=1)
    cause_key: str = Field(min_length=1, max_length=160)
    cause_summary: str = Field(min_length=1, max_length=4000)
    remediation_summary: str = Field(max_length=4000)
    evidence_refs: list[Reference] = Field(min_length=1, max_length=100)
    remediation_refs: list[Reference] = Field(max_length=100)
    action: Literal['HOLD', 'RETRY', 'REPREPARE']


def normalized_cause(value):
    key = re.sub(r'[^a-z0-9]+', '-', value.casefold()).strip('-')
    if not key:
        raise TestError('Stable ASCII cause key required', 'ANALYSIS_INVALID', 422)
    return key


def policy(run):
    return run.get('execution_policy', run.get('integration', {}).get('retry_policy'))


def blocked(run):
    return bool(run.get('failure_analysis', {}).get('latched'))


def supported(run):
    saved = policy(run)
    return saved in {None, POLICY, LEGACY_POLICY}


class FailureAnalysis:
    def __init__(self, manager, verifier=None, *, clock=time.time):
        self.manager, self.verifier, self.clock = manager, verifier, clock

    @staticmethod
    def _write(c, item):
        c.execute('INSERT INTO documents VALUES(?,?,?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data',
                  (KIND, item['id'], json.dumps(item)))

    def _read(self, c, identity):
        row = c.execute('SELECT data FROM documents WHERE kind=? AND name=?', (KIND, identity)).fetchone()
        if not row:
            raise TestError('Analysis not found', 'NOT_FOUND', 404)
        return json.loads(row[0])

    def enqueue(self, c, run, *, attempt=None, phase='TC'):
        """Called before Store.save in the SAME transaction as the failure."""
        if policy(run) != POLICY or blocked(run):
            return
        chain = run.setdefault('retry_chain', {'id': uid(), 'automatic_retries': 0, 'causes': []})
        revision = run['version'] + 1
        identity = digest({'run': run['id'], 'attempt': attempt['id'] if attempt else None,
                           'phase': phase, 'revision': revision})
        refs = [f"run:{run['id']}:revision:{revision}"]
        if attempt:
            refs.append(f"attempt:{attempt['id']}")
        item = {'id': identity, 'run_id': run['id'], 'chain_id': chain['id'], 'phase': phase,
                'attempt_id': attempt['id'] if attempt else None, 'evidence_revision': revision,
                'controller': run['controller'], 'status': 'PENDING', 'created_at': now(),
                'evidence_refs': refs, 'deliveries': 0}
        self._write(c, item)
        run['failure_analysis'] = {'request_id': identity, 'status': 'PENDING', 'latched': True,
                                   'evidence_revision': revision, 'reason': 'Failure analysis required'}
        run.update(overall_result='INCOMPLETE', environment_ready=False)
        if run['state'] not in {'UNKNOWN', 'CANCEL_REQUESTED', 'PAUSE_REQUESTED', 'CANCELLED'}:
            run['state'] = 'PAUSED'

    def refresh(self, c, run):
        """New physical evidence supersedes the leased revision without losing its latch."""
        if not blocked(run):
            return
        old = self._read(c, run['failure_analysis']['request_id'])
        if old['status'] in {'STOPPED', 'CHILD_CREATED'}:
            return
        old['status'] = 'SUPERSEDED'
        self._write(c, old)
        attempt = next((a for a in run['attempts'] if a['id'] == old['attempt_id']), None)
        run['failure_analysis']['latched'] = False
        self.enqueue(c, run, attempt=attempt, phase=old['phase'])

    @staticmethod
    def _authorized(run, principal):
        return run['controller'] == principal or not run.get('integration')

    def list(self, principal):
        # Ownership follows the current Run controller; transfer invalidates old work.
        result = []
        for item in self.manager.store.documents(KIND):
            run = self.manager.store.snapshot(item['run_id'])
            if self._authorized(run, principal):
                result.append(self.public(item))
        return result

    @staticmethod
    def public(item):
        return {k: v for k, v in item.items() if k not in {'lease_token', 'submission_hash', 'name'}}

    def get(self, identity, principal):
        with self.manager.store.connection() as c:
            item = self._read(c, identity)
            if not self._authorized(self.manager.store.get(c, item['run_id']), principal):
                raise TestError('Controller required', 'CONTROL_REQUIRED', 403)
            return self.public(item)

    def claim(self, principal, consumer, lease_seconds=60):
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', consumer) or type(lease_seconds) is not int or not 1 <= lease_seconds <= 600:
            raise TestError('Invalid analysis lease', 'ANALYSIS_INVALID', 422)
        with self.manager.store.transaction() as c:
            rows = c.execute('SELECT data FROM documents WHERE kind=? ORDER BY rowid', (KIND,)).fetchall()
            for row in rows:
                item = json.loads(row[0])
                if item['status'] not in {'PENDING', 'LEASED'} or (item['status'] == 'LEASED' and item['lease_until'] > self.clock()):
                    continue
                run = self.manager.store.get(c, item['run_id'])
                if not self._authorized(run, principal):
                    continue
                if run['controller'] != item['controller'] or run['version'] != item['evidence_revision'] or run['state'] in {'CANCELLED', 'CANCEL_REQUESTED', 'PAUSE_REQUESTED'}:
                    item.update(status='STALE', reason='Run control changed')
                    self._write(c, item)
                    continue
                token = uid()
                item.update(status='LEASED', consumer=consumer, lease_token=token,
                            lease_until=self.clock() + lease_seconds, deliveries=item['deliveries'] + 1)
                self._write(c, item)
                # Claim does not change Run version, preserving the evidence CAS.
                run['failure_analysis']['status'] = 'LEASED'
                c.execute('UPDATE runs SET data=? WHERE id=?', (json.dumps(run), run['id']))
                return self.public(item) | {'lease_token': token,
                    'run': self.manager.decorate(run)}
        return None

    def requeue(self, identity, principal, expected_version):
        with self.manager.store.transaction() as c:
            item = self._read(c, identity)
            run = self.manager.store.get(c, item['run_id'])
            if not self._authorized(run, principal):
                raise TestError('Controller required', 'CONTROL_REQUIRED', 403)
            if run['version'] != expected_version:
                raise TestError('Run changed', 'VERSION_CONFLICT')
            if not blocked(run) or run['state'] in {'CANCELLED', 'CANCEL_REQUESTED', 'PAUSE_REQUESTED'} or item['id'] != run['failure_analysis']['request_id']:
                raise TestError('No current failure available for analysis', 'ANALYSIS_STALE')
            if item['status'] == 'STOPPED' or run.get('child_run_id'):
                raise TestError('Retry chain stopped', 'ANALYSIS_STOPPED')
            if run.get('analysis_manual_hold') and run['controller'] != principal:
                raise TestError('Only the controller can release a manual analysis hold', 'CONTROL_REQUIRED', 403)
            # Explicit requeue lifts only the user's pause; remediation still gates execution.
            run.pop('analysis_manual_hold', None)
            item.update(status='SUPERSEDED')
            self._write(c, item)
            attempt = next((a for a in run['attempts'] if a['id'] == item['attempt_id']), None)
            run['failure_analysis']['latched'] = False
            self.enqueue(c, run, attempt=attempt, phase=item['phase'])
            self.manager.store.save(c, run, 'FAILURE_ANALYSIS_REQUEUED')
            return self.public(self._read(c, run['failure_analysis']['request_id']))

    @snapshot_operation
    def submit(self, identity, principal, token, result):
        value = AnalysisResult.model_validate(result).model_dump()
        value['cause_key'] = normalized_cause(value['cause_key'])
        submission_hash = digest(value)
        # Potential host I/O must run outside SQLite's exclusive transaction.
        with self.manager.store.connection() as c:
            initial = self._read(c, identity)
            snapshot = self.manager.store.get(c, initial['run_id'])
        if not self._authorized(snapshot, principal):
            raise TestError('Controller required', 'CONTROL_REQUIRED', 403)
        proof = None
        if (initial.get('lease_token') == token and initial.get('status') == 'LEASED' and
                initial.get('lease_until', 0) > self.clock() and self.verifier and value['action'] != 'HOLD'):
            try:
                proof = self.verifier(self.manager.decorate(snapshot), self.public(initial), value)
            except Exception:
                proof = None
        prepared_child = child_acceptance = None
        if value['action'] == 'REPREPARE' and isinstance(proof, dict):
            try:
                prepared_child, child_acceptance = self._prepare_child(snapshot, proof)
            except (TestError, ValueError, TypeError, KeyError):
                prepared_child = None
        with self.manager.store.transaction() as c, ExitStack() as acceptance:
            item = self._read(c, identity)
            run = self.manager.store.get(c, item['run_id'])
            if not self._authorized(run, principal):
                raise TestError('Controller required', 'CONTROL_REQUIRED', 403)
            if item.get('submission_hash') == submission_hash and item.get('lease_token') == token:
                return self.public(item)
            if item.get('status') != 'LEASED' or item.get('lease_token') != token or item.get('lease_until', 0) <= self.clock():
                raise TestError('Analysis lease expired or superseded', 'ANALYSIS_LEASE_CONFLICT')
            if (value['base_revision'] != item['evidence_revision'] or run['version'] != item['evidence_revision'] or run['controller'] != item['controller'] or
                    run['state'] in {'CANCELLED', 'CANCEL_REQUESTED', 'PAUSE_REQUESTED'} or
                    run.get('integration', {}).get('cancel_requested')):
                raise TestError('Run changed after failure; analysis is stale', 'ANALYSIS_STALE')
            if any(ref not in item['evidence_refs'] for ref in value['evidence_refs']):
                raise TestError('Evidence does not belong to this failure', 'ANALYSIS_EVIDENCE_INVALID', 422)
            item.update(result=value, submission_hash=submission_hash, completed_at=now(), status='HOLD')
            latch = run['failure_analysis']
            latch.update(status='HOLD', cause_key=value['cause_key'], reason='Remediation requires trusted verification')
            chain = run['retry_chain']
            if value['cause_key'] in chain['causes'] or chain['automatic_retries'] >= 3:
                item['status'] = latch['status'] = 'STOPPED'
                latch['reason'] = 'Same cause recurred' if value['cause_key'] in chain['causes'] else 'Automatic retry chain limit reached'
            elif value['action'] == 'RETRY' and self._verified(c, run, item, value, proof):
                if run.get('module_context'):
                    acceptance.enter_context(self.manager.module_selection_service.guard(self.manager,
                        run['module_context'], {'revision': run['source_revision'], 'tests': run['tests']},
                        [test['id'] for test in run['tests']]))
                chain['causes'].append(value['cause_key'])
                chain['automatic_retries'] += 1
                latch.update(status='RETRY_READY', latched=False, reason='Trusted remediation and execution conditions verified')
                item['status'] = 'RETRY_READY'
                run.update(state='QUEUED', environment_ready=True, reason='')
                # Preserve the failed raw Attempt. Only the logical failed slot is retried.
                if item['attempt_id']:
                    previous = next(a for a in run['attempts'] if a['id'] == item['attempt_id'])
                    record_result(run, previous, 'PENDING')
            elif value['action'] == 'REPREPARE':
                latch['reason'] = 'Changed inputs require verified new preparation and release of the old batch'
                if prepared_child and self._verified(c, run, item, value, proof, changed=True):
                    if prepared_child.get('module_context'):
                        acceptance.enter_context(self.manager.module_selection_service.retry_guard(
                            self.manager, run['module_context'], prepared_child['module_context'],
                            child_acceptance['catalog'], [test['id'] for test in prepared_child['tests']]))
                    chain['causes'].append(value['cause_key'])
                    chain['automatic_retries'] += 1
                    child = self._commit_child(c, run, prepared_child, proof)
                    item['status'] = 'CHILD_CREATED'
                    item['child_run_id'] = child['id']
                    latch.update(status='CHILD_CREATED', child_run_id=child['id'], reason='New inputs prepared; retry continues in child Run')
            item['reason'] = latch['reason']
            self._write(c, item)
            self.manager.store.save(c, run, 'FAILURE_ANALYSIS_' + item['status'])
            if (item['status'] == 'CHILD_CREATED' and prepared_child.get('module_context')) or (item['status'] == 'RETRY_READY' and run.get('module_context')):
                # The BSP writer lock protects the complete GUI acceptance receipt.
                c.commit()
            return self.public(item)

    def _verified(self, c, run, item, value, proof, changed=False):
        if not value['remediation_refs'] or not isinstance(proof, dict):
            return False
        expected = {'run_id': run['id'], 'evidence_revision': item['evidence_revision'],
                    'source_revision': run['source_revision'],
                    'command_revision': run['command_snapshot']['revision'],
                    'runner_id': run.get('runner_id_snapshot', run.get('integration', {}).get('config', {}).get('runner_id')),
                    'remediation_refs': value['remediation_refs']}
        if any(proof.get(k) != v for k, v in expected.items()) or any(proof.get(k) is not True for k in ('remediation_verified', 'process_stopped', 'board_ready')):
            return False
        if not changed and proof.get('inputs_unchanged') is not True:
            return False
        if changed and proof.get('inputs_unchanged') is not False and not (item['attempt_id'] is None and proof.get('inputs_unchanged') is True):
            return False
        if run.get('child_run_id'):
            return False
        if changed and run.get('integration', {}).get('batch') and not run['integration'].get('batch_released'):
            batch, release = run['integration']['batch'], proof.get('batch_release_receipt', {})
            if (release.get('state') != 'RELEASED' or release.get('batch_id', release.get('id')) != batch.get('batch_id', batch.get('id')) or
                    any(release.get(k) != batch[k] for k in ('epoch', 'runner_id') if k in batch)):
                return False
        if run['state'] == 'UNKNOWN' or any(a['state'] in {'UNKNOWN', 'RUNNING'} or not a.get('terminated') for a in run['attempts']):
            return False
        # An ordinary claim can fail its readiness check before creating an Attempt.
        # Its pending slot remains accepted and reserved; integration preparation
        # still requires the normal child preparation/flash path.
        preflight_retry = (not changed and not run.get('integration') and item['phase'] == 'PREFLIGHT' and
                           item['attempt_id'] is None and
                           0 <= run['index'] < len(run.get('plan', run['tests'])) and
                           slot_states(run)[run['index']] == 'PENDING')
        if not item['attempt_id'] and not changed and not preflight_retry:
            return False
        if run.get('analysis_manual_hold') or run.get('baseline_changed'):
            return False
        try:
            status = self.manager.runner.readiness()
            if not status.get('ready') or (not self.manager.simulation and status.get('runner_id') != expected['runner_id']):
                return False
            self.manager.boards.verify(run['connection_snapshot'], any(t['kind'] == 'Dual' for t in run['tests']))
            if run['link']:
                self.manager.dashboard.validate(run['link'])
            if not changed and run.get('module_context'):
                if self.manager.module_selection_service is None:
                    return False
                self.manager.module_selection_service.validate(self.manager, run['module_context'],
                    {'revision': run['source_revision'], 'tests': run['tests']}, [test['id'] for test in run['tests']])
            resources = self.manager.resources(run['connection_snapshot'], any(t['kind'] == 'Dual' for t in run['tests']))
            if not item['attempt_id'] and not preflight_retry:
                return all(not c.execute('SELECT 1 FROM reservations WHERE resource=? AND run_id<>?', (r, run['id'])).fetchone() for r in resources)
            return all(c.execute('SELECT 1 FROM reservations WHERE resource=? AND run_id=? AND token=?',
                                 (r, run['id'], run['lease_token'])).fetchone() for r in resources)
        except TestError:
            return False

    def _prepare_child(self, parent, proof):
        """Normal source/config/command/timeout preparation, never hardware execution."""
        checked = None
        child = json.loads(json.dumps(parent))
        child.update(id=uid(), version=0, created_at=now(), started_at=None, ended_at=None,
                     state='QUEUED', overall_result='INCOMPLETE', attempts=[], results={}, slot_results={}, index=0,
                     parent_run_id=parent['id'], lease_token=uid(), reason='', control_request=None,
                     controller_seen_at=now(), sync={'status': 'NOT_LINKED'})
        for key in ('failure_analysis', 'child_run_id', 'baseline_changed', 'updated_at'):
            child.pop(key, None)
        if parent.get('integration'):
            service = self.manager.integration
            req = service.request_value(proof['retry_request'])
            if req['tc_patterns'] != parent['integration']['request']['tc_patterns'] or req.get('prepared_token'):
                raise TestError('Retry must preserve the complete selected TC pattern sequence', 'ANALYSIS_INVALID')
            config = service.acceptance_config()
            timeouts = self.manager.timeouts.read()
            receipt = service.preparer(req, config)
            from .integration import select_patterns, CONTRACT_VERSION
            catalog = self.manager.timeouts.apply(receipt['catalog'], timeouts)
            tests = select_patterns(catalog, req['tc_patterns'])
            child.update(connection_snapshot=config['connection'], command_snapshot=config['command_snapshot'],
                         tests=tests, plan=[], source_revision='', metadata_revision='', environment_ready=False,
                         timeout_settings_snapshot=timeouts, timeout_override=catalog.get('timeout_settings_active', False))
            child['integration'] = {'contract_version': CONTRACT_VERSION, 'request_hash': digest(req),
                'config_revision': config['config_revision'], 'config': config, 'principal': parent['controller'],
                'request': req, 'retry_policy': POLICY, 'phase': 'PREPARING', 'preparation_id': None, 'receipt': receipt}
        else:
            req = StartRequest.model_validate(proof['retry_request'])
            if bool(parent.get('module_context')) != (req.module_context is not None):
                raise TestError('Retry must preserve its BSP module binding', 'MODULE_CONTEXT_CHANGED')
            if req.tc_ids != [t['id'] for t in parent['tests']] or req.tc_repeats != parent['tc_repeats'] or req.cycles != parent['cycles']:
                raise TestError('Retry must preserve the complete selected TC sequence and repetitions', 'ANALYSIS_INVALID')
            checked = self.manager.preflight(req.model_dump())
            if req.module_context is not None:
                service = self.manager.module_selection_service
                if not callable(getattr(service, 'validate_retry', None)) or not callable(getattr(service, 'retry_guard', None)):
                    raise TestError('Host module retry acceptance is unavailable', 'MODULE_CONTEXT_UNAVAILABLE')
                service.validate_retry(self.manager, parent['module_context'], req.module_context.model_dump(),
                                       checked['catalog'], req.tc_ids)
                child['module_context'] = req.module_context.model_dump()
            if checked['link'] != parent.get('link'):
                raise TestError('Changed-input retry must preserve the BSP job gate', 'ANALYSIS_INVALID')
            from .repetition import execution_plan
            child.update(source_revision=req.source_revision, metadata_revision=checked['catalog']['metadata_revision'],
                         suite_revision=req.suite_revision, connection_snapshot=req.connection.model_dump(),
                         command_snapshot=checked['command_snapshot'], tests=checked['tests'],
                         plan=execution_plan(checked['tests'], req.tc_repeats, req.cycles),
                         timeout_settings_snapshot=checked['timeout_settings_snapshot'],
                         timeout_override=checked['timeout_override'], environment_ready=True,
                         link=checked['link'], runner_id_snapshot=checked.get('runner_id_snapshot'))
            child.pop('source_snapshot', None)
            if checked.get('source_snapshot'):
                child['source_snapshot'] = checked['source_snapshot']

        if parent['attempts'] and self._inputs(parent) == self._inputs(child):
            raise TestError('Unchanged TC inputs require a new Attempt in the failed slot', 'ANALYSIS_INVALID')
        return child, checked

    @staticmethod
    def _inputs(run):
        meta = run.get('integration', {})
        return digest({'source': meta.get('receipt', {}).get('source_snapshot', run.get('source_snapshot', run['source_revision'])),
                       'installer': meta.get('receipt', {}).get('installer_snapshot'),
                       'request': meta.get('request'), 'config': meta.get('config'),
                       'connection': run['connection_snapshot'], 'command': run['command_snapshot'],
                       'timeout': run.get('timeout_settings_snapshot')})

    def _commit_child(self, c, parent, child, proof):
        self.manager.timeouts.require_revision(child['timeout_settings_snapshot']['revision'], c)
        if child.get('integration'):
            if self.manager.integration.frozen_config()['config_revision'] != child['integration']['config_revision']:
                raise TestError('Configuration changed during child preparation', 'CONFIG_CHANGED')
        else:
            active = self.manager.sources.state(c)
            frozen = child.get('source_snapshot')
            if ((frozen is None and active['active']['kind'] != 'legacy') or
                    (frozen is not None and (active['version'] != frozen['version'] or
                     active['active']['source_revision'] != frozen['source_revision']))):
                raise TestError('Source selection changed during child preparation', 'SOURCE_CHANGED')
            command = child['command_snapshot']
            current_command = self.manager.command_snapshot(command['name'], command['revision'] if command['name'] else '')
            if current_command != command:
                raise TestError('Command changed during child preparation', 'COMMAND_CHANGED')
        resources = self.manager.resources(child['connection_snapshot'], any(t['kind'] == 'Dual' for t in child['tests']))
        if any(c.execute('SELECT 1 FROM reservations WHERE resource=? AND run_id<>?', (resource, parent['id'])).fetchone() for resource in resources):
            raise TestError('Child board/COM reserved elsewhere', 'RESERVATION_CONFLICT')
        c.execute('DELETE FROM reservations WHERE run_id=? AND token=?', (parent['id'], parent['lease_token']))
        for resource in resources:
            c.execute('INSERT INTO reservations VALUES(?,?,?)', (resource, child['id'], child['lease_token']))
        if parent.get('integration', {}).get('batch'):
            parent['integration']['batch_released'] = True
            release = proof.get('batch_release_receipt', {})
            parent['integration']['finalization_receipt'] = {k: release[k] for k in ('id', 'batch_id', 'state', 'epoch', 'runner_id') if k in release}
        child['retry_chain'] = json.loads(json.dumps(parent['retry_chain']))
        parent['child_run_id'] = child['id']
        self.manager.store.save(c, child, 'FAILURE_ANALYSIS_CHILD_CREATED', {'parent_run_id': parent['id']})
        return child
