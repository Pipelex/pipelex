from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex import pretty_print
from pipelex.core.pipes.exceptions import PipeBlueprintError
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories, AllowedPipeTypes
from pipelex.core.stuffs.structured_content import StructuredContent


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
    type: AllowedPipeTypes | str = Field(description="Pipe type.")
    pipe_category: SkipJsonSchema[AllowedPipeCategories] = Field(description="Pipe category set according to its type.")
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
            raise PipeBlueprintError(msg) from exc
        # we need to convert the type string to the AllowedPipeTypes enum because it arrives as a str implictly converted to enum but not yet
        the_type = AllowedPipeTypes(type_str)
        values["pipe_category"] = the_type.category
        return values

    @field_validator("type", mode="before")
    @classmethod
    def validate_type(cls, type_value: str) -> AllowedPipeTypes:
        return AllowedPipeTypes(type_value)

    @override
    def pretty_print_content(self, title: str | None = None, number: int | None = None) -> None:
        # Build title
        if number:
            main_title = f"Pipe Signature #{number}: {self.code}"
        else:
            main_title = f"Pipe Signature: {self.code}"

        # Build subtitle with type and result
        pipe_type = self.type.value if isinstance(self.type, AllowedPipeTypes) else str(self.type)
        subtitle = f"{pipe_type} → {self.result} : {self.output}"

        # Create content sections
        sections: list[Any] = []

        # Description
        sections.append(Text(self.description, style="italic"))
        sections.append(Text(""))  # Empty line

        # Inputs table
        if self.inputs:
            inputs_table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
            inputs_table.add_column("Input Variable", style="yellow")
            inputs_table.add_column("Concept", style="green")

            for var_name, concept_code in self.inputs.items():
                inputs_table.add_row(var_name, concept_code)

            sections.append(Text("Inputs:", style="bold"))
            sections.append(inputs_table)
            sections.append(Text(""))  # Empty line

        # Output info
        output_text = Text()
        output_text.append("Output: ", style="bold")
        output_text.append(f"{self.output}", style="green")
        output_text.append(" → ", style="dim")
        output_text.append(f"{self.result}", style="yellow")
        sections.append(output_text)

        # Dependencies
        if self.pipe_dependencies:
            sections.append(Text(""))  # Empty line
            deps_text = Text()
            deps_text.append("Dependencies: ", style="bold")
            deps_text.append(", ".join(self.pipe_dependencies), style="blue")
            sections.append(deps_text)

        # Group all sections and print
        content = Group(*sections)
        pretty_print(content, title=main_title, subtitle=subtitle, border_style="blue")
