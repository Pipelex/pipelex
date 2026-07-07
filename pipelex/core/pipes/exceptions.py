from enum import StrEnum

from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_reference import ModelReference


class PipeFactoryErrorType(StrEnum):
    """Types of pipe factory errors.

    These error types are raised during pipe creation from blueprints.
    """

    UNKNOWN_CONCEPT = "unknown_concept"

    # Generic fallback for unexpected factory errors
    UNKNOWN_FACTORY_ERROR = "unknown_factory_error"


class PipeFactoryError(PipelexError):
    """Raised when a pipe cannot be created from a blueprint.

    This error includes structured data about the failure.

    Attributes:
        message: Human-readable error message
        error_type: The type of factory error
        pipe_code: The pipe code that failed to be created
        domain: The domain of the pipe
        missing_concept_code: The concept code that is missing (for MISSING_OUTPUT_CONCEPT errors)
        declared_concepts: List of concepts declared in the domain
    """

    def __init__(
        self,
        message: str,
        error_type: PipeFactoryErrorType = PipeFactoryErrorType.UNKNOWN_FACTORY_ERROR,
        pipe_code: str | None = None,
        domain_code: str | None = None,
        missing_concept_code: str | None = None,
        declared_concepts: list[str] | None = None,
    ):
        self.error_type = error_type
        self.pipe_code = pipe_code
        self.domain_code = domain_code
        self.missing_concept_code = missing_concept_code
        self.declared_concepts = declared_concepts or []
        super().__init__(message)


class PipeVariableMultiplicityError(ValueError):
    pass


class PipeOperatorModelChoiceError(PipelexError):
    def __init__(
        self,
        message: str,
        pipe_type: str,
        pipe_code: str,
        model_type: ModelType,
        model_choice: LLMModelChoice | ExtractModelChoice | ImgGenModelChoice,
    ):
        self.pipe_type = pipe_type
        self.pipe_code = pipe_code
        self.model_type = model_type
        self.model_choice = model_choice
        super().__init__(message)

    def desc(self) -> str:
        msg = f"{self.message}"
        msg += f" • pipe='{self.pipe_code}' ({self.pipe_type})"
        msg += f" • model_type='{self.model_type}'"

        # Extract the choice identifier from the model_choice union type
        if isinstance(self.model_choice, str):
            # It's a raw string (shouldn't happen but handle it)
            msg += f" • choice='{self.model_choice}'"
        elif isinstance(self.model_choice, ModelReference):
            # It's a ModelReference with kind and name
            msg += f" • choice='{self.model_choice.raw}' ({self.model_choice.kind})"
        else:
            # It's a Setting object with a model field and optional desc()
            msg += f" • choice={self.model_choice.desc()}"

        return msg

    @override
    def __str__(self) -> str:
        return self.desc()


class PipeValidationErrorType(StrEnum):
    """Types of pipe validation errors.

    These error types are raised during pipe validation from Pipe/Concept classes.
    """

    MISSING_INPUT_VARIABLE = "missing_input_variable"
    EXTRANEOUS_INPUT_VARIABLE = "extraneous_input_variable"
    INPUT_STUFF_SPEC_MISMATCH = "input_stuff_spec_mismatch"
    INADEQUATE_OUTPUT_CONCEPT = "inadequate_output_concept"
    INADEQUATE_OUTPUT_MULTIPLICITY = "inadequate_output_multiplicity"

    CIRCULAR_DEPENDENCY_ERROR = "circular_dependency_error"

    LLM_OUTPUT_CANNOT_BE_IMAGE = "llm_output_cannot_be_image"
    INVALID_PIPE_CODE_SYNTAX = "invalid_pipe_code_syntax"
    UNKNOWN_PIPE_TYPE = "unknown_pipe_type"
    # A `[pipe.x]` section declared no `type` yet carries fields beyond the signature contract
    # (`description`, `inputs`, `output`). The author is describing an implementation without naming
    # its type — the counterpart to UNKNOWN_PIPE_TYPE (a declared-but-invalid type).
    MISSING_PIPE_TYPE = "missing_pipe_type"
    BATCH_ITEM_NAME_COLLISION = "batch_item_name_collision"

    # Presence-marker grammar misuse, detected at blueprint parse time: a presence marker
    # (`?` or `!`) combined with a multiplicity suffix, or `!` on an output (D1, D4 of the
    # optionals design).
    OPTIONAL_MARKER_INVALID = "optional_marker_invalid"

    # Static absence-taint violations (D6/D7/D11 of the optionals design): a maybe-absent slot
    # escaping through a non-optional controller boundary; a `continue`-reachable PipeCondition
    # without a `?` output; an unguarded template reference to a declared-optional input; a
    # required structure field fed by a maybe-absent PipeParallel branch.
    OPTIONAL_NOT_HANDLED = "optional_not_handled"
    OPTIONAL_OUTPUT_REQUIRED = "optional_output_required"
    OPTIONAL_INPUT_UNGUARDED = "optional_input_unguarded"
    OPTIONAL_BRANCH_REQUIRED_FIELD = "optional_branch_required_field"

    # Advisory-only (rides the validation report's `warnings` array, never raised as an error):
    # a `!` (force) input whose slot is guaranteed present in every analyzed flow — the
    # assertion can never fire.
    OPTIONAL_FORCE_REDUNDANT = "optional_force_redundant"

    # Wiring / reference-resolution failures, detected when validating a pipe's contract against the
    # merged library (a referenced concept or dependency pipe does not resolve).
    UNRESOLVED_CONCEPT = "unresolved_concept"
    UNRESOLVED_PIPE_DEPENDENCY = "unresolved_pipe_dependency"

    # Generic fallback for unexpected validation errors
    UNKNOWN_VALIDATION_ERROR = "unknown_validation_error"

    @property
    def is_controller_input_drift(self) -> bool:
        """True for the input-drift trio the fix planner can act on when enriched."""
        match self:
            case (
                PipeValidationErrorType.MISSING_INPUT_VARIABLE
                | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE
                | PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
            ):
                return True
            case (
                PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT
                | PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY
                | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                | PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                | PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX
                | PipeValidationErrorType.UNKNOWN_PIPE_TYPE
                | PipeValidationErrorType.MISSING_PIPE_TYPE
                | PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
                | PipeValidationErrorType.OPTIONAL_MARKER_INVALID
                | PipeValidationErrorType.OPTIONAL_NOT_HANDLED
                | PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED
                | PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED
                | PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD
                | PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT
                | PipeValidationErrorType.UNRESOLVED_CONCEPT
                | PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY
                | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
            ):
                return False

    @property
    def is_inadequate_output(self) -> bool:
        """True for the output-mismatch pair the fix planner can act on when enriched."""
        match self:
            case PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT | PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY:
                return True
            case (
                PipeValidationErrorType.MISSING_INPUT_VARIABLE
                | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE
                | PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
                | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                | PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                | PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX
                | PipeValidationErrorType.UNKNOWN_PIPE_TYPE
                | PipeValidationErrorType.MISSING_PIPE_TYPE
                | PipeValidationErrorType.BATCH_ITEM_NAME_COLLISION
                | PipeValidationErrorType.OPTIONAL_MARKER_INVALID
                | PipeValidationErrorType.OPTIONAL_NOT_HANDLED
                | PipeValidationErrorType.OPTIONAL_OUTPUT_REQUIRED
                | PipeValidationErrorType.OPTIONAL_INPUT_UNGUARDED
                | PipeValidationErrorType.OPTIONAL_BRANCH_REQUIRED_FIELD
                | PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT
                | PipeValidationErrorType.UNRESOLVED_CONCEPT
                | PipeValidationErrorType.UNRESOLVED_PIPE_DEPENDENCY
                | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
            ):
                return False


class PipeValidationError(ValueError):
    def __init__(
        self,
        message: str,
        error_type: PipeValidationErrorType | None = None,
        domain_code: str | None = None,
        pipe_code: str | None = None,
        variable_names: list[str] | None = None,
        required_concept_codes: list[str] | None = None,
        provided_concept_code: str | None = None,
        expected_output_ref: str | None = None,
        expected_inputs: dict[str, str] | None = None,
        declared_inputs: dict[str, str] | None = None,
        file_path: str | None = None,
        explanation: str | None = None,
    ):
        self.error_type = error_type
        self.domain_code = domain_code
        self.pipe_code = pipe_code
        self.variable_names = variable_names
        self.required_concept_codes = required_concept_codes
        self.provided_concept_code = provided_concept_code
        # The output ref the pipe should declare (full bundle representation: concept +
        # multiplicity + presence marker), set only where the validator knows the correct
        # value at detection time — the semantic fact the fix planner translates into a
        # suggested fix.
        self.expected_output_ref = expected_output_ref
        # The full inputs mapping the pipe should declare (variable name → bundle-representation
        # ref), set only at the controller input-drift raise sites where ``needed_inputs()`` is
        # in hand — the semantic fact the fix planner translates into a sync-controller-inputs fix.
        # ``declared_inputs`` is the pipe's current declaration rendered the same way, so the
        # planner (pure, no file access) can emit a minimal diff instead of a table rewrite.
        self.expected_inputs = expected_inputs
        self.declared_inputs = declared_inputs
        self.file_path = file_path
        self.explanation = explanation
        super().__init__(message)

    def desc(self) -> str:
        msg = f"{self.error_type} • domain_code='{self.domain_code}'"
        if self.pipe_code:
            msg += f" • pipe='{self.pipe_code}'"
        if self.variable_names:
            msg += f" • variable='{self.variable_names}'"
        if self.required_concept_codes:
            msg += f" • required_concept_codes='{self.required_concept_codes}'"
        if self.provided_concept_code:
            msg += f" • provided_concept_code='{self.provided_concept_code}'"
        if self.expected_output_ref:
            msg += f" • expected_output_ref='{self.expected_output_ref}'"
        if self.expected_inputs:
            msg += f" • expected_inputs='{self.expected_inputs}'"
        if self.declared_inputs:
            msg += f" • declared_inputs='{self.declared_inputs}'"
        if self.file_path:
            msg += f" • file='{self.file_path}'"
        if self.explanation:
            msg += f" • explanation='{self.explanation}'"
        return msg
