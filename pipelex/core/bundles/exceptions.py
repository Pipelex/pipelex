from pydantic import BaseModel, Field

from pipelex.types import StrEnum


class PipeValidationErrorType(StrEnum):
    """Types of pipe validation errors.

    These error types are raised during pipe validation from Pipe/Concept classes.
    Only some are auto-fixed in the builder loop (marked below).
    """

    # Errors that are auto-fixed in builder_loop.py
    MISSING_INPUT_VARIABLE = "missing_input_variable"  # AUTO-FIXED
    EXTRANEOUS_INPUT_VARIABLE = "extraneous_input_variable"  # AUTO-FIXED
    INPUT_REQUIREMENT_MISMATCH = "input_requirement_mismatch"  # AUTO-FIXED
    INADEQUATE_OUTPUT_CONCEPT = "inadequate_output_concept"  # AUTO-FIXED

    # Errors that are raised but NOT auto-fixed (will fail validation)
    LLM_OUTPUT_CANNOT_BE_IMAGE = "llm_output_cannot_be_image"
    IMG_GEN_INPUT_NOT_TEXT_COMPATIBLE = "img_gen_input_not_text_compatible"

    # Generic fallback for unexpected validation errors
    UNKNOWN_VALIDATION_ERROR = "unknown_validation_error"


class PipesConceptValidationErrorData(BaseModel):
    """Structured validation error data for Pipe/Concept validation errors.

    This model captures validation errors raised by Pipe or Concept classes during
    their validation (NOT blueprint validation errors).

    These errors come from:
    - PipeAbstract and its subclasses (PipeLLM, PipeExtract, etc.)
    - Concept validation
    """

    # === Source Context ===
    domain: str | None = Field(None, description="Domain where error occurred")
    source: str | None = Field(None, description="Source file path")

    # === Entity Context (what failed) ===
    pipe_code: str | None = Field(None, description="Pipe code if error is in a pipe")
    concept_code: str | None = Field(None, description="Concept code if error is in a concept")
    field_name: str | None = Field(None, description="Specific field that failed")

    # === Error Classification ===
    error_type: PipeValidationErrorType = Field(
        description="Type of pipe/concept validation error",
    )

    # === Error Details ===
    message: str = Field(description="Human-readable error message")
    field_path: str = Field(description="Path to field in dot notation")

    # === Variable names for input/output errors ===
    variable_names: list[str] | None = Field(None, description="Variable names (for input errors)")


class PipelexBundleBlueprintFixableErrorType(StrEnum):
    """Types of fixable validation errors in Pipelex bundle blueprints.

    These error types represent validation issues that are actually fixed
    in the builder loop auto-fix system.
    """

    PIPE_SEQUENCE_OUTPUT_MISMATCH = "pipe_sequence_output_mismatch"


class PipelexBundleBlueprintValidationErrorData(BaseModel):
    """Structured validation error data for bundle blueprint validation errors.

    This model captures information about validation errors that are actually fixed
    in the builder loop auto-fix system.
    """

    # === Source Context ===
    domain: str | None = Field(None, description="Domain where error occurred")
    source: str | None = Field(None, description="Source file path")

    # === Entity Context (what failed) ===
    pipe_code: str | None = Field(None, description="Pipe code if error is in a pipe")
    concept_code: str | None = Field(None, description="Concept code if error is in a concept")
    field_name: str | None = Field(None, description="Specific field that failed")

    # === Error Classification ===
    error_type: PipelexBundleBlueprintFixableErrorType = Field(
        description="Type of error for dispatch and fixing",
    )
    error_scope: str | None = Field(None, description="Scope of error: 'concept', 'pipe', 'domain', 'bundle'")

    # === Error Details ===
    message: str = Field(description="Human-readable error message")
    field_path: str = Field(description="Path to field in dot notation")

    # === Context-specific Data (for fixing) ===
    # For pipe sequence output mismatch errors
    last_step_pipe_code: str | None = Field(None, description="Last step pipe code (for sequence errors)")
    last_step_output_concept: str | None = Field(None, description="Output concept of last step")
    expected_output_concept: str | None = Field(None, description="Expected output concept")
