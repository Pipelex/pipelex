from __future__ import annotations

from click import ClickException
from typing_extensions import override

from pipelex.builder.validation_error_data import (
    ConceptDefinitionErrorData,
    LibraryLoadingErrorData,
    PipeDefinitionErrorData,
    StaticValidationErrorType,
    SyntaxErrorData,
)
from pipelex.core.validation_errors import ValidationErrorDetailsProtocol
from pipelex.system.exceptions import RootException
from pipelex.tools.misc.context_provider_abstract import ContextProviderException


class PipelexException(RootException):
    pass


class PipelexUnexpectedError(PipelexException):
    pass


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


class LibraryLoadingError(LibraryError, ValidationErrorDetailsProtocol):
    """Error raised when loading library components fails."""

    def __init__(
        self,
        message: str,
        concept_definition_errors: list[ConceptDefinitionErrorData] | None = None,
        pipe_definition_errors: list[PipeDefinitionErrorData] | None = None,
    ):
        self.concept_definition_errors = concept_definition_errors
        self.pipe_definition_errors = pipe_definition_errors
        super().__init__(message)

    @override
    def get_concept_definition_errors(self) -> list[ConceptDefinitionErrorData]:
        return self.concept_definition_errors or []

    def as_structured_content(self) -> LibraryLoadingErrorData:
        return LibraryLoadingErrorData(
            message=str(self),
            concept_definition_errors=self.concept_definition_errors,
            pipe_definition_errors=self.pipe_definition_errors,
        )


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
        structure_class_syntax_error_data: SyntaxErrorData | None = None,
        source: str | None = None,
    ):
        self.domain_code = domain_code
        self.concept_code = concept_code
        self.description = description
        self.structure_class_python_code = structure_class_python_code
        self.structure_class_syntax_error_data = structure_class_syntax_error_data
        self.source = source
        super().__init__(message)

    def as_structured_content(self) -> ConceptDefinitionErrorData:
        return ConceptDefinitionErrorData(
            message=str(self),
            domain_code=self.domain_code,
            concept_code=self.concept_code,
            description=self.description,
            structure_class_python_code=self.structure_class_python_code,
            structure_class_syntax_error_data=self.structure_class_syntax_error_data,
            source=self.source,
        )


class ConceptStructureGeneratorError(PipelexException):
    def __init__(self, message: str, structure_class_python_code: str | None = None, syntax_error_data: SyntaxErrorData | None = None):
        self.structure_class_python_code = structure_class_python_code
        self.syntax_error_data = syntax_error_data
        super().__init__(message)


class PipeInputError(PipelexException):
    def __init__(self, message: str, pipe_code: str, variable_name: str, concept_code: str | None = None):
        self.pipe_code = pipe_code
        self.variable_name = variable_name
        self.concept_code = concept_code
        super().__init__(message)


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
    def __init__(self, message: str, pipe_definition_error: PipeDefinitionErrorData, pipe_code: str, description: str, source: str | None = None):
        self.pipe_definition_error = pipe_definition_error
        self.pipe_code = pipe_code
        self.description = description
        self.source = source
        super().__init__(message)


class StuffError(PipelexException):
    pass


class StuffContentTypeError(StuffError):
    def __init__(self, message: str, expected_type: str, actual_type: str):
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(message)


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


# TODO: create variants of DryRunError for each type of Pipe
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


class PipeControllerError(PipelexException):
    pass


class PipeControllerOutputConceptMismatchError(PipeControllerError):
    def __init__(self, message: str, tested_concept: str, wanted_concept: str):
        self.tested_concept = tested_concept
        self.wanted_concept = wanted_concept
        super().__init__(message)


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


class StuffArtefactError(PipelexException):
    pass


class StuffArtefactReservedFieldError(StuffArtefactError):
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
