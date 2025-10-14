"""Error classes and their structured content representations for the builder domain."""

from pydantic import Field

from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.exceptions import (
    PipelexException,
    StaticValidationErrorType,
)
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


# ============================================================================
# BaseModel (StructuredContent) versions of error information
# ============================================================================


class StaticValidationErrorData(StructuredContent):
    """Structured data for StaticValidationError."""

    error_type: StaticValidationErrorType = Field(description="The type of static validation error")
    domain: str = Field(description="The domain where the error occurred")
    pipe_code: str | None = Field(None, description="The pipe code if applicable")
    variable_names: list[str] | None = Field(None, description="Variable names involved in the error")
    required_concept_codes: list[str] | None = Field(None, description="Required concept codes")
    provided_concept_code: str | None = Field(None, description="The provided concept code")
    file_path: str | None = Field(None, description="The file path where the error occurred")
    explanation: str | None = Field(None, description="Additional explanation of the error")


class ConceptDefinitionErrorData(StructuredContent):
    """Structured data for ConceptDefinitionError."""

    message: str = Field(description="The error message")
    domain_code: str = Field(description="The domain code")
    concept_code: str = Field(description="The concept code")
    description: str = Field(description="Description of the concept")
    structure_class_python_code: str | None = Field(None, description="Python code for the structure class if available")
    source: str | None = Field(None, description="Source of the error")


class PipeDefinitionErrorData(StructuredContent):
    """Structured data for PipeDefinitionError."""

    message: str = Field(description="The error message")
    domain_code: str | None = Field(None, description="The domain code")
    pipe_code: str | None = Field(None, description="The pipe code")
    description: str | None = Field(None, description="Description of the pipe")
    source: str | None = Field(None, description="Source of the error")


class DomainFailure(StructuredContent):
    """Details of a single domain failure during dry run."""

    domain_code: str = Field(description="The code of the domain that failed")
    error_message: str = Field(description="The error message for this domain")


class ConceptFailure(StructuredContent):
    """Details of a single concept failure during dry run."""

    concept_spec: ConceptSpec = Field(description="The failing concept spec with concept code")
    error_message: str = Field(description="The error message for this concept")


class PipeFailure(StructuredContent):
    """Details of a single pipe failure during dry run."""

    pipe_spec: (
        PipeFuncSpec
        | PipeImgGenSpec
        | PipeComposeSpec
        | PipeLLMSpec
        | PipeExtractSpec
        | PipeBatchSpec
        | PipeConditionSpec
        | PipeParallelSpec
        | PipeSequenceSpec
    ) = Field(description="The failing pipe spec with pipe code")
    error_message: str = Field(description="The error message for this pipe")


class PipelexBundleErrorData(StructuredContent):
    """Structured data for PipelexBundleError."""

    message: str = Field(description="The main error message")
    static_validation_error: StaticValidationErrorData | None = Field(None, description="Static validation error if present")
    domain_failures: list[DomainFailure] | None = Field(None, description="List of domain failures")
    pipe_failures: list[PipeFailure] | None = Field(None, description="List of pipe failures")
    concept_failures: list[ConceptFailure] | None = Field(None, description="List of concept failures")
    concept_definition_errors: list[ConceptDefinitionErrorData] | None = Field(None, description="List of concept definition errors")
    pipe_definition_errors: list[PipeDefinitionErrorData] | None = Field(None, description="List of pipe definition errors")


# ============================================================================
# Exception classes with as_structured_content() methods
# ============================================================================


class PipeBuilderError(Exception):
    """Base exception for pipe builder errors."""


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
    ) -> None:
        self.static_validation_error = static_validation_error
        self.domain_failures = domain_failures
        self.pipe_failures = pipe_failures
        self.concept_failures = concept_failures
        self.concept_definition_errors = concept_definition_errors
        self.pipe_definition_errors = pipe_definition_errors
        super().__init__(message)

    def as_structured_content(self: Self) -> PipelexBundleErrorData:
        """Convert the error to structured content."""
        return PipelexBundleErrorData(
            message=str(self),
            static_validation_error=self.static_validation_error,
            domain_failures=self.domain_failures,
            pipe_failures=self.pipe_failures,
            concept_failures=self.concept_failures,
            concept_definition_errors=self.concept_definition_errors,
            pipe_definition_errors=self.pipe_definition_errors,
        )


class PipelexBundleNoFixForError(PipelexException):
    """Raised when no fix is found for a static validation error."""


class PipelexBundleUnexpectedError(PipelexException):
    """Raised when an unexpected error occurs during validation."""
