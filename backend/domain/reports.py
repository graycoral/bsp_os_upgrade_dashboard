"""Two-phase, immutable module report intake. File IO never occurs in commit."""
import copy
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from backend.contracts import ContractError, report_hash, validate_module_result
from backend.domain.policy import ACTIVE, STAGES, Conflict, file_hash, gate, now, uid, valid, reviewer, satisfied_candidate_decision


@dataclass
class PreparedIntake:
    claim: dict
    envelope: dict
    reports: list = field(default_factory=list)
    files: list = field(default_factory=list)
    error: str | None = None


class ReportIntake:
    def __init__(self, engine):
        self.engine = engine

    def prepare(self, claim, envelope):
        prepared = PreparedIntake(copy.deepcopy(claim), copy.deepcopy(envelope))
        request = claim['attempt']['request']
        try:
            self._verify_frozen_claim(claim)
            if envelope.get('envelope_version') != 1:
                raise ContractError(safe_message='Private adapter envelope is required.')
            raw = envelope.get('wire_result')
            if raw is None:
                return prepared
            wire = validate_module_result(raw, request)
            self._semantics(claim, wire, request, envelope.get('observations', {}))
            prepared.reports.append(wire)
            self._copy_files(prepared, wire)
            related = envelope.get('related_reports', [])
            if claim['stage'] != 'code' and related:
                raise ContractError(safe_message='Unexpected related reports.')
            if len(related) > 1:
                raise ContractError(safe_message='Only the allocated review may be submitted.')
            for review_envelope in related:
                if review_envelope.get('wire_result') is None:
                    continue
                expected = copy.deepcopy(claim['attempt']['review_request'])
                expected['source_revision'] = wire['source_revision']
                expected['implementation'] = wire
                expected['report_expectations']['reviewed_diff_sha256'] = self._diff_hash(wire)
                expected['report_expectations']['source_identity'] = {'kind': 'workspace-content-sha256-v1', 'sha256': wire['source_revision']}
                expected['input_result_refs'] = wire['input_result_refs'] + [{'report_id': wire['report_id'], 'sha256': report_hash(wire)}]
                review = validate_module_result(review_envelope['wire_result'], expected)
                self._semantics(claim, review, expected, review_envelope.get('observations', {}))
                prepared.reports.append(review)
                self._copy_files(prepared, review)
                available = dict.fromkeys(['opencode', 'claude', 'codex'], True) if claim['job']['execution'] == 'demo' else {key: bool(value) for key, value in claim['job']['profile']['agents'].items()}
                selected = reviewer([claim['attempt']['tool']], available, profile=claim['job']['profile'])
                if claim['attempt'].get('review_tool', selected) != selected or expected['report_expectations'].get('selected_tool', selected) != selected or expected['report_expectations'].get('author_tools', [claim['attempt']['tool']]) != [claim['attempt']['tool']] or review_envelope.get('transport', {}).get('tool') != selected:
                    raise ContractError(safe_message='Review adapter tool does not satisfy cross-review policy.')
                code_external = envelope.get('transport', {}).get('external_session_id')
                if code_external and review_envelope.get('transport', {}).get('external_session_id') == code_external:
                    raise ContractError(safe_message='Code and review reused one external session.')
        except (ContractError, Conflict, OSError, ValueError, KeyError, TypeError) as exc:
            prepared.error = exc.safe_message if isinstance(exc, ContractError) else exc.message if isinstance(exc, Conflict) else 'Report evidence or completion requirements are invalid.'
        return prepared

    def _verify_frozen_claim(self, claim):
        job = self.engine.store.snapshot(claim['job']['id'])
        fields = ['contract_capabilities', 'module_report_version', 'execution', 'runner', 'agents', 'build_argv', 'build_command']
        if any(report_hash(job['profile'].get(key)) != report_hash(claim['job']['profile'].get(key)) for key in fields):
            raise ContractError(safe_message='Claim capabilities differ from the persisted frozen profile.')
        if claim['stage'] == 'integration':
            stored = job['integration'].get('attempt', {})
        else:
            module = self.engine.module(job, claim['module']['id'])
            stored = next((item for item in module['stages'][claim['stage']]['attempts'] if item['id'] == claim['attempt']['id']), {})
        if not self._same_frozen_attempt(stored, claim['attempt']):
            raise ContractError(safe_message='Claim author, selected tool, or request differs from the persisted allocation.')

    @staticmethod
    def _same_frozen_attempt(stored, claimed):
        return all(report_hash(stored.get(key)) == report_hash(claimed.get(key)) for key in ['tool', 'review_tool', 'request', 'review_request'])

    @staticmethod
    def _diff_hash(wire):
        path = wire['report']['details'].get('diff_path')
        return next((r['sha256'] for r in wire['report']['evidence_refs'] if r['path'] == path), None)

    def _semantics(self, claim, wire, request, observations=None):
        job = claim['job']
        report = wire['report']
        paths = {r['path'] for r in report['evidence_refs']}
        modules = {m['id'] for m in job['modules'] if m.get('active', True)}
        for candidate in report['decision_requests']:
            if not set(candidate['affected_module_ids']) <= modules or not candidate['affected_module_ids']:
                raise ContractError(safe_message='Decision impact contains unknown module IDs.')
            if not set(candidate['affected_stages']) <= set(STAGES):
                raise ContractError(safe_message='Decision impact contains unknown stages.')
            if not set(candidate['evidence_paths']) <= paths:
                raise ContractError(safe_message='Decision evidence was not registered.')
        details = report['details']
        if wire['outcome'] == 'SUCCEEDED' and job['execution'] != 'demo':
            observed = observations or {}
            expected_identity = request['report_expectations'].get('source_identity')
            actual_identity = observed.get('source_identity')
            if not expected_identity or not actual_identity or observed.get('before_source_revision') != expected_identity['sha256'] or observed.get('source_revision') != wire['source_revision'] or actual_identity.get('kind') != expected_identity['kind'] or actual_identity.get('sha256') != wire['source_revision']:
                raise ContractError(safe_message='Authoritative source identity does not match the frozen request and authored target.')
            if wire['stage'] != 'code' and wire['source_revision'] != expected_identity['sha256']:
                raise ContractError(safe_message='Read-only or command result no longer targets its frozen source identity.')
            if wire['stage'] == 'code' and (observed.get('diff_format') != 'bsp-workspace-diff-v1' or observed.get('diff_sha256') != self._diff_hash(wire)):
                raise ContractError(safe_message='Implementation diff is not bound to the authoritative before/after change.')
            if wire['stage'] == 'review' and observed.get('diff_sha256') != request['report_expectations']['reviewed_diff_sha256']:
                raise ContractError(safe_message='Review is not bound to the authoritative implementation diff.')
        if wire['stage'] == 'analysis':
            known = {x.get('change_id', x.get('id')) for x in request.get('module', {}).get('vendor_changes', [])}
            for change in details.get('vendor_changes') or []:
                if change['change_id'] not in known or not set(change['dependency_module_ids']) <= modules:
                    raise ContractError(safe_message='Analysis contains an unknown inventory or dependency ID.')
                if change['disposition'] == 'excluded':
                    decision = next((d for d in job['decisions'] if d['id'] == change.get('decision_id')), None)
                    if not decision or decision['status'] != 'APPLIED':
                        raise ContractError(safe_message='Exclusion requires an applied approved decision.')
        if wire['stage'] == 'code' and wire['outcome'] == 'SUCCEEDED':
            if not self._diff_hash(wire):
                raise ContractError(safe_message='Code must register its actual diff evidence.')
            observed = claim.get('_observations', {})
            if observed.get('source_revision') and observed['source_revision'] != wire['source_revision']:
                raise ContractError(safe_message='Observed source differs from the authored report.')
        if wire['outcome'] == 'SUCCEEDED' and wire['stage'] in {'verification', 'integration'}:
            required = request['report_expectations'].get('required_case_ids', [])
            results = {r['case_id']: r for r in report['test_results']}
            artifact = request['report_expectations'].get('artifact_sha256')
            if any(case not in results or results[case]['status'] != 'PASS' or results[case]['source_revision'] != wire['source_revision'] or results[case]['artifact_sha256'] != artifact for case in required):
                raise ContractError(safe_message='Every required test must pass for the exact source and image.')
            if wire['stage'] == 'integration' and details.get('included_modules') != request['report_expectations'].get('included_modules', []):
                raise ContractError(safe_message='Integrated module evidence differs from the frozen request.')
        for result in report['test_results']:
            if not set(result['evidence_paths']) <= paths:
                raise ContractError(safe_message='Test evidence was not registered.')

    def _copy_files(self, prepared, wire):
        profile = prepared.claim['job']['profile']
        workspace = Path(profile['workspace']).resolve()
        folder = self.engine.artifacts / wire['job_id']
        folder.mkdir(parents=True, exist_ok=True)
        refs = list(wire['report']['evidence_refs'])
        if wire.get('artifact'):
            refs.append(dict(wire['artifact'], kind='artifact'))
        for reference in refs:
            raw_path = workspace / reference['path']
            path = raw_path.resolve()
            linked = any(parent.is_symlink() for parent in [raw_path, *raw_path.parents] if parent != workspace and parent.is_relative_to(workspace))
            if not path.is_relative_to(workspace) or not path.is_file() or linked or file_hash(path) != reference['sha256']:
                raise ContractError(safe_message='Evidence path, file, or hash is invalid.')
            identifier = uid() + path.suffix[:16]
            target = folder / identifier
            with path.open('rb') as source, target.open('xb') as destination:
                shutil.copyfileobj(source, destination)
            if file_hash(target) != reference['sha256']:
                target.unlink()
                raise ContractError(safe_message='Evidence changed during immutable import.')
            prepared.files.append({'report_id': wire['report_id'], 'id': identifier, 'path': reference['path'], 'sha256': reference['sha256'], 'bytes': target.stat().st_size, 'name': path.name, 'kind': reference['kind']})

    def commit(self, c, current_job, prepared):
        job, claim = current_job, prepared.claim
        a = claim['attempt']
        request = a['request']
        current_stage = job['integration'] if claim['stage'] == 'integration' else self.engine.module(job, claim['module']['id'])['stages'][claim['stage']]
        current = current_stage.get('attempt', {}) if claim['stage'] == 'integration' else (current_stage['attempts'][-1] if current_stage['attempts'] else {})
        writable = a.get('writable', claim['stage'] in {'code', 'build', 'integration'})
        lease = not writable or c.execute('SELECT 1 FROM leases WHERE attempt=? AND token=?', (a['id'], a['token'])).fetchone()
        refs_current = all(c.execute("SELECT 1 FROM agent_reports WHERE report_id=? AND sha256=? AND job_id=? AND disposition='APPLIED'", (ref['report_id'], ref['sha256'], job['id'])).fetchone() for ref in request['input_result_refs'])
        effective = current.get('id') == a['id'] and current.get('token') == a['token'] and self._same_frozen_attempt(current, a) and current_stage['status'] in ACTIVE and job['fingerprint'] == request['fingerprint'] and job['plan_version'] == request['plan_version'] and bool(lease) and refs_current
        wires = prepared.reports
        raw = prepared.envelope.get('wire_result')
        digest = report_hash(raw) if isinstance(raw, dict) else report_hash({'transport': prepared.envelope.get('transport', {}), 'report_id': request['report_id']})
        report_id = request['report_id']
        old = c.execute('SELECT sha256 FROM agent_reports WHERE report_id=?', (report_id,)).fetchone()
        disposition = 'CONFLICT' if old and old['sha256'] != digest else 'REPLAY' if old else 'APPLIED' if effective else 'STALE'
        resumed = disposition == 'REPLAY' and effective and current_stage['status'] == 'UNKNOWN' and claim.get('_verified_terminal') is True
        if resumed:
            disposition = 'APPLIED'
        receipt = {'wire_result': raw, 'related_reports': prepared.envelope.get('related_reports', []), 'transport': prepared.envelope.get('transport', {}), 'observations': prepared.envelope.get('observations', {}), 'error': prepared.error}
        c.execute('INSERT INTO report_receipts VALUES(?,?,?,?,?,?,?)', (uid(), report_id, job['id'], digest, disposition, json.dumps(receipt), now()))
        if disposition in {'REPLAY', 'CONFLICT'}:
            self.engine.store.audit(c, job, 'REPORT_' + disposition, {'report_id': report_id})
            return {'disposition': disposition, 'report_id': report_id, 'sha256': digest, 'version': job['version']}
        # Preserve code and review as full independent reports even on review failure.
        for wire in wires:
            identifier = wire['report_id'] if wire else report_id
            wire_digest = report_hash(wire) if wire else digest
            facts = {'wire_result': wire, 'legacy_report': False, 'files': [f for f in prepared.files if f['report_id'] == identifier], 'transport': prepared.envelope.get('transport', {}), 'contract_error': prepared.error}
            existing = c.execute('SELECT sha256 FROM agent_reports WHERE report_id=?', (identifier,)).fetchone()
            if existing and existing['sha256'] != wire_digest:
                raise Conflict('Related report content conflicts with immutable history.', 'REPORT_CONFLICT')
            if not existing:
                c.execute('INSERT INTO agent_reports VALUES(?,?,?,?,?,?,?,?,?)', (identifier, job['id'], a['id'], request['module_id'], wire['stage'], wire_digest, disposition, json.dumps(facts), now()))
        if not effective:
            self.engine.store.audit(c, job, 'REPORT_STALE', {'report_id': report_id})
            return {'disposition': 'STALE', 'report_id': report_id, 'sha256': digest, 'version': job['version']}
        transport = prepared.envelope.get('transport', {})
        wire = wires[0] if wires else None
        result = copy.deepcopy(wire) if wire else {'evidence': transport.get('error') or prepared.error or 'No authored result was available.', 'error_class': transport.get('error_class') or 'ENVIRONMENT'}
        result.update(report_id=report_id, report_sha256=digest)
        outcome = wire['outcome'] if wire and not prepared.error else 'FAILED'
        if transport.get('status') not in {'COMPLETED', 'SUCCEEDED', 'UNKNOWN'}:
            outcome = 'FAILED'
        if transport.get('status') == 'UNKNOWN':
            outcome = 'UNKNOWN'
        if prepared.error:
            result.update(error_class='CONTRACT', evidence=prepared.error)
        if wire and wire['stage'] == 'code':
            review = wires[1] if len(wires) > 1 else None
            related = prepared.envelope.get('related_reports', [])
            result['review_report_id'] = review['report_id'] if review else a['review_request']['report_id']
            review_unknown = any(x.get('transport', {}).get('status') == 'UNKNOWN' for x in related)
            if wire['outcome'] == 'SUCCEEDED' and (not review or review['outcome'] != 'SUCCEEDED'):
                outcome = 'UNKNOWN' if review_unknown else 'FAILED'
                result['error_class'] = 'REVIEW'
                result['evidence'] = 'Independent current review did not pass; full code evidence is retained.'
            if review:
                result['review'] = {'outcome': 'PASS' if review['outcome'] == 'SUCCEEDED' else 'FAIL', 'session_id': review['session_id'], 'report_id': review['report_id'], 'revision': review['source_revision'], 'evidence': review['evidence']}
        if current_stage['status'] == 'CANCEL_REQUESTED' and outcome != 'UNKNOWN':
            outcome = 'CANCELLED'
        if wire and not prepared.error and not resumed:
            for accepted_wire in wires:
                self._candidates(c, job, accepted_wire)
        if outcome == 'SUCCEEDED' and request['module_id'] is not None:
            module = self.engine.module(job, request['module_id'])
            # Newly received holds must gate subsequent work, not erase factual report acceptance.
            reason = gate(job | {'paused': False}, module, claim['stage'])
            if reason:
                outcome = 'FAILED'
                result.update(error_class='DEPENDENCY', evidence='Current dependency or decision gate changed during execution.')
        if wire and wire.get('artifact'):
            imported = next((f for f in prepared.files if f['report_id'] == report_id and f['kind'] == 'artifact'), None)
            if imported:
                result['artifact'] = {k: imported[k] for k in ['id', 'name', 'sha256', 'bytes']}
                result['artifact']['source_revision'] = wire['source_revision']
        if wire and wire['stage'] == 'analysis' and not prepared.error:
            module = self.engine.module(job, request['module_id'])
            supplied = {x['change_id']: x for x in wire['report']['details'].get('vendor_changes') or []}
            for change in module['changes']:
                identifier = change.get('change_id', change.get('id'))
                if identifier in supplied:
                    change.update(supplied[identifier], evidence=wire['evidence'], report_id=report_id)
        if wire and wire['stage'] == 'code' and not prepared.error and wire.get('source_revision'):
            job['working_source_revision'] = wire['source_revision']
        current.update(status=outcome, result=result, error_class=result.get('error_class'), cause_key=result.get('cause_key'))
        if outcome != 'UNKNOWN':
            current['ended_at'] = now()
            c.execute('DELETE FROM leases WHERE attempt=? AND token=?', (a['id'], a['token']))
        current_stage.update(status=outcome, validity='CURRENT' if outcome == 'SUCCEEDED' else 'UNVERIFIED', result=result)
        if claim['stage'] == 'integration':
            current_stage['evidence'] = result.get('evidence')
        self.engine.store.save(c, job, 'REPORT_APPLIED', {'report_id': report_id, 'outcome': outcome})
        if outcome == 'FAILED':
            self.engine.orchestration.enqueue(c, job, 'ATTEMPT_FAILED', a['id'], {'module_id': request['module_id'], 'stage': claim['stage']})
        if claim['stage'] == 'analysis' and all(valid(m['stages']['analysis']) for m in job['modules'] if m.get('active', True)):
            self.engine.orchestration.enqueue(c, job, 'ANALYSIS_SET_COMPLETED', 'analysis:' + str(job['plan_version']))
        if claim['stage'] == 'integration' and outcome != 'UNKNOWN':
            self.engine.orchestration.enqueue(c, job, 'INTEGRATION_FINISHED', a['id'])
        return {'disposition': 'APPLIED', 'report_id': report_id, 'sha256': digest, 'version': job['version']}

    def _candidates(self, c, job, wire):
        for item in wire['report']['decision_requests']:
            context = {'source_revision': job['source_revision'], 'report_source_revision': wire['source_revision']}
            old = c.execute('SELECT id,data FROM decision_candidates WHERE job_id=? AND module_id=? AND candidate_key=?', (job['id'], wire['module_id'] or '*', item['candidate_key'])).fetchone()
            if old:
                candidate = json.loads(old['data'])
                source = {'report_id': wire['report_id'], 'sha256': report_hash(wire), 'stage': wire['stage']}
                sources = candidate.setdefault('source_refs', [])
                if source not in sources:
                    sources.append(source)
                    candidate.setdefault('history', []).append({'type': 'REPORTED_AGAIN', 'source': source, 'request': item, 'at': now()})
                    previous_request = candidate.get('last_reported_request', candidate)
                    materially_changed = any(previous_request.get(key) != item[key] for key in ['question', 'options', 'blocking']) or any(set(previous_request.get(key, [])) != set(item[key]) for key in ['affected_module_ids', 'affected_stages'])
                    source_changed = candidate.get('source_context') != context
                    linked_applied = next((decision for decision in job['decisions'] if decision['id'] == candidate.get('decision_id') and decision['status'] == 'APPLIED'), None)
                    reopen = materially_changed or source_changed or bool(linked_applied and not satisfied_candidate_decision(job, candidate))
                    if reopen:
                        candidate['history'].append({'type': 'JUDGMENT_REOPENED', 'previous_status': candidate['status'], 'previous_decision_id': candidate.get('decision_id'), 'previous_report_id': candidate['report_id'], 'previous_source_context': candidate.get('source_context'), 'source': source, 'at': now()})
                        candidate['affected_module_ids'] = sorted(set(candidate['affected_module_ids']) | set(item['affected_module_ids']))
                        candidate['affected_stages'] = sorted(set(candidate['affected_stages']) | set(item['affected_stages']))
                        candidate['blocking'] = candidate['blocking'] or item['blocking']
                        candidate.update(question=item['question'], options=item['options'], recommendation=item['recommendation'], status='OPEN', decision_id=None, source_context=context, report_id=wire['report_id'])
                        self.engine.orchestration.enqueue(c, job, 'DECISION_REQUESTED', candidate['id'] + ':' + wire['report_id'])
                    candidate['last_reported_request'] = item
                    if candidate['blocking'] and candidate['status'] != 'DISMISSED' and not satisfied_candidate_decision(job, candidate):
                        self._candidate_hold(c, job, candidate)
                    c.execute('UPDATE decision_candidates SET report_id=?,status=?,decision_id=?,data=? WHERE id=?', (candidate['report_id'], candidate['status'], candidate.get('decision_id'), json.dumps(candidate), old['id']))
                self.engine.store.audit(c, job, 'CANDIDATE_REPEAT', {'candidate_id': old['id'], 'report_id': wire['report_id']})
                continue
            identifier = uid()
            data = dict(item, id=identifier, job_id=job['id'], report_id=wire['report_id'], module_id=wire['module_id'], status='OPEN', decision_id=None, source_context=context, last_reported_request=item, source_refs=[{'report_id': wire['report_id'], 'sha256': report_hash(wire), 'stage': wire['stage']}], history=[], created_at=now())
            c.execute('INSERT INTO decision_candidates VALUES(?,?,?,?,?,?,?,?)', (identifier, job['id'], wire['report_id'], item['candidate_key'], wire['module_id'] or '*', 'OPEN', None, json.dumps(data)))
            if item['blocking']:
                self._candidate_hold(c, job, data)
            self.engine.orchestration.enqueue(c, job, 'DECISION_REQUESTED', identifier)

    def _candidate_hold(self, c, job, candidate):
        affected = set(candidate['affected_module_ids'])
        while True:
            expanded = affected | {module['id'] for module in job['modules'] if set(module.get('dependency_module_ids', [])) & affected}
            if expanded == affected:
                break
            affected = expanded
        existing = c.execute("SELECT id,data FROM scope_holds WHERE candidate_id=? AND status='ACTIVE'", (candidate['id'],)).fetchone()
        if existing:
            hold = json.loads(existing['data'])
            hold['module_ids'] = sorted(set(hold['module_ids']) | affected)
            hold['stages'] = sorted(set(hold['stages']) | set(candidate['affected_stages']))
            c.execute('UPDATE scope_holds SET data=? WHERE id=?', (json.dumps(hold), existing['id']))
        else:
            hold = {'id': uid(), 'candidate_id': candidate['id'], 'module_ids': sorted(affected), 'stages': candidate['affected_stages'], 'reason': candidate['question'], 'status': 'ACTIVE', 'created_at': now()}
            c.execute('INSERT INTO scope_holds VALUES(?,?,?,?,?)', (hold['id'], job['id'], candidate['id'], 'ACTIVE', json.dumps(hold)))

    @staticmethod
    def _page_bounds(limit, before):
        if type(limit) is not int or not 1 <= limit <= 100 or before is not None and (type(before) is not int or before < 1):
            raise Conflict('Pagination requires limit 1..100 and a positive before cursor.', status=422)

    def page(self, job_id, limit=50, before=None):
        self._page_bounds(limit, before)
        with self.engine.store.connection() as c:
            if not c.execute('SELECT 1 FROM jobs WHERE id=?', (job_id,)).fetchone():
                raise Conflict('Job not found.', 'NOT_FOUND', 404)
            query = 'SELECT rowid AS cursor,report_id,job_id,attempt_id,module_id,stage,sha256,disposition,created_at FROM agent_reports WHERE job_id=?'
            params = [job_id]
            if before is not None:
                query += ' AND rowid<?'
                params.append(before)
            rows = c.execute(query + ' ORDER BY rowid DESC LIMIT ?', (*params, limit + 1)).fetchall()
            items = [dict(row) for row in reversed(rows[:limit])]
            total = c.execute('SELECT count(*) FROM agent_reports WHERE job_id=?', (job_id,)).fetchone()[0]
            return {'items': items, 'limit': limit, 'next_cursor': items[0]['cursor'] if len(rows) > limit else None, 'total': total}

    def list(self, job_id, limit=50, before=None):
        return self.page(job_id, limit, before)['items']

    def detail(self, job_id, report_id):
        with self.engine.store.connection() as c:
            row = c.execute('SELECT * FROM agent_reports WHERE job_id=? AND report_id=?', (job_id, report_id)).fetchone()
            return dict(row) | {'data': json.loads(row['data'])} if row else None
