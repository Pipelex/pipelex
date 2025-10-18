from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import override

from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.llm.llm_setting import LLMModelChoice


class AvailableLLM(StrEnum):
    CLAUDE_4_SONNET = "claude-4.5-sonnet"
    CLAUDE_4_1_OPUS = "claude-4.1-opus"
    GPT_5 = "gpt-5"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"


class LLMSkill(StrEnum):
    LLM_TO_RETRIEVE = "llm_to_retrieve"
    LLM_CHEAP_FOR_EASY_QUESTIONS = "llm_cheap_for_easy_questions"
    LLM_TO_ANSWER_HARD_QUESTIONS = "llm_to_answer_hard_questions"
    LLM_CHEAP_FOR_VISION = "llm_cheap_for_vision"
    LLM_FOR_VISUAL_ANALYSIS = "llm_for_visual_analysis"
    LLM_FOR_VISUAL_DESIGN = "llm_for_visual_design"
    LLM_FOR_CREATIVE_WRITING = "llm_for_creative_writing"
    LLM_TO_REASON = "llm_to_reason"
    LLM_TO_REASON_ON_DIAGRAM = "llm_to_reason_on_diagram"
    LLM_TO_ANALYZE_DATA = "llm_to_analyze_data"
    LLM_TO_CODE = "llm_to_code"
    LLM_TO_ANALYZE_LARGE_CODEBASE = "llm_to_analyze_large_codebase"

    @property
    def llm_recommendation(self) -> AvailableLLM:
        match self:
            case LLMSkill.LLM_TO_RETRIEVE:
                return AvailableLLM.GEMINI_2_5_FLASH
            case LLMSkill.LLM_CHEAP_FOR_EASY_QUESTIONS:
                return AvailableLLM.CLAUDE_4_SONNET
            case LLMSkill.LLM_TO_ANSWER_HARD_QUESTIONS:
                return AvailableLLM.GPT_5
            case LLMSkill.LLM_CHEAP_FOR_VISION:
                return AvailableLLM.GEMINI_2_5_FLASH_LITE
            case LLMSkill.LLM_FOR_VISUAL_ANALYSIS:
                return AvailableLLM.GEMINI_2_5_FLASH
            case LLMSkill.LLM_FOR_VISUAL_DESIGN:
                return AvailableLLM.GEMINI_2_5_FLASH
            case LLMSkill.LLM_FOR_CREATIVE_WRITING:
                return AvailableLLM.CLAUDE_4_1_OPUS
            case LLMSkill.LLM_TO_REASON:
                return AvailableLLM.CLAUDE_4_SONNET
            case LLMSkill.LLM_TO_REASON_ON_DIAGRAM:
                return AvailableLLM.GPT_5
            case LLMSkill.LLM_TO_ANALYZE_DATA:
                return AvailableLLM.CLAUDE_4_SONNET
            case LLMSkill.LLM_TO_CODE:
                return AvailableLLM.CLAUDE_4_SONNET
            case LLMSkill.LLM_TO_ANALYZE_LARGE_CODEBASE:
                return AvailableLLM.GEMINI_2_5_PRO


class PipeLLMSpec(PipeSpec):
    """Spec for LLM-based pipe operations in the Pipelex framework.

    PipeLLM enables Large Language Model processing to generate text or structured output.
    Supports text, structured data, and image inputs.

    Output Multiplicity:
        Specify using bracket notation in output field:
        - output = "Text" - single item (default)
        - output = "Text[]" - variable list
        - output = "Text[3]" - exactly 3 items

    """

    type: SkipJsonSchema[Literal["PipeLLM"]] = "PipeLLM"
    pipe_category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"
    llm: LLMSkill | str = Field(description="Select the most adequate LLM model skill according to the task to be performed.")
    temperature: float | None = Field(default=None, ge=0, le=1)
    system_prompt: str | None = Field(default=None, description="A system prompt to guide the LLM's behavior, style and skills. Can be a template.")
    prompt: str | None = Field(
        description="""A template for the user prompt:
Use `$` prefix for inline variables (e.g., `$topic`) and `@` prefix to insert content as a block with delimiters
For example, `@extracted_text` will generate this:
extracted_text: ```
[the extracted_text goes here]
```
so you don't need to write the delimiters yourself.

**Notes**:
• Image variables must be inserted too.
They can be simply added with the `$` prefix on a line, e.g. `$image_1`.
Or you can mention them by their number in order in the inputs section, starting from 1.
Example: `Only analyze the colors from $image_1 and the shapes from $image_2.
• If we are generating a structured concept, DO NOT detail the structure in the prompt: we will add the schema later.
So, don't have to write a bullet-list of all the attributes definitions yourself.
"""
    )

    @field_validator("llm", mode="before")
    @classmethod
    def validate_llm(cls, llm_value: str) -> LLMSkill:
        return LLMSkill(llm_value)

    @override
    def to_blueprint(self) -> PipeLLMBlueprint:
        base_blueprint = super().to_blueprint()

        # create llm choice as a str
        llm_choice: LLMModelChoice
        if isinstance(self.llm, LLMSkill):
            llm_choice = self.llm.llm_recommendation.value
        else:
            llm_choice = LLMSkill(self.llm).llm_recommendation.value

        # Make it a LLMSetting if temperature is provided
        if self.temperature:
            llm_choice = LLMSetting(model=llm_choice, temperature=self.temperature)

        return PipeLLMBlueprint(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            system_prompt=self.system_prompt,
            prompt=self.prompt,
            model=llm_choice,
        )
