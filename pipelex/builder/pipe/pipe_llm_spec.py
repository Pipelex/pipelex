from typing import Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint, StructuringMethod
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle


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
    model: str | None = Field(
        default=None,
        description="Model preset, alias, waterfall, or direct model handle. Use presets from 'pipelex-agent models'.",
    )
    system_prompt: str | None = Field(default=None, description="A system prompt to guide the LLM's behavior, style and skills. Can be a template.")
    structuring_method: StructuringMethod | None = Field(
        default=None,
        description=(
            "Build-time directive that controls how the structured output is produced. "
            "Default (None or 'direct'): a single LLM call produces the structured output directly. "
            "'preliminary_text': the bundle elaborator splits this pipe into a PipeSequence of "
            "[PipeLLM(text), PipeStructure], so the LLM first drafts a free-form text and a second "
            "call structures it. Useful when reasoning is easier in prose than in JSON. "
            "Cannot be combined with a Text output."
        ),
    )
    prompt: str | None = Field(
        default=None,
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
""",
    )

    templating_style: TagStyle | TemplatingStyle | None = Field(
        default=None,
        description=(
            "How this pipe's inputs are tagged into the prompt. A bare string names the tag style "
            "('xml', 'ticks', 'square_brackets', 'no_tag'); an inline table sets both tag style and "
            'text format, e.g. { tag_style = "xml", text_format = "markdown" }. Omit to use the '
            "runtime default."
        ),
    )

    @field_validator("model", mode="before")
    @classmethod
    def reject_empty_model(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            msg = "Model cannot be an empty string; omit the field to use defaults"
            raise ValueError(msg)
        return value

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with LLM-specific details
        llm_group = Group()
        llm_group.renderables.append(base_group)

        # Add LLM-specific information
        llm_group.renderables.append(Text())  # Blank line
        llm_group.renderables.append(Text.from_markup(f"Model: [bold yellow]{escape(self.model or '(default)')}[/bold yellow]"))

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

        return PipeLLMBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs_concept_specs,
            output=base_blueprint.output,
            system_prompt=self.system_prompt,
            prompt=self.prompt,
            model=self.model,
            structuring_method=self.structuring_method,
            templating_style=self.templating_style,
        )
