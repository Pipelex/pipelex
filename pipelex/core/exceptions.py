from pydantic import BaseModel, Field

from pipelex.core.pipes.exceptions import PipeValidationErrorType


class PipesAndConceptValidationErrorData(BaseModel):
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
