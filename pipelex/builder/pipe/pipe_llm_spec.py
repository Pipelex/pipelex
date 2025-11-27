from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.llm.llm_setting import LLMModelChoice


class LLMSkill(StrEnum):
    LLM_TO_RETRIEVE = "llm_to_retrieve"

    LLM_TO_ANSWER_QUESTIONS_CHEAP = "llm_to_answer_questions_cheap"
    LLM_TO_ANSWER_QUESTIONS = "llm_to_answer_questions"

    LLM_FOR_WRITING_CHEAP = "llm_for_writing_cheap"
    LLM_FOR_IMG_TO_TEXT_CHEAP = "llm_for_img_to_text_cheap"
    LLM_FOR_VISUAL_DESIGN = "cheap_llm_for_creativity"
    LLM_FOR_CREATIVE_WRITING = "llm_for_creative_writing"
    LLM_TO_CODE = "llm_to_code"
    LLM_TO_ANALYZE_LARGE_CODEBASE = "llm_to_analyze_large_codebase"


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
    llm_skill: LLMSkill | str = Field(description="Select the simplest LLM skill corresponding to the task to be performed.")
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

    @field_validator("llm_skill", mode="before")
    @classmethod
    def validate_llm(cls, llm_value: str) -> LLMSkill:
        return LLMSkill(llm_value)

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with LLM-specific details
        llm_group = Group()
        llm_group.renderables.append(base_group)

        # Add LLM-specific information
        llm_group.renderables.append(Text())  # Blank line
        llm_group.renderables.append(Text.from_markup(f"LLM Skill: [bold yellow]{self.llm_skill}[/bold yellow]"))

        # Add system prompt if present
        if self.system_prompt:
            system_prompt_panel = Panel(
                self.system_prompt,
                title="System Prompt",
                title_align="left",
                border_style="blue",
                padding=(0, 1),
            )
            llm_group.renderables.append(Text())  # Blank line
            llm_group.renderables.append(system_prompt_panel)

        # Add prompt if present
        if self.prompt:
            prompt_panel = Panel(
                self.prompt,
                title="Prompt",
                title_align="left",
                border_style="green",
                padding=(0, 1),
            )
            llm_group.renderables.append(Text())  # Blank line
            llm_group.renderables.append(prompt_panel)

        return llm_group

    @override
    def to_blueprint(self) -> PipeLLMBlueprint:
        base_blueprint = super().to_blueprint()

        # create llm choice as a str
        llm_choice: LLMModelChoice = self.llm_skill

        return PipeLLMBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            system_prompt=self.system_prompt,
            prompt=self.prompt,
            model=llm_choice,
        )
