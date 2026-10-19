from typing import ClassVar

from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.errors.error_code_declaration import ErrorCodeDeclaration, ErrorCodeSet


class NativeConceptRedeclarationError(PipelexError, ValueError):
    """A bundle declares a concept whose code collides with a native Pipelex concept.

    Subclasses ``ValueError`` so a ``mode="before"`` pydantic field validator can raise it and
    pydantic preserves it in ``ctx["error"]``; the blueprint categorizer unwraps it structurally
    to recover ``concept_code`` (which a bare ``ValueError`` leaves buried in the message text).
    Carrying the offending code is what lets the fix planner emit a targeted delete.
    """

    error_code = CoreCode.METHOD_NAME_CONFLICT

    def __init__(self, message: str, concept_code: str):
        self.concept_code = concept_code
        super().__init__(message)


class InvalidPipeCodeSyntaxError(PipelexError, ValueError):
    """A pipe code that breaks the naming rules, as a ``[pipe."<code>"]`` declaration key or as the ``main_pipe`` value.

    Raised at the two snake_case-enforcing raise sites, carrying the ``offending_code`` as the method writes it, which
    the item names. Subclasses ``ValueError`` so a ``mode="before"`` field validator can raise it and pydantic keeps it
    in ``ctx["error"]`` for the categorizer to unwrap structurally. When the code is a same-domain over-qualified one
    the fix planner can strip back to its bare form (the prefix equals the bundle's own ``domain``, the bare tail is
    itself a valid snake_case code, and, for a declaration, no bare code already occupies that key), it also carries
    the ``stripped_code`` the ``strip-namespace`` planner needs; a genuinely malformed code or a cross-package dotted
    ref carries none, so it is never stripped.
    """

    error_code = CoreCode.METHOD_IDENTIFIER_INVALID

    def __init__(self, message: str, offending_code: str, stripped_code: str | None = None):
        self.offending_code = offending_code
        self.stripped_code = stripped_code
        super().__init__(message)


class MthdsParserError(PipelexError):
    """Raised when MthdsParser fails.

    Covers every way the caller's ``.mthds`` source can be rejected — TOML that
    does not parse, and TOML that parses but fails blueprint validation. The
    message always describes a fault in the caller's own input.

    The default ``method.invalid`` is the umbrella refusal whose items carry their own codes. A raise site that
    finds one fault chooses its code: ``method.syntax`` for a source that does not parse, ``method.schema_violation``
    for one that parses into no valid bundle, ``method.dependency_invalid`` for a dependency's bundle,
    ``request.invalid`` or ``request.pipe_unspecified`` for a request naming no usable pipe, and
    ``runtime.unexpected`` for a caller of the parser that passed it nothing to parse.
    """

    error_code: ClassVar[ErrorCodeDeclaration] = ErrorCodeSet(
        default=CoreCode.METHOD_INVALID,
        others=(
            CoreCode.METHOD_SYNTAX,
            CoreCode.METHOD_SCHEMA_VIOLATION,
            CoreCode.METHOD_DEPENDENCY_INVALID,
            CoreCode.REQUEST_INVALID,
            CoreCode.REQUEST_PIPE_UNSPECIFIED,
            CoreCode.RUNTIME_UNEXPECTED,
        ),
    )

    def __init__(
        self,
        message: str,
        validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
    ):
        self.validation_errors = validation_errors or []
        super().__init__(message)


class BundleElaboratorError(MthdsParserError):
    """Raised when bundle elaboration fails (e.g. synthetic-name collision, invalid output for preliminary_text)."""

    error_code = CoreCode.METHOD_SCHEMA_VIOLATION
