from click import ClickException
from typing_extensions import override

from pipelex.system.exceptions import RootException
from pipelex.tools.misc.context_provider_abstract import ContextProviderException
from pipelex.types import StrEnum


class PipelexException(RootException):
    pass


class PipelexUnexpectedError(PipelexException):
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
        pipe_code: str | None = None,
        variable_names: list[str] | None = None,
        required_concept_codes: list[str] | None = None,
        provided_concept_code: str | None = None,
        file_path: str | None = None,
        explanation: str | None = None,
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


class WorkingMemoryFactoryError(PipelexException):
    pass


class WorkingMemoryError(PipelexException):
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


class PipelexCLIError(PipelexException, ClickException):
    """Raised when there's an error in CLI usage or operation."""


class PipelexConfigError(PipelexException):
    pass


class PipelexSetupError(PipelexException):
    pass


class ClientAuthenticationError(PipelexException):
    pass


class ConceptLibraryConceptNotFoundError(PipelexException):
    pass


class LibraryError(PipelexException):
    pass


class LibraryLoadingError(LibraryError):
    pass


class DomainLibraryError(LibraryError):
    pass


class ConceptLibraryError(LibraryError):
    pass


class PipeLibraryError(LibraryError):
    pass


class PipeLibraryPipeNotFoundError(PipeLibraryError):
    pass


class PipeFactoryError(PipelexException):
    pass


class LibraryParsingError(LibraryError):
    pass


class DomainDefinitionError(PipelexException):
    def __init__(self, message: str, domain_code: str, description: str, source: str | None = None):
        self.domain_code = domain_code
        self.description = description
        self.source = source
        super().__init__(message)


class ConceptDefinitionError(PipelexException):
    def __init__(
        self,
        message: str,
        domain_code: str,
        concept_code: str,
        description: str,
        structure_class_python_code: str | None = None,
        source: str | None = None,
    ):
        self.domain_code = domain_code
        self.concept_code = concept_code
        self.description = description
        self.structure_class_python_code = structure_class_python_code
        self.source = source
        super().__init__(message)


class ConceptStructureGeneratorError(PipelexException):
    def __init__(self, message: str, structure_class_python_code: str | None = None):
        self.structure_class_python_code = structure_class_python_code
        super().__init__(message)


# TODO: add details from all cases raising this error
class PipeDefinitionError(PipelexException):
    def __init__(
        self,
        message: str,
        domain_code: str | None = None,
        pipe_code: str | None = None,
        description: str | None = None,
        source: str | None = None,
    ):
        self.domain_code = domain_code
        self.pipe_code = pipe_code
        self.description = description
        self.source = source
        message = message + " • " + self.pipe_details()
        super().__init__(message)

    def pipe_details(self) -> str:
        if not self.domain_code and not self.pipe_code and not self.description and not self.source:
            return "No pipe details provided"
        details = "Pipe details:"
        if self.domain_code:
            details += f" • domain='{self.domain_code}'"
        if self.pipe_code:
            details += f" • pipe='{self.pipe_code}'"
        if self.description:
            details += f" • description='{self.description}'"
        if self.source:
            details += f" • source='{self.source}'"
        return details


class DomainLoadingError(LibraryLoadingError):
    def __init__(self, message: str, domain_code: str, description: str, source: str | None = None):
        self.domain_code = domain_code
        self.description = description
        self.source = source
        super().__init__(message)


class ConceptLoadingError(LibraryLoadingError):
    def __init__(
        self, message: str, concept_definition_error: ConceptDefinitionError, concept_code: str, description: str, source: str | None = None
    ):
        self.concept_definition_error = concept_definition_error
        self.concept_code = concept_code
        self.description = description
        self.source = source
        super().__init__(message)


class PipeLoadingError(LibraryLoadingError):
    def __init__(self, message: str, pipe_definition_error: PipeDefinitionError, pipe_code: str, description: str, source: str | None = None):
        self.pipe_definition_error = pipe_definition_error
        self.pipe_code = pipe_code
        self.description = description
        self.source = source
        super().__init__(message)


class UnexpectedPipeDefinitionError(PipeDefinitionError):
    pass


class StuffError(PipelexException):
    pass


class StuffContentValidationError(StuffError):
    """Raised when content validation fails during type conversion."""

    def __init__(self, original_type: str, target_type: str, validation_error: str):
        self.original_type = original_type
        self.target_type = target_type
        self.validation_error = validation_error
        super().__init__(f"Failed to validate content from {original_type} to {target_type}: {validation_error}")


class PipeExecutionError(PipelexException):
    pass


class PipeRunError(PipeExecutionError):
    pass


class PipeStackOverflowError(PipeExecutionError):
    pass


class DryRunError(PipeExecutionError):
    """Raised when a dry run fails due to missing inputs or other validation issues."""

    def __init__(self, message: str, missing_inputs: list[str] | None = None, pipe_code: str | None = None):
        self.missing_inputs = missing_inputs or []
        self.pipe_code = pipe_code
        super().__init__(message)


class BatchParamsError(PipelexException):
    pass


class PipeConditionError(PipelexException):
    pass


class StructureClassError(PipelexException):
    pass


class PipeRunParamsError(PipelexException):
    pass


class PipeBatchError(PipelexException):
    """Base class for all PipeBatch-related errors."""


class PipeBatchRecursionError(PipeBatchError):
    """Raised when a PipeBatch attempts to run itself recursively."""


class PipeBatchInputError(PipeBatchError):
    """Raised when the input to a PipeBatch is not a ListContent or is invalid."""


class PipeBatchOutputError(PipeBatchError):
    """Raised when there's an error with the output structure of a PipeBatch operation."""


class PipeBatchBranchError(PipeBatchError):
    """Raised when there's an error with a branch pipe execution in PipeBatch."""


class JobHistoryError(PipelexException):
    pass


class PipeInputError(PipelexException):
    pass


class StuffArtefactError(PipelexException):
    pass


class ConceptError(Exception):
    pass


class ConceptCodeError(ConceptError):
    pass


class ConceptRefineError(ConceptError):
    pass


class PipelineManagerNotFoundError(PipelexException):
    pass


class PipeInputSpecError(PipelexException):
    pass


class PipeInputNotFoundError(PipelexException):
    pass


class PipeInputDetailsError(PipelexException):
    pass


class ApiSerializationError(Exception):
    """Exception raised when API serialization fails."""


class StartPipelineError(Exception):
    pass


class PipelineInputError(Exception):
    pass
