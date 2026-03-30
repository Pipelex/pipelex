"""Helpers for structured JSON output in agent CLI commands."""

import sys
import traceback
from typing import Any, NoReturn

import typer

from pipelex.pipeline.validate_bundle import ValidateBundleError
from pipelex.tools.misc.json_utils import clean_json_dumps
from pipelex.types import StrEnum


class CliOutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


AGENT_ERROR_HINTS: dict[str, str] = {
    # Model/routing errors
    "ModelChoiceNotFoundError": (
        "Check model name for typos. Use 'pipelex-agent check-model <name> -t <type>' "
        "to validate or 'pipelex-agent models -t <type>' to list available models."
    ),
    "PipeOperatorModelChoiceError": "Run 'pipelex-agent doctor' to check available models and routing configuration",
    "PipeOperatorModelAvailabilityError": "Run 'pipelex-agent doctor' to check available models and verify API keys",
    "ModelDeckPresetValidatonError": (
        "Run 'pipelex-agent doctor' to check model configuration. "
        "Update the preset model, configure it in an enabled backend, or enable a supporting backend"
    ),
    # Validation errors
    "ValidateBundleError": "Check the 'validation_errors' array for specific issues to fix",
    "PipeValidationError": "Check pipe inputs, outputs, and concept references for consistency",
    # Execution errors
    "PipelineExecutionError": "Check 'pipe_stack' to identify which pipe failed and 'cause_type' for the root cause",
    "PipeExecutionError": "A pipe input validation failed during pipeline execution. Check the error message for the failing model and field.",
    # File/input errors
    "FileNotFoundError": "Verify the file path exists and is accessible from the current working directory",
    "ArgumentError": "Check command usage with 'pipelex-agent <command> --help'",
    "JSONDecodeError": "Verify the JSON input is valid (check for trailing commas, unquoted keys, etc.)",
    # Interpreter errors
    "PipelexInterpreterError": "Check MTHDS file TOML syntax and ensure all referenced concepts and pipes are defined",
    "MthdsDecodeError": "The MTHDS file has TOML syntax errors; validate TOML syntax before retrying",
    # Configuration/initialization errors
    "TelemetryConfigValidationError": "Run 'pipelex init telemetry' to create a valid telemetry configuration",
    "GatewayTermsNotAcceptedError": "Run 'pipelex init config' to accept gateway terms, or disable pipelex_gateway in backends.toml",
    "GatewayApiKeyMissingError": "Set the PIPELEX_GATEWAY_API_KEY environment variable, or disable pipelex_gateway in backends.toml",
    "GatewayDoNotTrackConflictError": "Unset the DO_NOT_TRACK environment variable, or disable pipelex_gateway in backends.toml",
    "BinaryNotFoundError": "Install pipelex-tools: uv tool install pipelex-tools",
    "RemoteConfigFetchError": "Check internet connection and firewall settings, or disable pipelex_gateway in backends.toml",
    "RemoteConfigValidationError": (
        "This is a server-side issue; report it on Discord/GitHub. Disable pipelex_gateway in backends.toml as a workaround"
    ),
    # API runner errors
    "ClientAuthenticationError": "Run 'pipelex-agent doctor' to check credentials, or set the PIPELEX_API_KEY environment variable",
    "PipelineRequestError": "Check that pipe_code or mthds_contents is provided",
    # Graph errors
    "GraphSpecParseError": "Validate graphspec.json structure; ensure it matches the expected GraphSpec schema",
    # Input/type errors
    "JsonTypeError": "Input file must be a JSON object {...}, not an array or scalar value",
    "BundleError": "Bundle must declare a 'main_pipe' or use the --pipe flag to specify which pipe to run",
    "ValidationError": "Check that spec fields match the expected schema for the given type",
    "ValueError": "Check that the provided value is valid for the parameter (e.g., --type must be a valid pipe type)",
    # Init errors
    "InitConfigError": "Check the --config JSON and ensure backend keys match available backends in the template",
    # Unknown command
    "UnknownCommandError": "Check 'valid_commands' in this error response for available commands",
}

RETRYABLE_ERROR_TYPES: set[str] = {
    "RemoteConfigFetchError",
    "PipeOperatorModelAvailabilityError",
}

AGENT_ERROR_DOMAINS: dict[str, str] = {
    # input = agent can fix (bad .mthds, wrong args, bad JSON)
    "ModelChoiceNotFoundError": "input",
    "ValidateBundleError": "input",
    "PipeValidationError": "input",
    "FileNotFoundError": "input",
    "JSONDecodeError": "input",
    "JsonTypeError": "input",
    "ArgumentError": "input",
    "MthdsDecodeError": "input",
    "PipelexInterpreterError": "input",
    "ValidationError": "input",
    "ValueError": "input",
    "BundleError": "input",
    "PipelineRequestError": "input",
    "GraphSpecParseError": "input",
    "UnknownCommandError": "input",
    # config = environment/config changes needed
    "ClientAuthenticationError": "config",
    "PipeOperatorModelChoiceError": "config",
    "PipeOperatorModelAvailabilityError": "config",
    "ModelDeckPresetValidatonError": "config",
    "TelemetryConfigValidationError": "config",
    "GatewayTermsNotAcceptedError": "config",
    "GatewayApiKeyMissingError": "config",
    "GatewayDoNotTrackConflictError": "config",
    "RemoteConfigFetchError": "config",
    "BinaryNotFoundError": "config",
    "RemoteConfigValidationError": "config",
    "InitConfigError": "config",
    # runtime = execution failure
    "PipelineExecutionError": "runtime",
    "PipeExecutionError": "runtime",
}


def _build_error_source(exc: BaseException) -> list[str]:
    """Build a compact source trace from an exception's cause chain.

    Each entry shows where the exception was raised:
    ``"ExceptionType @ module:line (in function)"``.

    Args:
        exc: The exception (walks ``__cause__`` chain).

    Returns:
        List of source location strings, outermost first.
    """
    sources: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        if current.__traceback__ is None:
            sources.append(f"{type(current).__name__} (no traceback)")
            current = current.__cause__
            continue
        tbe = traceback.extract_tb(current.__traceback__)
        if tbe:
            frame = tbe[-1]  # default fallback
            for candidate in reversed(tbe):
                if "/pipelex/" in candidate.filename and "/.venv/" not in candidate.filename:
                    frame = candidate
                    break
            location = f"{type(current).__name__} @ {frame.filename}:{frame.lineno} (in {frame.name})"
            sources.append(location)
        else:
            sources.append(f"{type(current).__name__} (no traceback)")
        current = current.__cause__
    return sources


def agent_error(message: str, error_type: str, cause: BaseException | None = None, **extra: Any) -> NoReturn:
    """Print a structured JSON error to stderr and exit with code 1.

    Args:
        message: Human-readable error message.
        error_type: Error class name for programmatic matching.
        cause: Optional exception to chain with ``raise ... from``.
        **extra: Additional fields merged into the JSON object.
                 Can override the auto-added ``hint`` field.
    """
    error_json: dict[str, Any] = {
        "error": True,
        "error_type": error_type,
        "message": message,
    }
    hint = AGENT_ERROR_HINTS.get(error_type)
    if hint:
        error_json["hint"] = hint
    if error_type in RETRYABLE_ERROR_TYPES:
        error_json["retryable"] = True
    domain = AGENT_ERROR_DOMAINS.get(error_type)
    if domain:
        error_json["error_domain"] = domain
    if cause is not None:
        error_json["error_source"] = _build_error_source(cause)
    error_json.update(extra)
    print(clean_json_dumps(error_json, indent=2), file=sys.stderr)
    raise typer.Exit(1) from cause


def agent_success(result: dict[str, Any]) -> None:
    """Print a structured JSON success result to stdout.

    Args:
        result: Dictionary to serialize as JSON.
    """
    print(clean_json_dumps(result, indent=2))


def extract_validation_errors(exc: ValidateBundleError) -> list[dict[str, Any]]:
    """Extract all validation error categories from a ValidateBundleError into a flat list.

    Covers all 4 error sources:
    - Blueprint validation errors (from interpreter)
    - Pipe factory errors (e.g., missing concepts)
    - Pipe validation errors (e.g., missing inputs, type mismatches)
    - Pipe/concept instantiation errors (from Pydantic validation during factory)

    Each entry includes a ``category`` field identifying its source.

    Args:
        exc: The ValidateBundleError to extract errors from.

    Returns:
        List of dicts, each with at minimum ``category``, ``error_type``, and ``message``.
    """
    validation_errors: list[dict[str, Any]] = []

    for blueprint_error in exc.pipelex_bundle_blueprint_validation_errors:
        entry: dict[str, Any] = {
            "category": "blueprint_validation",
            "error_type": str(blueprint_error.error_type) if blueprint_error.error_type else None,
            "pipe_code": blueprint_error.pipe_code,
            "message": blueprint_error.message,
        }
        if blueprint_error.domain_code:
            entry["domain_code"] = blueprint_error.domain_code
        if blueprint_error.variable_names:
            entry["variable_names"] = blueprint_error.variable_names
        validation_errors.append(entry)

    for factory_error in exc.pipe_factory_errors:
        entry = {
            "category": "pipe_factory",
            "error_type": str(factory_error.error_type),
            "pipe_code": factory_error.pipe_code,
            "message": factory_error.message,
        }
        if factory_error.domain_code:
            entry["domain_code"] = factory_error.domain_code
        if factory_error.missing_concept_code:
            entry["missing_concept_code"] = factory_error.missing_concept_code
        if factory_error.declared_concepts:
            entry["declared_concepts"] = factory_error.declared_concepts
        validation_errors.append(entry)

    for pipe_error in exc.pipe_validation_errors:
        entry = {
            "category": "pipe_validation",
            "error_type": str(pipe_error.error_type),
            "pipe_code": pipe_error.pipe_code,
            "message": pipe_error.message,
        }
        if pipe_error.domain_code:
            entry["domain_code"] = pipe_error.domain_code
        if pipe_error.concept_code:
            entry["concept_code"] = pipe_error.concept_code
        if pipe_error.field_path:
            entry["field_path"] = pipe_error.field_path
        if pipe_error.variable_names:
            entry["variable_names"] = pipe_error.variable_names
        validation_errors.append(entry)

    for instantiation_error in exc.pipe_concept_instantiation_errors:
        entry = {
            "category": "instantiation",
            "error_type": str(instantiation_error.error_type),
            "pipe_code": instantiation_error.pipe_code,
            "message": instantiation_error.message,
        }
        if instantiation_error.domain_code:
            entry["domain_code"] = instantiation_error.domain_code
        if instantiation_error.concept_code:
            entry["concept_code"] = instantiation_error.concept_code
        if instantiation_error.field_path:
            entry["field_path"] = instantiation_error.field_path
        if instantiation_error.variable_names:
            entry["variable_names"] = instantiation_error.variable_names
        validation_errors.append(entry)

    return validation_errors
