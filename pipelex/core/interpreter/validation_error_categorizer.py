import re
from typing import Any, cast

from pydantic_core import ErrorDetails

from pipelex import log
from pipelex.core.bundles.exceptions import (
    PipelexBundleBlueprintValidationErrorData,
)
from pipelex.core.interpreter.helpers import get_error_scope
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.types import StrEnum


class ErrorCatKey(StrEnum):
    LOC = "loc"
    MSG = "msg"
    TYPE = "type"


PIPELEX_BUNDLE_BLUEPRINT_DOMAIN_FIELD = "domain"
PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD = "source"


def _extract_variable_names_from_message(message: str) -> list[str] | None:
    """Extract variable names from error messages like 'Missing input variable(s): var1, var2.'"""
    # Pattern to match variable names after the colon
    match = re.search(r"variable\(s\):\s*([^.]+)\.", message)
    if match:
        vars_str = match.group(1)
        return [var.strip() for var in vars_str.split(",")]
    return None


def _categorize_input_validation_error(
    message: str,
    domain: str | None,
    source: str | None,
    pipe_code: str | None,
) -> PipelexBundleBlueprintValidationErrorData | None:
    """Categorize input validation errors (missing or unused inputs).

    Args:
        message: The error message from the validation
        domain: Domain code
        source: Source file path
        pipe_code: Pipe code being validated

    Returns:
        Categorized error data, or None if not an input validation error
    """
    message_lower = message.lower()

    # Detect missing input variables
    if "missing input variable" in message_lower:
        variable_names = _extract_variable_names_from_message(message)
        return PipelexBundleBlueprintValidationErrorData(
            error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
            domain_code=domain,
            source=source,
            pipe_code=pipe_code,
            message=message,
            variable_names=variable_names,
        )

    # Detect unused/extraneous input variables
    if "unused input variable" in message_lower:
        variable_names = _extract_variable_names_from_message(message)
        return PipelexBundleBlueprintValidationErrorData(
            error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
            domain_code=domain,
            source=source,
            pipe_code=pipe_code,
            message=message,
            variable_names=variable_names,
        )

    return None


def categorize_blueprint_validation_error(
    blueprint_dict: dict[str, Any],
    error: ErrorDetails,
) -> PipelexBundleBlueprintValidationErrorData | None:
    """Categorize a BLUEPRINT validation error and create structured error data or return None if the error cannot be categorized.

    Args:
        blueprint_dict: The blueprint dict being validated (for context extraction)
        error: Pydantic error from PipelexBundleBlueprint.model_validate()

    Returns:
        PipelexBundleBlueprintValidationErrorData with all relevant fields populated, or None if error cannot be categorized
    """
    domain = cast("str | None", blueprint_dict.get(PIPELEX_BUNDLE_BLUEPRINT_DOMAIN_FIELD)) if blueprint_dict else None
    source = cast("str | None", blueprint_dict.get(PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD)) if blueprint_dict else None

    loc = error.get(ErrorCatKey.LOC.value, ())
    message = error.get(ErrorCatKey.MSG.value, "Unknown validation error")

    # Extract pipe code from location if available (e.g., ('pipes', 'extract_details_of_task', ...))
    pipe_code: str | None = None
    if len(loc) >= 2 and loc[0] == "pipes":
        pipe_code = str(loc[1])

    # Try to categorize input validation errors (missing/unused inputs)
    input_error = _categorize_input_validation_error(
        message=message,
        domain=domain,
        source=source,
        pipe_code=pipe_code,
    )
    if input_error:
        return input_error

    # If we couldn't categorize the error, log a warning
    error_scope = get_error_scope(loc)
    log.warning(f"Pipelex bundle blueprint validation error that is not categorized: {error_scope} - {source} - {domain}")

    return None
