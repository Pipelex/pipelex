from pydantic import BaseModel, Field

from pipelex.core.concepts.exceptions import ConceptDefinitionError, ConceptDefinitionErrorData
from pipelex.core.pipes.exceptions import PipeDefinitionErrorData
from pipelex.exceptions import PipelexException


class LibraryError(PipelexException):
    pass


class LibraryLoadingErrorData(BaseModel):
    """Structured data for LibraryLoadingError."""

    message: str = Field(description="The main error message")
    concept_definition_errors: list[ConceptDefinitionErrorData] | None = Field(None, description="List of concept definition errors")
    pipe_definition_errors: list[PipeDefinitionErrorData] | None = Field(None, description="List of pipe definition errors")


class LibraryLoadingError(LibraryError):
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
