"""Categorization utilities for PIPE/CONCEPT validation errors ONLY.

This module handles validation errors raised by Pipe or Concept classes during their
validation (NOT blueprint validation errors).

⚠️ IMPORTANT: This is separate from blueprint validation errors.
- Blueprint errors → Use validation_error_categorizer.py
- Pipe/Concept errors → Use this module

Pipe/Concept validation errors come from:
- PipeAbstract and its subclasses (PipeLLM, PipeExtract, PipeImgGen, etc.)
- Concept validation

These errors include types from PipeValidationErrorType:
- MISSING_INPUT_VARIABLE (auto-fixed in builder loop)
- EXTRANEOUS_INPUT_VARIABLE (auto-fixed in builder loop)
- INPUT_REQUIREMENT_MISMATCH (auto-fixed in builder loop)
- INADEQUATE_OUTPUT_CONCEPT (auto-fixed in builder loop)
- LLM_OUTPUT_CANNOT_BE_IMAGE (not auto-fixed)
- IMG_GEN_INPUT_NOT_TEXT_COMPATIBLE (not auto-fixed)
- UNKNOWN_VALIDATION_ERROR (fallback)
"""

from pydantic_core import ErrorDetails

from pipelex.core.bundles.exceptions import (
    PipesConceptValidationErrorData,
    PipeValidationErrorType,
)


def categorize_pipe_concept_validation_error(
    error: ErrorDetails,
) -> PipesConceptValidationErrorData:
    """Categorize a PIPE or CONCEPT validation error and create structured error data.

    ⚠️ IMPORTANT: This function is ONLY for Pipe/Concept validation errors.
    Do NOT use this for blueprint validation errors (use categorize_blueprint_validation_error instead).

    All context (pipe_code, concept_code, domain, source, etc.) is extracted from the error itself.

    Args:
        error: Pydantic error from Pipe or Concept validation

    Returns:
        PipesConceptValidationErrorData with all relevant fields populated
    """
    # Extract data from error
    loc = error.get("loc", ())
    message = error.get("msg", "Unknown validation error")
    pydantic_type = error.get("type", "")
    field_path = " → ".join(str(item) for item in loc)

    # Extract pipe_code or concept_code from loc[0] and loc[1]
    pipe_code = None
    concept_code = None
    domain = None
    source = None

    if loc and len(loc) >= 1:
        first = str(loc[0])
        if first == "pipe" and len(loc) >= 2:
            pipe_code = str(loc[1])
        elif first == "concept" and len(loc) >= 2:
            concept_code = str(loc[1])

    # Extract field_name from loc (depends on whether it's pipe/concept or top-level)
    if pipe_code or concept_code:
        # For pipe/concept errors: loc = ('pipe', 'pipe_code', 'field_name', ...)
        field_name = str(loc[2]) if len(loc) >= 3 else None
    else:
        # For top-level errors: loc = ('field_name', ...)
        field_name = str(loc[0]) if len(loc) >= 1 else None

    # Extract variable names from loc (for input/output errors)
    variable_names = [str(item) for item in loc] if loc else None

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

    return PipesConceptValidationErrorData(
        domain=domain,
        source=source,
        pipe_code=pipe_code,
        concept_code=concept_code,
        field_name=field_name,
        error_type=error_type,
        message=message,
        field_path=field_path,
        variable_names=variable_names,
    )
