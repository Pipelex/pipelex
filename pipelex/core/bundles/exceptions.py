from pydantic import BaseModel, Field

from pipelex.types import StrEnum


class PipelexBundleBlueprintFixableErrorType(StrEnum):
    """Types of fixable validation errors in Pipelex bundle blueprints.

    These error types represent validation issues that can potentially be
    automatically fixed or for which we can provide specific guidance.
    """

    # Concept-related fixable errors
    CONCEPT_REFINES_STRUCTURE_CONFLICT = "concept_refines_structure_conflict"  # Has both refines and structure
    CONCEPT_REFINES_INVALID = "concept_refines_invalid"  # Refines references non-existent concept
    CONCEPT_STRUCTURE_INVALID = "concept_structure_invalid"  # Structure definition has errors

    # Pipe sequence errors
    PIPE_SEQUENCE_OUTPUT_MISMATCH = "pipe_sequence_output_mismatch"  # Last step output doesn't match sequence output
    PIPE_SEQUENCE_EMPTY_STEPS = "pipe_sequence_empty_steps"  # No steps defined

    # Pipe input/output errors (from StaticValidationError)
    PIPE_MISSING_INPUT_VARIABLE = "pipe_missing_input_variable"  # Input variable not in inputs dict
    PIPE_EXTRANEOUS_INPUT_VARIABLE = "pipe_extraneous_input_variable"  # Extra variable in inputs dict
    PIPE_INADEQUATE_INPUT_CONCEPT = "pipe_inadequate_input_concept"  # Input concept doesn't match requirement
    PIPE_TOO_MANY_CANDIDATE_INPUTS = "pipe_too_many_candidate_inputs"  # Multiple inputs match requirement
    PIPE_INADEQUATE_OUTPUT_CONCEPT = "pipe_inadequate_output_concept"  # Output concept incompatible

    # Domain errors
    DOMAIN_CODE_INVALID = "domain_code_invalid"  # Domain code format invalid

    # Bundle-level errors
    MAIN_PIPE_NOT_FOUND = "main_pipe_not_found"  # Main pipe doesn't exist in bundle

    # Pydantic validation errors (often fixable)
    MISSING_REQUIRED_FIELD = "missing_required_field"  # Required field not provided
    TYPE_MISMATCH = "type_mismatch"  # Wrong type for field
    EXTRA_FORBIDDEN_FIELD = "extra_forbidden_field"  # Extra field not allowed
    DISCRIMINATOR_MISSING = "discriminator_missing"  # Union discriminator field missing
    ENUM_INVALID_VALUE = "enum_invalid_value"  # Invalid enum value

    # Fallback
    UNKNOWN = "unknown"  # Could not categorize error


class PipelexBundleBlueprintValueError(ValueError):
    pass


class PipelexBundleBlueprintValidationErrorData(BaseModel):
    """Structured validation error data with context for categorization and fixing.

    This model captures comprehensive information about validation errors to enable:
    - Automatic error fixing
    - Targeted error messages and suggestions
    - Analytics tracking
    - Action dispatch based on error type
    """

    # === Source Context ===
    domain: str | None = Field(None, description="Domain where error occurred")
    source: str | None = Field(None, description="Source file path")

    # === Entity Context (what failed) ===
    pipe_code: str | None = Field(None, description="Pipe code if error is in a pipe")
    concept_code: str | None = Field(None, description="Concept code if error is in a concept")
    field_name: str | None = Field(None, description="Specific field that failed (e.g., 'refines', 'structure')")

    # === Error Classification ===
    error_type: PipelexBundleBlueprintFixableErrorType = Field(
        default=PipelexBundleBlueprintFixableErrorType.UNKNOWN,
        description="Type of error for dispatch and fixing",
    )
    error_scope: str | None = Field(None, description="Scope of error: 'concept', 'pipe', 'domain', 'bundle'")

    # === Error Details ===
    message: str = Field(description="Human-readable error message")
    field_path: str = Field(description="Path to field in dot notation (e.g., 'concept.Invoice.refines')")

    # === Context-specific Data (for fixing) ===
    # For concept errors
    concept_refines: str | None = Field(None, description="Value of refines field (if applicable)")
    concept_structure: dict[str, str] | None = Field(None, description="Value of structure field (if applicable)")

    # For pipe sequence errors
    last_step_pipe_code: str | None = Field(None, description="Last step pipe code (for sequence errors)")
    last_step_output_concept: str | None = Field(None, description="Output concept of last step")
    expected_output_concept: str | None = Field(None, description="Expected output concept")

    # For input/output errors
    variable_name: str | None = Field(None, description="Variable name (for input errors)")
    provided_concept: str | None = Field(None, description="Provided concept code")
    required_concept: str | None = Field(None, description="Required concept code")
    candidate_inputs: list[str] | None = Field(None, description="List of candidate inputs")

    # For type/value errors
    expected_type: str | None = Field(None, description="Expected type for field")
    actual_type: str | None = Field(None, description="Actual type provided")
    provided_value: str | None = Field(None, description="String representation of provided value")

    # === Legacy fields (for backwards compatibility) ===
    other: str | None = Field(None, description="Other context (legacy)")
