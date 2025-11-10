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
from pipelex.core.pipes.exceptions import StaticValidationErrorType
from pipelex.core.stuffs.structured_content import StructuredContent

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
