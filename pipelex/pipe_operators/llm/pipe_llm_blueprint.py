from typing import Literal

from pydantic import field_validator, model_validator

from pipelex.cogt.llm.llm_setting import LLMModelChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_list
from pipelex.types import Self, StrEnum


class StructuringMethod(StrEnum):
    DIRECT = "direct"
    PRELIMINARY_TEXT = "preliminary_text"


class PipeLLMBlueprint(PipeBlueprint):
    type: Literal["PipeLLM"] = "PipeLLM"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    model: LLMModelChoice | None = None
    model_to_structure: LLMModelChoice | None = None

    system_prompt: str | None = None
    prompt: str | None = None

    structuring_method: StructuringMethod | None = None
    prompt_template_to_structure: str | None = None
    system_prompt_to_structure: str | None = None

    nb_output: int | None = None
    multiple_output: bool | None = None

    @field_validator("nb_output", mode="after")
    @classmethod
    def validate_nb_output(cls, value: int | None = None) -> int | None:
        if value and value < 2:
            msg = "PipeLLMBlueprint nb_output must be at least 2"
            raise PipeDefinitionError(message=msg)
        return value

    @model_validator(mode="after")
    def validate_multiple_output(self) -> Self:
        if excess_attributes_list := has_more_than_one_among_attributes_from_list(
            self,
            attributes_list=["nb_output", "multiple_output"],
        ):
            msg = f"PipeLLMBlueprint should have no more than one of {excess_attributes_list} among them"
            raise PipeDefinitionError(msg)
        return self
