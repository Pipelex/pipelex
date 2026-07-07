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
