from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.types import StrEnum


class PipeFactoryError(PipelexError):
    pass


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
            # It's a preset/alias string
            msg += f" • choice='{self.model_choice}'"
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
    Only some are auto-fixed in the builder loop (marked below).
    """

    # Errors that are auto-fixed in builder_loop.py
    MISSING_INPUT_VARIABLE = "missing_input_variable"  # AUTO-FIXED
    EXTRANEOUS_INPUT_VARIABLE = "extraneous_input_variable"  # AUTO-FIXED
    INPUT_REQUIREMENT_MISMATCH = "input_requirement_mismatch"  # AUTO-FIXED
    INADEQUATE_OUTPUT_CONCEPT = "inadequate_output_concept"  # AUTO-FIXED

    CIRCULAR_DEPENDENCY_ERROR = "circular_dependency_error"

    # Errors that are raised but NOT auto-fixed (will fail validation)
    LLM_OUTPUT_CANNOT_BE_IMAGE = "llm_output_cannot_be_image"
    IMG_GEN_INPUT_NOT_TEXT_COMPATIBLE = "img_gen_input_not_text_compatible"

    # Generic fallback for unexpected validation errors
    UNKNOWN_VALIDATION_ERROR = "unknown_validation_error"


class PipeValidationError(ValueError):
    def __init__(
        self,
        message: str,
        error_type: PipeValidationErrorType | None = None,
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
        super().__init__(message)

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
