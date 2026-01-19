import re
from typing import Any

from pydantic import Field, field_validator
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.validation import validate_concept_ref_or_code
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint, PipeCategory, PipeType
from pipelex.core.pipes.variable_multiplicity import MUTLIPLICITY_PATTERN, parse_concept_with_multiplicity
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.tools.misc.string_utils import is_snake_case, normalize_to_ascii


class PipeSpec(StructuredContent):
    """Spec defining a pipe: an executable component with a clear contract defined by its inputs and output.

    Pipes are the building blocks of a Pipelex pipeline. There are two categories:
    - Controllers: Manage execution flow (PipeSequence, PipeParallel, PipeCondition, PipeBatch)
    - Operators: Perform specific tasks (PipeLLM, PipeImgGen, PipeExtract, PipeFunc, PipeCompose)

    Multiplicity Notation:
        Both inputs and outputs use bracket notation to specify item counts:
        - No brackets: single item (default)
        - []: variable-length list (e.g., "Text[]")
        - [N]: exactly N items (e.g., "Image[3]" for 3 images)

    Examples:
        inputs = {"document": "Document", "queries": "Text[]"}  # single document, multiple texts
        output = "Article[]"  # produces a list of articles
        output = "Image[5]"  # produces exactly 5 images
    """

    pipe_code: str = Field(description="Unique pipe identifier. Must be snake_case.")
    type: Any = Field(
        description=(
            f"Pipe type. Validated at runtime, must be one of: {PipeType}. Examples: PipeLLM, PipeImgGen, PipeExtract, PipeSequence, PipeParallel."
        )
    )
    pipe_category: Any = Field(
        description=(f"Pipe category. Validated at runtime, must be one of: {PipeCategory}. Either 'PipeController' or 'PipeOperator'.")
    )
    description: str = Field(description="Natural language description of the pipe's purpose and functionality.")
    inputs: dict[str, str] = Field(
        description=(
            "Input specifications mapping variable names to concept codes with optional multiplicity. "
            "Keys: input names in snake_case. "
            "Values: ConceptCodes in PascalCase with optional brackets. "
            "Examples: 'Text' (single), 'Text[]' (variable list), 'Image[2]' (exactly 2 images), 'domain.Concept[]' (domain-qualified list)."
        )
    )
    output: str = Field(
        description=(
            "Output concept code in PascalCase with optional multiplicity brackets. "
            "Examples: 'Text' (single text), 'Article[]' (list of articles), 'Image[3]' (exactly 3 images). "
            "IMPORTANT: Always use PascalCase for the concept name."
        )
    )

    @field_validator("pipe_code", mode="before")
    @classmethod
    def validate_pipe_code(cls, value: str) -> str:
        return cls.validate_pipe_code_syntax(value)

    @field_validator("type", mode="after")
    @classmethod
    def validate_pipe_type(cls, value: Any) -> Any:
        if value not in PipeType.value_list():
            msg = f"Invalid pipe type '{value}'. Must be one of: {PipeType.value_list()}"
            raise ValueError(msg)
        return value

    @field_validator("output", mode="after")
    @classmethod
    def validate_output(cls, output: str) -> str:
        # Extract concept without multiplicity for validation
        parse_result = parse_concept_with_multiplicity(output)
        validate_concept_ref_or_code(concept_ref_or_code=parse_result.concept)
        return output  # Return original with brackets intact

    @field_validator("inputs", mode="after")
    @classmethod
    def validate_inputs(cls, inputs: dict[str, str] | None) -> dict[str, str] | None:
        if inputs is None:
            return None

        for input_name, concept_spec in inputs.items():
            if not is_snake_case(input_name):
                msg = f"Invalid input name syntax '{input_name}'. Must be in snake_case."
                raise ValueError(msg)

            # Validate the concept spec format with optional multiplicity brackets
            # Pattern allows: ConceptName, domain.ConceptName, ConceptName[], ConceptName[N]
            match = re.match(MUTLIPLICITY_PATTERN, concept_spec)
            if not match:
                msg = (
                    f"Invalid input syntax for '{input_name}': '{concept_spec}'. "
                    f"Expected format: 'ConceptName', 'ConceptName[]', or 'ConceptName[N]' where N is an integer."
                )
                raise ValueError(msg)

            # Extract the concept part (without multiplicity) and validate it
            concept_ref_or_code = match.group(1)
            validate_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code)

        return inputs

    @classmethod
    def validate_pipe_code_syntax(cls, pipe_code: str) -> str:
        # First, normalize Unicode to ASCII to prevent homograph attacks
        normalized_pipe_code = normalize_to_ascii(pipe_code)

        if normalized_pipe_code != pipe_code:
            log.warning(f"Pipe code '{pipe_code}' contained non-ASCII characters, normalized to '{normalized_pipe_code}'")

        if not is_snake_case(normalized_pipe_code):
            msg = f"Invalid pipe code syntax '{normalized_pipe_code}'. Must be in snake_case."
            raise ValueError(msg)
        return normalized_pipe_code

    def to_blueprint(self) -> PipeBlueprint:
        return PipeBlueprint(
            description=self.description,
            inputs=self.inputs or None,
            output=self.output,
            type=self.type,
            pipe_category=self.pipe_category,
        )

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        pipe_group = Group()
        if title:
            pipe_group.renderables.append(Text(title, style="bold"))
        pipe_group.renderables.append(Text.from_markup(f"Pipe: [bold red]{self.pipe_code}[/bold red]\n"))
        pipe_group.renderables.append(Text.from_markup(f"Type: [bold magenta]{self.type}[/bold magenta] ({self.pipe_category})\n"))
        if self.description:
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

        # Show output
        pipe_group.renderables.append(Text.from_markup(f"\nOutput: [bold green]{self.output}[/bold green]"))

        return pipe_group
