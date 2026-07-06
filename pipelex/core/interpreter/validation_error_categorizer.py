import re
from typing import Any, cast

from pydantic_core import ErrorDetails

from pipelex import log
from pipelex.core.bundles.exceptions import (
    PipelexBundleBlueprintValidationErrorData,
)
from pipelex.core.interpreter.helpers import ValidationErrorScope, get_error_scope
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.core.pipes.handle_pipe_errors import extract_wrapped_pipe_validation_error

PIPELEX_BUNDLE_BLUEPRINT_DOMAIN_FIELD = "domain"
PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD = "source"

# Distinctive fragments of the two type-tag errors raised by the `pipe` before-validators (via
# `normalize_typeless_signature_section` in `pipe_blueprint.py`, shared by the blueprint and spec
# layers). Kept in sync with those single-source messages. They map to DIFFERENT structured
# categories — no-type-declared is `MISSING_PIPE_TYPE`, the retired-tag-declared is `UNKNOWN_PIPE_TYPE`
# (a declared-but-invalid type) — and both name the pipe as ``Pipe `<code>``` so the pipe code is
# recoverable from the message. See `_categorize_typeless_pipe_error`.
_MISSING_PIPE_TYPE_MARKER = "has no `type` but declares"
_EXPLICIT_SIGNATURE_TAG_MARKER = "is no longer a pipe type"


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
    *,
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


def _categorize_typeless_pipe_error(
    message: str,
    *,
    domain: str | None,
    source: str | None,
) -> PipelexBundleBlueprintValidationErrorData | None:
    """Categorize the two type-tag errors raised by the `pipe` before-validator.

    They are distinct failure modes and get distinct `error_type`s:

    - A `[pipe.x]` section with **no** `type` that declares more than the signature contract →
      `MISSING_PIPE_TYPE` (the author is describing an implementation but named no type).
    - A section that writes the retired explicit `type = "PipeSignature"` → `UNKNOWN_PIPE_TYPE` (a
      `type` **was** declared, but it is no longer a valid pipe type — the same category as a typo'd
      type; the message carries the specific migration guidance).

    Both are raised on the aggregate `pipe` field, so their pydantic `loc` carries no pipe code —
    recover it from the shared ``Pipe `<code>``` prefix so agent/API surfaces get a clean, located item.

    Args:
        message: The error message from the validation
        domain: Domain code
        source: Source file path

    Returns:
        Categorized error data, or None if not one of the two type-tag errors
    """
    if _MISSING_PIPE_TYPE_MARKER in message:
        error_type = PipeValidationErrorType.MISSING_PIPE_TYPE
    elif _EXPLICIT_SIGNATURE_TAG_MARKER in message:
        error_type = PipeValidationErrorType.UNKNOWN_PIPE_TYPE
    else:
        return None
    pipe_code_match = re.search(r"Pipe `([^`]+)`", message)
    return PipelexBundleBlueprintValidationErrorData(
        error_type=error_type,
        domain_code=domain,
        source=source,
        pipe_code=pipe_code_match.group(1) if pipe_code_match else None,
        message=message,
    )


def _categorize_syntax_validation_error(
    message: str,
    *,
    domain: str | None,
    source: str | None,
) -> PipelexBundleBlueprintValidationErrorData | None:
    """Categorize syntax validation errors (invalid pipe code, invalid main_pipe).

    Args:
        message: The error message from the validation
        domain: Domain code
        source: Source file path

    Returns:
        Categorized error data, or None if not a syntax validation error
    """
    message_lower = message.lower()

    # Detect invalid main_pipe syntax
    if "invalid main pipe syntax" in message_lower:
        return PipelexBundleBlueprintValidationErrorData(
            error_type=PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX,
            domain_code=domain,
            source=source,
            message=message,
        )

    # Detect invalid pipe code syntax
    if "is not a valid pipe code" in message_lower:
        return PipelexBundleBlueprintValidationErrorData(
            error_type=PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX,
            domain_code=domain,
            source=source,
            message=message,
        )

    return None


def _is_pydantic_internal_loc_element(element: str) -> bool:
    """Check if a loc element is a pydantic internal type discriminator rather than a user-facing field name.

    Pydantic loc tuples contain both field names (e.g. "structure", "cv_summary") and
    internal type discriminators (e.g. "ConceptBlueprint", "dict[str,union[str,function-after]]",
    "function-after", "str"). We filter out the internal ones to build cleaner error paths.
    """
    # Elements containing brackets or hyphens are pydantic type names (e.g. "dict[str,...]", "function-after")
    if "[" in element or "-" in element:
        return True
    # Builtin type names and pydantic model class names used as union discriminators
    return element in {"str", "int", "float", "bool", "list", "dict", "set", "tuple", "none", "ConceptBlueprint"}


def _categorize_concept_validation_error(
    loc: tuple[int | str, ...],
    *,
    message: str,
    domain: str | None,
    source: str | None,
) -> PipelexBundleBlueprintValidationErrorData | None:
    """Categorize concept validation errors (e.g., missing concept_ref in structure fields).

    Args:
        loc: Location tuple from pydantic validation error
        message: The error message from the validation
        domain: Domain code
        source: Source file path

    Returns:
        Categorized error data with concept_code and enriched message, or None for
        noise errors (e.g. pydantic union branch failures like "Input should be a valid string")
    """
    # Skip pydantic union branch failure noise: when validating a union type like
    # `ConceptBlueprint | str`, pydantic tries each branch and reports failures for both.
    # The "Input should be a valid string" errors from the `str` branch are not actionable.
    if message == "Input should be a valid string":
        return None

    concept_code: str | None = None
    if len(loc) >= 2:
        concept_code = str(loc[1])

    # Build a clean location path filtering out pydantic internal type discriminators
    # e.g. "concept.InterviewPreparationPackage.structure.cv_summary" instead of
    # "concept.InterviewPreparationPackage.ConceptBlueprint.structure.dict[str,union[str,function-after]].cv_summary.function-after"
    clean_parts = [str(part) for part in loc if not _is_pydantic_internal_loc_element(str(part))]
    location_path = ".".join(clean_parts)

    enriched_message = f"Concept validation error at '{location_path}': {message}"

    return PipelexBundleBlueprintValidationErrorData(
        domain_code=domain,
        source=source,
        concept_code=concept_code,
        message=enriched_message,
    )


def categorize_blueprint_validation_error(
    error: ErrorDetails,
    *,
    blueprint_dict: dict[str, Any],
) -> PipelexBundleBlueprintValidationErrorData | None:
    """Categorize a BLUEPRINT validation error and create structured error data or return None if the error cannot be categorized.

    Args:
        error: Pydantic error from PipelexBundleBlueprint.model_validate()
        blueprint_dict: The blueprint dict being validated (for context extraction)

    Returns:
        PipelexBundleBlueprintValidationErrorData with all relevant fields populated, or None if error cannot be categorized
    """
    domain = cast("str | None", blueprint_dict.get(PIPELEX_BUNDLE_BLUEPRINT_DOMAIN_FIELD)) if blueprint_dict else None
    source = cast("str | None", blueprint_dict.get(PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD)) if blueprint_dict else None

    loc = error["loc"]
    message = error["msg"]

    # Extract pipe code from location if available (e.g., ('pipe', 'extract_details_of_task', ...)).
    # The blueprint field is `pipe` (singular), so the loc key is "pipe" — the previous "pipes"
    # never matched, silently dropping the pipe_code locator from every categorized pipe item.
    pipe_code: str | None = None
    if len(loc) >= 2 and loc[0] == "pipe":
        pipe_code = str(loc[1])

    # A blueprint-stage ``PipeValidationError`` (e.g. the PipeBatch ``input_item_name`` ==
    # ``input_list_name`` collision raised by ``PipeBatchBlueprint.validate_inputs``, or the SubPipe
    # ``batch_over`` == ``batch_as`` collision raised by ``SubPipeBlueprint.validate_batch_params``) is
    # raised *inside* a pydantic model validator, so pydantic wraps it as a ``value_error`` with the
    # original exception in ``ctx["error"]``. Unwrap it — mirroring the pipe categorizer's
    # ``extract_wrapped_pipe_validation_error`` (one shared helper) — so its structured ``error_type``
    # and locators survive instead of degrading to an uncategorized residual (``error_type`` absent).
    # This recovers the ``error_type`` for ANY blueprint-stage ``PipeValidationError``, not just batch.
    #
    # Category decision: the recovered item stays ``blueprint_validation`` (the only shape this
    # categorizer emits), NOT re-bucketed to ``pipe_validation``. The fault genuinely surfaced at the
    # blueprint-parse boundary — inside ``PipelexBundleBlueprint.model_validate``, before any pipe was
    # instantiated — so ``blueprint_validation`` is the honest stage; we recover the ``error_type``,
    # not the stage. The wrapped error carries no ``pipe_code`` / ``domain_code`` of its own at this
    # boundary, so backfill the locators from the pydantic ``loc`` (the ``pipe.<code>`` prefix) and the
    # bundle dict, preferring any the error does carry.
    wrapped_pipe_error = extract_wrapped_pipe_validation_error(error)
    if wrapped_pipe_error is not None:
        return PipelexBundleBlueprintValidationErrorData(
            error_type=wrapped_pipe_error.error_type,
            domain_code=wrapped_pipe_error.domain_code or domain,
            source=wrapped_pipe_error.file_path or source,
            pipe_code=wrapped_pipe_error.pipe_code or pipe_code,
            message=wrapped_pipe_error.explanation or str(wrapped_pipe_error),
            variable_names=wrapped_pipe_error.variable_names,
        )

    error_scope = get_error_scope(loc)

    # Categorize based on error scope
    match error_scope:
        case ValidationErrorScope.CONCEPT:
            # Concept validation errors (e.g., missing concept_ref in structure fields)
            # Returns None for noise errors like union branch failures, which we silently skip
            return _categorize_concept_validation_error(
                loc=loc,
                message=message,
                domain=domain,
                source=source,
            )
        case ValidationErrorScope.PIPE | ValidationErrorScope.DOMAIN | ValidationErrorScope.MAIN_PIPE | ValidationErrorScope.BUNDLE:
            pass

    # Unknown pipe `type`: a pydantic discriminated-union tag failure (the pipe declared a `type`
    # matching no known pipe operator/controller). Carry it as a categorized blueprint item with the
    # pipe_code locator instead of letting it fall through to a bare residual.
    if error["type"] == "union_tag_invalid" and pipe_code is not None:
        return PipelexBundleBlueprintValidationErrorData(
            error_type=PipeValidationErrorType.UNKNOWN_PIPE_TYPE,
            domain_code=domain,
            source=source,
            pipe_code=pipe_code,
            message=message,
        )

    # Type-tag errors from the before-validator (raised on the aggregate `pipe` field, so the
    # pipe_code is recovered from the message rather than the bare `loc`): a typeless section
    # declaring more than the contract → MISSING_PIPE_TYPE; the retired explicit tag → UNKNOWN_PIPE_TYPE.
    missing_type_error = _categorize_typeless_pipe_error(
        message=message,
        domain=domain,
        source=source,
    )
    if missing_type_error:
        return missing_type_error

    # Try to categorize input validation errors (missing/unused inputs)
    input_error = _categorize_input_validation_error(
        message=message,
        domain=domain,
        source=source,
        pipe_code=pipe_code,
    )
    if input_error:
        return input_error

    # Try to categorize syntax validation errors (invalid pipe code, main_pipe)
    syntax_error = _categorize_syntax_validation_error(
        message=message,
        domain=domain,
        source=source,
    )
    if syntax_error:
        return syntax_error

    # If we couldn't categorize the error, log a warning
    log.warning(f"Pipelex bundle blueprint validation error that is not categorized: {error_scope} - {source} - {domain}")

    return None
