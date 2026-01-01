from pydantic import BaseModel, Field

from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType


class PipeFactoryErrorData(BaseModel):
    """Structured error data for Pipe factory errors.

    This model captures errors raised during pipe creation from blueprints,
    particularly missing concept errors that can be auto-fixed by the builder loop.
    """

    # === Error Classification ===
    error_type: PipeFactoryErrorType = Field(
        description="Type of pipe factory error",
    )

    # === Source Context ===
    domain_code: str | None = Field(None, description="Domain where error occurred")

    # === Entity Context (what failed) ===
    pipe_code: str | None = Field(None, description="Pipe code that failed to be created")
    missing_concept_code: str | None = Field(None, description="The concept code that is missing")
    declared_concepts: list[str] = Field(default_factory=list, description="List of concepts declared in the domain")

    # === Error Details ===
    message: str = Field(description="Human-readable error message")


class PipesAndConceptValidationErrorData(BaseModel):
    """Structured validation error data for Pipe/Concept validation errors.

    This model captures validation errors raised by Pipe or Concept classes during
    their validation (NOT blueprint validation errors).

    These errors come from:
    - PipeAbstract and its subclasses (PipeLLM, PipeExtract, etc.)
    - Concept validation
    """

    # === Source Context ===
    domain_code: str | None = Field(None, description="Domain where error occurred")
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
