import json
import re
from pydantic import ValidationError
from datetime import datetime, timezone
from gui_test.core.models import TestError, StartRequest, Connection, TERMINAL, uid, now, digest
from gui_test.core.results import aggregate, progress, parse_result, PARSER_REVISION, module_results
from gui_test.core.discovery import select
from gui_test.adapters.mock import MockBoards, MockRunner, demo_catalog
from gui_test.adapters.runner import resolve_argv


class Manager:
    def __init__(self, store, mode='standalone', dashboard=None):
        self.store, self.mode, self.dashboard = store, mode, dashboard
        self.boards, self.runner = MockBoards(), MockRunner()
        # Explicit demo-only limits. Production values must be supplied by an approved adapter.
        self.log_limit = 64 * 1024
        self.control_seconds = 60
        self.sync_retries = 2

    def catalog(self, branch='demo/main'):
        return demo_catalog(branch)

    def preflight(self, request):
        req = StartRequest.model_validate(request)
        if req.execution != 'mock':
            raise TestError('Hardware adapter is not configured. Demo/UI/reports remain available.', 'HARDWARE_NOT_CONFIGURED', 422)
        catalog = next((self.catalog(b) for b in ('demo/main', 'demo/next') if self.catalog(b)['revision'] == req.source_revision), None)
        if not catalog:
            raise TestError('TC source changed; refresh and explicitly review the selection', 'SOURCE_CHANGED')
        tests = select(catalog, req.tc_ids)
        if req.suite_revision:
            suites = self.store.documents('suite')
            suite = next((s for s in suites if s['revision'] == req.suite_revision), None)
            if not suite or suite['tc_ids'] != req.tc_ids or suite['source_revision'] != req.source_revision:
                raise TestError('Suite snapshot no longer matches this selection', 'SUITE_CHANGED')
        self.boards.verify(req.connection.model_dump(), any(t['kind'] == 'Dual' for t in tests))
        link = None
        if req.job_id:
            if not self.dashboard or self.mode == 'standalone':
                raise TestError('Standalone runs cannot link to a Dashboard job')
            link = self.dashboard.pin(req.job_id, req.connection.model_dump())
        return {'ok': True, 'simulation': True, 'checks': ['TC source/order', 'Board identity/COM', 'Mock adapter configured'],
                'tests': tests, 'catalog': catalog, 'link': link}

    def command(self, key, payload, operation):
        if not key or len(key) > 180:
            raise TestError('Command ID required', 'IDEMPOTENCY_REQUIRED', 400)
        hashed = digest(payload)
        with self.store.transaction() as c:
            row = c.execute('SELECT * FROM commands WHERE id=?', (key,)).fetchone()
            if row:
                if row['hash'] != hashed:
                    raise TestError('Command ID reused with different content', 'IDEMPOTENCY_CONFLICT')
                return json.loads(row['result'])
            result = operation(c)
            c.execute('INSERT INTO commands VALUES(?,?,?)', (key, hashed, json.dumps(result)))
            return result

    def start(self, key, session, request):
        def operation(c):
            checked = self.preflight(request)
            req = StartRequest.model_validate(request)
            if req.parent_run_id:
                parent = self.store.get(c, req.parent_run_id)
                if parent['state'] not in TERMINAL:
                    raise TestError('Retest requires a finished original run')
            connection = req.connection.model_dump()
            resources = self.resources(connection, any(t['kind'] == 'Dual' for t in checked['tests']))
            if any(c.execute('SELECT 1 FROM reservations WHERE resource=?', (r,)).fetchone() for r in resources):
                raise TestError('Board/COM already reserved in this manager', 'RESERVATION_CONFLICT')
            run = {'id': uid(), 'mode': self.mode, 'simulation': True, 'state': 'QUEUED', 'overall_result': 'INCOMPLETE',
                   'version': 0, 'created_at': now(), 'started_at': None, 'ended_at': None,
                   'source_revision': req.source_revision, 'metadata_revision': checked['catalog']['metadata_revision'],
                   'suite_revision': req.suite_revision, 'connection_snapshot': connection,
                   'tests': checked['tests'], 'results': {}, 'attempts': [], 'index': 0,
                   'controller': session, 'controller_seen_at': now(), 'control_request': None,
                   'scenario': req.scenario, 'speed': req.speed, 'injected_fault': None, 'environment_ready': True,
                   'link': checked['link'], 'sync': {'status': 'PENDING' if checked['link'] else 'NOT_LINKED'},
                   'parent_run_id': req.parent_run_id, 'lease_token': uid(), 'reason': ''}
            for resource in resources:
                c.execute('INSERT INTO reservations VALUES(?,?,?)', (resource, run['id'], run['lease_token']))
            self.store.save(c, run, 'RUN_CREATED', {'simulation': True, 'resources': resources})
            return self.decorate(run)
        return self.command(key, {'session': session, 'request': request}, operation)

    @staticmethod
    def resources(connection, dual):
        boards = [connection['a']] + ([connection['b']] if dual else [])
        return [f'{b["host"].casefold()}:{kind}:{b[field].casefold()}' for b in boards for kind, field in [('board', 'board_id'), ('com', 'com')]]

    @staticmethod
    def decorate(run):
        return run | {'progress': progress(run)}

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
                elif action == 'demo-recover':
                    if run['state'] not in {'PAUSED', 'UNKNOWN'}:
                        raise TestError('Recover a paused/unknown demo run')
                    if run['state'] == 'UNKNOWN':
                        a = run['attempts'][-1]
                        if self.runner.probe(a['process_ref']) != 'STOPPED':
                            raise TestError('Process termination remains unknown')
                        a.update(state='ERROR', terminated=True, ended_at=now(), reason='Mock process confirmed stopped')
                        run['results'][a['tc_id']] = 'ERROR'
                        run['state'] = 'PAUSED'
                    run['environment_ready'] = True
                elif action == 'demo-inject':
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
        with self.store.transaction() as c:
            run = self.store.get(c, run_id)
            if run['state'] not in {'QUEUED', 'RUNNING'} or self.active_attempt(run):
                return None
            tc = run['tests'][run['index']]
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
            a = {'id': uid(), 'tc_id': tc['id'], 'ordinal': ordinal, 'state': 'RUNNING', 'started_at': now(),
                 'ended_at': None, 'stdout': '', 'stderr': '', 'exit_code': None, 'result_line': None,
                 'parser_revision': PARSER_REVISION, 'terminated': False, 'reason': '', 'process_ref': 'mock:' + uid(),
                 'board_ids': [run['connection_snapshot']['a']['board_id']] + ([run['connection_snapshot']['b']['board_id']] if tc['kind'] == 'Dual' else []),
                 'com_mapping': run['connection_snapshot'], 'resolved_command_argv': resolve_argv(
                     ['mock-tc', '{tc_path}', '{com_a}'] + (['{com_b}'] if tc['kind'] == 'Dual' else []), tc, run['connection_snapshot'])}
            a['warnings'] = [f'Predecessor {dep} did not pass' for dep in tc['after'] if run['results'].get(dep) != 'PASS']
            run['attempts'].append(a)
            run['results'][tc['id']] = 'RUNNING'
            run['state'] = 'RUNNING'
            run['started_at'] = run['started_at'] or now()
            fault = run['injected_fault'] or (run['scenario'] if run['index'] == 1 and ordinal == 1 else 'pass')
            run['injected_fault'] = None
            self.store.save(c, run, 'ATTEMPT_STARTED', {'attempt_id': a['id']})
            return {'run': run, 'tc': tc, 'attempt': a, 'context': {'fault': fault, 'speed': run['speed']}}

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

    def finish(self, claim, result):
        with self.store.transaction() as c:
            run = self.store.get(c, claim['run']['id'])
            a = run['attempts'][-1]
            if a['id'] != claim['attempt']['id'] or a['state'] != 'RUNNING':
                return False
            state, reason, line = parse_result(a['stdout'], a['stderr'], result.get('exit_code'),
                                              terminated=result.get('terminated', False),
                                              **claim['tc'].get('parser', {}))
            if result.get('terminated') and result.get('forced_state') in {'ERROR', 'TIMEOUT', 'CANCELLED'}:
                state, reason = result['forced_state'], 'Mock ' + result['forced_state']
            if a.get('log_overflow') and state != 'UNKNOWN':
                state, reason = 'ERROR', 'Output limit exceeded; result evidence incomplete'
            if run['state'] == 'CANCEL_REQUESTED' and result.get('terminated'):
                state, reason = 'CANCELLED', 'User cancellation confirmed'
            a.update(state=state, reason=reason, result_line=line, exit_code=result.get('exit_code'),
                     terminated=result.get('terminated', False), ended_at=now() if result.get('terminated') else None)
            run['results'][a['tc_id']] = state
            if state == 'UNKNOWN':
                run.update(state='UNKNOWN', reason=reason)
            elif state == 'CANCELLED':
                self.end(c, run, 'CANCELLED')
            elif state in {'ERROR', 'TIMEOUT'}:
                run.update(state='PAUSED', reason=reason, environment_ready=False)
            else:
                run['index'] += 1
                if run['index'] == len(run['tests']):
                    self.end(c, run, 'COMPLETED')
                elif run['state'] == 'PAUSE_REQUESTED':
                    run['state'] = 'PAUSED'
                else:
                    run['state'] = 'QUEUED'
            self.store.save(c, run, 'ATTEMPT_FINISHED', {'attempt_id': a['id'], 'state': state})
            return True

    def end(self, c, run, state):
        run.update(state=state, ended_at=now(), overall_result=aggregate([run['results'].get(t['id'], 'PENDING') for t in run['tests']]))
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
                    run['results'][a['tc_id']] = a['state']
                    run.update(state='PAUSED' if stopped else 'UNKNOWN', reason=a['reason'])
                    self.store.save(c, run, 'RECOVERED')

    def save_document(self, kind, name, payload):
        if kind not in {'suite', 'profile'} or not re.fullmatch(r'[\w .-]{1,80}', name):
            raise TestError('Invalid saved item', status=422)
        if kind == 'profile':
            try:
                payload = {'connection': Connection.model_validate(payload.get('connection')).model_dump()}
            except ValidationError as exc:
                raise TestError('A valid connection snapshot is required', status=422) from exc
        else:
            catalog = self.catalog(payload.get('branch', 'demo/main'))
            tests = select(catalog, payload.get('tc_ids', []))
            payload = {'tc_ids': [t['id'] for t in tests], 'source_revision': catalog['revision'],
                       'branch': catalog['branch'], 'tc_hashes': {t['id']: t['content_hash'] for t in tests}}
        payload['revision'] = digest(payload)
        with self.store.transaction() as c:
            c.execute('INSERT INTO documents VALUES(?,?,?) ON CONFLICT(kind,name) DO UPDATE SET data=excluded.data',
                      (kind, name, json.dumps(payload)))
        return payload
