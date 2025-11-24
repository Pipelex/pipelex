from typing import Any

from pydantic_core import ErrorDetails

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.bundles.exceptions import (
    PipelexBundleBlueprintFixableErrorType,
    PipelexBundleBlueprintValidationErrorData,
)
from pipelex.types import StrEnum


class ValidationErrorScope(StrEnum):
    """Scope of validation errors based on loc[0]."""

    PIPE = "pipe"
    CONCEPT = "concept"
    DOMAIN = "domain"
    MAIN_PIPE = "main_pipe"
    BUNDLE = "bundle"

    @classmethod
    def is_pipe_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return True
            case ValidationErrorScope.CONCEPT:
                return False
            case ValidationErrorScope.DOMAIN:
                return False
            case ValidationErrorScope.MAIN_PIPE:
                return False
            case ValidationErrorScope.BUNDLE:
                return False

    @classmethod
    def is_concept_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return False
            case ValidationErrorScope.CONCEPT:
                return True
            case ValidationErrorScope.DOMAIN:
                return False
            case ValidationErrorScope.MAIN_PIPE:
                return False
            case ValidationErrorScope.BUNDLE:
                return False

    @classmethod
    def is_domain_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return False
            case ValidationErrorScope.CONCEPT:
                return False
            case ValidationErrorScope.DOMAIN:
                return True
            case ValidationErrorScope.MAIN_PIPE:
                return False
            case ValidationErrorScope.BUNDLE:
                return False

    @classmethod
    def is_main_pipe_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return False
            case ValidationErrorScope.CONCEPT:
                return False
            case ValidationErrorScope.DOMAIN:
                return False
            case ValidationErrorScope.MAIN_PIPE:
                return True
            case ValidationErrorScope.BUNDLE:
                return False

    @classmethod
    def is_bundle_scope(cls, scope: str) -> bool:
        match cls(scope):
            case ValidationErrorScope.PIPE:
                return False
            case ValidationErrorScope.CONCEPT:
                return False
            case ValidationErrorScope.DOMAIN:
                return False
            case ValidationErrorScope.MAIN_PIPE:
                return False
            case ValidationErrorScope.BUNDLE:
                return True


def _get_error_scope(loc: tuple[int | str, ...]) -> ValidationErrorScope:
    if not loc:
        return ValidationErrorScope.BUNDLE

    first = str(loc[0])

    if ValidationErrorScope.is_pipe_scope(scope=first):
        return ValidationErrorScope.PIPE
    elif ValidationErrorScope.is_concept_scope(scope=first):
        return ValidationErrorScope.CONCEPT
    elif ValidationErrorScope.is_domain_scope(scope=first):
        return ValidationErrorScope.DOMAIN
    elif ValidationErrorScope.is_main_pipe_scope(scope=first):
        return ValidationErrorScope.MAIN_PIPE
    elif ValidationErrorScope.is_bundle_scope(scope=first):
        return ValidationErrorScope.BUNDLE
    else:
        msg = f"Unexpected validation error scope: {first}"
        raise PipelexUnexpectedError(msg)


def categorize_blueprint_validation_error(
    blueprint_dict: dict[str, Any],
    error: ErrorDetails,
) -> PipelexBundleBlueprintValidationErrorData:
    """Categorize a BLUEPRINT validation error and create structured error data.

    Args:
        blueprint_dict: The blueprint dict being validated (for context extraction)
        error: Pydantic error from PipelexBundleBlueprint.model_validate()

    Returns:
        PipelexBundleBlueprintValidationErrorData with all relevant fields populated

    Raises:
        PipelexUnexpectedError: If the error is not expected
    """
    # Extract domain and source from blueprint_dict
    domain = blueprint_dict.get("domain") if blueprint_dict else None
    source = blueprint_dict.get("source") if blueprint_dict else None

    loc = error.get("loc", ())

    # Extract error scope from loc[0]
    error_scope = _get_error_scope(loc)

    # Redirect to scope-specific handlers based on error scope
    if ValidationErrorScope.is_pipe_scope(scope=error_scope):
        return _handle_pipe_errors(
            error=error,
            domain=domain,
            source=source,
            error_scope=error_scope,
        )
    elif ValidationErrorScope.is_concept_scope(scope=error_scope):
        return _handle_concept_errors(
            error=error,
        )
    else:
        # Domain, Main Pipe, or Bundle errors are not auto-fixed
        msg = error.get("msg", "Unknown validation error")
        pydantic_type = error.get("type", "")
        field_path = " → ".join(str(item) for item in loc)
        msg = (
            f"Unexpected validation error that cannot be auto-fixed: "
            f"type='{pydantic_type}', scope='{error_scope}', path='{field_path}', message='{msg}'"
        )
        raise PipelexUnexpectedError(msg)


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


def _handle_concept_errors(
    error: ErrorDetails,
) -> PipelexBundleBlueprintValidationErrorData:
    """Handle all CONCEPT scope validation errors.

    Extracts concept_code and all other necessary context from error,
    then processes the specific error type.

    Currently NO concept errors are auto-fixed in the builder loop, so this
    always raises an exception.

    Args:
        error: Pydantic error details
        domain: Domain where error occurred
        source: Source file path
        error_scope: The error scope (CONCEPT)

    Raises:
        PipelexUnexpectedError: Always, since no concept errors are auto-fixed
    """
    # Extract data from error
    loc = error.get("loc", ())
    message = error.get("msg", "Unknown validation error")
    pydantic_type = error.get("type", "")
    field_path = " → ".join(str(item) for item in loc)

    # Extract concept_code from loc[1]
    concept_code = str(loc[1]) if len(loc) >= 2 else None

    # Extract field_name from loc[2] if present
    field_name = str(loc[2]) if len(loc) >= 3 else None

    # No concept errors are currently auto-fixed
    msg = (
        f"Unexpected CONCEPT validation error that cannot be auto-fixed: "
        f"type='{pydantic_type}', concept_code='{concept_code}', field_name='{field_name}', "
        f"path='{field_path}', message='{message}'"
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
