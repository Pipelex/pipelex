from typing import Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeSignature(PipeSpec):
    """A contract for a pipe: inputs, output, and purpose declared without an implementation.

    Multiplicity Notation:
        Use bracket notation to specify multiplicity for both inputs and outputs:
        - No brackets: single item (default)
        - []: variable-length list
        - [N]: exactly N items (where N is a positive integer)

    Examples:
        - output = "Text" - one text item
        - output = "Text[]" - multiple text items
        - output = "Image[3]" - exactly 3 images

    Strict validation refuses pipelines that still contain signatures (use `--allow-signatures`
    to dry-run lenient). `signature_for` is an optional hint to downstream tooling describing
    the intended downstream pipe type once the signature is implemented.
    """

    type: SkipJsonSchema[Literal["PipeSignature"]] = "PipeSignature"
    pipe_category: SkipJsonSchema[Literal["PipeSignature"]] = "PipeSignature"
    signature_for: PipeType | None = Field(
        default=None,
        description="Intended downstream pipe type when this signature is implemented (optional hint for agents).",
    )
    # Stored as `pipe_dependencies` on the spec (user-authoring surface), mapped to
    # `signature_pipe_dependencies` on the blueprint and `declared_dependencies` on the runtime —
    # both layers carry `pipe_dependencies` already as a property/method returning `set[str]`,
    # which a list-typed field would silently shadow.
    pipe_dependencies: list[str] = Field(
        default_factory=list,
        description="Pipes this signature claims to depend on (metadata for tooling).",
    )

    @field_validator("signature_for", mode="after")
    @classmethod
    def reject_signature_for_pipe_signature(cls, value: PipeType | None) -> PipeType | None:
        if value is PipeType.PIPE_SIGNATURE:
            msg = "A PipeSignature cannot have signature_for=PipeSignature."
            raise ValueError(msg)
        return value

    @override
    def to_blueprint(self) -> PipeSignatureBlueprint:
        return PipeSignatureBlueprint(
            description=self.description,
            inputs=self.inputs,
            output=self.output,
            signature_for=self.signature_for,
            signature_pipe_dependencies=list(self.pipe_dependencies),
        )

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        pipe_group = Group()
        if title:
            pipe_group.renderables.append(Text(title, style="bold"))
        pipe_group.renderables.append(Text.from_markup(f"Pipe Signature: [red]{self.pipe_code}[/red]\n", style="bold"))
        pipe_group.renderables.append(Text.from_markup(f"Type: [bold magenta]{self.type}[/bold magenta] ({self.pipe_category})\n"))
        pipe_group.renderables.append(Text.from_markup(f"Description: [yellow italic]{self.description}[/yellow italic]\n"))

        if not self.inputs:
            pipe_group.renderables.append(Text.from_markup("\nNo inputs"))
        elif len(self.inputs) == 1:
            input_name, concept_spec = next(iter(self.inputs.items()))
            pipe_group.renderables.append(Text.from_markup(f"\nInput: [cyan]{input_name}[/cyan] ([bold green]{concept_spec}[/bold green])"))
        else:
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

        pipe_group.renderables.append(Text.from_markup(f"\nOutput concept: [bold green]{self.output}[/bold green]"))
        if self.signature_for is not None:
            pipe_group.renderables.append(Text.from_markup(f"\nSignature for: [bold yellow]{self.signature_for}[/bold yellow]"))
        if self.pipe_dependencies:
            pipe_group.renderables.append(Text.from_markup(f"\nDependencies: [red]{', '.join(self.pipe_dependencies)}[/red]"))

        return pipe_group
