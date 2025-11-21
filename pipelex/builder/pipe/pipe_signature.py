from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeCategory, PipeType
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeSignature(StructuredContent):
    """PipeSignature is a contract for a pipe.

    It defines the inputs, outputs, and the purpose of the pipe without implementation details.

    Multiplicity Notation:
        Use bracket notation to specify multiplicity for both inputs and outputs:
        - No brackets: single item (default)
        - []: variable-length list
        - [N]: exactly N items (where N is a positive integer)

    Examples:
        - output = "Text" - one text items
        - output = "Text[]" - multiple text items
        - output = "Image[3]" - exactly 3 images
    """

    code: str = Field(description="Pipe code identifying the pipe. Must be snake_case.")
    type: PipeType | str = Field(description="Pipe type.")
    pipe_category: SkipJsonSchema[PipeCategory] = Field(description="Pipe category set according to its type.")
    description: str = Field(description="What the pipe does")
    inputs: dict[str, str] = Field(
        description=(
            "Input specifications mapping variable names to concept codes. "
            "Keys: input variable names in snake_case. "
            "Values: ConceptCodes in PascalCase. Don't use multiplicity brackets. "
        )
    )
    result: str = Field(description="Variable name for the pipe's result in snake_case. This name can be referenced as input in subsequent pipes.")
    output: str = Field(
        description=(
            "Output concept code in PascalCase with optional multiplicity brackets. "
            "Examples: 'Text' (single text), 'Article[]' (list of articles), 'Image[5]' (exactly 5 images)."
        )
    )
    pipe_dependencies: list[str] = Field(description="List of pipe codes that this pipe depends on. This is for the PipeControllers")

    @model_validator(mode="before")
    @classmethod
    def set_pipe_category(cls, values: dict[str, Any]) -> dict[str, Any]:
        try:
            type_str = values["type"]
        except TypeError as exc:
            msg = f"Invalid type for '{values}': could not get subscript, required for 'type'"
            raise ValueError(msg) from exc
        # we need to convert the type string to the PipeType enum because it arrives as a str implictly converted to enum but not yet
        the_type = PipeType(type_str)
        values["pipe_category"] = the_type.category
        return values

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, type_value: str) -> PipeType:
        return PipeType(type_value)

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        pipe_group = Group()
        if title:
            pipe_group.renderables.append(Text(title, style="bold"))
        pipe_group.renderables.append(Text.from_markup(f"Pipe Signature: [red]{self.code}[/red]\n", style="bold"))
        pipe_type = self.type.value if isinstance(self.type, PipeType) else str(self.type)
        pipe_group.renderables.append(Text.from_markup(f"Type: [bold magenta]{pipe_type}[/bold magenta] ({self.pipe_category.value})\n"))
        pipe_group.renderables.append(Text.from_markup(f"Description: [yellow italic]{self.description}[/yellow italic]\n"))

        # Create inputs section
        if not self.inputs:
            pipe_group.renderables.append(Text.from_markup("\nNo inputs"))
        elif len(self.inputs) == 1:
            # Single input: display as a simple line of text
            input_name, concept_spec = next(iter(self.inputs.items()))
            pipe_group.renderables.append(Text.from_markup(f"\nInput: [cyan]{input_name}[/cyan] ([bold green]{concept_spec}[/bold green])"))
        else:
            # Multiple inputs: display as a table
            inputs_table = Table(
                title="Inputs:",
                title_justify="left",
                title_style="not italic",
                show_header=False,
                show_edge=True,
                show_lines=True,
                border_style="dim",
            )
            inputs_table.add_column("Variable Name", style="cyan")
            inputs_table.add_column("Concept", style="bold green")
            for input_name, concept_spec in self.inputs.items():
                inputs_table.add_row(input_name, concept_spec)
            pipe_group.renderables.append(inputs_table)

        # Show output and result
        pipe_group.renderables.append(Text.from_markup(f"\nOutput concept: [bold green]{self.output}[/bold green]"))
        pipe_group.renderables.append(Text.from_markup(f"\nOutput name: [cyan]{self.result}[/cyan]"))

        # Show dependencies if any
        if self.pipe_dependencies:
            pipe_group.renderables.append(Text.from_markup(f"\nDependencies: [red]{', '.join(self.pipe_dependencies)}[/red]"))

        return pipe_group
