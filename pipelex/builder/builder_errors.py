from pipelex.base_exceptions import PipelexException
from pipelex.builder.validation_error_data import (
    ConceptFailure,
    PipeFailure,
)
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.types import Self


class PipeBuilderError(Exception):
    def __init__(self: Self, message: str, working_memory: WorkingMemory | None = None) -> None:
        self.working_memory = working_memory
        super().__init__(message)


class ConceptSpecError(PipelexException):
    """Details of a single concept failure during dry run."""

    def __init__(self: Self, message: str, concept_failure: ConceptFailure) -> None:
        self.concept_failure = concept_failure
        super().__init__(message)


class PipeSpecError(PipelexException):
    """Details of a single pipe failure during dry run."""

    def __init__(self: Self, message: str, pipe_failure: PipeFailure) -> None:
        self.pipe_failure = pipe_failure
        super().__init__(message)


class ValidateDryRunError(Exception):
    """Raised when validating the dry run of a pipe."""


class PipelexBundleNoFixForError(PipelexException):
    """Raised when no fix is found for a static validation error."""


class PipelexBundleUnexpectedError(PipelexException):
    """Raised when an unexpected error occurs during validation."""
