from pydantic import BaseModel, Field
from typing_extensions import override

from pipelex.base_exceptions import PipelexException
from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice
from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.types import StrEnum


class PipeBlueprintValueError(ValueError):
    pass


class PipeInputNotFoundError(PipelexException):
    pass


class PipeFactoryError(PipelexException):
    pass


class PipeInputError(PipelexException):
    def __init__(self, message: str, pipe_code: str, variable_name: str, concept_code: str | None = None):
        self.pipe_code = pipe_code
        self.variable_name = variable_name
        self.concept_code = concept_code
        super().__init__(message)


class PipeRunInputsError(PipelexException):
    def __init__(self, message: str, pipe_code: str, missing_inputs: dict[str, str]):
        self.pipe_code = pipe_code
        self.missing_inputs = missing_inputs
        super().__init__(message)


class PipeDefinitionErrorData(BaseModel):
    message: str = Field(description="The error message")
    domain_code: str | None = Field(None, description="The domain code")
    pipe_code: str | None = Field(None, description="The pipe code")
    description: str | None = Field(None, description="Description of the pipe")
    source: str | None = Field(None, description="Source of the error")


class StaticValidationErrorType(StrEnum):
    MISSING_INPUT_VARIABLE = "missing_input_variable"
    EXTRANEOUS_INPUT_VARIABLE = "extraneous_input_variable"
    INADEQUATE_INPUT_CONCEPT = "inadequate_input_concept"
    TOO_MANY_CANDIDATE_INPUTS = "too_many_candidate_inputs"


class PipeOperatorModelChoiceError(PipelexException):
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
