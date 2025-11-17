from pydantic import BaseModel
from typing_extensions import override

from pydantic import Field
from pipelex.base_exceptions import PipelexError
from pipelex.core.pipes.exceptions import StaticValidationErrorType
from pipelex.tools.misc.toml_utils import TomlError
from pipelex.types import StrEnum

class PipelexConfigurationError(PipelexError):
    """Raised when there are configuration issues with the PipelexInterpreter."""


class SyntaxErrorData(BaseModel):
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


class StaticValidationError(ValueError):
    def __init__(
        self,
        error_type: StaticValidationErrorType,
        domain: str | None = None,
        pipe_code: str | None = None,
        variable_names: list[str] | None = None,
        required_concept_codes: list[str] | None = None,
        provided_concept_code: str | None = None,
        file_path: str | None = None,
        explanation: str | None = None,
    ):
        self.error_type = error_type
        self.domain = domain
        self.pipe_code = pipe_code
        self.variable_names = variable_names
        self.required_concept_codes = required_concept_codes
        self.provided_concept_code = provided_concept_code
        self.file_path = file_path
        self.explanation = explanation
        super().__init__()

    def desc(self) -> str:
        msg = f"{self.error_type} • domain='{self.domain}'"
        if self.pipe_code:
            msg += f" • pipe='{self.pipe_code}'"
        if self.variable_names:
            msg += f" • variable='{self.variable_names}'"
        if self.required_concept_codes:
            msg += f" • required_concept_codes='{self.required_concept_codes}'"
        if self.provided_concept_code:
            msg += f" • provided_concept_code='{self.provided_concept_code}'"
        if self.file_path:
            msg += f" • file='{self.file_path}'"
        if self.explanation:
            msg += f" • explanation='{self.explanation}'"
        return msg

    @override
    def __str__(self) -> str:
        return self.desc()


class PLXDecodeError(TomlError):
    """Raised when PLX decoding fails."""


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

    @property
    def is_concept_error(self) -> bool:
        """Check if this is a concept-related error."""
        return self.error_scope == "concept" or self.concept_code is not None

    @property
    def is_pipe_error(self) -> bool:
        """Check if this is a pipe-related error."""
        return self.error_scope == "pipe" or self.pipe_code is not None

    @property
    def is_fixable(self) -> bool:
        """Check if this error type is potentially fixable."""
        return self.error_type != PipelexBundleBlueprintFixableErrorType.UNKNOWN

    def get_dispatch_key(self) -> str:
        """Get unique key for error dispatch: 'concept.refines_structure_conflict', etc."""
        if self.error_scope and self.error_type:
            return f"{self.error_scope}.{self.error_type}"
        return str(self.error_type)


class PipelexInterpreterError(PipelexError):
    """Raised when PipelexInterpreter fails."""

    def __init__(
        self,
        message: str,
        validation_errors: list[PipelexBundleBlueprintValidationErrorData] | None = None,
    ):
        self.validation_errors = validation_errors or []
        super().__init__(message)
