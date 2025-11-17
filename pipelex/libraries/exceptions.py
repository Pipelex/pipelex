from pydantic import BaseModel, Field
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.core.concepts.exceptions import ConceptDefinitionError, ConceptDefinitionErrorData, PipelexValidationExceptionAbstractError
from pipelex.core.pipes.exceptions import PipeDefinitionErrorData


class LibraryError(PipelexError):
    pass


class LibraryLoadingErrorData(BaseModel):
    """Structured data for LibraryLoadingError."""

    message: str = Field(description="The main error message")
    concept_definition_errors: list[ConceptDefinitionErrorData] | None = Field(None, description="List of concept definition errors")
    pipe_definition_errors: list[PipeDefinitionErrorData] | None = Field(None, description="List of pipe definition errors")


class LibraryLoadingError(LibraryError, PipelexValidationExceptionAbstractError):
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
