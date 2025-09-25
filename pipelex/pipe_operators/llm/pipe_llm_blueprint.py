from typing import Literal, Self

from pydantic import field_validator, model_validator

from pipelex.cogt.llm.llm_setting import LLMChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists
from pipelex.types import StrEnum


class StructuringMethod(StrEnum):
    DIRECT = "direct"
    PRELIMINARY_TEXT = "preliminary_text"


class PipeLLMBlueprint(PipeBlueprint):
    type: Literal["PipeLLM"] = "PipeLLM"
    category: Literal["PipeOperator"] = "PipeOperator"
    system_prompt_template: str | None = None
    system_prompt_template_name: str | None = None
    system_prompt_name: str | None = None
    system_prompt: str | None = None

    prompt_template: str | None = None
    template_name: str | None = None
    prompt_name: str | None = None
    prompt: str | None = None

    llm: LLMChoice | None = None
    llm_to_structure: LLMChoice | None = None

    structuring_method: StructuringMethod | None = None
    prompt_template_to_structure: str | None = None
    system_prompt_to_structure: str | None = None

    nb_output: int | None = None
    multiple_output: bool | None = None

    @field_validator("nb_output", mode="after")
    def validate_nb_output(cls, value: int | None = None) -> int | None:
        if value and value < 1:
            raise PipeDefinitionError("PipeLLMBlueprint nb_output must be greater than 0")
        return value

    @model_validator(mode="after")
    def validate_multiple_output(self) -> Self:
        if excess_attributes_list := has_more_than_one_among_attributes_from_lists(
            self,
            attributes_lists=[
                ["nb_output", "multiple_output"],
                ["system_prompt", "system_prompt_name", "system_prompt_template", "system_prompt_template_name"],
                ["prompt", "prompt_name", "prompt_template", "template_name"],
            ],
        ):
            raise PipeDefinitionError(f"PipeLLMBlueprint should have no more than one of {excess_attributes_list} among them")
        return self
