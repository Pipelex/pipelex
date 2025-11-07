from typing_extensions import override

from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.validation_error_data import (
    ConceptDefinitionErrorData,
    ConceptFailure,
    DomainFailure,
    PipeDefinitionErrorData,
    PipeFailure,
    PipeInputErrorData,
    PipelexBundleErrorData,
    StaticValidationErrorData,
)
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.validation_errors import PipelexValidationExceptionAbstract
from pipelex.exceptions import PipelexException
from pipelex.types import Self

# Type alias for pipe spec union
PipeSpecUnion = (
    PipeFuncSpec
    | PipeImgGenSpec
    | PipeComposeSpec
    | PipeLLMSpec
    | PipeExtractSpec
    | PipeBatchSpec
    | PipeConditionSpec
    | PipeParallelSpec
    | PipeSequenceSpec
)


class PipeBuilderError(Exception):
    def __init__(self: Self, message: str, working_memory: WorkingMemory | None = None) -> None:
        self.working_memory = working_memory
        super().__init__(message)


class ConceptSpecError(PipelexException):
    """Details of a single concept failure during dry run."""

    def __init__(self: Self, message: str, concept_failure: ConceptFailure) -> None:
        self.concept_failure = concept_failure
        super().__init__(message)

    def as_structured_content(self: Self) -> ConceptFailure:
        """Return the concept failure as structured content."""
        return self.concept_failure


class PipeSpecError(PipelexException):
    """Details of a single pipe failure during dry run."""

    def __init__(self: Self, message: str, pipe_failure: PipeFailure) -> None:
        self.pipe_failure = pipe_failure
        super().__init__(message)

    def as_structured_content(self: Self) -> PipeFailure:
        """Return the pipe failure as structured content."""
        return self.pipe_failure


class ValidateDryRunError(Exception):
    """Raised when validating the dry run of a pipe."""


class PipelexBundleError(PipelexException, PipelexValidationExceptionAbstract):
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

    @override
    def get_concept_definition_errors(self: Self) -> list[ConceptDefinitionErrorData]:
        """Get concept definition errors."""
        return self.concept_definition_errors or []

    def as_structured_content(self: Self) -> PipelexBundleErrorData:
        """Convert the error to structured content."""
        return PipelexBundleErrorData(
            message=str(self),
            static_validation_error=self.static_validation_error,
            domain_failures=self.domain_failures,
            pipe_input_errors=self.pipe_input_errors,
            pipe_failures=self.pipe_failures,
            concept_failures=self.concept_failures,
            concept_definition_errors=self.concept_definition_errors,
            pipe_definition_errors=self.pipe_definition_errors,
        )


class PipelexBundleNoFixForError(PipelexException):
    """Raised when no fix is found for a static validation error."""


class PipelexBundleUnexpectedError(PipelexException):
    """Raised when an unexpected error occurs during validation."""
