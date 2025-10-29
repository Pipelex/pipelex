from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from pipelex.cogt.templating.template_category import TemplateCategory
    from pipelex.pipe_run.pipe_run_mode import PipeRunMode


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
    def __init__(self, message: str, variable_name: str, pipe_code: str | None = None, concept_code: str | None = None):
        super().__init__(message, variable_name)
        self.pipe_code = pipe_code
        self.concept_code = concept_code


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


class PipeRunInputsError(PipelexException):
    def __init__(self, message: str, pipe_code: str, missing_inputs: dict[str, str]):
        self.pipe_code = pipe_code
        self.missing_inputs = missing_inputs
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


class PipeRunError(PipelexException):
    pass


class DryRunError(PipeRunError):
    """Raised when a dry run fails due to missing inputs or other validation issues."""

    def __init__(self, message: str, pipe_type: str, pipe_code: str | None = None):
        self.pipe_type = pipe_type
        self.pipe_code = pipe_code
        super().__init__(message)


class DryRunMissingInputsError(DryRunError):
    """Raised when a dry run fails due to missing inputs or other validation issues."""

    def __init__(self, message: str, pipe_type: str, pipe_code: str, missing_inputs: list[str] | None = None):
        self.missing_inputs = missing_inputs or []
        super().__init__(message, pipe_type, pipe_code)


class DryRunMissingPipesError(DryRunError):
    """Raised when a dry run fails due to missing pipes or other validation issues."""

    def __init__(self, message: str, pipe_type: str, pipe_code: str, missing_pipes: list[str] | None = None):
        self.missing_pipes = missing_pipes or []
        super().__init__(message, pipe_type, pipe_code)


class DryRunTemplatingError(DryRunError):
    """Raised when a dry run fails due to templating issues."""

    def __init__(self, message: str, pipe_type: str, pipe_code: str, template_category: TemplateCategory, template: str):
        self.template_category = template_category
        self.template = template
        super().__init__(message, pipe_type, pipe_code)


class PipeStackOverflowError(PipeRunError):
    def __init__(self, message: str, limit: int, pipe_stack: list[str]):
        self.limit = limit
        self.pipe_stack = pipe_stack
        super().__init__(message)





