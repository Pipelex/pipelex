from pipelex.builder.validation_error_data import (
    ConceptFailure,
    DomainFailure,
    PipeFailure,
    PipeInputErrorData,
    StaticValidationErrorData,
)
from pipelex.core.concepts.exceptions import ConceptDefinitionErrorData
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeDefinitionErrorData
from pipelex.exceptions import PipelexException
from pipelex.types import Self


class PipeBuilderError(Exception):
    def __init__(self: Self, message: str, working_memory: WorkingMemory | None = None) -> None:
        self.working_memory = working_memory
        super().__init__(message)


class ConceptSpecError(PipelexException):
    """Details of a single concept failure during dry run."""

    def __init__(self: Self, message: str, concept_failure: ConceptFailure) -> None:
        self.concept_failure = concept_failure
        super().__init__(message)


class PipeSpecError(PipelexException):
    """Details of a single pipe failure during dry run."""

    def __init__(self: Self, message: str, pipe_failure: PipeFailure) -> None:
        self.pipe_failure = pipe_failure
        super().__init__(message)


class ValidateDryRunError(Exception):
    """Raised when validating the dry run of a pipe."""


class PipelexBundleError(PipelexException):
    """Main bundle error that aggregates multiple types of errors."""

    def __init__(
        self: Self,
        message: str,
        static_validation_error: StaticValidationErrorData | None = None,
        domain_failures: list[DomainFailure] | None = None,
        pipe_failures: list[PipeFailure] | None = None,
        concept_failures: list[ConceptFailure] | None = None,
        concept_definition_errors: list[ConceptDefinitionErrorData] | None = None,
        pipe_definition_errors: list[PipeDefinitionErrorData] | None = None,
        pipe_input_errors: list[PipeInputErrorData] | None = None,
    ) -> None:
        self.static_validation_error = static_validation_error
        self.domain_failures = domain_failures
        self.pipe_input_errors = pipe_input_errors
        self.pipe_failures = pipe_failures
        self.concept_failures = concept_failures
        self.concept_definition_errors = concept_definition_errors
        self.pipe_definition_errors = pipe_definition_errors
        super().__init__(message)


class PipelexBundleNoFixForError(PipelexException):
    """Raised when no fix is found for a static validation error."""


class PipelexBundleUnexpectedError(PipelexException):
    """Raised when an unexpected error occurs during validation."""
