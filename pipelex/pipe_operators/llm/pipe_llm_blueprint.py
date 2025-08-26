from typing import Literal, Optional

from pydantic import field_validator, model_validator
from typing_extensions import Self

from pipelex.cogt.llm.llm_models.llm_setting import LLMSettingOrPresetId
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists
from pipelex.types import StrEnum


class StructuringMethod(StrEnum):
    DIRECT = "direct"
    PRELIMINARY_TEXT = "preliminary_text"


class PipeLLMBlueprint(PipeBlueprint):
    type: Literal["PipeLLM"] = "PipeLLM"
    system_prompt_template: Optional[str] = None
    system_prompt_template_name: Optional[str] = None
    system_prompt_name: Optional[str] = None
    system_prompt: Optional[str] = None

    prompt_template: Optional[str] = None
    template_name: Optional[str] = None
    prompt_name: Optional[str] = None
    prompt: Optional[str] = None

    llm: Optional[LLMSettingOrPresetId] = None
    llm_to_structure: Optional[LLMSettingOrPresetId] = None

    structuring_method: Optional[StructuringMethod] = None
    prompt_template_to_structure: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None

    nb_output: Optional[int] = None
    multiple_output: Optional[bool] = None

    @field_validator("nb_output", mode="after")
    def validate_nb_output(cls, value: Optional[int] = None) -> Optional[int]:
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
