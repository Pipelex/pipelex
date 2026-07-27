from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData


class NativeConceptRedeclarationError(ValueError):
    """A bundle declares a concept whose code collides with a native Pipelex concept.

    Subclasses ``ValueError`` so a ``mode="before"`` pydantic field validator can raise it and
    pydantic preserves it in ``ctx["error"]``; the blueprint categorizer unwraps it structurally
    to recover ``concept_code`` (which a bare ``ValueError`` leaves buried in the message text).
    Carrying the offending code is what lets the fix planner emit a targeted delete.
    """

    def __init__(self, message: str, concept_code: str):
        self.concept_code = concept_code
        super().__init__(message)


class InvalidPipeCodeSyntaxError(ValueError):
    """A same-domain over-qualified pipe code the fix planner can strip back to its bare form.

    Raised (in place of a bare ``ValueError``) only at the two snake_case-enforcing raise sites —
    a ``[pipe."<domain>.<code>"]`` declaration key and a ``main_pipe = "<domain>.<code>"`` value —
    and only when the code is safely strippable: the prefix equals the bundle's own ``domain``, the
    bare tail is itself a valid snake_case code, and (for a declaration) no bare code already
    occupies that key. Subclasses ``ValueError`` so a ``mode="before"`` field validator can raise
    it and pydantic keeps it in ``ctx["error"]`` for the categorizer to unwrap structurally —
    carrying the ``stripped_code`` (and, for a declaration, the ``offending_code`` to rename from)
    that the ``strip-namespace`` planner needs. Genuinely malformed codes and cross-package dotted
    refs stay bare ``ValueError``s → uncategorized-as-fixable, so they are never stripped.
    """

    def __init__(self, message: str, offending_code: str, stripped_code: str):
        self.offending_code = offending_code
        self.stripped_code = stripped_code
        super().__init__(message)


class MthdsParserError(PipelexError):
    """Raised when MthdsParser fails.

    Covers every way the caller's ``.mthds`` source can be rejected — TOML that
    does not parse, and TOML that parses but fails blueprint validation. The
    message is always caller-facing copy describing a fault in the caller's own
    input.
    """

    error_domain = ErrorDomain.INPUT
    # The parser's messages describe faults in the caller's own .mthds
    # source — caller-facing copy, kept verbatim under STRICT disclosure.
    _authors_caller_facing_message = True

    def __init__(
        self,
        message: str,
        validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
    ):
        self.validation_errors = validation_errors or []
        super().__init__(message)


class BundleElaboratorError(MthdsParserError):
    """Raised when bundle elaboration fails (e.g. synthetic-name collision, invalid output for preliminary_text)."""
