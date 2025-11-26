from pipelex.base_exceptions import PipelexError
from pipelex.tools.misc.context_provider_abstract import ContextProviderError


class WorkingMemoryFactoryError(PipelexError):
    pass


class WorkingMemoryError(PipelexError):
    pass


class WorkingMemoryConsistencyError(WorkingMemoryError):
    pass


class WorkingMemoryVariableError(WorkingMemoryError, ContextProviderError):
    pass


class WorkingMemoryTypeError(WorkingMemoryVariableError):
    pass


class WorkingMemoryStuffAttributeNotFoundError(WorkingMemoryVariableError):
    pass


class WorkingMemoryStuffNotFoundError(WorkingMemoryVariableError):
    def __init__(self, message: str, variable_name: str, pipe_code: str | None = None, concept_code: str | None = None):
        super().__init__(message, variable_name)
        self.pipe_code = pipe_code
        self.concept_code = concept_code
