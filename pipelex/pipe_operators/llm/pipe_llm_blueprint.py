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
    """Blueprint for LLM-based pipe operations in the Pipelex framework.

    PipeLLM enables Large Language Model processing to generate text or structured output.
    Supports text, structured data, and image inputs with flexible prompt configuration
    and output structuring methods.

    Attributes:
        type: Fixed to "PipeLLM" for this pipe type.
        system_prompt_template: Template for system prompt with inline variables using $ syntax.
        system_prompt_template_name: Name reference to a system prompt template.
                                    Mutually exclusive with other system_prompt fields.
        system_prompt_name: Name reference to a system prompt.
                           Mutually exclusive with other system_prompt fields.
        system_prompt: Direct system-level prompt to guide LLM behavior. Can be inline text
                      or file reference ('file:path/to/prompt.md'). Mutually exclusive with
                      other system_prompt fields.
        prompt_template: User prompt template with variable substitution. Use $ for inline
                        variables (e.g., $topic) and @ for entire input content (e.g., @text_to_summarize).
                        Note: Don't use @ or $ for image variables. Mutually exclusive with other
                        prompt fields.
        template_name: Name reference to a prompt template. Mutually exclusive with other prompt fields.
        prompt_name: Name reference to a prompt. Mutually exclusive with other prompt fields.
        prompt: Static user prompt without variable injection. Mutually exclusive with other prompt fields.
        llm: LLM preset(s) configuration. Can be single preset or mapping for different
            generation modes (e.g., main, object_direct).
        llm_to_structure: LLM preset specifically for output structuring in preliminary_text mode.
        structuring_method: Method for structured output generation ('direct' or 'preliminary_text').
                           Defaults to global configuration.
        prompt_template_to_structure: Prompt template for second step in preliminary_text mode.
        system_prompt_to_structure: System prompt for structuring step in preliminary_text mode.
        nb_output: Fixed number of outputs to generate (e.g., 3 for exactly 3 outputs).
                  Must be > 0. Mutually exclusive with multiple_output.
        multiple_output: Enables variable-length list generation. Default is false (single output).
                        Set to true for indeterminate number of outputs. Mutually exclusive with nb_output.

    Validation Rules:
        1. System prompt fields are mutually exclusive (only one can be set).
        2. User prompt fields are mutually exclusive (only one can be set).
        3. Output cardinality: nb_output and multiple_output are mutually exclusive.
        4. nb_output must be greater than 0 when specified.
        5. Structuring method must be 'direct' or 'preliminary_text' when specified.

    Raises:
        PipeDefinitionError: When validation rules are violated or mutually exclusive
                            fields are set simultaneously.
    """

    type: Literal["PipeLLM"] = "PipeLLM"
    category: Literal["PipeOperator"] = "PipeOperator"
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
