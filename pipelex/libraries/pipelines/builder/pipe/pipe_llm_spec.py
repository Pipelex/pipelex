from typing import Literal, Union

from pydantic import Field, field_validator, model_validator
from typing_extensions import override

from pipelex.cogt.llm.llm_setting import LLMChoice, LLMSetting
from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.exceptions import PipeDefinitionError
from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint, StructuringMethod
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists
from pipelex.types import Self


class LLMSettingSpec(StructuredContent):
    llm_handle: str
    temperature: float = Field(..., ge=0, le=1)
    max_tokens: int | None = None

    @field_validator("max_tokens", mode="before")
    @classmethod
    def validate_max_tokens(cls, value: int | Literal["auto"] | None) -> int | None:
        if value is None or (isinstance(value, str) and value == "auto"):
            return None
        if isinstance(value, int):  # pyright: ignore[reportUnnecessaryIsInstance]
            return value


LLMChoiceSpec = Union[LLMSettingSpec, str]


class PipeLLMSpec(PipeSpec):
    """Spec for LLM-based pipe operations in the Pipelex framework.

    PipeLLM enables Large Language Model processing to generate text or structured output.
    Supports text, structured data, and image inputs with flexible prompt configuration
    and output structuring methods.

    Attributes:
        the_pipe_code: Pipe code. Must be snake_case.
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

    """

    type: Literal["PipeLLM"] = "PipeLLM"
    category: Literal["PipeOperator"] = "PipeOperator"
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
    system_prompt_template: str | None = None
    system_prompt_template_name: str | None = None
    system_prompt_name: str | None = None
    system_prompt: str | None = None

    prompt_template: str | None = None
    template_name: str | None = None
    prompt_name: str | None = None
    prompt: str | None = None

    llm: LLMChoiceSpec | None = None
    llm_to_structure: LLMChoiceSpec | None = None

    structuring_method: StructuringMethod | None = None
    prompt_template_to_structure: str | None = None
    system_prompt_to_structure: str | None = None

    nb_output: int | None = None
    multiple_output: bool | None = None

    @field_validator("nb_output", mode="after")
    @staticmethod
    def validate_nb_output(value: int | None = None) -> int | None:
        if value and value < 1:
            msg = "PipeLLMBlueprint nb_output must be greater than 0"
            raise PipeDefinitionError(msg)
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
            msg = f"PipeLLMBlueprint should have no more than one of {excess_attributes_list} among them"
            raise PipeDefinitionError(msg)
        return self

    @override
    def to_blueprint(self) -> PipeLLMBlueprint:
        base_blueprint = super().to_blueprint()
        llm: LLMChoice | None = None
        if isinstance(self.llm, LLMSettingSpec):
            llm = LLMSetting(llm_handle=self.llm.llm_handle, temperature=self.llm.temperature, max_tokens=self.llm.max_tokens)
        elif isinstance(self.llm, str):
            llm = self.llm

        llm_to_structure: LLMChoice | None = None
        if isinstance(self.llm_to_structure, LLMSettingSpec):
            llm_to_structure = LLMSetting(
                llm_handle=self.llm_to_structure.llm_handle,
                temperature=self.llm_to_structure.temperature,
                max_tokens=self.llm_to_structure.max_tokens,
            )
        elif isinstance(self.llm_to_structure, str):
            llm_to_structure = self.llm_to_structure

        return PipeLLMBlueprint(
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            system_prompt_template=self.system_prompt_template,
            system_prompt_template_name=self.system_prompt_template_name,
            system_prompt_name=self.system_prompt_name,
            system_prompt=self.system_prompt,
            prompt_template=self.prompt_template,
            template_name=self.template_name,
            prompt_name=self.prompt_name,
            prompt=self.prompt,
            llm=llm,
            llm_to_structure=llm_to_structure,
            structuring_method=self.structuring_method,
            prompt_template_to_structure=self.prompt_template_to_structure,
            system_prompt_to_structure=self.system_prompt_to_structure,
            nb_output=self.nb_output,
            multiple_output=self.multiple_output,
        )
