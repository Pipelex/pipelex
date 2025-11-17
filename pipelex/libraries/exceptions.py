from pipelex.base_exceptions import PipelexError
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData


class LibraryError(PipelexError):
    pass


class LibraryLoadingError(LibraryError):
    """Error raised when loading library components fails.

    This error aggregates all validation errors from:
    - Factory errors (Domain, Concept, Pipe)
    - Validation errors (Pydantic ValidationError from validators)
    - Interpreter errors (blueprint parsing)

    All errors are categorized and stored in validation_errors.
    """

    def __init__(
        self,
        message: str,
        validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
    ):
        self.validation_errors = validation_errors or []
        super().__init__(message)


class DomainLoadingError(LibraryLoadingError):
    def __init__(self, message: str, domain_code: str, description: str, source: str | None = None):
        self.domain_code = domain_code
        self.description = description
        self.source = source
        super().__init__(message)


class ConceptLoadingError(LibraryLoadingError):
    def __init__(
        self,
        message: str,
        concept_code: str,
        description: str,
        source: str | None = None,
        original_error: Exception | None = None,
    ):
        self.concept_code = concept_code
        self.description = description
        self.source = source
        self.original_error = original_error
        super().__init__(message)


class PipeLoadingError(LibraryLoadingError):
    def __init__(
        self,
        message: str,
        pipe_code: str,
        description: str,
        source: str | None = None,
        original_error: Exception | None = None,
    ):
        self.pipe_code = pipe_code
        self.description = description
        self.source = source
        self.original_error = original_error
        super().__init__(message)
