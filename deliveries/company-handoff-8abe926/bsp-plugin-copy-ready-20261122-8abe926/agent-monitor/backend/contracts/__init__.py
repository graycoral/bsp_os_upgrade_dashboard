"""Versioned wire contracts. Validation never starts processes or touches the database."""
from .wire import (
    ContractError, canonical_json, report_hash, parse_json, schema_for_request,
    validate_module_result, validate_orchestration_result, validate_command_result,
    ModuleRequest, ModuleResult, OrchestrationRequest, OrchestrationResult,
    CapabilityDocument, CommandResult, write_schemas,
    validate_legacy_result,
)
