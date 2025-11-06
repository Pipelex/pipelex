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
from pipelex.types import StrEnum


class StaticValidationErrorType(StrEnum):
    MISSING_INPUT_VARIABLE = "missing_input_variable"
    EXTRANEOUS_INPUT_VARIABLE = "extraneous_input_variable"
    INADEQUATE_INPUT_CONCEPT = "inadequate_input_concept"
    TOO_MANY_CANDIDATE_INPUTS = "too_many_candidate_inputs"


class SyntaxErrorData(StructuredContent):
    message: str
    lineno: int | None = None
    offset: int | None = None
    text: str | None = None
    end_lineno: int | None = None
    end_offset: int | None = None

    @classmethod
    def from_syntax_error(cls, syntax_error: SyntaxError) -> "SyntaxErrorData":
        return cls(
            message=syntax_error.msg,
            lineno=syntax_error.lineno,
            offset=syntax_error.offset,
            text=syntax_error.text,
            end_lineno=syntax_error.end_lineno,
            end_offset=syntax_error.end_offset,
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
    structure_class_syntax_error_data: SyntaxErrorData | None = Field(None, description="Syntax error data for the structure class if available")
    source: str | None = Field(None, description="Source of the error")


class PipeDefinitionErrorData(StructuredContent):
    """Structured data for PipeDefinitionError."""

    message: str = Field(description="The error message")
    domain_code: str | None = Field(None, description="The domain code")
    pipe_code: str | None = Field(None, description="The pipe code")
    description: str | None = Field(None, description="Description of the pipe")
    source: str | None = Field(None, description="Source of the error")


class PipeInputErrorData(StructuredContent):
    """Structured data for PipeInputError."""

    message: str = Field(description="The error message")
    pipe_code: str | None = Field(None, description="The pipe code")
    variable_name: str | None = Field(None, description="The variable name")
    concept_code: str | None = Field(None, description="The concept code")


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


class LibraryLoadingErrorData(StructuredContent):
    """Structured data for LibraryLoadingError."""

    message: str = Field(description="The main error message")
    concept_definition_errors: list[ConceptDefinitionErrorData] | None = Field(None, description="List of concept definition errors")
    pipe_definition_errors: list[PipeDefinitionErrorData] | None = Field(None, description="List of pipe definition errors")


class PipelexBundleErrorData(StructuredContent):
    """Structured data for PipelexBundleError."""

    message: str = Field(description="The main error message")
    static_validation_error: StaticValidationErrorData | None = Field(None, description="Static validation error if present")
    domain_failures: list[DomainFailure] | None = Field(None, description="List of domain failures")
    pipe_input_errors: list[PipeInputErrorData] | None = Field(None, description="List of pipe input errors")
    pipe_failures: list[PipeFailure] | None = Field(None, description="List of pipe failures")
    concept_failures: list[ConceptFailure] | None = Field(None, description="List of concept failures")
    concept_definition_errors: list[ConceptDefinitionErrorData] | None = Field(None, description="List of concept definition errors")
    pipe_definition_errors: list[PipeDefinitionErrorData] | None = Field(None, description="List of pipe definition errors")
