"""Categorization utilities for validation errors.

This module provides functions to analyze Pydantic ValidationErrors and categorize them
into PipelexBundleBlueprintFixableErrorType with proper context extraction.
"""

from typing import Any

from pydantic_core import ErrorDetails

from pipelex.core.bundles.exceptions import (
    PipelexBundleBlueprintFixableErrorType,
    PipelexBundleBlueprintValidationErrorData,
)


def categorize_and_create_error_data(
    error: ErrorDetails,
    blueprint_dict: dict[str, Any] | None,
    domain: str | None,
    source: str | None,
) -> PipelexBundleBlueprintValidationErrorData:
    """Categorize a Pydantic validation error and create structured error data.

    Args:
        error: Pydantic error dict with 'loc', 'msg', 'type', etc.
        blueprint_dict: The blueprint dict being validated (for context extraction)
        domain: Domain name
        source: Source file path

    Returns:
        PipelexBundleBlueprintValidationErrorData with all relevant fields populated
    """
    loc = error.get("loc", ())
    msg = error.get("msg", "Unknown validation error")
    pydantic_type = error.get("type", "")

    # Extract basic context
    pipe_code, concept_code, field_name, error_scope = _extract_context_from_loc(loc)
    field_path = " → ".join(str(item) for item in loc)

    # Categorize error type and extract specific context
    error_type, extra_context = _categorize_error(
        loc=loc,
        msg=msg,
        pydantic_type=pydantic_type,
        blueprint_dict=blueprint_dict,
        pipe_code=pipe_code,
        concept_code=concept_code,
        field_name=field_name,
    )

    # Build and return base error data
    return PipelexBundleBlueprintValidationErrorData(
        domain=domain,
        source=source,
        pipe_code=pipe_code,
        concept_code=concept_code,
        field_name=field_name,
        error_type=error_type,
        error_scope=error_scope,
        message=msg,
        field_path=field_path,
        **extra_context,  # Add any type-specific context
    )


def _extract_context_from_loc(loc: tuple[int | str, ...]) -> tuple[str | None, str | None, str | None, str | None]:
    """Extract pipe_code, concept_code, field_name, and error_scope from location tuple.

    Returns:
        (pipe_code, concept_code, field_name, error_scope)
    """
    if not loc:
        return None, None, None, None

    first = str(loc[0])

    # Pipe errors: ('pipe', 'my_pipe', 'field_name', ...)
    if first == "pipe" and len(loc) >= 2:
        pipe_code = str(loc[1])
        field_name = str(loc[2]) if len(loc) >= 3 else None
        return pipe_code, None, field_name, "pipe"

    # Concept errors: ('concept', 'Invoice', 'field_name', ...)
    elif first == "concept" and len(loc) >= 2:
        concept_code = str(loc[1])
        field_name = str(loc[2]) if len(loc) >= 3 else None
        return None, concept_code, field_name, "concept"

    # Domain errors: ('domain',)
    elif first == "domain":
        return None, None, None, "domain"

    # Main pipe errors: ('main_pipe',)
    elif first == "main_pipe":
        return None, None, None, "bundle"

    # Other bundle-level errors
    else:
        return None, None, None, "bundle"


def _categorize_error(
    loc: tuple[int | str, ...],
    msg: str,
    pydantic_type: str,
    blueprint_dict: dict[str, Any] | None,
    pipe_code: str | None,
    concept_code: str | None,
    field_name: str | None,
) -> tuple[PipelexBundleBlueprintFixableErrorType, dict[str, Any]]:
    """Categorize error and extract type-specific context.

    Returns:
        (error_type, extra_context_dict)
    """
    extra_context: dict[str, Any] = {}

    # Handle Pydantic built-in errors first
    if pydantic_type == "missing":
        return PipelexBundleBlueprintFixableErrorType.MISSING_REQUIRED_FIELD, extra_context

    elif pydantic_type in ("type_error", "int_type", "float_type", "bool_type", "str_type"):
        return PipelexBundleBlueprintFixableErrorType.TYPE_MISMATCH, extra_context

    elif pydantic_type == "extra_forbidden":
        return PipelexBundleBlueprintFixableErrorType.EXTRA_FORBIDDEN_FIELD, extra_context

    elif pydantic_type == "union_tag_not_found":
        return PipelexBundleBlueprintFixableErrorType.DISCRIMINATOR_MISSING, extra_context

    elif pydantic_type == "enum":
        return PipelexBundleBlueprintFixableErrorType.ENUM_INVALID_VALUE, extra_context

    # Handle custom ValueError subclasses (wrapped as 'value_error')
    elif pydantic_type == "value_error":
        return _categorize_value_error(
            loc=loc,
            msg=msg,
            blueprint_dict=blueprint_dict,
            pipe_code=pipe_code,
            concept_code=concept_code,
            field_name=field_name,
        )

    return PipelexBundleBlueprintFixableErrorType.UNKNOWN, extra_context


def _categorize_value_error(
    loc: tuple[int | str, ...],
    msg: str,
    blueprint_dict: dict[str, Any] | None,
    pipe_code: str | None,
    concept_code: str | None,
    field_name: str | None,
) -> tuple[PipelexBundleBlueprintFixableErrorType, dict[str, Any]]:
    """Categorize custom ValueError subclasses."""
    extra_context: dict[str, Any] = {}

    # Concept errors
    if concept_code:
        # Check for specific concept error patterns
        if "refines and structure" in msg:
            # Extract refines and structure values from blueprint
            if blueprint_dict:
                concepts = blueprint_dict.get("concept", {})
                concept_data = concepts.get(concept_code, {})
                if isinstance(concept_data, dict):
                    extra_context["concept_refines"] = concept_data["refines"]
                    extra_context["concept_structure"] = concept_data["structure"]
            return PipelexBundleBlueprintFixableErrorType.CONCEPT_REFINES_STRUCTURE_CONFLICT, extra_context

        elif field_name == "refines" or "Could not validate refine" in msg:
            if blueprint_dict:
                concepts = blueprint_dict.get("concept", {})
                concept_data = concepts.get(concept_code, {})
                if isinstance(concept_data, dict):
                    extra_context["concept_refines"] = concept_data["refines"]
            return PipelexBundleBlueprintFixableErrorType.CONCEPT_REFINES_INVALID, extra_context

        elif field_name == "structure":
            return PipelexBundleBlueprintFixableErrorType.CONCEPT_STRUCTURE_INVALID, extra_context

    # Pipe errors
    elif pipe_code:
        # Pipe sequence errors
        if "concept mismatch" in msg.lower() or "not compatible with the output concept" in msg:
            # Extract pipe sequence context from message
            if "last step" in msg:
                # Try to parse the error message for context
                # Example: "the output concept 'Text' of the last step 'my_pipe'"
                extra_context["last_step_pipe_code"] = _extract_last_step_from_msg(msg)
                extra_context["last_step_output_concept"] = _extract_last_step_output_from_msg(msg)
                extra_context["expected_output_concept"] = _extract_expected_output_from_msg(msg)
            return PipelexBundleBlueprintFixableErrorType.PIPE_SEQUENCE_OUTPUT_MISMATCH, extra_context

    # Domain errors
    elif "domain" in str(loc).lower() or "Domain code" in msg:
        return PipelexBundleBlueprintFixableErrorType.DOMAIN_CODE_INVALID, extra_context

    # Main pipe errors
    elif "main_pipe" in msg.lower() or "Main pipe" in msg:
        return PipelexBundleBlueprintFixableErrorType.MAIN_PIPE_NOT_FOUND, extra_context

    return PipelexBundleBlueprintFixableErrorType.UNKNOWN, extra_context


def _extract_last_step_from_msg(msg: str) -> str | None:
    """Extract last step pipe code from error message."""
    # Example: "of the last step 'my_pipe'"
    try:
        if "last step '" in msg:
            start = msg.index("last step '") + len("last step '")
            end = msg.index("'", start)
            return msg[start:end]
    except (ValueError, IndexError):
        pass
    return None


def _extract_last_step_output_from_msg(msg: str) -> str | None:
    """Extract last step output concept from error message."""
    # Example: "the output concept 'Text' of the last step"
    try:
        if "output concept '" in msg:
            start = msg.index("output concept '") + len("output concept '")
            end = msg.index("'", start)
            return msg[start:end]
    except (ValueError, IndexError):
        pass
    return None


def _extract_expected_output_from_msg(msg: str) -> str | None:
    """Extract expected output concept from error message."""
    # Example: "with the output concept 'Image' of the sequence"
    try:
        if "with the output concept '" in msg:
            start = msg.index("with the output concept '") + len("with the output concept '")
            end = msg.index("'", start)
            return msg[start:end]
    except (ValueError, IndexError):
        pass
    return None
