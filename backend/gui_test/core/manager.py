import json
import re
import shlex
from contextlib import nullcontext
from pydantic import ValidationError
from datetime import datetime, timezone
from .models import TestError, StartRequest, Selection, Connection, TERMINAL, uid, now, digest
from .results import aggregate, progress, parse_result, PARSER_REVISION, module_results
from .discovery import select
from .repetition import execution_plan, record_result, slot_states
from .usage import normalize_usage, usage_summary
from .targets import normalize_target, target_summary
from .sources import SourceService
from .ports import DashboardPort
from ..catalog_settings import CatalogSettings
from ..adapters.mock import MockRunner
from ..adapters.runner import ExecutionAdapter, resolve_argv, default_command_template, validate_command_template, validate_windows_command


class Manager:
    def __init__(self, store, mode='standalone', dashboard: DashboardPort | None = None,
                 adapter: ExecutionAdapter | None = None, module_selection_service=None, catalog_settings=None):
        self.store, self.mode, self.dashboard = store, mode, dashboard
        self.catalog_settings = catalog_settings if catalog_settings is not None else CatalogSettings(store.path.parent / 'gui-test-settings.json')
        self.module_selection_service = module_selection_service
        self.sources = SourceService(store)
        self.runner: ExecutionAdapter = adapter if adapter is not None else MockRunner()
        self.boards = self.runner
        self.simulation = self.runner.simulation
        self.branches = self.runner.branches
        # Explicit demo-only limits. Production values must be supplied by an approved adapter.
        self.log_limit = 64 * 1024
        self.control_seconds = 60
        self.sync_retries = 2

    def catalog(self, branch='demo/main'):
        selected = self.sources.catalog()
        return selected if selected is not None else self.runner.catalog(branch)

    def current_catalog(self, revision):
        if self.sources.state()['active']['kind'] != 'legacy':
            catalog = self.sources.catalog()
            return catalog if catalog and catalog['revision'] == revision else None
        return next((c for c in (self.catalog(b) for b in self.branches) if c['revision'] == revision), None)

    def source_execution(self):
        status = self.runner.readiness()
        if not status['ready']:
            return {'ready': False, 'reason': status['message'], 'code': 'RUNNER_UNAVAILABLE'}
        if self.sources.state()['active']['kind'] != 'legacy' and status['capabilities'].get('source_snapshot_v1') is not True:
            return {'ready': False, 'reason': 'Windows 실행기를 source_snapshot_v1 지원 버전으로 업데이트하세요.', 'code': 'SOURCE_SNAPSHOT_UNSUPPORTED'}
        return {'ready': True, 'reason': None, 'code': 'READY'}

    def source_state(self):
        return self.sources.state() | {'execution': self.source_execution()}

    def command_snapshot(self, name, revision):
        if not name:
            if not self.simulation:
                raise TestError('Save and select a Windows TC command profile before running', 'COMMAND_REQUIRED')
            if revision:
                raise TestError('A command revision requires a saved command profile', status=422)
            template = default_command_template()
            return {'name': None, 'revision': digest(template), 'template': template}
        profile = next((p for p in self.store.documents('command') if p['name'] == name), None)
        if not profile or not revision or profile['revision'] != revision:
            raise TestError('Command profile changed or is missing; reload and run Preflight again', 'COMMAND_CHANGED')
        template = validate_command_template({key: profile[key] for key in ('single', 'dual')})
        if digest(template) != profile['revision']:
            raise TestError('Command profile revision is invalid', 'COMMAND_CHANGED')
        return {'name': name, 'revision': revision, 'template': template}

    def preview_command(self, tc_id, source_revision, connection, template):
        template = validate_command_template(template)
        catalog = self.current_catalog(source_revision)
        if not catalog:
            raise TestError('TC source changed; refresh before preview', 'SOURCE_CHANGED')
        tc = next((t for t in catalog['tests'] if t['id'] == tc_id), None)
        if not tc or tc['disabled_reason']:
            raise TestError('Choose an available TC to preview', status=422)
        argv = resolve_argv(template[tc['kind'].lower()], tc, connection)
        return {'simulation': self.simulation, 'tc_id': tc_id, 'kind': tc['kind'], 'argv': argv,
                'display': shlex.join(argv), 'revision': digest(template)}

    def preflight(self, request):
        req = StartRequest.model_validate(request)
        if req.execution != ('mock' if self.simulation else 'hardware'):
            raise TestError('Hardware adapter is not configured. Demo/UI/reports remain available.', 'HARDWARE_NOT_CONFIGURED', 422)
        catalog = self.current_catalog(req.source_revision)
        if not catalog:
            raise TestError('TC source changed; refresh and explicitly review the selection', 'SOURCE_CHANGED')
        descriptor = self.sources.descriptor()
        if descriptor is not None:
            if descriptor['source_revision'] != req.source_revision:
                raise TestError('TC source changed; repeat Preflight', 'SOURCE_CHANGED')
            readiness = self.source_execution()
            if not readiness['ready']:
                raise TestError(readiness['reason'], readiness['code'], 503)
            descriptor = {k: descriptor[k] for k in ('version', 'snapshot_id', 'source_revision')}
        tests = select(catalog, req.tc_ids)
        if req.module_context is not None:
            if self.module_selection_service is None or self.mode != 'dashboard':
                raise TestError('BSP module context is unavailable in this workspace', 'MODULE_CONTEXT_UNAVAILABLE', 422)
            self.module_selection_service.validate(self, req.module_context.model_dump(), catalog, req.tc_ids)
        command_snapshot = self.command_snapshot(req.command_profile, req.command_revision)
        if not self.simulation:
            validate_windows_command(command_snapshot['template'])
        for tc in tests:
            resolve_argv(command_snapshot['template'][tc['kind'].lower()], tc, req.connection.model_dump())
        if req.suite_revision:
            suites = self.store.documents('suite')
            suite = next((s for s in suites if s['revision'] == req.suite_revision), None)
            if not suite or suite['tc_ids'] != req.tc_ids or suite['source_revision'] != req.source_revision or suite.get('cycles', 1) != req.cycles or any(suite.get('tc_repeats', {}).get(i, 1) != req.tc_repeats.get(i, 1) for i in req.tc_ids):
                raise TestError('Suite snapshot no longer matches this selection', 'SUITE_CHANGED')
        self.boards.verify(req.connection.model_dump(), any(t['kind'] == 'Dual' for t in tests))
        link = None
        if req.job_id:
            if not self.dashboard or self.mode == 'standalone':
                raise TestError('Standalone runs cannot link to a Dashboard job')
            link = self.dashboard.pin(req.job_id, req.connection.model_dump())
        if req.module_context is not None:
            self.module_selection_service.validate(self, req.module_context.model_dump(), catalog, req.tc_ids)
        return {'ok': True, 'simulation': self.simulation, 'checks': ['TC source/order', 'Board/COM configuration', 'Mock adapter configured' if self.simulation else 'Windows runner reachable', 'Command template/revision'],
                'tests': tests, 'catalog': catalog, 'link': link, 'command_snapshot': command_snapshot,
                'source_snapshot': descriptor}

    def command(self, key, payload, operation, prepare=None, guard=None):
        if not key or len(key) > 180:
            raise TestError('Command ID required', 'IDEMPOTENCY_REQUIRED', 400)
        hashed = digest(payload)
        if prepare is not None:
            # Preserve idempotent replies before preparing network-backed input.
            with self.store.connection() as connection:
                row = connection.execute('SELECT * FROM commands WHERE id=?', (key,)).fetchone()
                if row:
                    if row['hash'] != hashed:
                        raise TestError('Command ID reused with different content', 'IDEMPOTENCY_CONFLICT')
                    return json.loads(row['result'])
            prepare()
        with self.store.transaction() as c:
            row = c.execute('SELECT * FROM commands WHERE id=?', (key,)).fetchone()
            if row:
                if row['hash'] != hashed:
                    raise TestError('Command ID reused with different content', 'IDEMPOTENCY_CONFLICT')
                return json.loads(row['result'])
            with guard() if guard is not None else nullcontext():
                result = operation(c)
                c.execute('INSERT INTO commands VALUES(?,?,?)', (key, hashed, json.dumps(result)))
                if guard is not None:
                    # Commit the GUI reservation and command ledger while the
                    # injected BSP guard still prevents a competing dispatch.
                    c.commit()
            return result

    def start(self, key, session, request):
        req = StartRequest.model_validate(request) if request.get('module_context') is not None else None
        prepared = None

        def prepare():
            nonlocal prepared
            prepared = self.preflight(request)

        def guard():
            return self.module_selection_service.guard(self, req.module_context.model_dump(), prepared['catalog'], req.tc_ids)

        def operation(c):
            nonlocal req
            checked = prepared if prepared is not None else self.preflight(request)
            req = req or StartRequest.model_validate(request)
            active = self.sources.state(c)
            frozen = checked.get('source_snapshot')
            if ((frozen is None and active['active']['kind'] != 'legacy') or
                (frozen is not None and (active['version'] != frozen['version'] or
                 active['active']['source_revision'] != frozen['source_revision']))):
                raise TestError('Source selection changed before run creation', 'SOURCE_CHANGED')
            if req.parent_run_id:
                parent = self.store.get(c, req.parent_run_id)
                if parent['state'] not in TERMINAL:
                    raise TestError('Retest requires a finished original run')
            connection = req.connection.model_dump()
            resources = self.resources(connection, any(t['kind'] == 'Dual' for t in checked['tests']))
            if any(c.execute('SELECT 1 FROM reservations WHERE resource=?', (r,)).fetchone() for r in resources):
                raise TestError('Board/COM already reserved in this manager', 'RESERVATION_CONFLICT')
            run = {'id': uid(), 'mode': self.mode, 'simulation': self.simulation, 'state': 'QUEUED', 'overall_result': 'INCOMPLETE',
                   'version': 0, 'created_at': now(), 'started_at': None, 'ended_at': None,
                   'source_revision': req.source_revision, 'metadata_revision': checked['catalog']['metadata_revision'],
                   'suite_revision': req.suite_revision, 'connection_snapshot': connection,
                   'command_snapshot': checked['command_snapshot'],
                   'tests': checked['tests'], 'tc_repeats': req.tc_repeats, 'cycles': req.cycles,
                   'plan': execution_plan(checked['tests'], req.tc_repeats, req.cycles), 'slot_results': {}, 'results': {}, 'attempts': [], 'index': 0,
                   'controller': session, 'controller_seen_at': now(), 'control_request': None,
                   'scenario': req.scenario, 'speed': req.speed, 'injected_fault': None, 'environment_ready': True,
                   'link': checked['link'], 'sync': {'status': 'PENDING' if checked['link'] else 'NOT_LINKED'},
                   'parent_run_id': req.parent_run_id, 'lease_token': uid(), 'reason': ''}
            if req.module_context is not None:
                run['module_context'] = req.module_context.model_dump()
            if frozen is not None:
                run['source_snapshot'] = frozen
            for resource in resources:
                c.execute('INSERT INTO reservations VALUES(?,?,?)', (resource, run['id'], run['lease_token']))
            self.store.save(c, run, 'RUN_CREATED', {'simulation': self.simulation, 'resources': resources})
            return self.decorate(run)
        return self.command(key, {'session': session, 'request': request}, operation,
                            prepare=prepare,
                            guard=guard if req is not None else None)

    @staticmethod
    def resources(connection, dual):
        boards = [connection['a']] + ([connection['b']] if dual else [])
        return [f'{b["host"].casefold()}:{kind}:{b[field].casefold()}' for b in boards for kind, field in [('board', 'board_id'), ('com', 'com')]]

    @staticmethod
    def decorate(run):
        return run | {'progress': progress(run) | {'usage': usage_summary(run)},
                      'execution_targets': target_summary(run['attempts']),
                      'targets_by_tc': {t['id']: target_summary([a for a in run['attempts'] if a['tc_id'] == t['id']]) for t in run['tests']}}

    def get(self, run_id):
        return self.decorate(self.store.snapshot(run_id))

    def heartbeat(self, run_id, session):
        with self.store.transaction() as c:
            run = self.store.get(c, run_id)
            if run['controller'] == session:
                run['controller_seen_at'] = now()
                # Heartbeats do not invalidate expected_version of user commands.
                c.execute('UPDATE runs SET data=? WHERE id=?', (json.dumps(run), run_id))
        return {'controller': run['controller'], 'control_request': run['control_request']}

    def act(self, run_id, key, session, expected, action, data=None):
        data = data or {}
        def operation(c):
            run = self.store.get(c, run_id)
            if run['version'] != expected:
                raise TestError('State changed; refresh before sending a new command', 'VERSION_CONFLICT')
            if action == 'request-control':
                run['control_request'] = session
            elif action == 'take-control':
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(run['controller_seen_at'])).total_seconds()
                if age <= self.control_seconds:
                    raise TestError('Current controller must approve the transfer')
                if run['state'] == 'UNKNOWN':
                    raise TestError('Resolve unknown execution before taking control')
                run.update(controller=session, controller_seen_at=now(), control_request=None)
            else:
                if run['controller'] != session:
                    raise TestError('This browser is an observer; request control first', 'CONTROL_REQUIRED', 403)
                if action == 'grant-control':
                    if not run['control_request']:
                        raise TestError('No control transfer requested')
                    run.update(controller=run['control_request'], controller_seen_at=now(), control_request=None)
                elif action == 'retry-sync':
                    if run['sync']['status'] not in {'FAILED', 'BLOCKED'}:
                        raise TestError('No failed/blocked sync to retry')
                    self.queue_sync(c, run)
                elif action in {'demo-recover', 'recover'}:
                    if action == 'demo-recover' and not self.simulation:
                        raise TestError('Demo recovery is unavailable for real executions')
                    if run['state'] not in {'PAUSED', 'UNKNOWN'}:
                        raise TestError('Recover a paused/unknown demo run')
                    if run['state'] == 'UNKNOWN':
                        a = run['attempts'][-1]
                        if self.runner.probe(a['process_ref']) != 'STOPPED':
                            raise TestError('Process termination remains unknown')
                        a.update(state='ERROR', terminated=True, ended_at=now(), reason='Runner confirmed process termination')
                        record_result(run, a, 'ERROR')
                        run['state'] = 'PAUSED'
                    self.boards.verify(run['connection_snapshot'], any(t['kind'] == 'Dual' for t in run['tests']))
                    run['environment_ready'] = True
                elif action == 'demo-inject':
                    if not self.simulation: raise TestError('Fault injection is only available in Mock mode')
                    if run['state'] in TERMINAL:
                        raise TestError('Completed run verdict is immutable')
                    if data.get('fault') not in {'disconnect', 'timeout', 'unknown', 'fail'}:
                        raise TestError('Unsupported demo fault', status=422)
                    run['injected_fault'] = data['fault']
                elif action == 'pause':
                    if run['state'] not in {'QUEUED', 'RUNNING'}:
                        raise TestError('Run is not running')
                    run['state'] = 'PAUSE_REQUESTED' if self.active_attempt(run) else 'PAUSED'
                elif action == 'resume':
                    if run['state'] != 'PAUSED' or not run['environment_ready']:
                        raise TestError('Recover the environment before explicitly resuming')
                    if run.get('baseline_changed'):
                        raise TestError('Job baseline changed; cancel and create a new run')
                    self.boards.verify(run['connection_snapshot'], any(t['kind'] == 'Dual' for t in run['tests']))
                    if run['link']:
                        self.dashboard.validate(run['link'])
                    run['state'], run['reason'] = 'QUEUED', ''
                elif action == 'cancel':
                    if run['state'] in TERMINAL or run['state'] == 'UNKNOWN':
                        raise TestError('Finished/unknown run cannot be cancelled without termination evidence')
                    if self.active_attempt(run):
                        run['state'] = 'CANCEL_REQUESTED'
                    else:
                        self.end(c, run, 'CANCELLED')
                else:
                    raise TestError('Unsupported action', status=422)
            self.store.save(c, run, action.upper(), {'session': session})
            return self.decorate(run)
        return self.command(key, {'run_id': run_id, 'session': session, 'expected': expected, 'action': action, 'data': data}, operation)

    @staticmethod
    def active_attempt(run):
        return run['attempts'] and run['attempts'][-1]['state'] == 'RUNNING'

    def claim(self, run_id):
        # Resolve the private directory outside the reservation/state transaction.
        previous = self.store.snapshot(run_id)
        descriptor = previous.get('source_snapshot')
        source_context = ({'source_snapshot': descriptor, 'source_directory': str(self.sources.directory(descriptor))}
                          if descriptor else {})
        with self.store.transaction() as c:
            run = self.store.get(c, run_id)
            if run['state'] not in {'QUEUED', 'RUNNING'} or self.active_attempt(run):
                return None
            slot = run.get('plan', [{'tc_id': t['id'], 'cycle': 1, 'iteration': 1} for t in run['tests']])[run['index']]
            tc = next(t for t in run['tests'] if t['id'] == slot['tc_id'])
            try:
                self.boards.verify(run['connection_snapshot'], tc['kind'] == 'Dual')
                if run['link']:
                    self.dashboard.validate(run['link'])
                resources = self.resources(run['connection_snapshot'], tc['kind'] == 'Dual')
                if any(not c.execute('SELECT 1 FROM reservations WHERE resource=? AND run_id=? AND token=?',
                                     (r, run_id, run['lease_token'])).fetchone() for r in resources):
                    raise TestError('Reservation lost')
            except TestError as exc:
                run.update(state='PAUSED', reason=exc.message, baseline_changed=exc.code == 'BASELINE_CHANGED')
                self.store.save(c, run, 'PREFLIGHT_BLOCKED')
                return None
            ordinal = 1 + sum(a['tc_id'] == tc['id'] for a in run['attempts'])
            a = {'id': uid(), 'tc_id': tc['id'], 'slot_index': run['index'], 'cycle': slot['cycle'], 'iteration': slot['iteration'], 'ordinal': ordinal, 'state': 'RUNNING', 'started_at': now(),
                 'ended_at': None, 'stdout': '', 'stderr': '', 'exit_code': None, 'result_line': None,
                 'parser_revision': PARSER_REVISION, 'terminated': False, 'reason': '', 'process_ref': ('mock:' if self.simulation else 'windows:') + uid(),
                 'board_ids': [run['connection_snapshot']['a']['board_id']] + ([run['connection_snapshot']['b']['board_id']] if tc['kind'] == 'Dual' else []),
                 'com_mapping': run['connection_snapshot'], 'resolved_command_argv': resolve_argv(
                     run.get('command_snapshot', {'template': default_command_template()})['template'][tc['kind'].lower()], tc, run['connection_snapshot'])}
            a['warnings'] = [f'Predecessor {dep} did not pass' for dep in tc['after'] if run['results'].get(dep) != 'PASS']
            run['attempts'].append(a)
            record_result(run, a, 'RUNNING')
            run['state'] = 'RUNNING'
            run['started_at'] = run['started_at'] or now()
            fault = run['injected_fault'] or (run['scenario'] if run['index'] == 1 and sum(item.get('slot_index') == run['index'] for item in run['attempts']) == 1 else 'pass')
            run['injected_fault'] = None
            self.store.save(c, run, 'ATTEMPT_STARTED', {'attempt_id': a['id']})
            return {'run': run, 'tc': tc, 'attempt': a, 'context': {'fault': fault, 'speed': run['speed'], 'resolved_command_argv': a['resolved_command_argv'], 'process_ref': a['process_ref'], 'source_revision': run['source_revision'], 'command_template': run.get('command_snapshot', {'template': default_command_template()})['template'], **source_context}}

    def emit(self, run_id, attempt_id, stream, text):
        # Adapters must remove secrets before emitting; defense in depth for common key=value output.
        text = re.sub(r'(?i)(token|password|secret|authorization)(\s*[:=]\s*)[^\s]+', r'\1\2[REDACTED]', text)
        with self.store.transaction() as c:
            run = self.store.get(c, run_id)
            a = run['attempts'][-1]
            if a['id'] != attempt_id or a['state'] != 'RUNNING':
                return
            if len(a[stream].encode()) + len(text.encode()) > self.log_limit:
                a['log_overflow'] = True
                text = '\n[Output limit exceeded]\n'
                if len(a[stream]) >= self.log_limit:
                    return
            a[stream] += text
            # Output is persisted without changing the control version.
            c.execute('UPDATE runs SET data=? WHERE id=?', (json.dumps(run), run_id))

    def record_target(self, run_id, attempt_id, target):
        with self.store.transaction() as c:
            run = self.store.get(c, run_id)
            a = run['attempts'][-1] if run['attempts'] else None
            if not a or a['id'] != attempt_id or a['state'] != 'RUNNING':
                return False
            tc = next(t for t in run['tests'] if t['id'] == a['tc_id'])
            try:
                verified = normalize_target(target, run['connection_snapshot'], tc['kind'] == 'Dual')
            except ValueError:
                return False
            if a.get('execution_target') and a['execution_target'] != verified:
                return False
            a['execution_target'] = verified
            c.execute('UPDATE runs SET data=? WHERE id=?', (json.dumps(run), run_id))
        return True

    def record_usage(self, run_id, attempt_id, sequence, usage):
        # Cumulative snapshots are replaced, never added twice; stale callbacks are ignored.
        if type(sequence) is not int or sequence < 0:
            return False
        try:
            rows = normalize_usage(usage)
        except ValueError:
            return False
        with self.store.transaction() as c:
            run = self.store.get(c, run_id)
            a = run['attempts'][-1] if run['attempts'] else None
            if not a or a['id'] != attempt_id or a['state'] != 'RUNNING' or sequence <= a.get('usage_sequence', -1):
                return False
            a.update(usage=rows, usage_sequence=sequence)
            c.execute('UPDATE runs SET data=? WHERE id=?', (json.dumps(run), run_id))
        return True

    def finish(self, claim, result):
        with self.store.transaction() as c:
            run = self.store.get(c, claim['run']['id'])
            a = run['attempts'][-1]
            if a['id'] != claim['attempt']['id'] or a['state'] != 'RUNNING':
                return False
            executed = result.get('executed_command_argv')
            if not self.simulation and isinstance(executed, list) and 1 <= len(executed) <= 64 and all(isinstance(v, str) and 0 < len(v) <= 4096 for v in executed):
                a['executed_command_argv'] = executed
            if 'execution_target' in result:
                try:
                    verified = normalize_target(result['execution_target'], run['connection_snapshot'], claim['tc']['kind'] == 'Dual')
                    if a.get('execution_target') and a['execution_target'] != verified:
                        raise ValueError('Execution target changed within an attempt')
                    a['execution_target'] = verified
                except ValueError:
                    a['target_warning'] = 'Invalid execution target; last verified target retained'
            if 'usage' in result:
                try:
                    a['usage'] = normalize_usage(result['usage'])
                except ValueError:
                    a['usage_warning'] = 'Invalid adapter usage; last valid snapshot retained'
            state, reason, line = parse_result(a['stdout'], a['stderr'], result.get('exit_code'),
                                              terminated=result.get('terminated', False),
                                              **claim['tc'].get('parser', {}))
            if result.get('terminated') and result.get('forced_state') in {'ERROR', 'TIMEOUT', 'CANCELLED'}:
                state, reason = result['forced_state'], ('Mock ' if self.simulation else 'Windows runner ') + result['forced_state']
            if a.get('log_overflow') and state != 'UNKNOWN':
                state, reason = 'ERROR', 'Output limit exceeded; result evidence incomplete'
            if run['state'] == 'CANCEL_REQUESTED' and result.get('terminated'):
                state, reason = 'CANCELLED', 'User cancellation confirmed'
            a.update(state=state, reason=reason, result_line=line, exit_code=result.get('exit_code'),
                     terminated=result.get('terminated', False), ended_at=now() if result.get('terminated') else None)
            record_result(run, a, state)
            if state == 'UNKNOWN':
                run.update(state='UNKNOWN', reason=reason)
            elif state == 'CANCELLED':
                self.end(c, run, 'CANCELLED')
            elif state in {'ERROR', 'TIMEOUT'}:
                run.update(state='PAUSED', reason=reason, environment_ready=False)
            else:
                run['index'] += 1
                if run['index'] == len(run.get('plan', run['tests'])):
                    self.end(c, run, 'COMPLETED')
                elif run['state'] == 'PAUSE_REQUESTED':
                    run['state'] = 'PAUSED'
                else:
                    run['state'] = 'QUEUED'
            self.store.save(c, run, 'ATTEMPT_FINISHED', {'attempt_id': a['id'], 'state': state})
            return True

    def end(self, c, run, state):
        run.update(state=state, ended_at=now(), overall_result=aggregate(slot_states(run)))
        c.execute('DELETE FROM reservations WHERE run_id=? AND token=?', (run['id'], run['lease_token']))
        if run['link']:
            self.queue_sync(c, run)

    def queue_sync(self, c, run):
        results, reason = module_results(run, run['link']['mapping'])
        if not results:
            run['sync'] = {'status': 'BLOCKED', 'reason': reason}
            return
        run['sync'] = {'status': 'PENDING', 'reason': '', 'attempts': 0}
        c.execute('INSERT INTO outbox VALUES(?,?) ON CONFLICT(run_id) DO UPDATE SET data=excluded.data',
                  (run['id'], json.dumps({'attempts': 0, 'results': results})))

    def sync_one(self):
        # Dedicated GUI worker is the only dispatcher. Receiver's run ID key handles response loss.
        with self.store.connection() as c:
            row = c.execute('SELECT * FROM outbox LIMIT 1').fetchone()
        if not row or not self.dashboard:
            return
        run = self.store.snapshot(row['run_id'])
        item = json.loads(row['data'])
        item['attempts'] += 1
        try:
            if run['scenario'] == 'sync-failure' and item['attempts'] == 1:
                raise TimeoutError('Injected mock sync connection failure')
            receipt = self.dashboard.submit(run)
            if run['scenario'] == 'sync-lost-response' and item['attempts'] == 1:
                raise TimeoutError('Injected lost response after commit')
            sync = {'status': 'SUCCEEDED', 'attempts': item['attempts'], 'receipt': receipt}
        except TimeoutError as exc:
            sync = {'status': 'PENDING' if item['attempts'] <= self.sync_retries else 'FAILED', 'reason': str(exc), 'attempts': item['attempts']}
        except TestError as exc:
            sync = {'status': 'BLOCKED', 'reason': exc.message, 'attempts': item['attempts']}
        with self.store.transaction() as c:
            latest = self.store.get(c, run['id'])
            latest['sync'] = sync
            if sync['status'] == 'PENDING':
                c.execute('UPDATE outbox SET data=? WHERE run_id=?', (json.dumps(item), run['id']))
            else:
                c.execute('DELETE FROM outbox WHERE run_id=?', (run['id'],))
            self.store.save(c, latest, 'SYNC_' + sync['status'])

    def recover(self):
        # Called only after the process-wide worker lock is held.
        with self.store.transaction() as c:
            for row in c.execute('SELECT data FROM runs').fetchall():
                run = json.loads(row[0])
                if self.active_attempt(run):
                    a = run['attempts'][-1]
                    stopped = self.runner.probe(a['process_ref']) == 'STOPPED'
                    a.update(state='ERROR' if stopped else 'UNKNOWN', terminated=stopped,
                             ended_at=now() if stopped else None, reason='Manager restart; process state checked')
                    record_result(run, a, a['state'])
                    run.update(state='PAUSED' if stopped else 'UNKNOWN', reason=a['reason'])
                    self.store.save(c, run, 'RECOVERED')

    def save_document(self, kind, name, payload):
        if kind not in {'suite', 'profile', 'command'} or not re.fullmatch(r'[\w .-]{1,80}', name):
            raise TestError('Invalid saved item', status=422)
        suite_generation = None
        if kind == 'command':
            payload = validate_command_template(payload)
        elif kind == 'profile':
            try:
                payload = {'connection': Connection.model_validate(payload.get('connection')).model_dump()}
            except ValidationError as exc:
                raise TestError('A valid connection snapshot is required', status=422) from exc
        else:
            suite_generation = self.sources.state()['version']
            catalog = self.catalog(payload.get('branch', 'demo/main'))
            if ((self.sources.state()['active']['kind'] != 'legacy' or payload.get('source_revision')) and
                payload.get('source_revision') != catalog['revision']):
                raise TestError('TC source changed; refresh before saving Suite', 'SOURCE_CHANGED')
            tests = select(catalog, payload.get('tc_ids', []))
            try:
                repeats = Selection.model_validate({'tc_ids': [t['id'] for t in tests],
                    'tc_repeats': payload.get('tc_repeats', {}), 'cycles': payload.get('cycles', 1)})
            except ValidationError as exc:
                raise TestError('Invalid TC repeat counts or total execution budget', status=422) from exc
            payload = {'tc_repeats': repeats.tc_repeats, 'cycles': repeats.cycles,
                       'tc_ids': [t['id'] for t in tests], 'source_revision': catalog['revision'],
                       'branch': catalog['branch'], 'tc_hashes': {t['id']: t['content_hash'] for t in tests}}
        payload['revision'] = digest(payload)
        with self.store.transaction() as c:
            if kind == 'suite' and self.sources.state(c)['version'] != suite_generation:
                raise TestError('Source selection changed before Suite save', 'SOURCE_CHANGED')
            c.execute('INSERT INTO documents VALUES(?,?,?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data',
                      (kind, name, json.dumps(payload)))
        return payload
