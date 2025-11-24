from pydantic import BaseModel, Field

from pipelex.types import StrEnum


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
