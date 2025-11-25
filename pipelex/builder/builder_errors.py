from pipelex.base_exceptions import PipelexError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.types import Self


class PipeBuilderError(PipelexError):
    def __init__(self: Self, message: str, working_memory: WorkingMemory | None = None) -> None:
        self.working_memory = working_memory
        super().__init__(message)


class ConceptSpecError(PipelexError):
    """Details of a single concept failure during dry run."""


class PipelexBundleUnexpectedError(PipelexError):
    """Raised when an unexpected error occurs during validation."""
