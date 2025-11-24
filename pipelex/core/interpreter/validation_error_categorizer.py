from typing import Any

from pydantic_core import ErrorDetails

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.bundles.exceptions import (
    PipelexBundleBlueprintFixableErrorType,
    PipelexBundleBlueprintValidationErrorData,
)
from pipelex.core.interpreter.helpers import ValidationErrorScope, get_error_scope


def categorize_blueprint_validation_error(
    blueprint_dict: dict[str, Any],
    error: ErrorDetails,
) -> PipelexBundleBlueprintValidationErrorData | None:
    """Categorize a BLUEPRINT validation error and create structured error data or return None if the error is not expected.

    Args:
        blueprint_dict: The blueprint dict being validated (for context extraction)
        error: Pydantic error from PipelexBundleBlueprint.model_validate()

    Returns:
        PipelexBundleBlueprintValidationErrorData with all relevant fields populated

    Raises:
        PipelexUnexpectedError: If the error is not expected
    """
    domain = blueprint_dict.get("domain") if blueprint_dict else None
    source = blueprint_dict.get("source") if blueprint_dict else None

    loc = error.get("loc", ())
    error_scope = get_error_scope(loc)

    if ValidationErrorScope.is_pipe_scope(scope=error_scope):
        return _handle_pipe_errors(
            error=error,
            domain=domain,
            source=source,
            error_scope=error_scope,
        )
    return None


def _handle_pipe_errors(
    error: ErrorDetails,
    domain: str | None,
    source: str | None,
    error_scope: ValidationErrorScope,
) -> PipelexBundleBlueprintValidationErrorData:
    """Handle all PIPE scope validation errors.

    Extracts pipe_code and all other necessary context from error,
    then processes the specific error type.

    Currently only handles PIPE_SEQUENCE_OUTPUT_MISMATCH which is the only
    pipe error that is auto-fixed in the builder loop.

    Args:
        error: Pydantic error details
        domain: Domain where error occurred
        source: Source file path
        error_scope: The error scope (PIPE)

    Returns:
        PipelexBundleBlueprintValidationErrorData with all context populated

    Raises:
        PipelexUnexpectedError: If the error is not a PIPE_SEQUENCE_OUTPUT_MISMATCH
    """
    # Extract data from error
    loc = error.get("loc", ())
    message = error.get("msg", "Unknown validation error")
    pydantic_type = error.get("type", "")
    field_path = " → ".join(str(item) for item in loc)

    # Extract pipe_code from loc[1]
    pipe_code = str(loc[1]) if len(loc) >= 2 else None
    if not pipe_code:
        msg = f"PIPE error without pipe_code: path='{field_path}', message='{message}'"
        raise PipelexUnexpectedError(msg)

    # Extract field_name from loc[2] if present
    field_name = str(loc[2]) if len(loc) >= 3 else None

    # Detect specific error type: PIPE_SEQUENCE_OUTPUT_MISMATCH
    if pydantic_type == "value_error":
        if "concept mismatch" in message.lower() or "not compatible with the output concept" in message:
            return _handle_pipe_sequence_output_mismatch(
                pipe_code=pipe_code,
                field_name=field_name,
                message=message,
                field_path=field_path,
                domain=domain,
                source=source,
                error_scope=error_scope.value,
            )

    # Any other pipe error is unexpected
    msg = (
        f"Unexpected PIPE validation error that cannot be auto-fixed: "
        f"type='{pydantic_type}', pipe_code='{pipe_code}', path='{field_path}', message='{message}'"
    )
    raise PipelexUnexpectedError(msg)


def _handle_pipe_sequence_output_mismatch(
    pipe_code: str,
    field_name: str | None,
    message: str,
    field_path: str,
    domain: str | None,
    source: str | None,
    error_scope: str,
) -> PipelexBundleBlueprintValidationErrorData:
    """Handle PIPE_SEQUENCE_OUTPUT_MISMATCH error and extract all relevant context.

    This is the ONLY error type that is auto-fixed in the builder loop.

    Args:
        pipe_code: The pipe code where the error occurred
        field_name: Field name if applicable
        message: Error message from Pydantic
        field_path: Full field path
        domain: Domain where error occurred
        source: Source file path
        error_scope: Scope of the error

    Returns:
        PipelexBundleBlueprintValidationErrorData with all context populated
    """
    # Extract all context from the message in one go
    last_step_pipe_code: str | None = None
    last_step_output_concept: str | None = None
    expected_output_concept: str | None = None

    if "last step" in message:
        # Extract: "of the last step 'my_pipe'"
        try:
            if "last step '" in message:
                start = message.index("last step '") + len("last step '")
                end = message.index("'", start)
                last_step_pipe_code = message[start:end]
        except (ValueError, IndexError):
            pass

        # Extract: "the output concept 'Text' of the last step"
        try:
            if "output concept '" in message:
                start = message.index("output concept '") + len("output concept '")
                end = message.index("'", start)
                last_step_output_concept = message[start:end]
        except (ValueError, IndexError):
            pass

        # Extract: "with the output concept 'Image' of the sequence"
        try:
            if "with the output concept '" in message:
                start = message.index("with the output concept '") + len("with the output concept '")
                end = message.index("'", start)
                expected_output_concept = message[start:end]
        except (ValueError, IndexError):
            pass

    return PipelexBundleBlueprintValidationErrorData(
        domain=domain,
        source=source,
        pipe_code=pipe_code,
        concept_code=None,
        field_name=field_name,
        error_type=PipelexBundleBlueprintFixableErrorType.PIPE_SEQUENCE_OUTPUT_MISMATCH,
        error_scope=error_scope,
        message=message,
        field_path=field_path,
        last_step_pipe_code=last_step_pipe_code,
        last_step_output_concept=last_step_output_concept,
        expected_output_concept=expected_output_concept,
    )
