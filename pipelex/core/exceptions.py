from pydantic import BaseModel, Field

from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType


class PipeFactoryErrorData(BaseModel):
    """Structured error data for Pipe factory errors.

    This model captures errors raised during pipe creation from blueprints.
    """

    # === Error Classification ===
    error_type: PipeFactoryErrorType = Field(
        description="Type of pipe factory error",
    )

    # === Source Context ===
    domain_code: str | None = Field(default=None, description="Domain where error occurred")

    # === Entity Context (what failed) ===
    pipe_code: str | None = Field(default=None, description="Pipe code that failed to be created")
    missing_concept_code: str | None = Field(default=None, description="The concept code that is missing")
    declared_concepts: list[str] = Field(default_factory=list, description="List of concepts declared in the domain")

    # === Error Details ===
    message: str = Field(description="Human-readable error message")


class PipelexBundleBlueprintValidationErrorData(BaseModel):
    """Structured validation error data for bundle blueprint validation errors.

    This model captures information about validation errors that occur during
    blueprint validation (before pipe instantiation).

    Lives here rather than beside the parser that raises it: `pipeline/` and `libraries/`
    carry it into every kernel-layer import closure, so an interpreter-layer home would
    make the boundary the closure test guards unenforceable. It is the third of the three
    structured error-data models in this module, all keyed on `PipeValidationErrorType`.
    """

    error_type: PipeValidationErrorType | None = None
    domain_code: str | None = None
    source: str | None = None
    pipe_code: str | None = None
    concept_code: str | None = None
    message: str
    variable_names: list[str] | None = None

    # The namespace-stripped bare code for a strippable same-domain over-qualified pipe code
    # (``strip-namespace`` enrichment). Present only when the fix planner can act; ``pipe_code``
    # discriminates the two raise sites — set to the offending dotted code for a declaration-key
    # rename, ``None`` for a ``main_pipe`` value strip (which is a root ``set_key``, not a rename).
    stripped_pipe_code: str | None = None


class PipesAndConceptValidationErrorData(BaseModel):
    """Structured validation error data for Pipe/Concept validation errors.

    This model captures validation errors raised by Pipe or Concept classes during
    their validation (NOT blueprint validation errors).

    These errors come from:
    - PipeAbstract and its subclasses (PipeLLM, PipeExtract, etc.)
    - Concept validation
    """

    # === Source Context ===
    domain_code: str | None = Field(default=None, description="Domain where error occurred")
    source: str | None = Field(default=None, description="Source file path")

    # === Entity Context (what failed) ===
    pipe_code: str | None = Field(default=None, description="Pipe code if error is in a pipe")
    concept_code: str | None = Field(default=None, description="Concept code if error is in a concept")
    missing_pipe_code: str | None = Field(
        default=None, description="Referenced pipe code that does not resolve (for unresolved pipe-dependency errors)"
    )
    field_name: str | None = Field(default=None, description="Specific field that failed")

    # === Error Classification ===
    error_type: PipeValidationErrorType = Field(
        description="Type of pipe/concept validation error",
    )

    # === Error Details ===
    message: str = Field(description="Human-readable error message")
    field_path: str = Field(description="Path to field in dot notation")

    # === Variable names for input/output errors ===
    variable_names: list[str] | None = Field(default=None, description="Variable names (for input errors)")

    # === Enriched expected value (for output-mismatch errors) ===
    expected_output_ref: str | None = Field(
        default=None,
        description="The output ref the pipe should declare (bundle representation), set when the validator knows the correct value",
    )

    # === Enriched expected inputs mapping (for controller input-drift errors) ===
    expected_inputs: dict[str, str] | None = Field(
        default=None,
        description="The full inputs mapping the pipe should declare (variable name → bundle-representation ref), "
        "set when the validator knows the correct value",
    )
    declared_inputs: dict[str, str] | None = Field(
        default=None,
        description="The pipe's currently declared inputs mapping, rendered like expected_inputs, "
        "so a fix planner can diff the two without file access",
    )
