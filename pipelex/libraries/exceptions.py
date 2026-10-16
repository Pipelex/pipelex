from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.core.exceptions import PipelexBundleBlueprintValidationErrorData, PipesAndConceptValidationErrorData


class LibraryError(PipelexError):
    _declared_title = "Library error"


class CrateNormalizationError(LibraryError):
    """Raised when a library crate cannot be normalized (e.g. a non-domain-qualified key, or a pipe ref matching no crate pipe, or several)."""

    _declared_title = "Crate normalization error"


class CrateIntegrityError(LibraryError):
    """Raised when a library crate names a method tree it does not carry: the host that assembled it built it wrong."""

    _declared_title = "Crate integrity error"


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


class MethodTreeLoadError(LibraryLoadingError):
    """Raised when a method tree a load reads from this host's disk cannot be listed.

    The tree of a method's folder, of a library directory, of a `.mthds` file named alone or of a dependency package:
    the standard refused it (a symbolic link, a name that is not a tree path, a lone file the membership rule keeps
    out), it passed a limit this machine lists trees under, or a directory or a file of it could not be read. The
    tree is the caller's own method, so the message, which names the tree's root and the files by their tree paths,
    is theirs to read, and the same load is refused again until the tree changes.
    """

    error_domain = ErrorDomain.INPUT
    retryable = False
    _authors_caller_facing_message = True


class HostLibraryTreeError(PipelexError):
    """Raised when a library directory of this host, one a load reads beside a caller's bundles, cannot be read as a method tree.

    Such a directory is the host's own (installed libraries, the defaults, `PIPELEXPATH` on a server), so a tree of it
    that the standard refuses, that passes a limit or that cannot be read is a fault of the host's configuration, not
    of the caller's method: it is not an `INPUT` error, and its message, which names paths on the host, is not
    caller-facing. It is deliberately no `LibraryError`, which a validation would report as the caller's invalid bundle.
    """

    error_domain = ErrorDomain.CONFIG
    retryable = False
