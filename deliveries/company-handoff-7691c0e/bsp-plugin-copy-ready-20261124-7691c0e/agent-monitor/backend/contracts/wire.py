"""Strict, bounded JSON contracts, separate from adapter-owned transport observations."""
import hashlib
import json
import math
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

MAX_WIRE_BYTES = 1_048_576
MAX_DEPTH = 40
Text = Annotated[str, Field(min_length=1, max_length=16000, pattern=r'\S')]
Identifier = Annotated[str, Field(min_length=1, max_length=256, pattern=r'\S')]
Sha = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Stage = Literal['analysis', 'design', 'code', 'build', 'review', 'verification', 'integration']
AffectedStage = Literal['analysis', 'design', 'code', 'build', 'review', 'verification', 'device_test', 'integration']
ROLE_STAGE = {'analyst': 'analysis', 'designer': 'design', 'implementer': 'code', 'builder': 'build',
              'reviewer': 'review', 'verifier': 'verification', 'integration': 'integration'}
Role = Literal['analyst', 'designer', 'implementer', 'builder', 'reviewer', 'verifier', 'integration']


class ContractError(ValueError):
    def __init__(self, code='CONTRACT', field_path='$', safe_message='Wire contract validation failed.'):
        self.code, self.field_path, self.safe_message = code, field_path, safe_message
        super().__init__(safe_message)


def _shape(value, depth=0):
    if depth > MAX_DEPTH:
        raise ContractError(field_path='$', safe_message='JSON nesting limit exceeded.')
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ContractError(safe_message='JSON object keys must be strings.')
        for child in value.values():
            _shape(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _shape(child, depth + 1)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ContractError(safe_message='Non-finite JSON number rejected.')
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ContractError(safe_message='Unsupported JSON value.')


def canonical_json(value):
    _shape(value)
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ContractError(safe_message='Cannot encode canonical JSON.') from None


def report_hash(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def parse_json(raw, max_bytes=MAX_WIRE_BYTES):
    limit = max_bytes
    if isinstance(raw, dict):
        if len(canonical_json(raw)) > limit:
            raise ContractError(safe_message='JSON size limit exceeded.')
        return raw
    if not isinstance(raw, (str, bytes, bytearray)):
        raise ContractError(safe_message='Expected a JSON object.')
    if len(raw.encode('utf-8') if isinstance(raw, str) else raw) > limit:
        raise ContractError(safe_message='JSON size limit exceeded.')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError(safe_message='Duplicate JSON key rejected.')
            result[key] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ContractError()))
        _shape(result)
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError(safe_message='Invalid or unsafe JSON.') from None
    if not isinstance(result, dict):
        raise ContractError(safe_message='Expected a JSON object.')
    return result


class Closed(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)

    @model_validator(mode='before')
    @classmethod
    def strict_version(cls, value):
        if isinstance(value, dict) and 'schema_version' in value and type(value['schema_version']) is not int:
            raise ValueError('schema_version must be a JSON integer.')
        return value


class ResultRef(Closed):
    report_id: Identifier
    sha256: Sha


class EvidenceRef(Closed):
    path: Text
    sha256: Sha
    kind: Literal['report', 'log', 'diff', 'image']


class TestResult(Closed):
    case_id: Identifier
    status: Literal['PASS', 'FAIL', 'NOT_RUN']
    source_revision: Text
    artifact_sha256: Sha | None
    evidence_paths: list[Text] = Field(max_length=1000)


class DecisionRequest(Closed):
    candidate_key: Identifier
    question: Text
    options: list[Text] = Field(min_length=2, max_length=30)
    recommendation: Text
    affected_module_ids: list[Identifier] = Field(max_length=1000)
    affected_stages: list[AffectedStage] = Field(min_length=1, max_length=8)
    blocking: bool
    evidence_paths: list[Text] = Field(max_length=1000)

    @model_validator(mode='after')
    def distinct_options(self):
        if len(set(self.options)) != len(self.options):
            raise ValueError('Decision options must be distinct.')
        return self


class Details(Closed):
    unavailable_reasons: dict[Identifier, Text] = Field(default_factory=dict, max_length=30)


class VendorChange(Closed):
    change_id: Identifier
    disposition: Literal['already_upstream', 'port_required', 'excluded', 'needs_decision']
    rationale: Text
    affected_files: list[Text]
    dependency_module_ids: list[Identifier]
    required_cases: list[Identifier]
    decision_id: Identifier | None = None


class AnalysisDetails(Details):
    vendor_changes: list[VendorChange] | None


class VerificationCase(Closed):
    case_id: Identifier
    method: Text
    expected_result: Text


class DesignDetails(Details):
    design_summary: Text | None
    target_files: list[Text] | None
    interface_impacts: list[Text] | None
    dependency_module_ids: list[Identifier] | None
    verification_plan: list[VerificationCase] | None


class DifficultyEvidence(Closed):
    reason: Text
    evidence_paths: list[Text] = Field(min_length=1, max_length=1000)


class CodeDetails(Details):
    changed_files: list[Text] | None
    diff_path: Text | None
    fix_description: Text | None
    previous_attempt_difference: Text | None
    difficulty_evidence: DifficultyEvidence | None = None


class BuildDetails(Details):
    build_profile: Text | None
    command_summary: Text | None
    exit_code: int | None
    target_description: Text | None


class Finding(Closed):
    severity: Literal['critical', 'high', 'medium', 'low', 'info', 'BLOCKER', 'MAJOR', 'MINOR', 'INFO']
    location: Text
    description: Text
    recommendation: Text
    evidence_paths: list[Text]


class ReviewDetails(Details):
    reviewed_source_revision: Text | None
    reviewed_diff_sha256: Sha | None
    findings: list[Finding] | None


class VerificationDetails(Details):
    verification_scope: Text | None
    required_case_ids: list[Identifier] | None
    limitations: list[Text] | None


class IncludedModule(Closed):
    module_id: Identifier
    source_revision: Text
    report_id: Identifier


class IntegrationDetails(Details):
    included_modules: list[IncludedModule] | None
    build_profile: Text | None
    required_case_ids: list[Identifier] | None
    limitations: list[Text] | None


DETAILS = dict(zip(ROLE_STAGE.values(), (AnalysisDetails, DesignDetails, CodeDetails, BuildDetails, ReviewDetails, VerificationDetails, IntegrationDetails)))


class Report(Closed):
    summary: Text
    details: AnalysisDetails | DesignDetails | CodeDetails | BuildDetails | ReviewDetails | VerificationDetails | IntegrationDetails
    evidence_refs: list[EvidenceRef] = Field(max_length=1000)
    test_results: list[TestResult] = Field(max_length=2000)
    decision_requests: list[DecisionRequest] = Field(max_length=100)


class Artifact(Closed):
    path: Text
    sha256: Sha


class ModuleResult(Closed):
    schema_version: Literal[2]
    message_type: Literal['module_result']
    job_id: Identifier
    module_id: Identifier | None
    stage: Stage
    attempt_id: Identifier
    session_id: Identifier
    report_id: Identifier
    plan_version: int = Field(ge=1)
    fingerprint: Identifier
    input_result_refs: list[ResultRef] = Field(max_length=2000)
    source_revision: Text | None
    outcome: Literal['SUCCEEDED', 'FAILED']
    evidence: Text
    error_class: Literal['', 'FIX', 'ENVIRONMENT', 'CONTRACT', 'ARTIFACT', 'DEPENDENCY', 'REVIEW'] = ''
    cause_key: str = Field(default='', max_length=256)
    artifact: Artifact | None = None
    report: Report

    @model_validator(mode='before')
    @classmethod
    def role_details(cls, value):
        if isinstance(value, dict) and value.get('stage') in DETAILS and isinstance(value.get('report'), dict):
            value = dict(value)
            value['report'] = dict(value['report'])
            value['report']['details'] = DETAILS[value['stage']].model_validate(value['report'].get('details'))
        return value

    @model_validator(mode='after')
    def semantics(self):
        if (self.module_id is None) != (self.stage == 'integration'):
            raise ValueError('Only integration uses a null module_id.')
        success = self.outcome == 'SUCCEEDED'
        details = self.report.details
        unavailable = details.unavailable_reasons
        for field in type(details).model_fields:
            if field == 'unavailable_reasons':
                continue
            if not type(details).model_fields[field].is_required() and field not in details.model_fields_set:
                continue
            if field == 'difficulty_evidence' and getattr(details, field) is None:
                continue
            if getattr(details, field) is None and (success or not unavailable.get(field)):
                raise ValueError('Unavailable fields require a failure and an explicit reason.')
        allowed_reasons = set(type(details).model_fields) | {'source_revision'}
        if set(unavailable) - allowed_reasons or any(getattr(details, key, None) is not None for key in unavailable if key != 'source_revision'):
            raise ValueError('Unavailable reason must identify a null field.')
        if self.source_revision is None and (success or not unavailable.get('source_revision')):
            raise ValueError('Source identity is required or explicitly unavailable on failure.')
        if success and (self.error_class or self.cause_key or unavailable):
            raise ValueError('Success cannot carry failure classification.')
        if not success and not self.error_class:
            raise ValueError('Failure requires error_class.')
        if self.error_class == 'FIX' and (self.stage != 'code' or not self.cause_key.strip()):
            raise ValueError('Only code FIX failures require a stable cause key.')
        paths = [e.path for e in self.report.evidence_refs]
        if len(set(paths)) != len(paths):
            raise ValueError('Duplicate evidence path.')
        for item in [*self.report.test_results, *self.report.decision_requests]:
            if not set(item.evidence_paths) <= set(paths):
                raise ValueError('Evidence path was not registered.')
        if self.stage == 'code' and details.difficulty_evidence is not None and not set(details.difficulty_evidence.evidence_paths) <= set(paths):
            raise ValueError('Difficulty evidence path was not registered.')
        cases = [case.case_id for case in self.report.test_results]
        if len(set(cases)) != len(cases):
            raise ValueError('Duplicate test case.')
        if success and self.stage == 'build' and (self.artifact is None or details.exit_code != 0):
            raise ValueError('Build success requires an artifact and exit code zero.')
        if success and self.stage in {'verification', 'integration'}:
            results = {case.case_id: case for case in self.report.test_results}
            if any(case not in results or results[case].status != 'PASS' or results[case].source_revision != self.source_revision for case in details.required_case_ids):
                raise ValueError('All required cases must pass on the current source.')
        if self.stage == 'code' and details.diff_path is not None:
            if details.diff_path not in {e.path for e in self.report.evidence_refs if e.kind == 'diff'}:
                raise ValueError('Code diff must be a registered diff evidence file.')
        return self


class ModuleRequest(Closed):
    schema_version: Literal[2]
    message_type: Literal['module_request']
    job_id: Identifier
    module_id: Identifier | None
    stage: Stage
    attempt_id: Identifier
    session_id: Identifier
    report_id: Identifier
    plan_version: int = Field(ge=1)
    fingerprint: Identifier
    role: Role
    source_revision: Text
    input_result_refs: list[ResultRef]
    report_expectations: dict
    module: dict | None = None
    model_policy: str = 'configured'
    source_paths: dict[str, str] = Field(default_factory=dict)
    implementation: dict | None = None
    resume_external_id: str | None = None

    @model_validator(mode='after')
    def stage_matches_role(self):
        if ROLE_STAGE[self.role] != self.stage:
            raise ValueError('Stage and role mismatch.')
        return self


Trigger = Literal['JOB_STARTED', 'ANALYSIS_SET_COMPLETED', 'ATTEMPT_FAILED', 'DECISION_REQUESTED', 'PLAN_OR_SOURCE_CHANGED', 'DEPENDENCY_CHANGED', 'DECISION_UPDATED', 'INTEGRATION_FINISHED', 'USER_REPLAN_REQUESTED']


class OrchestrationRequest(Closed):
    schema_version: Literal[1]
    message_type: Literal['orchestration_request']
    stage: Literal['orchestrate']
    job_id: Identifier
    orchestration_run_id: Identifier
    session_id: Identifier
    trigger_ids: list[Identifier] = Field(min_length=1, max_length=1000)
    trigger_types: list[Trigger] = Field(min_length=1, max_length=1000)
    base_state_version: int = Field(ge=0)
    plan_version: int = Field(ge=1)
    fingerprint: Identifier
    snapshot: dict
    result_refs: list[ResultRef]
    constraints: dict
    request: str | None


class Target(Closed):
    module_ids: list[Identifier]
    stage: AffectedStage | None


class PlanModule(Closed):
    name: Text
    stable_key: Identifier
    group: Literal['boot', 'main']
    target_paths: list[Text]
    dependency_module_ids: list[Identifier]
    required_cases: list[VerificationCase]
    completion_conditions: list[Text]


class PlanChange(Closed):
    operation: Literal['add', 'update', 'deactivate']
    module_id: Identifier | None
    new_module_key: Identifier | None
    before: PlanModule | None
    after: PlanModule | None
    reason: Text

    @model_validator(mode='after')
    def identifiers(self):
        if self.operation == 'add':
            if self.module_id is not None or self.new_module_key is None or self.before is not None or self.after is None:
                raise ValueError('Invalid add operation.')
        elif self.module_id is None or self.new_module_key is not None or self.before is None or (self.operation == 'update' and self.after is None):
            raise ValueError('Invalid existing module operation.')
        return self


class PlanData(Closed):
    base_plan_version: int = Field(ge=1)
    changes: list[PlanChange] = Field(min_length=1, max_length=100)


class RetryData(Closed):
    previous_attempt_id: Identifier
    cause_key: Identifier
    changed_approach: Text


class EscalationData(Closed):
    previous_attempt_id: Identifier
    cause_key: Identifier
    requested_tool: Literal['claude']
    model_policy: Literal['opus']
    evidence: Text


class DecisionData(Closed):
    candidate_ids: list[Identifier] = Field(min_length=1)
    question: Text
    options: list[Text] = Field(min_length=2)
    recommendation: Text
    affected_stages: list[AffectedStage] = Field(min_length=1)
    blocking: bool


class VerificationData(Closed):
    source_revision: Text
    artifact: Artifact | None
    cases: list[VerificationCase] = Field(min_length=1)


PROPOSAL_DATA = {'PLAN_CHANGE': PlanData, 'RETRY': RetryData, 'TOOL_ESCALATION': EscalationData, 'DECISION': DecisionData, 'VERIFICATION_PLAN': VerificationData}


class Proposal(Closed):
    proposal_key: Identifier
    kind: Literal['PLAN_CHANGE', 'RETRY', 'TOOL_ESCALATION', 'DECISION', 'VERIFICATION_PLAN']
    target: Target
    reason: Text
    evidence_refs: list[ResultRef]
    data: PlanData | RetryData | EscalationData | DecisionData | VerificationData

    @model_validator(mode='before')
    @classmethod
    def kind_data(cls, value):
        if isinstance(value, dict) and value.get('kind') in PROPOSAL_DATA:
            value = dict(value)
            value['data'] = PROPOSAL_DATA[value['kind']].model_validate(value.get('data'))
        return value


class OrchestrationResult(Closed):
    schema_version: Literal[1]
    message_type: Literal['orchestration_result']
    job_id: Identifier
    orchestration_run_id: Identifier
    session_id: Identifier
    trigger_ids: list[Identifier] = Field(min_length=1)
    base_state_version: int = Field(ge=0)
    plan_version: int = Field(ge=1)
    fingerprint: Identifier
    outcome: Literal['SUCCEEDED', 'FAILED']
    summary: Text
    result_refs: list[ResultRef]
    proposals: list[Proposal] = Field(max_length=100)
    error_class: Literal['', 'ENVIRONMENT', 'CONTRACT', 'INSUFFICIENT_EVIDENCE'] = ''

    @model_validator(mode='after')
    def semantics(self):
        if self.outcome == 'FAILED' and (not self.error_class or self.proposals):
            raise ValueError('Failed orchestration cannot propose actions.')
        if self.outcome == 'SUCCEEDED' and self.error_class:
            raise ValueError('Success cannot carry an error class.')
        keys = [proposal.proposal_key for proposal in self.proposals]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate proposal key.')
        return self


class CapabilityDocument(Closed):
    schema_version: Literal[1]
    module_report_versions: list[Literal[1, 2]]
    orchestration_versions: list[Literal[1]]
    roles: list[Literal['analyst', 'designer', 'implementer', 'builder', 'reviewer', 'verifier', 'integration', 'orchestrator']]
    command_result_versions: list[Literal[1]] = Field(default_factory=list)


class CommandResult(ModuleResult):
    schema_version: Literal[1]
    message_type: Literal['command_result']
    stage: Literal['build', 'verification', 'integration']


def _validate(model, raw):
    try:
        data = parse_json(raw)
        return model.model_validate(data).model_dump(mode='json', exclude_unset=True)
    except ValidationError as exc:
        location = '.'.join(str(part) for part in exc.errors()[0]['loc'])
        raise ContractError(field_path=location or '$', safe_message='Wire fields or completion requirements are invalid.') from None


def _correlate(data, expected, fields):
    for key in fields:
        if key not in expected or data.get(key) != expected[key]:
            raise ContractError(field_path=key, safe_message='Result correlation does not match the frozen request.')


MODULE_IDS = ('job_id', 'module_id', 'stage', 'attempt_id', 'session_id', 'report_id', 'plan_version', 'fingerprint', 'input_result_refs')


def validate_legacy_result(raw):
    """Reject a different explicit wire protocol before any v1 normalization.

    Original v1 results are unversioned. An explicit integer version 1 is also
    accepted, but message_type belongs to the newer named wire protocols and has
    no meaning in v1. This guard deliberately applies to failures as well as
    successes so mismatched reports cannot acquire legacy FIX semantics.
    """
    if not isinstance(raw, dict):
        raise ContractError(safe_message='Legacy result must be an object.')
    if 'schema_version' in raw and (type(raw['schema_version']) is not int or raw['schema_version'] != 1):
        raise ContractError(field_path='schema_version', safe_message='Explicit result version does not match the negotiated v1 protocol.')
    if 'message_type' in raw:
        raise ContractError(field_path='message_type', safe_message='Named result protocol does not match the negotiated legacy v1 protocol.')
    return raw


def validate_module_result(raw, expected):
    data = _validate(ModuleResult, raw)
    _correlate(data, expected, MODULE_IDS)
    refs = [ref['report_id'] for ref in data['input_result_refs']]
    if len(refs) != len(set(refs)) or data['report_id'] in refs:
        raise ContractError(field_path='input_result_refs', safe_message='Input references must be unique prior reports.')
    if data['stage'] != 'code' and data['source_revision'] is not None and data['source_revision'] != expected.get('source_revision'):
        raise ContractError(field_path='source_revision', safe_message='Result source does not match the requested source.')
    implementation = expected.get('implementation')
    if data['stage'] == 'review' and implementation:
        if data['session_id'] == implementation.get('session_id') or data['report_id'] == implementation.get('report_id'):
            raise ContractError(safe_message='Review must use its own session and report ID.')
        details = data['report']['details']
        if data['outcome'] == 'SUCCEEDED' and (details['reviewed_source_revision'] != implementation['source_revision'] or details['reviewed_diff_sha256'] != expected.get('report_expectations', {}).get('reviewed_diff_sha256')):
            raise ContractError(safe_message='Review revision or diff does not match implementation.')
    return data


def validate_orchestration_result(raw, expected):
    data = _validate(OrchestrationResult, raw)
    _correlate(data, expected, ('job_id', 'orchestration_run_id', 'session_id', 'trigger_ids', 'base_state_version', 'plan_version', 'fingerprint'))
    allowed = {canonical_json(ref) for ref in expected.get('result_refs', [])}
    if any(canonical_json(ref) not in allowed for ref in data['result_refs']):
        raise ContractError(field_path='result_refs', safe_message='Unknown input result reference.')
    for proposal in data['proposals']:
        if any(canonical_json(ref) not in allowed for ref in proposal['evidence_refs']):
            raise ContractError(field_path='proposals.evidence_refs', safe_message='Unknown proposal evidence reference.')
    return data


def validate_command_result(raw, expected):
    data = _validate(CommandResult, raw)
    _correlate(data, expected, MODULE_IDS)
    if data['source_revision'] != expected['source_revision']:
        raise ContractError('DEPENDENCY', 'source_revision', 'Command result source is not current.')
    return data


def schema_for_request(request):
    model = OrchestrationResult if request.get('message_type') == 'orchestration_request' else ModuleResult
    schema = model.model_json_schema()
    if model is OrchestrationResult:
        schema['$defs']['Proposal']['allOf'] = [{'if': {'properties': {'kind': {'const': kind}}},
            'then': {'properties': {'data': {'$ref': '#/$defs/' + data_model.__name__}}}} for kind, data_model in PROPOSAL_DATA.items()]
    for key in (('job_id', 'orchestration_run_id', 'session_id', 'trigger_ids', 'base_state_version', 'plan_version', 'fingerprint') if model is OrchestrationResult else MODULE_IDS):
        if key in request:
            schema['properties'][key] = {'const': request[key]}
    if model is ModuleResult and request.get('stage') in DETAILS:
        detail_schema = DETAILS[request['stage']].model_json_schema(ref_template='#/$defs/{model}')
        schema['$defs'].update(detail_schema.pop('$defs', {}))
        schema['$defs']['Report']['properties']['details'] = detail_schema
    return schema


def write_schemas(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    models = {'module-request-v2': ModuleRequest, 'module-result-v2': ModuleResult,
              'orchestration-request-v1': OrchestrationRequest, 'orchestration-result-v1': OrchestrationResult,
              'adapter-capabilities-v1': CapabilityDocument, 'command-result-v1': CommandResult}
    for name, model in models.items():
        schema = model.model_json_schema()
        schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
        schema['$id'] = name + '.schema.json'
        if model in {ModuleResult, CommandResult}:
            schema['allOf'] = []
            for stage, detail_model in DETAILS.items():
                if model is CommandResult and stage not in {'build', 'verification', 'integration'}:
                    continue
                schema['allOf'].append({'if': {'properties': {'stage': {'const': stage}}},
                    'then': {'properties': {'report': {'properties': {'details': {'$ref': '#/$defs/' + detail_model.__name__}}}}}})
        if model is OrchestrationResult:
            schema['$defs']['Proposal']['allOf'] = [{'if': {'properties': {'kind': {'const': kind}}},
                'then': {'properties': {'data': {'$ref': '#/$defs/' + data_model.__name__}}}} for kind, data_model in PROPOSAL_DATA.items()]
        (folder / (name + '.schema.json')).write_text(json.dumps(schema, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
