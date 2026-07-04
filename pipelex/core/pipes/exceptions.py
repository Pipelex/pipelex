from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_reference import ModelReference
from pipelex.types import StrEnum


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

    # Wiring / reference-resolution failures, detected when validating a pipe's contract against the
    # merged library (a referenced concept or dependency pipe does not resolve).
    UNRESOLVED_CONCEPT = "unresolved_concept"
    UNRESOLVED_PIPE_DEPENDENCY = "unresolved_pipe_dependency"

    # Generic fallback for unexpected validation errors
    UNKNOWN_VALIDATION_ERROR = "unknown_validation_error"


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
        file_path: str | None = None,
        explanation: str | None = None,
    ):
        self.error_type = error_type
        self.domain_code = domain_code
        self.pipe_code = pipe_code
        self.variable_names = variable_names
        self.required_concept_codes = required_concept_codes
        self.provided_concept_code = provided_concept_code
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
        if self.file_path:
            msg += f" • file='{self.file_path}'"
        if self.explanation:
            msg += f" • explanation='{self.explanation}'"
        return msg
