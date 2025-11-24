from enum import Enum

from pydantic import ValidationError
from pydantic_core import ErrorDetails

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.bundles.exceptions import (
    PipesAndConceptValidationErrorData,
    PipeValidationErrorType,
)


class ModelScope(str, Enum):
    """Indicates which type of model is being validated."""

    PIPE = "pipe"
    CONCEPT = "concept"


def categorize_pipe_concept_validation_error_from_validation_error(
    validation_error: ValidationError,
) -> list[PipesAndConceptValidationErrorData]:
    """Categorize all errors from a ValidationError for Pipe or Concept instantiation.

    This function determines the model scope (PIPE or CONCEPT) from the ValidationError
    and processes all errors accordingly.

    Args:
        validation_error: Pydantic ValidationError from Pipe or Concept model validation

    Returns:
        List of PipesAndConceptValidationErrorData for all errors
    """
    # Determine model scope by examining field names in errors
    # Pipe-specific fields: type, inputs, output, pipe_category
    # Concept-specific fields: structure_class_name, refines
    errors = validation_error.errors()

    model_scope = ModelScope.PIPE
    if errors:
        # Check first error's field name to determine model type
        first_error = errors[0]
        loc = first_error.get("loc", ())
        if loc:
            field_name = str(loc[0])
            # Concept-specific fields
            if field_name in ("structure_class_name", "refines"):
                model_scope = ModelScope.CONCEPT
            # Pipe-specific fields
            elif field_name in ("type", "inputs", "output", "pipe_category"):
                model_scope = ModelScope.PIPE
            # Ambiguous fields - try to infer from error message
            else:
                error_msg = str(validation_error).lower()
                if "concept" in error_msg and "pipe" not in error_msg:
                    model_scope = ModelScope.CONCEPT

    # Process all errors
    categorized_errors: list[PipesAndConceptValidationErrorData] = []
    for error in errors:
        categorized_error = categorize_pipe_concept_validation_error(
            error=error,
            model_scope=model_scope,
            model_code=None,  # We don't have the code at this point
        )
        categorized_errors.append(categorized_error)

    return categorized_errors


def categorize_pipe_concept_validation_error(
    error: ErrorDetails,
    model_scope: ModelScope,
    model_code: str | None = None,
) -> PipesAndConceptValidationErrorData:
    """Categorize a PIPE or CONCEPT validation error and create structured error data.

    Args:
        error: Pydantic error from Pipe or Concept model validation
        model_scope: Whether this is a PIPE or CONCEPT validation
        model_code: The pipe_code or concept_code being validated (if known)

    Returns:
        PipesAndConceptValidationErrorData with all relevant fields populated

    Raises:
        PipelexUnexpectedError: If the model scope is unexpected
    """
    if model_scope == ModelScope.PIPE:
        return _handle_pipe_errors(
            error=error,
            pipe_code=model_code,
        )
    elif model_scope == ModelScope.CONCEPT:
        return _handle_concept_errors(
            error=error,
            concept_code=model_code,
        )
    else:
        # Unexpected scope for pipe/concept validation
        message = error.get("msg", "Unknown validation error")
        pydantic_type = error.get("type", "")
        loc = error.get("loc", ())
        field_path = " → ".join(str(item) for item in loc)
        msg = (
            f"Unexpected model scope for pipe/concept validation: "
            f"type='{pydantic_type}', scope='{model_scope}', path='{field_path}', message='{message}'"
        )
        raise PipelexUnexpectedError(msg)


def _handle_pipe_errors(
    error: ErrorDetails,
    pipe_code: str | None,
) -> PipesAndConceptValidationErrorData:
    """Handle all PIPE validation errors.

    Extracts all necessary context from error and categorizes the error type.

    Args:
        error: Pydantic error details
        pipe_code: The pipe code being validated (if known)

    Returns:
        PipesAndConceptValidationErrorData with all context populated
    """
    # Extract data from error
    loc = error.get("loc", ())
    message = error.get("msg", "Unknown validation error")
    pydantic_type = error.get("type", "")
    field_path = " → ".join(str(item) for item in loc)

    # Extract field_name from loc[0] (direct field on Pipe model)
    field_name = str(loc[0]) if len(loc) >= 1 else None

    # Extract variable names from loc (for input/output errors)
    variable_names = [str(item) for item in loc]

    # Determine error type - default to UNKNOWN_VALIDATION_ERROR
    error_type = PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR

    # Try to categorize based on error message patterns
    message_lower = message.lower()

    if "missing" in message_lower or "required" in pydantic_type:
        # Could be MISSING_INPUT_VARIABLE but we can't tell for sure from generic Pydantic errors
        # The specific error type should come from PipeValidationError exceptions instead
        error_type = PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
    elif "extra" in message_lower or "forbidden" in pydantic_type:
        error_type = PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR

    return PipesAndConceptValidationErrorData(
        domain=None,
        source=None,
        pipe_code=pipe_code,
        concept_code=None,
        field_name=field_name,
        error_type=error_type,
        message=message,
        field_path=field_path,
        variable_names=variable_names,
    )


def _handle_concept_errors(
    error: ErrorDetails,
    concept_code: str | None,
) -> PipesAndConceptValidationErrorData:
    """Handle all CONCEPT validation errors.

    Extracts all necessary context from error and categorizes the error type.

    Args:
        error: Pydantic error details
        concept_code: The concept code being validated (if known)

    Returns:
        PipesAndConceptValidationErrorData with all context populated
    """
    # Extract data from error
    loc = error.get("loc", ())
    message = error.get("msg", "Unknown validation error")
    pydantic_type = error.get("type", "")
    field_path = " → ".join(str(item) for item in loc)

    # Extract field_name from loc[0] (direct field on Concept model)
    field_name = str(loc[0]) if len(loc) >= 1 else None

    # Extract variable names from loc (for input/output errors)
    variable_names = [str(item) for item in loc]

    # Determine error type - default to UNKNOWN_VALIDATION_ERROR
    error_type = PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR

    # Try to categorize based on error message patterns
    message_lower = message.lower()

    if "missing" in message_lower or "required" in pydantic_type or "extra" in message_lower or "forbidden" in pydantic_type:
        error_type = PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR

    return PipesAndConceptValidationErrorData(
        domain=None,
        source=None,
        pipe_code=None,
        concept_code=concept_code,
        field_name=field_name,
        error_type=error_type,
        message=message,
        field_path=field_path,
        variable_names=variable_names,
    )
