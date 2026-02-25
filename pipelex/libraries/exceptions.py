from pipelex.base_exceptions import PipelexError
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipesAndConceptValidationErrorData


class LibraryError(PipelexError):
    pass


class LibraryLoadingError(LibraryError):
    """Error raised when loading library components fails.

    This error aggregates TWO types of validation errors:
    1. Blueprint validation errors (from PipelexBundleBlueprint.model_validate())
       - Stored in: blueprint_validation_errors
       - Example: PIPE_SEQUENCE_OUTPUT_MISMATCH

    2. Pipe/Concept validation errors (from Pipe or Concept class validation)
       - Stored in: pipe_concept_validation_errors
       - Example: MISSING_INPUT_VARIABLE, INPUT_STUFF_SPEC_MISMATCH

    Also handles:
    - Factory errors (Domain, Concept, Pipe)
    - Interpreter errors (blueprint parsing)
    """

    def __init__(
        self,
        message: str,
        blueprint_validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
        pipe_concept_validation_errors: list[PipesAndConceptValidationErrorData] | None = None,
    ):
        """Initialize LibraryLoadingError.

        Args:
            message: Error message
            blueprint_validation_errors: Blueprint validation errors (from PipelexBundleBlueprint validation)
            pipe_concept_validation_errors: Pipe/Concept validation errors (from Pipe/Concept validation)
        """
        self.blueprint_validation_errors = blueprint_validation_errors or []
        self.pipe_concept_validation_errors = pipe_concept_validation_errors or []
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
