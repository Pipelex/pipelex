from pydantic import BaseModel

from pipelex.core.pipes.exceptions import PipeValidationErrorType


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


class PipelexBundleBlueprintValidationErrorData(BaseModel):
    """Structured validation error data for bundle blueprint validation errors.

    This model captures information about validation errors that occur during
    blueprint validation (before pipe instantiation).
    """

    error_type: PipeValidationErrorType | None = None
    domain_code: str | None = None
    source: str | None = None
    pipe_code: str | None = None
    concept_code: str | None = None
    message: str
    variable_names: list[str] | None = None

    # The namespace-stripped bare code for a strippable same-domain over-qualified pipe code
    # (``strip-namespace`` enrichment). Present only when the fix planner can act; ``pipe_code``
    # discriminates the two raise sites — set to the offending dotted code for a declaration-key
    # rename, ``None`` for a ``main_pipe`` value strip (which is a root ``set_key``, not a rename).
    stripped_pipe_code: str | None = None
