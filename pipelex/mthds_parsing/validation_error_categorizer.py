import re
from typing import Any, cast, get_args

from pydantic_core import ErrorDetails
from pydantic_core.core_schema import CoreSchemaType

from pipelex import log
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.mthds_parsing.exceptions import (
    InvalidPipeCodeSyntaxError,
    NativeConceptRedeclarationError,
)
from pipelex.mthds_parsing.handle_pipe_errors import extract_wrapped_pipe_validation_error
from pipelex.mthds_parsing.helpers import ValidationErrorScope, get_error_scope
from pipelex.pipe_machinery.pipe_blueprint import PIPE_SIGNATURE_TYPE_TAG, PipeType
from pipelex.validation_error_types import PipeValidationErrorType

PIPELEX_BUNDLE_BLUEPRINT_DOMAIN_FIELD = "domain"
PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD = "source"
PIPELEX_BUNDLE_BLUEPRINT_MAIN_PIPE_FIELD = "main_pipe"
PIPELEX_BUNDLE_BLUEPRINT_PIPE_FIELD = "pipe"

# Distinctive fragments of the two type-tag errors raised by the `pipe` before-validators (via
# `normalize_typeless_signature_section` in `pipe_blueprint.py`, shared by the blueprint and spec
# layers). Kept in sync with those single-source messages. They map to DIFFERENT structured
# categories — no-type-declared is `MISSING_PIPE_TYPE`, the retired-tag-declared is `UNKNOWN_PIPE_TYPE`
# (a declared-but-invalid type) — and both name the pipe as ``Pipe `<code>``` so the pipe code is
# recoverable from the message. See `_categorize_typeless_pipe_error`.
_MISSING_PIPE_TYPE_MARKER = "has no `type` but declares"
_EXPLICIT_SIGNATURE_TAG_MARKER = "is no longer a pipe type"

# The tags of the union a `[pipe.<code>]` section validates through. Pydantic names the tag it routed to in
# an error's location (`pipe.<code>.PipeLLM.<field>`), but the tag is not a field of the bundle.
_PIPE_UNION_TAGS = frozenset([*PipeType.value_list(), PIPE_SIGNATURE_TYPE_TAG])

# Pydantic's own schema tags that contain a hyphen ("function-after", "tagged-union"...). A key an author
# writes may contain one too ("prompt-template"), so a hyphen alone does not make a location element pydantic's.
_PYDANTIC_HYPHENATED_SCHEMA_TAGS = frozenset(tag for tag in get_args(CoreSchemaType) if "-" in tag)

# The pydantic error type of a key the model does not define, whose location ends with the key as written.
_PYDANTIC_EXTRA_FORBIDDEN_ERROR_TYPE = "extra_forbidden"

# The prefix pydantic puts before the message of a ``ValueError`` a validator raised.
_PYDANTIC_VALUE_ERROR_PREFIX = "Value error, "


def _extract_wrapped_native_concept_redeclaration_error(error: ErrorDetails) -> NativeConceptRedeclarationError | None:
    """Extract a ``NativeConceptRedeclarationError`` wrapped by pydantic, or ``None``.

    ``validate_concept_keys`` raises it (a ``ValueError`` subclass) from a ``mode="before"``
    field validator, so pydantic reports a ``value_error`` and keeps the original in
    ``ctx["error"]`` — the same wrapping ``extract_wrapped_pipe_validation_error`` unwraps for
    pipe errors. Structural, never message-matched: the offending ``concept_code`` rides the
    exception itself.
    """
    if error["type"] != "value_error":
        return None
    ctx: dict[str, Any] | None = error.get("ctx")
    if ctx:
        original_error = ctx.get("error")
        if isinstance(original_error, NativeConceptRedeclarationError):
            return original_error
    return None


def _extract_wrapped_invalid_pipe_code_syntax_error(error: ErrorDetails) -> InvalidPipeCodeSyntaxError | None:
    """Extract an ``InvalidPipeCodeSyntaxError`` wrapped by pydantic, or ``None``.

    Raised (a ``ValueError`` subclass) from the ``main_pipe`` / ``pipe`` ``mode="before"`` field
    validators only when the over-qualified code is safely strippable, so pydantic reports a
    ``value_error`` and keeps the original in ``ctx["error"]`` — the same wrapping the native-concept
    and pipe-error unwraps rely on. Structural, never message-matched: the offending + stripped codes
    ride the exception itself.
    """
    if error["type"] != "value_error":
        return None
    ctx: dict[str, Any] | None = error.get("ctx")
    if ctx:
        original_error = ctx.get("error")
        if isinstance(original_error, InvalidPipeCodeSyntaxError):
            return original_error
    return None


def _main_pipe_strip_is_safe(*, offending_code: str, stripped_code: str, blueprint_dict: dict[str, Any]) -> bool:
    """Whether stripping ``main_pipe`` is provably safe at the document level.

    The ``main_pipe`` raise site runs before the ``pipe`` field validates, so it cannot see the
    declarations — this categorizer can (it holds the raw bundle dict), making it the document-level
    gate the raise site cannot be. The strip is safe iff EXACTLY ONE of the two codes exists as a
    declaration key:

    - Only the bare tail exists: ``main_pipe`` is an over-qualified *reference* (a same-domain
      qualified ref resolves to the bare pipe), so stripping just normalizes the spelling.
    - Only the dotted code exists: its paired strip-namespace rename will materialize the bare
      target, so the strip converges with it (the loop's cross-file collision split still drops
      the pair together when a sibling file blocks the rename).
    - Both exist: the dotted declaration's own rename is collision-blocked, and stripping
      ``main_pipe`` would silently retarget it from the dotted declaration the author referenced
      to the unrelated bare one — suppressed, ambiguity left to a human.
    - Neither exists (typo'd tail): stripping would rewrite ``main_pipe`` to a pipe that does not
      exist — a SAFE-labeled fix mutating the file while the bundle stays invalid — suppressed.
    """
    raw_pipe = blueprint_dict.get(PIPELEX_BUNDLE_BLUEPRINT_PIPE_FIELD)
    if not isinstance(raw_pipe, dict):
        return False
    pipe_keys = {key for key in cast("dict[Any, Any]", raw_pipe) if isinstance(key, str)}
    return (offending_code in pipe_keys) != (stripped_code in pipe_keys)


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
    # Elements containing brackets are pydantic type names (e.g. "dict[str,...]"), and so are its hyphenated
    # schema tags (e.g. "function-after"); a hyphenated key the author wrote is kept.
    if "[" in element or element in _PYDANTIC_HYPHENATED_SCHEMA_TAGS:
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


def _bundle_field_path(*, loc: tuple[int | str, ...], ends_with_authored_key: bool) -> str | None:
    """The dot path from the bundle root that a pydantic ``loc`` names, without pydantic's own elements.

    A pipe section validates through a union tagged by its ``type``, so pydantic puts the tag in the
    location (``pipe.summarize.PipeLLM.promtp``); the tag and pydantic's type discriminators are
    dropped, leaving the path the author would follow in the file (``pipe.summarize.promtp``). When the
    location ends with a key the author wrote (``ends_with_authored_key``), that key is kept whatever it
    looks like, since a key named ``str`` is still the key to fix.
    """
    parts = [str(part) for part in loc]
    if len(parts) >= 3 and parts[0] == PIPELEX_BUNDLE_BLUEPRINT_PIPE_FIELD and parts[2] in _PIPE_UNION_TAGS:
        del parts[2]
    authored_key = parts.pop() if ends_with_authored_key and parts else None
    clean_parts = [part for part in parts if not _is_pydantic_internal_loc_element(part)]
    if authored_key is not None:
        clean_parts.append(authored_key)
    return ".".join(clean_parts) or None


def _make_uncategorized_blueprint_error(
    *,
    error: ErrorDetails,
    domain: str | None,
    source: str | None,
    pipe_code: str | None,
) -> PipelexBundleBlueprintValidationErrorData:
    """Keep an error no categorizer knows as an item of its own, with the locators its location gives.

    It carries no ``error_type``: no closed code identifies the fault, as for the parse-level residual.
    It keeps the ``source`` the parser seeded, the pipe its location names and the ``field_path``, so an
    error such as a misspelled field reaches the author beside the errors that are categorized, rather
    than only once those are fixed.
    """
    field_path = _bundle_field_path(loc=error["loc"], ends_with_authored_key=error["type"] == _PYDANTIC_EXTRA_FORBIDDEN_ERROR_TYPE)
    message = error["msg"].removeprefix(_PYDANTIC_VALUE_ERROR_PREFIX)
    return PipelexBundleBlueprintValidationErrorData(
        domain_code=domain,
        source=source,
        pipe_code=pipe_code,
        field_path=field_path,
        message=f"Validation error at '{field_path}': {message}" if field_path else message,
    )


def categorize_blueprint_validation_error(
    error: ErrorDetails,
    *,
    blueprint_dict: dict[str, Any],
) -> PipelexBundleBlueprintValidationErrorData | None:
    """Categorize a BLUEPRINT validation error into structured error data.

    An error no categorizer knows is kept as an uncategorized item (no ``error_type``) located by its
    source, pipe and field path, so every error of a bundle becomes an item. ``None`` is returned only
    for the union-branch noise of a concept declared as ``ConceptBlueprint | str``, whose table branch
    already reports the fault.

    Args:
        error: Pydantic error from PipelexBundleBlueprint.model_validate()
        blueprint_dict: The blueprint dict being validated (for context extraction)

    Returns:
        PipelexBundleBlueprintValidationErrorData with all relevant fields populated, or None for concept union noise
    """
    # Read off the raw dict, whose values are whatever the author wrote: a `domain = 123` is itself one of
    # the errors being categorized, so a value that is not a string locates nothing.
    raw_domain = blueprint_dict.get(PIPELEX_BUNDLE_BLUEPRINT_DOMAIN_FIELD) if blueprint_dict else None
    raw_source = blueprint_dict.get(PIPELEX_BUNDLE_BLUEPRINT_SOURCE_FIELD) if blueprint_dict else None
    domain = raw_domain if isinstance(raw_domain, str) else None
    source = raw_source if isinstance(raw_source, str) else None

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

    # A native-concept redeclaration: ``validate_concept_keys`` raised a typed ``ValueError``
    # carrying the offending code (which the pydantic ``loc`` — ``("concept",)`` — cannot). Recover
    # it structurally so the fix planner can strip exactly that concept key.
    wrapped_native_redeclaration = _extract_wrapped_native_concept_redeclaration_error(error)
    if wrapped_native_redeclaration is not None:
        return PipelexBundleBlueprintValidationErrorData(
            error_type=PipeValidationErrorType.NATIVE_CONCEPT_REDECLARATION,
            domain_code=domain,
            source=source,
            concept_code=wrapped_native_redeclaration.concept_code,
            # The exception's own clean message, not the pydantic ``msg`` (which carries a
            # "Value error, " prefix) — same choice as the wrapped-pipe-error path above.
            message=str(wrapped_native_redeclaration),
        )

    # A strippable same-domain over-qualified pipe code: ``validate_pipe_keys`` /
    # ``validate_main_pipe_syntax`` raised a typed ``ValueError`` carrying the stripped bare code
    # (which the message text and pydantic ``loc`` — ``("pipe",)`` / ``("main_pipe",)`` — cannot).
    # ``pipe_code`` discriminates the two raise sites for the planner: the offending dotted code for
    # a declaration-key rename, ``None`` for a ``main_pipe`` value strip (loc's first element names
    # the field). The bare ``ValueError`` path (malformed codes, cross-package refs) still falls
    # through to the message-matching ``_categorize_syntax_validation_error`` → unfixable.
    #
    # The ``main_pipe`` raise site cannot see the declarations (the ``pipe`` field validates after
    # it), so the safety gate lives here, on the raw bundle dict: a strip that would retarget
    # ``main_pipe`` to a different declaration, or rewrite it to a pipe that does not exist,
    # keeps its category but loses the enrichment → no fix is planned.
    wrapped_invalid_pipe_code = _extract_wrapped_invalid_pipe_code_syntax_error(error)
    if wrapped_invalid_pipe_code is not None:
        is_main_pipe = bool(loc) and loc[0] == PIPELEX_BUNDLE_BLUEPRINT_MAIN_PIPE_FIELD
        stripped_pipe_code: str | None = wrapped_invalid_pipe_code.stripped_code
        if is_main_pipe and not _main_pipe_strip_is_safe(
            offending_code=wrapped_invalid_pipe_code.offending_code,
            stripped_code=wrapped_invalid_pipe_code.stripped_code,
            blueprint_dict=blueprint_dict,
        ):
            stripped_pipe_code = None
        return PipelexBundleBlueprintValidationErrorData(
            error_type=PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX,
            domain_code=domain,
            source=source,
            pipe_code=None if is_main_pipe else wrapped_invalid_pipe_code.offending_code,
            stripped_pipe_code=stripped_pipe_code,
            message=str(wrapped_invalid_pipe_code),
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

    # No categorizer knows it: keep it as an item of its own, never dropped because another item exists.
    log.verbose(f"Pipelex bundle blueprint validation error that is not categorized: {error_scope} - {source} - {domain}")
    return _make_uncategorized_blueprint_error(error=error, domain=domain, source=source, pipe_code=pipe_code)
