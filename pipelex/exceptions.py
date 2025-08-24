from typing import List, Optional

from click import ClickException
from typing_extensions import override

from pipelex.tools.exceptions import RootException
from pipelex.tools.misc.context_provider_abstract import ContextProviderException
from pipelex.types import StrEnum


class PipelexError(RootException):
    pass


class StaticValidationErrorType(StrEnum):
    MISSING_INPUT_VARIABLE = "missing_input_variable"
    EXTRANEOUS_INPUT_VARIABLE = "extraneous_input_variable"
    INADEQUATE_INPUT_CONCEPT = "inadequate_input_concept"
    TOO_MANY_CANDIDATE_INPUTS = "too_many_candidate_inputs"


class StaticValidationError(Exception):
    def __init__(
        self,
        error_type: StaticValidationErrorType,
        domain: str,
        pipe_code: Optional[str] = None,
        variable_names: Optional[List[str]] = None,
        required_concept_codes: Optional[List[str]] = None,
        provided_concept_code: Optional[str] = None,
        file_path: Optional[str] = None,
        explanation: Optional[str] = None,
    ):
        self.error_type = error_type
        self.domain = domain
        self.pipe_code = pipe_code
        self.variable_names = variable_names
        self.required_concept_codes = required_concept_codes
        self.provided_concept_code = provided_concept_code
        self.file_path = file_path
        self.explanation = explanation
        super().__init__()

    def desc(self) -> str:
        msg = f"{self.error_type} • domain='{self.domain}'"
        if self.pipe_code:
            msg += f" • pipe='{self.pipe_code}'"
        if self.variable_names:
            msg += f" • variable='{self.variable_names}'"
        if self.required_concept_codes:
            msg += f" • required_concept_codes='{self.required_concept_codes}'"
        if self.provided_concept_code:
            msg += f" • provided_concept_code='{self.provided_concept_code}'"
        if self.file_path:
            msg += f" • file='{self.file_path}'"
        if self.explanation:
            msg += f" • explanation='{self.explanation}'"
        return msg

    @override
    def __str__(self) -> str:
        return self.desc()


class WorkingMemoryFactoryError(PipelexError):
    pass


class WorkingMemoryError(PipelexError):
    pass


class WorkingMemoryConsistencyError(WorkingMemoryError):
    pass


class WorkingMemoryVariableError(WorkingMemoryError, ContextProviderException):
    pass


class WorkingMemoryTypeError(WorkingMemoryVariableError):
    pass


class WorkingMemoryStuffAttributeNotFoundError(WorkingMemoryVariableError):
    pass


class WorkingMemoryStuffNotFoundError(WorkingMemoryVariableError):
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


class ConceptLibraryConceptNotFoundError(PipelexError):
    pass


class ConceptFactoryError(PipelexError):
    pass


class LibraryError(PipelexError):
    pass


class DomainLibraryError(LibraryError):
    pass


class ConceptLibraryError(LibraryError):
    pass


class PipeLibraryError(LibraryError):
    pass


class PipeLibraryPipeNotFoundError(PipeLibraryError):
    pass


class PipeFactoryError(PipelexError):
    pass


class LibraryParsingError(LibraryError):
    pass


class PipeDefinitionError(PipelexError):
    pass


class UnexpectedPipeDefinitionError(PipeDefinitionError):
    pass


class StuffError(PipelexError):
    pass


class StuffContentValidationError(StuffError):
    """Raised when content validation fails during type conversion."""

    def __init__(self, original_type: str, target_type: str, validation_error: str):
        self.original_type = original_type
        self.target_type = target_type
        self.validation_error = validation_error
        super().__init__(f"Failed to validate content from {original_type} to {target_type}: {validation_error}")


class PipeExecutionError(PipelexError):
    pass


class PipeRunError(PipeExecutionError):
    pass


class PipeStackOverflowError(PipeExecutionError):
    pass


class DryRunError(PipeExecutionError):
    """Raised when a dry run fails due to missing inputs or other validation issues."""

    def __init__(self, message: str, missing_inputs: Optional[List[str]] = None, pipe_code: Optional[str] = None):
        self.missing_inputs = missing_inputs or []
        self.pipe_code = pipe_code
        super().__init__(message)


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


class PipelineManagerNotFoundError(PipelexError):
    pass


class PipeInputSpecError(PipelexError):
    pass


class PipeInputNotFoundError(PipelexError):
    pass


class PipeInputDetailsError(PipelexError):
    pass


class ApiSerializationError(Exception):
    """Exception raised when API serialization fails."""

    pass


class StartPipelineException(Exception):
    pass


class PipelineInputError(Exception):
    pass
