from click import ClickException

from pipelex.tools.exceptions import RootException


class PipelexError(RootException):
    pass


class PipelexCLIError(PipelexError, ClickException):
    """Raised when there's an error in CLI usage or operation."""

    pass


class PipelexConfigError(PipelexError):
    pass


class PipelexSetupError(PipelexError):
    pass


class ClientAuthenticationError(PipelexError):
    pass


class DomainDefinitionError(PipelexError):
    pass


class DomainLibraryError(PipelexError):
    pass


class ConceptLibraryError(PipelexError):
    pass


class ConceptLibraryConceptNotFoundError(PipelexError):
    pass


class ConceptFactoryError(PipelexError):
    pass


class PipeLibraryError(PipelexError):
    pass


class PipeLibraryPipeNotFoundError(PipelexError):
    pass


class PipeFactoryError(PipelexError):
    pass


class LibraryError(PipelexError):
    pass


class LibraryParsingError(PipelexError):
    pass


class PipeDefinitionError(PipelexError):
    pass


class WorkingMemoryError(PipelexError):
    pass


class WorkingMemoryTypeError(WorkingMemoryError):
    pass


class WorkingMemoryNotFoundError(WorkingMemoryError):
    pass


class WorkingMemoryStuffNotFoundError(WorkingMemoryNotFoundError):
    pass


class StuffError(PipelexError):
    pass


class PipeExecutionError(PipelexError):
    pass


class PipeRunError(PipeExecutionError):
    pass


class PipeStackOverflowError(PipeExecutionError):
    pass


class PipeConditionError(PipelexError):
    pass


class StructureClassError(PipelexError):
    pass


class PipeRunParamsError(PipelexError):
    pass


class PipeBatchError(PipelexError):
    """Base class for all PipeBatch-related errors."""

    pass


class PipeBatchRecursionError(PipeBatchError):
    """Raised when a PipeBatch attempts to run itself recursively."""

    pass


class PipeBatchInputError(PipeBatchError):
    """Raised when the input to a PipeBatch is not a ListContent or is invalid."""

    pass


class PipeBatchOutputError(PipeBatchError):
    """Raised when there's an error with the output structure of a PipeBatch operation."""

    pass


class PipeBatchBranchError(PipeBatchError):
    """Raised when there's an error with a branch pipe execution in PipeBatch."""

    pass


class JobHistoryError(PipelexError):
    pass


class PipeInputError(PipelexError):
    pass


class StuffArtefactError(PipelexError):
    pass


class ConceptError(Exception):
    pass


class ConceptCodeError(ConceptError):
    pass


class ConceptDomainError(ConceptError):
    pass


class PipelineManagerNotFoundError(PipelexError):
    pass
