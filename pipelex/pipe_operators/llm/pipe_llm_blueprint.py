from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator
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
    """PipeLLM is used to run a LLM, to generate text, structured output. It can take as input text, structured information or images."""

    type: Literal["PipeLLM"] = "PipeLLM"
    system_prompt_template: Optional[str] = Field(
        default=None, description="The system prompt template to use. Can use inline variables with $ syntax"
    )
    system_prompt_template_name: Optional[str] = Field(
        default=None,
        description="The name of the system prompt template to use. "
        "Mutually exclusive with system_prompt, system_prompt_name, and system_prompt_template",
    )
    system_prompt_name: Optional[str] = Field(
        default=None,
        description="The name of the system prompt to use. "
        "Mutually exclusive with system_prompt, system_prompt_template, "
        "and system_prompt_template_name",
    )
    system_prompt: Optional[str] = Field(
        default=None,
        description="A system-level prompt to guide the LLM's behavior "
        "(e.g., 'You are a helpful assistant'). Can be inline text or a reference to a template file "
        "('file:path/to/prompt.md'). Mutually exclusive with other system_prompt fields",
    )

    prompt_template: Optional[str] = Field(
        default=None,
        description="A template for the user prompt. Use $ for inline variables "
        "(e.g., $topic) and @ to insert the content of an entire input (e.g., @text_to_summarize). "
        "Note: Do not use @ or $ for image variables. Mutually exclusive with prompt, prompt_name, "
        "and template_name",
    )
    template_name: Optional[str] = Field(
        default=None, description="The name of the prompt template to use. Mutually exclusive with prompt, prompt_name, and prompt_template"
    )
    prompt_name: Optional[str] = Field(
        default=None, description="The name of the prompt to use. Mutually exclusive with prompt, prompt_template, and template_name"
    )
    prompt: Optional[str] = Field(
        default=None,
        description="A simple, static user prompt. Use this when you don't need to inject any variables. Mutually exclusive with other prompt fields",
    )

    llm: Optional[LLMSettingOrPresetId] = Field(
        default=None,
        description="Specifies the LLM preset(s) to use. Can be a single "
        "preset or a table mapping different presets for different generation modes "
        "(e.g., main, object_direct)",
    )
    llm_to_structure: Optional[LLMSettingOrPresetId] = Field(
        default=None, description="LLM preset to use specifically for structuring output in preliminary_text mode"
    )

    structuring_method: Optional[StructuringMethod] = Field(
        default=None,
        description="The method for generating structured output. Can be 'direct' or 'preliminary_text'. Defaults to the global configuration",
    )
    prompt_template_to_structure: Optional[str] = Field(
        default=None, description="The prompt template for the second step in 'preliminary_text' mode"
    )
    system_prompt_to_structure: Optional[str] = Field(
        default=None, description="The system prompt for the structuring step in 'preliminary_text' mode"
    )

    nb_output: Optional[int] = Field(
        default=None,
        description="Specifies exactly how many outputs to generate (e.g., nb_output = 3 for "
        "exactly 3 outputs). Use when you need a fixed number of results. Mutually exclusive with multiple_output. "
        "Must be > 0",
    )
    multiple_output: Optional[bool] = Field(
        default=None,
        description="Controls output generation mode. Default is false (single output). "
        "Set to true for variable-length list generation when you need an indeterminate number of outputs. "
        "Mutually exclusive with nb_output",
    )

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
