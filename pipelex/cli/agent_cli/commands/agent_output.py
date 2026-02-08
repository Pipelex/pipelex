"""Helpers for structured JSON output in agent CLI commands."""

import json
import sys
from typing import Any, NoReturn

import typer

AGENT_ERROR_HINTS: dict[str, str] = {
    "PipeOperatorModelChoiceError": "Run 'pipelex-agent doctor' to check available models and routing configuration",
    "PipeOperatorModelAvailabilityError": "Run 'pipelex-agent doctor' to check available models and verify API keys",
    "ValidateBundleError": "Check the 'validation_errors' array for specific issues to fix",
}


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
    error_json.update(extra)
    print(json.dumps(error_json, indent=2), file=sys.stderr)
    raise typer.Exit(1) from cause


def agent_success(result: dict[str, Any]) -> None:
    """Print a structured JSON success result to stdout.

    Args:
        result: Dictionary to serialize as JSON.
    """
    print(json.dumps(result, indent=2))
