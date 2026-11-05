"""Durable coordinator queue; models propose, existing server policy authorizes."""
import copy
import json
from contextlib import nullcontext
from backend.contracts import ContractError, report_hash, validate_orchestration_result
from backend.domain.policy import ACTIVE, STAGES, Conflict, fingerprint, gate, now, uid, satisfied_candidate_decision

TRIGGERS = {'JOB_STARTED', 'ANALYSIS_SET_COMPLETED', 'ATTEMPT_FAILED', 'DECISION_REQUESTED', 'PLAN_OR_SOURCE_CHANGED', 'DEPENDENCY_CHANGED', 'DECISION_UPDATED', 'INTEGRATION_FINISHED', 'USER_REPLAN_REQUESTED'}


def public_snapshot(value):
    if isinstance(value, dict):
        return {key: public_snapshot(item) for key, item in value.items() if key not in {'token', 'owner', 'profile', 'request', 'review_request', 'process_receipt', 'transport'} and not key.startswith('_')}
    if isinstance(value, list):
        return [public_snapshot(item) for item in value]
    return value


class Orchestration:
    def __init__(self, engine):
        self.engine, self.store = engine, engine.store

    @staticmethod
    def enabled(job):
        return bool(job['profile'].get('orchestration', {}).get('enabled', False))

    def enqueue(self, c, job, trigger_type, event_id, detail=None):
        if trigger_type not in TRIGGERS:
            raise Conflict('Unknown orchestration trigger.', 'CONTRACT', 422)
        if not self.enabled(job):
            return None
        if trigger_type in {'JOB_STARTED', 'ANALYSIS_SET_COMPLETED'}:
            event_id = trigger_type + ':' + str(job['plan_version'])
        old = c.execute('SELECT id FROM orchestration_triggers WHERE job_id=? AND event_id=? AND type=?', (job['id'], event_id, trigger_type)).fetchone()
        if old:
            return old['id']
        identifier = uid()
        root = (detail or {}).get('root_id') or identifier
        c.execute('INSERT INTO orchestration_triggers VALUES(?,?,?,?,?,?,?,?,?,?)', (identifier, job['id'], event_id, trigger_type, job['plan_version'], 'PENDING', None, root, json.dumps(detail or {}), now()))
        self.store.audit(c, job, 'ORCHESTRATION_QUEUED', {'trigger_id': identifier, 'type': trigger_type})
        return identifier

    def acquire_lane(self, c, job_id, owner_id, kind):
        if c.execute('SELECT 1 FROM coordinator_lanes WHERE job_id=?', (job_id,)).fetchone():
            return False
        c.execute('INSERT INTO coordinator_lanes VALUES(?,?,?,?,?)', (job_id, owner_id, kind, 'RUNNING', '{}'))
        return True

    def release_lane(self, c, job_id, owner_id, unknown=False):
        if unknown:
            c.execute("UPDATE coordinator_lanes SET status='UNKNOWN' WHERE job_id=? AND owner_id=?", (job_id, owner_id))
        else:
            c.execute('DELETE FROM coordinator_lanes WHERE job_id=? AND owner_id=?', (job_id, owner_id))

    def launch_intent(self, c, job_id, owner_id, kind):
        receipt = {'id': uid(), 'job_id': job_id, 'owner_id': owner_id, 'kind': kind, 'nonce': uid(), 'status': 'INTENT', 'created_at': now()}
        c.execute('INSERT INTO launch_receipts VALUES(?,?,?,?,?,?,?)', (receipt['id'], job_id, owner_id, kind, receipt['nonce'], 'INTENT', json.dumps(receipt)))
        return receipt

    def record_transport(self, run_id, receipt):
        with self.store.transaction() as c:
            row = c.execute('SELECT * FROM launch_receipts WHERE owner_id=? ORDER BY rowid DESC LIMIT 1', (run_id,)).fetchone()
            if not row:
                raise Conflict('No durable launch intent.', 'RECEIPT_MISMATCH')
            prior = json.loads(row['data'])
            # The callback binds its server-owned launch nonce; clients cannot select a PID.
            if receipt.get('intent_nonce', receipt.get('nonce')) != prior['nonce'] or receipt.get('launch_id', prior['id']) != prior['id']:
                raise Conflict('Launch receipt nonce differs.', 'RECEIPT_MISMATCH')
            if prior.get('not_launched'):
                prior.setdefault('proof_history', []).append({'type': 'CONTRADICTED_NOT_LAUNCHED', 'proof': prior.pop('not_launched'), 'at': now()})
            prior['process_receipt'] = receipt
            prior['status'] = receipt.get('status', 'STARTED')
            c.execute('UPDATE launch_receipts SET status=?,data=? WHERE id=?', (prior['status'], json.dumps(prior), row['id']))

    def record_not_launched(self, owner_id, proof):
        """Only the server adapter's positively unentered branch may call this callback."""
        with self.store.transaction() as c:
            row = c.execute('SELECT id,data FROM launch_receipts WHERE owner_id=? ORDER BY rowid DESC LIMIT 1', (owner_id,)).fetchone()
            if not row:
                raise Conflict('No allocated launch for a no-launch proof.', 'RECEIPT_REQUIRED')
            data = json.loads(row['data'])
            if proof.get('launch_id') != data['id'] or proof.get('intent_nonce') != data['nonce'] or not str(proof.get('reason', '')).strip():
                raise Conflict('No-launch proof identity does not match allocation.', 'RECEIPT_MISMATCH')
            if data.get('process_receipt'):
                raise Conflict('A launched process cannot be marked not launched.', 'RECEIPT_CONFLICT')
            record = {'launch_id': data['id'], 'intent_nonce': data['nonce'], 'reason': proof['reason'], 'recorded_at': now(), 'source': 'server-adapter-unentered-branch'}
            data.update(status='NOT_LAUNCHED', not_launched=data.get('not_launched') or record)
            c.execute("UPDATE launch_receipts SET status='NOT_LAUNCHED',data=? WHERE id=?", (json.dumps(data), row['id']))

    @staticmethod
    def valid_not_launched(receipt):
        proof = receipt.get('not_launched') or {}
        return bool(receipt.get('status') == 'NOT_LAUNCHED' and not receipt.get('process_receipt') and proof.get('launch_id') == receipt.get('id') and proof.get('intent_nonce') == receipt.get('nonce') and proof.get('source') == 'server-adapter-unentered-branch' and proof.get('reason'))

    def record_result(self, owner_id, envelope):
        """Persist a completed private envelope before the worker can lose its future."""
        conflict = False
        with self.store.transaction() as c:
            row = c.execute('SELECT id,data FROM launch_receipts WHERE owner_id=? ORDER BY rowid DESC LIMIT 1', (owner_id,)).fetchone()
            if not row:
                raise Conflict('Missing durable result launch intent.', 'RECEIPT_REQUIRED')
            data = json.loads(row['data'])
            digest = report_hash(envelope)
            previous = data.get('result_sha256')
            conflict = previous is not None and previous != digest
            disposition = 'CONFLICT' if conflict else 'REPLAY' if previous else 'RECORDED'
            c.execute('INSERT INTO report_receipts VALUES(?,?,?,?,?,?,?)', (uid(), 'launch-result:' + owner_id, data['job_id'], digest, disposition, json.dumps(envelope), now()))
            if previous is None:
                data['result_envelope'] = envelope
                data['result_sha256'] = digest
                data['result_recorded_at'] = now()
                c.execute('UPDATE launch_receipts SET data=? WHERE id=?', (json.dumps(data), row['id']))
        if conflict:
            raise Conflict('Durable terminal result content conflicts with its launch identity.', 'RESULT_CONFLICT')

    def transport_context(self, owner_id):
        with self.store.connection() as c:
            row = c.execute('SELECT data FROM launch_receipts WHERE owner_id=? ORDER BY rowid DESC LIMIT 1', (owner_id,)).fetchone()
            return json.loads(row[0]) if row else {}

    def claim(self, job_id, owner):
        with self.store.transaction() as c:
            job = self.store.get(c, job_id)
            if not self.enabled(job):
                return None
            settings = job['profile']['orchestration']
            pending = c.execute("SELECT * FROM orchestration_triggers WHERE job_id=? AND status='PENDING' ORDER BY rowid LIMIT 1000", (job_id,)).fetchall()
            if not pending or c.execute('SELECT 1 FROM coordinator_lanes WHERE job_id=?', (job_id,)).fetchone():
                return None
            total = c.execute('SELECT count(*) FROM orchestration_runs WHERE job_id=?', (job_id,)).fetchone()[0]
            if total >= settings.get('max_calls', settings.get('max_runs_per_job', 20)):
                self.store.audit(c, job, 'ORCHESTRATION_LIMIT', {'reason': 'MAX_RUNS'})
                return None
            root = pending[0]['root_id']
            replans = c.execute('SELECT count(*) FROM orchestration_runs WHERE job_id=? AND root_id=?', (job_id, root)).fetchone()[0]
            if replans > settings.get('max_stale_replans', 2):
                self.store.audit(c, job, 'ORCHESTRATION_LIMIT', {'reason': 'MAX_STALE_REPLANS', 'root_id': root})
                return None
            identifier = uid()
            if not self.acquire_lane(c, job_id, identifier, 'orchestrate'):
                return None
            refs = [{'report_id': r['report_id'], 'sha256': r['sha256']} for r in c.execute('SELECT report_id,sha256 FROM agent_reports WHERE job_id=?', (job_id,))]
            snapshot = {k: public_snapshot(job[k]) for k in ['modules', 'decisions', 'integration', 'source_revision', 'plan_version', 'confirmed_plan', 'paused', 'scope_holds']}
            snapshot['leases'] = [dict(r) for r in c.execute('SELECT resource,attempt FROM leases')]
            snapshot['prior_proposals'] = [json.loads(r[0]) for r in c.execute('SELECT data FROM orchestration_proposals WHERE job_id=? ORDER BY rowid DESC LIMIT 100', (job_id,))]
            request = {'schema_version': 1, 'message_type': 'orchestration_request', 'stage': 'orchestrate', 'job_id': job_id, 'orchestration_run_id': identifier, 'session_id': job['session']['id'], 'trigger_ids': [r['id'] for r in pending], 'trigger_types': list(dict.fromkeys(r['type'] for r in pending)), 'base_state_version': job['version'], 'plan_version': job['plan_version'], 'fingerprint': job['fingerprint'], 'snapshot': snapshot, 'result_refs': refs, 'constraints': {'allowed_proposal_kinds': ['PLAN_CHANGE', 'RETRY', 'TOOL_ESCALATION', 'DECISION', 'VERIFICATION_PLAN'], 'auto_retry_limit': settings.get('auto_retry_limit', 0), 'human_plan_confirmation_required': True, 'manual_device_test': True, 'legacy_report': job['profile'].get('module_report_version', 1) == 1}, 'request': next((json.loads(r['data']).get('request') for r in reversed(pending) if json.loads(r['data']).get('request')), None)}
            data = {'id': identifier, 'job_id': job_id, 'owner': owner, 'status': 'RUNNING', 'root_id': root, 'base_state_version': job['version'], 'plan_version': job['plan_version'], 'created_at': now(), 'error_class': None}
            c.execute('INSERT INTO orchestration_runs VALUES(?,?,?,?,?,?,?)', (identifier, job_id, 'RUNNING', root, json.dumps(request), json.dumps(data), now()))
            for trigger in pending:
                c.execute("UPDATE orchestration_triggers SET status='ASSIGNED',run_id=? WHERE id=?", (identifier, trigger['id']))
            self.launch_intent(c, job_id, identifier, 'orchestrate')
            self.store.audit(c, job, 'ORCHESTRATION_STARTED', {'run_id': identifier})
            return {'id': identifier, 'job': job, 'request': request}

    def finish(self, run_id, envelope, _connection=None):
        with self.store.connection() as c:
            row = c.execute('SELECT * FROM orchestration_runs WHERE id=?', (run_id,)).fetchone()
            if not row:
                raise Conflict('Unknown coordinator run.', 'NOT_FOUND', 404)
            request = json.loads(row['request'])
        transport = envelope.get('transport', {})
        wire = None
        error = None
        try:
            if envelope.get('envelope_version') != 1:
                raise ContractError(safe_message='Coordinator adapter envelope is required.')
            if envelope.get('wire_result') is not None:
                wire = validate_orchestration_result(envelope['wire_result'], request)
                known = {m['id'] for m in request['snapshot']['modules']}
                for proposal in wire['proposals']:
                    if not set(proposal['target']['module_ids']) <= known:
                        raise ContractError(safe_message='Proposal targets an unknown module.')
        except (ContractError, ValueError, TypeError) as exc:
            error = exc.safe_message if isinstance(exc, ContractError) else 'Invalid coordinator response.'
        with nullcontext(_connection) if _connection is not None else self.store.transaction() as c:
            row = c.execute('SELECT * FROM orchestration_runs WHERE id=?', (run_id,)).fetchone()
            data = json.loads(row['data'])
            if row['status'] not in {'RUNNING', 'UNKNOWN', 'PENDING'}:
                if data.get('response_hash') != report_hash(envelope):
                    raise Conflict('Coordinator response content conflict.', 'IDEMPOTENCY_CONFLICT')
                return data
            job = self.store.get(c, row['job_id'])
            unknown = transport.get('status') == 'UNKNOWN'
            status = 'UNKNOWN' if unknown else wire['outcome'] if wire and not error else 'FAILED'
            if transport.get('status') not in {'COMPLETED', 'SUCCEEDED', 'UNKNOWN'}:
                status = 'FAILED'
            data.update(status=status, response=wire, response_hash=report_hash(envelope), transport=transport, error_class='CONTRACT' if error else wire.get('error_class') if wire else transport.get('error_class', 'ENVIRONMENT'), error=error or transport.get('error'), ended_at=None if unknown else now())
            stale = job['version'] != request['base_state_version'] or job['plan_version'] != request['plan_version'] or job['fingerprint'] != request['fingerprint']
            if wire and not error and not unknown and status == 'SUCCEEDED':
                for proposal in wire['proposals']:
                    identifier = fingerprint([job['id'], run_id, proposal['proposal_key']])
                    record = dict(proposal, id=identifier, job_id=job['id'], run_id=run_id, status='STALE' if stale else 'RECORDED', command_id='proposal:' + identifier, created_at=now(), result=None)
                    c.execute('INSERT INTO orchestration_proposals VALUES(?,?,?,?,?,?,?)', (identifier, job['id'], run_id, proposal['proposal_key'], report_hash(proposal), record['status'], json.dumps(record)))
            c.execute('UPDATE orchestration_runs SET status=?,data=? WHERE id=?', (status, json.dumps(data), run_id))
            if not unknown:
                c.execute("UPDATE orchestration_triggers SET status='CONSUMED' WHERE run_id=?", (run_id,))
                if stale:
                    self.enqueue(c, job, 'PLAN_OR_SOURCE_CHANGED', 'stale:' + run_id, {'root_id': row['root_id']})
            self.release_lane(c, job['id'], run_id, unknown)
            self.store.audit(c, job, 'ORCHESTRATION_RESULT', {'run_id': run_id, 'status': status, 'stale': stale})
            return data

    def apply(self, job_id, proposal_id, key, expected_version, actor='human'):
        def run(c, job):
            row = c.execute('SELECT * FROM orchestration_proposals WHERE id=? AND job_id=?', (proposal_id, job_id)).fetchone()
            if not row:
                raise Conflict('Unknown proposal.', 'NOT_FOUND', 404)
            proposal = json.loads(row['data'])
            if row['status'] == 'APPLIED':
                return proposal['result']
            request = json.loads(c.execute('SELECT request FROM orchestration_runs WHERE id=?', (row['run_id'],)).fetchone()[0])
            if job['version'] != request['base_state_version'] or job['plan_version'] != request['plan_version'] or job['fingerprint'] != request['fingerprint']:
                status, reason = 'STALE', 'Execution state changed after the coordinator snapshot.'
                self.enqueue(c, job, 'PLAN_OR_SOURCE_CHANGED', 'proposal-stale:' + proposal_id, {'root_id': c.execute('SELECT root_id FROM orchestration_runs WHERE id=?', (row['run_id'],)).fetchone()[0]})
            elif any(not c.execute('SELECT 1 FROM agent_reports WHERE report_id=? AND sha256=? AND job_id=?', (r['report_id'], r['sha256'], job_id)).fetchone() for r in proposal['evidence_refs']):
                status, reason = 'REJECTED', 'Evidence is no longer available.'
            else:
                working = copy.deepcopy(job)
                c.execute('SAVEPOINT proposal_application')
                try:
                    status, reason = self._apply(c, working, proposal, actor)
                except Conflict as exc:
                    status, reason = 'BLOCKED', exc.message
                if status == 'APPLIED':
                    c.execute('RELEASE SAVEPOINT proposal_application')
                    job.clear()
                    job.update(working)
                else:
                    c.execute('ROLLBACK TO SAVEPOINT proposal_application')
                    c.execute('RELEASE SAVEPOINT proposal_application')
            result = {'proposal_id': proposal_id, 'status': status, 'reason': reason, 'version': job['version']}
            proposal.update(status=status, result=result, applied_by=actor, updated_at=now())
            c.execute('UPDATE orchestration_proposals SET status=?,data=? WHERE id=?', (status, json.dumps(proposal), proposal_id))
            self.store.audit(c, job, 'PROPOSAL_' + status, result)
            return result
        # The proposal owns one deterministic execution command, independent of UI retries.
        return self.engine.command(key, {'action': 'apply-proposal', 'proposal_id': proposal_id, 'actor': actor}, run, job_id, expected_version)

    def _apply(self, c, job, proposal, actor):
        kind, data = proposal['kind'], proposal['data']
        modules = [self.engine.module(job, identifier) for identifier in proposal['target']['module_ids']]
        name = proposal['target']['stage']
        if kind in {'RETRY', 'TOOL_ESCALATION'}:
            if len(modules) != 1 or name not in STAGES:
                raise Conflict('Retry or escalation requires exactly one module and stage.')
            module = modules[0]
            stage = module['stages'][name]
            attempts = stage['attempts']
            previous = attempts[-1] if attempts else {}
            if previous.get('id') != data['previous_attempt_id'] or previous.get('cause_key') != data['cause_key']:
                raise Conflict('The latest terminal attempt and cause must match.')
            if previous.get('status') not in {'FAILED', 'CANCELLED'} or c.execute('SELECT 1 FROM leases WHERE attempt=?', (previous.get('id'),)).fetchone():
                raise Conflict('Previous execution termination is not established.')
            if kind == 'TOOL_ESCALATION':
                repeats = sum(a.get('status') == 'FAILED' and a.get('error_class') == 'FIX' and a.get('cause_key') == data['cause_key'] for a in attempts)
                # Difficulty evidence must be a current owned report, not a model assertion.
                difficulty = False
                for ref in proposal['evidence_refs']:
                    row = c.execute('SELECT data,attempt_id FROM agent_reports WHERE report_id=? AND sha256=? AND job_id=?', (ref['report_id'], ref['sha256'], job['id'])).fetchone()
                    if not row or row['attempt_id'] != previous.get('id'):
                        continue
                    record = json.loads(row['data'])
                    wire = record.get('wire_result') or {}
                    proof = wire.get('report', {}).get('details', {}).get('difficulty_evidence')
                    if proof and wire.get('stage') == 'code' and wire.get('outcome') == 'FAILED' and wire.get('error_class') == 'FIX' and wire.get('cause_key') == data['cause_key'] and set(proof['evidence_paths']) <= {file['path'] for file in record['files']}:
                        difficulty = True
                if name != 'code' or (repeats < 2 and not difficulty):
                    raise Conflict('Opus escalation needs two actual same-cause FIX failures or validated difficulty proof.')
                stage['tool_escalation'] = {'tool': 'claude', 'model': 'opus', 'cause_key': data['cause_key'], 'evidence_refs': proposal['evidence_refs']}
            else:
                reason = gate(job, module, name)
                if reason:
                    raise Conflict(reason, 'GATE_BLOCKED')
                if not data['changed_approach'].strip():
                    raise Conflict('A changed retry approach is required.')
                limit = job['profile']['orchestration'].get('auto_retry_limit', 0)
                used = stage.get('automatic_retries', 0)
                if actor != 'human' and used >= limit:
                    return 'WAITING_USER', 'Automatic retry allowance is exhausted.'
                if actor != 'human':
                    stage['automatic_retries'] = used + 1
                stage.update(status='PENDING', validity='UNVERIFIED', retry_approach=data['changed_approach'])
            self.store.save(c, job, 'PROPOSAL_' + kind, {'proposal_id': proposal['id']})
            return 'APPLIED', 'Server policy accepted the requested transition.'
        if kind == 'DECISION':
            candidates = []
            for identifier in data['candidate_ids']:
                row = c.execute('SELECT * FROM decision_candidates WHERE id=? AND job_id=?', (identifier, job['id'])).fetchone()
                if not row or row['status'] == 'DISMISSED':
                    raise Conflict('Decision candidate is unavailable.')
                candidate = json.loads(row['data'])
                if candidate['report_id'] not in {r['report_id'] for r in proposal['evidence_refs']}:
                    raise Conflict('Decision must cite each owned candidate report.')
                if not set(candidate['affected_module_ids']) <= {m['id'] for m in modules} or not set(candidate['affected_stages']) <= set(data['affected_stages']):
                    raise Conflict('Decision omits validated candidate impact.')
                candidates.append(candidate)
            linked = {candidate['decision_id'] for candidate in candidates if candidate.get('decision_id')}
            if len(linked) > 1:
                raise Conflict('Candidates already reference different decisions.')
            decision = next((d for d in job['decisions'] if d['id'] in linked), None)
            if not decision:
                decision = {'id': uid(), 'title': data['question'], 'options': data['options'], 'recommendation': data['recommendation'], 'affected_modules': [m['id'] for m in modules], 'affected_stages': data['affected_stages'], 'status': 'OPEN', 'resolution': None, 'jira_key': None, 'sync_status': 'QUEUED' if job['execution'] == 'bridge' and (job['profile'].get('jira_url') or job['profile'].get('mcp_argv')) else 'NOT_CONFIGURED', 'created_at': now()}
                job['decisions'].append(decision)
            for candidate in candidates:
                candidate.update(decision_id=decision['id'], status='LINKED')
                c.execute('UPDATE decision_candidates SET decision_id=?,status=?,data=? WHERE id=?', (decision['id'], 'LINKED', json.dumps(candidate), candidate['id']))
            self.store.save(c, job, 'DECISION_PROPOSED', {'decision_id': decision['id']})
            return 'APPLIED', 'Internal decision and Jira outbox intent recorded; no answer was selected.'
        if kind == 'PLAN_CHANGE':
            return self._plan(c, job, proposal, actor)
        if kind == 'VERIFICATION_PLAN':
            if data['source_revision'] != job['source_revision'] or not modules:
                raise Conflict('Verification source and targets must be current.')
            if job['integration']['status'] in ACTIVE:
                raise Conflict('Active or UNKNOWN integration prevents verification plan replacement.')
            for module in modules:
                stage = module['stages']['verification']
                if any(s['status'] in ACTIVE for s in module['stages'].values()):
                    raise Conflict('Active or unknown work prevents verification plan replacement.')
                cases = [case['case_id'] for case in data['cases']]
                if set(stage['required_cases']) - set(cases):
                    return 'WAITING_USER', 'Removing required cases needs an approved exclusion decision.'
                current_artifact = (module['stages']['build'].get('result') or {}).get('artifact')
                if data.get('artifact') and (not current_artifact or data['artifact']['sha256'] != current_artifact['sha256']):
                    raise Conflict('Verification image does not match the current build.')
                stage.update(required_cases=cases, verification_plan=data['cases'], status='PENDING', validity='INVALIDATED')
                for downstream in ['device_test']:
                    module['stages'][downstream].update(status='PENDING', validity='INVALIDATED')
            job['integration'].update(status='PENDING')
            job['final_review'] = None
            self.store.save(c, job, 'VERIFICATION_PLAN_CHANGED')
            self.enqueue(c, job, 'PLAN_OR_SOURCE_CHANGED', proposal['id'])
            return 'APPLIED', 'Required verification plan updated; results were invalidated.'
        raise Conflict('Unsupported proposal kind.', 'CONTRACT')

    @staticmethod
    def _plan_view(module):
        return {key: copy.deepcopy(module.get(key, default)) for key, default in {'name': '', 'stable_key': module['id'], 'group': 'main', 'target_paths': [], 'dependency_module_ids': [], 'required_cases': [], 'completion_conditions': []}.items()}

    def _plan(self, c, job, proposal, actor):
        from backend.domain.engine import new_stage
        data = proposal['data']
        if data['base_plan_version'] != job['plan_version']:
            raise Conflict('Plan version changed.')
        if any(s['status'] in ACTIVE for m in job['modules'] for s in m['stages'].values()):
            raise Conflict('Active or UNKNOWN work prevents plan replacement.')
        if job['integration']['status'] in ACTIVE:
            raise Conflict('Active or UNKNOWN integration prevents plan replacement.')
        copies = copy.deepcopy(job['modules'])
        changed = set()
        approval = False
        for change in data['changes']:
            if change['operation'] == 'add':
                after = change['after']
                if any(m.get('stable_key') == after['stable_key'] for m in copies):
                    raise Conflict('Stable module key already exists.')
                identifier = uid()
                module = dict(after, id=identifier, active=True, introduced_version=job['plan_version'] + 1, stages={n: new_stage(n) for n in STAGES}, changes=[])
                copies.append(module)
                changed.add(identifier)
                approval = True
            else:
                module = self.engine.module({'modules': copies}, change['module_id'])
                if change['before'] != self._plan_view(module):
                    raise Conflict('Plan before image does not match stored module scope.')
                if change['operation'] == 'deactivate':
                    module['active'] = False
                    approval = True
                else:
                    after = change['after']
                    scope_keys = {'stable_key', 'group', 'target_paths', 'dependency_module_ids', 'required_cases', 'completion_conditions'}
                    scope_changed = any(after[key] != self._plan_view(module)[key] for key in scope_keys)
                    if scope_changed:
                        changed.add(module['id'])
                        approval = True
                    module.update(after)
            module.setdefault('plan_history', []).append({'version': job['plan_version'], 'change': change, 'proposal_id': proposal['id']})
        if approval and job['confirmed_plan'] is not None and actor != 'human':
            return 'WAITING_USER', 'Scope, group, dependency, or required-case changes need human approval.'
        active = {m['id']: m for m in copies if m.get('active', True)}
        visited, visiting = set(), set()
        def visit(identifier):
            if identifier in visiting:
                raise Conflict('Dependency graph contains a cycle.')
            if identifier in visited:
                return
            if identifier not in active:
                raise Conflict('Dependency refers to an inactive or unknown module.')
            visiting.add(identifier)
            for other in active[identifier].get('dependency_module_ids', []):
                visit(other)
            visiting.remove(identifier)
            visited.add(identifier)
        for identifier in active:
            visit(identifier)
        inventory = job['profile'].get('vendor_inventory', {})
        items = inventory.get('changes', []) if isinstance(inventory, dict) else inventory
        for module in copies:
            if module['id'] in changed:
                paths = module.get('target_paths', [])
                module['changes'] = [dict(item, id=item['change_id'], disposition='needs_analysis', evidence=None) for item in items if module.get('stable_key', module['name']) in item.get('module_keys', []) or any(item['path'] == p or item['path'].startswith(p.rstrip('/') + '/') for p in paths)]
                for stage in module['stages'].values():
                    stage.update(status='PENDING', validity='INVALIDATED', invalidation_reason='Plan scope changed')
                case_ids = [case['case_id'] for case in module.get('required_cases', [])]
                if case_ids:
                    module['stages']['verification']['required_cases'] = case_ids
                    module['stages']['device_test']['required_cases'] = case_ids
        confirmed = job['confirmed_plan']
        job.setdefault('plan_history', []).append({'version': job['plan_version'], 'confirmed_plan': confirmed, 'modules': job['modules']})
        job['modules'] = copies
        job['plan_version'] += 1
        # Initial plans stay draft. Only unchanged approved scope carries confirmation forward.
        job['confirmed_plan'] = job['plan_version'] if confirmed is not None and not approval else None
        job['fingerprint'] = fingerprint([job['fingerprint'], job['plan_version']])
        job['integration'].update(status='PENDING')
        job['final_review'] = None
        self.store.save(c, job, 'PLAN_CHANGED', {'proposal_id': proposal['id']})
        self.enqueue(c, job, 'PLAN_OR_SOURCE_CHANGED', proposal['id'])
        return 'APPLIED', 'Plan draft recorded; affected scope requires fresh analysis and confirmation.'

    def classify(self, c, job, data, dismiss=False):
        row = c.execute('SELECT data FROM decision_candidates WHERE id=? AND job_id=?', (data.get('candidate_id'), job['id'])).fetchone()
        if not row or not str(data.get('reason', '')).strip():
            raise Conflict('A current candidate and classification reason are required.', status=422)
        candidate = json.loads(row[0])
        classification = 'DISMISSED' if dismiss else data.get('classification')
        if classification not in {'DECISION', 'ORDINARY_FAILURE', 'DISMISSED'}:
            raise Conflict('Unknown candidate classification.', status=422)
        candidate['history'].append({'status': candidate['status'], 'reason': data['reason'], 'at': now()})
        candidate.update(status=classification, classification_reason=data['reason'])
        decision_id = data.get('decision_id') or candidate.get('decision_id')
        if decision_id:
            decision = next((d for d in job['decisions'] if d['id'] == decision_id), None)
            if not decision or not set(candidate['affected_module_ids']) <= set(decision['affected_modules']):
                raise Conflict('Linked decision does not cover candidate impact.')
            candidate['decision_id'] = decision_id
        # Ordinary-failure classification alone does not release a blocking hold.
        if dismiss:
            candidate['dismissed_by'] = 'human'
            self._release_holds(c, job, candidate['id'], data['reason'], 'human-dismissal')
        c.execute('UPDATE decision_candidates SET status=?,decision_id=?,data=? WHERE id=?', (classification, candidate.get('decision_id'), json.dumps(candidate), candidate['id']))
        return candidate

    def _release_holds(self, c, job, candidate_id, reason, source):
        for row in c.execute("SELECT id,data FROM scope_holds WHERE candidate_id=? AND status='ACTIVE'", (candidate_id,)).fetchall():
            hold = json.loads(row['data'])
            hold.update(status='RELEASED', released_at=now(), release_reason=reason, release_source=source)
            c.execute('UPDATE scope_holds SET status=?,data=? WHERE id=?', ('RELEASED', json.dumps(hold), row['id']))

    def decision_applied(self, c, job, decision_id, evidence):
        for row in c.execute('SELECT id,data FROM decision_candidates WHERE job_id=? AND decision_id=?', (job['id'], decision_id)):
            if satisfied_candidate_decision(job, json.loads(row['data'])):
                self._release_holds(c, job, row['id'], evidence, 'decision-applied-verified')

    def reconcile(self, job_id, run_id, key, expected_version):
        with self.store.connection() as c:
            row = c.execute('SELECT data FROM launch_receipts WHERE job_id=? AND owner_id=?', (job_id, run_id)).fetchone()
        if not row:
            raise Conflict('Stored process receipt is required.', 'RECEIPT_REQUIRED')
        receipt = json.loads(row[0])
        from backend.adapters.process import verify_receipt
        verification = verify_receipt(receipt.get('process_receipt', {}))
        state = verification.get('status', verification.get('state')) if isinstance(verification, dict) else getattr(verification, 'state', verification)
        if state != 'TERMINATED':
            def unknown(c, job):
                self.store.audit(c, job, 'ORCHESTRATION_RECONCILIATION', {'run_id': run_id, 'process_status': state})
                return {'run_id': run_id, 'status': 'UNKNOWN', 'process_status': state, 'version': job['version']}
            return self.engine.command(key, {'action': 'reconcile-run', 'run_id': run_id}, unknown, job_id, expected_version)
        # A verified terminal receipt may contain the exact durable envelope from its callback.
        envelope = receipt.get('result_envelope')
        if not envelope:
            envelope = {'envelope_version': 1, 'wire_result': None, 'related_reports': [], 'observations': {}, 'transport': {'status': 'FAILED', 'error_class': 'ENVIRONMENT', 'error': 'Previous process termination verified; no durable authored response was recovered.', 'process_receipt': receipt['process_receipt']}}
        if envelope.get('transport', {}).get('status') == 'UNKNOWN':
            envelope = copy.deepcopy(envelope)
            envelope['transport']['status'] = 'FAILED'
            envelope['transport']['error'] = 'Verified interrupted execution; no terminal authored response recovered.'
        def terminal(c, job):
            row = c.execute('SELECT id FROM orchestration_runs WHERE id=? AND job_id=?', (run_id, job_id)).fetchone()
            if not row:
                lane = c.execute('SELECT * FROM coordinator_lanes WHERE owner_id=? AND job_id=?', (run_id, job_id)).fetchone()
                if not lane:
                    raise Conflict('Unknown coordinator run.', 'NOT_FOUND', 404)
                from backend.contracts import validate_legacy_result
                try:
                    result = validate_legacy_result(envelope.get('legacy_control_result', {}))
                except ContractError as exc:
                    result = {'outcome': 'FAILED', 'evidence': exc.safe_message, 'error_class': 'CONTRACT'}
                if lane['kind'] == 'initialize':
                    ready = result.get('outcome') == 'SUCCEEDED' and bool(result.get('external_session_id')) and bool(result.get('evidence'))
                    job['session'].update(status='READY' if ready else 'FAILED', evidence=result.get('evidence') or 'Previous process termination verified; session initialization was interrupted.')
                    if ready:
                        job['session']['external_id'] = result['external_session_id']
                elif lane['kind'] == 'question':
                    prompt = next((p for p in job['prompts'] if p['id'] == run_id), None)
                    if not prompt:
                        raise Conflict('Stored question is missing.')
                    prompt.update(status='SUCCEEDED' if result.get('outcome') == 'SUCCEEDED' else 'FAILED', response=result.get('evidence') or 'Previous question process termination verified; no response recovered.')
                else:
                    raise Conflict('Unsupported coordinator lane type.')
                self.release_lane(c, job_id, run_id)
                persist = self.store.audit if self.enabled(job) else self.store.save
                persist(c, job, 'CONTROL_RECONCILED', {'owner_id': run_id})
                return {'run_id': run_id, 'status': 'RECONCILED', 'version': job['version']}
            return self.finish(run_id, envelope, _connection=c)
        return self.engine.command(key, {'action': 'reconcile-run', 'run_id': run_id}, terminal, job_id, expected_version)

    COLLECTIONS = {'runs': 'orchestration_runs', 'proposals': 'orchestration_proposals', 'candidates': 'decision_candidates', 'holds': 'scope_holds'}

    def page(self, job_id, collection, limit=50, before=None):
        self.engine.reports._page_bounds(limit, before)
        table = self.COLLECTIONS.get(collection)
        if table is None:
            raise Conflict('Unknown orchestration collection.', 'NOT_FOUND', 404)
        # SQLite projects only bounded fields; Python never loads raw histories to list them.
        projections = {
            'runs': "id,job_id,status,created_at,json_extract(data,'$.base_state_version') AS base_state_version,json_extract(data,'$.plan_version') AS plan_version,json_extract(data,'$.error_class') AS error_class,substr(json_extract(data,'$.error'),1,1000) AS error,substr(json_extract(data,'$.response.summary'),1,2000) AS response_summary",
            'proposals': "id,job_id,run_id,status,proposal_key,json_extract(data,'$.kind') AS kind,substr(json_extract(data,'$.reason'),1,1000) AS reason,json_extract(data,'$.target') AS target,json_extract(data,'$.command_id') AS command_id,json_extract(data,'$.created_at') AS created_at,json_extract(data,'$.result.status') AS result_status,substr(json_extract(data,'$.result.reason'),1,1000) AS result_reason,json_extract(data,'$.result.version') AS result_version",
            'candidates': "id,job_id,report_id,status,decision_id,candidate_key,module_id,substr(json_extract(data,'$.question'),1,1000) AS question,substr(json_extract(data,'$.recommendation'),1,1000) AS recommendation,(SELECT json_group_array(preview) FROM (SELECT CASE WHEN length(value)>256 THEN substr(value,1,256)||'…' ELSE value END AS preview FROM json_each(json_extract(data,'$.options')) LIMIT 30)) AS options,json_extract(data,'$.affected_module_ids') AS affected_module_ids,json_extract(data,'$.affected_stages') AS affected_stages,json_extract(data,'$.blocking') AS blocking,substr(json_extract(data,'$.classification_reason'),1,1000) AS classification_reason,json_extract(data,'$.created_at') AS created_at",
            'holds': "id,job_id,candidate_id,status,substr(json_extract(data,'$.reason'),1,1000) AS reason,json_extract(data,'$.module_ids') AS module_ids,json_extract(data,'$.stages') AS stages,substr(json_extract(data,'$.release_reason'),1,1000) AS release_reason,json_extract(data,'$.release_source') AS release_source,json_extract(data,'$.created_at') AS created_at",
        }
        with self.store.connection() as c:
            if not c.execute('SELECT 1 FROM jobs WHERE id=?', (job_id,)).fetchone():
                raise Conflict('Job not found.', 'NOT_FOUND', 404)
            query = 'SELECT rowid AS cursor,' + projections[collection] + ' FROM ' + table + ' WHERE job_id=?'
            parameters = [job_id]
            if before is not None:
                query += ' AND rowid<?'
                parameters.append(before)
            rows = c.execute(query + ' ORDER BY rowid DESC LIMIT ?', (*parameters, limit + 1)).fetchall()
            items = []
            for row in reversed(rows[:limit]):
                item = dict(row)
                for field in ['target', 'affected_module_ids', 'affected_stages', 'module_ids', 'stages', 'options']:
                    if field in item:
                        item[field] = json.loads(item[field]) if item[field] else ({} if field == 'target' else [])
                if collection == 'candidates':
                    item['blocking'] = bool(item['blocking'])
                if collection == 'runs':
                    item['response'] = {'summary': item.pop('response_summary')} if item.get('response_summary') else None
                    item.pop('response_summary', None)
                if collection == 'proposals':
                    item['result'] = {'status': item.pop('result_status'), 'reason': item.pop('result_reason'), 'version': item.pop('result_version')} if item.get('result_status') else None
                    for field in ['result_status', 'result_reason', 'result_version']:
                        item.pop(field, None)
                items.append(item)
            total = c.execute('SELECT count(*) FROM ' + table + ' WHERE job_id=?', (job_id,)).fetchone()[0]
            return {'items': items, 'limit': limit, 'next_cursor': items[0]['cursor'] if len(rows) > limit else None, 'total': total}

    def detail(self, job_id, collection, identifier):
        table = self.COLLECTIONS.get(collection)
        if table is None:
            raise Conflict('Unknown orchestration collection.', 'NOT_FOUND', 404)
        with self.store.connection() as c:
            row = c.execute('SELECT * FROM ' + table + ' WHERE id=? AND job_id=?', (identifier, job_id)).fetchone()
            if not row:
                raise Conflict('Orchestration record not found.', 'NOT_FOUND', 404)
            result = json.loads(row['data'])
            if collection == 'runs':
                result['request'] = json.loads(row['request'])
            return result

    def pending_proposals(self, run_id):
        with self.store.connection() as c:
            return [{'id': row['id'], 'command_id': 'proposal:' + row['id']} for row in c.execute("SELECT id FROM orchestration_proposals WHERE run_id=? AND status='RECORDED' ORDER BY rowid LIMIT 100", (run_id,))]

    def summary(self, job_id, limit=50, before=None):
        pages = {collection: self.page(job_id, collection, limit, before) for collection in self.COLLECTIONS}
        with self.store.connection() as c:
            row = c.execute("SELECT version,json_extract(data,'$.profile.orchestration') AS settings,json_extract(data,'$.profile.module_report_version') AS report_version FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise Conflict('Job not found.', 'NOT_FOUND', 404)
            job = {'version': row['version'], 'profile': {'orchestration': json.loads(row['settings']) if row['settings'] else {}, 'module_report_version': row['report_version'] or 1}}
            runs = pages['runs']['items']
            used_runs = pages['runs']['total']
            for lane in c.execute("SELECT * FROM coordinator_lanes WHERE job_id=? AND kind!='orchestrate'", (job_id,)):
                runs.append({'id': lane['owner_id'], 'job_id': job_id, 'status': lane['status'], 'kind': lane['kind'], 'error': 'Coordinator control lane requires receipt reconciliation.' if lane['status'] == 'UNKNOWN' else None})
            settings = job['profile'].get('orchestration', {})
            call_limit = settings.get('max_calls', settings.get('max_runs_per_job', 20))
            unknown = c.execute("SELECT 1 FROM coordinator_lanes WHERE job_id=? AND status='UNKNOWN'", (job_id,)).fetchone()
            latest = c.execute("SELECT status,substr(json_extract(data,'$.error'),1,1000) AS error FROM orchestration_runs WHERE job_id=? ORDER BY rowid DESC LIMIT 1", (job_id,)).fetchone()
            status = 'DISABLED' if not self.enabled(job) else 'UNKNOWN' if unknown else 'LIMIT_REACHED' if used_runs >= call_limit else 'DEGRADED' if latest and latest['status'] == 'FAILED' else 'OK'
            return {'enabled': self.enabled(job), 'legacy_report': job['profile'].get('module_report_version', 1) == 1, 'health': {'status': status, 'reason': latest['error'] if latest else None}, 'limits': {'max_runs_per_job': call_limit, 'max_calls': call_limit, 'max_stale_replans': settings.get('max_stale_replans', 2), 'auto_retry_limit': settings.get('auto_retry_limit', 0), 'used_runs': used_runs}, 'execution_version': job['version'], 'runs': runs, 'proposals': pages['proposals']['items'], 'candidates': pages['candidates']['items'], 'holds': pages['holds']['items'], 'pagination': {collection: {key: page[key] for key in ['limit', 'next_cursor', 'total']} for collection, page in pages.items()}}
