from typing import Literal

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.core.pipes.pipe_blueprint import PipeType
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeSignatureSpec(PipeSpec):
    """A contract-only pipe: inputs, output, and purpose declared without an implementation.

    Use signatures to sketch a pipeline top-down — author the controller and stub each step
    as a `PipeSignature`, then replace each one with a real operator (PipeLLM, PipeFunc, ...)
    once the contract is settled.

    Validation behavior:
        - Strict (default), single pipe — `pipelex validate <pipe>` refuses any pipeline that
          reaches a signature through its dependency graph and reports the controller chain.
        - Strict (default), whole bundle — `validate bundle <file>` refuses a bundle that
          *contains* a signature at all (reached or not): an unimplemented placeholder means the
          bundle is not fully runnable. To validate just the implemented slice of a partially
          stubbed bundle, select it with `--pipe <code>` (only that pipe is dry-run).
        - Lenient — pass `--allow-signatures` to dry-run signatures as mocks (a `Stuff`
          matching the declared output, multiplicity included).
        - Live execution always raises `PipeSignatureNotExecutableError`; signatures have
          no implementation to run.

    Multiplicity notation (same rules as other pipes — see Understanding Multiplicity):
        - `Text` — single item
        - `Text[]` — variable-length list
        - `Image[3]` — exactly 3 items

    Optional fields:
        - `signature_for`: hint naming the downstream pipe type the signature stands in for
          (e.g. `PipeType.PIPE_LLM`). Tooling-only; `PipeSignature` is not a `PipeType`, so it
          cannot be selected here.
    """

    # Internal `PipeSpecUnion` discriminator, never written by the author and never rendered as a
    # "type" line (a signature is typeless). `SkipJsonSchema` keeps it out of the authoring schema;
    # `exclude=True` keeps it out of `model_dump()` so a dump→revalidate round-trip stays typeless and
    # re-injects the tag (mirrors `PipeSignatureBlueprint.type`) instead of tripping the migration error.
    type: SkipJsonSchema[Literal["PipeSignature"]] = Field(default="PipeSignature", exclude=True)
    # Spec-layer authoring tag only: NOT propagated by `to_blueprint()`, which leaves the blueprint
    # (and runtime) at `pipe_category = None` because a signature is outside the executable taxonomy.
    # Retained per the scope decision in wip/recursivity/signature-taxonomy-refactor.md; no longer
    # surfaced in `rendered_pretty` (a signature now renders as "Signature (contract only)", with no
    # type/category line). `exclude=True` (like `type`) keeps it out of `model_dump()` so it is not a
    # stray key on a round-trip.
    pipe_category: SkipJsonSchema[Literal["PipeSignature"]] = Field(default="PipeSignature", exclude=True)
    signature_for: PipeType | None = Field(
        default=None,
        description="Intended downstream pipe type when this signature is implemented (optional hint for agents).",
    )

    @override
    def to_blueprint(self) -> PipeSignatureBlueprint:
        return PipeSignatureBlueprint(
            description=self.description,
            inputs=self.inputs,
            output=self.output,
            signature_for=self.signature_for,
        )

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        pipe_group = Group()
        if title:
            pipe_group.renderables.append(Text(title, style="bold"))
        pipe_group.renderables.append(Text.from_markup(f"Pipe Signature: [red]{escape(self.pipe_code)}[/red]\n", style="bold"))
        pipe_group.renderables.append(Text.from_markup("[bold magenta]Signature[/bold magenta] (contract only)\n"))
        pipe_group.renderables.append(Text.from_markup(f"Description: [yellow italic]{escape(self.description)}[/yellow italic]\n"))

        if not self.inputs:
            pipe_group.renderables.append(Text.from_markup("\nNo inputs"))
        elif len(self.inputs) == 1:
            input_name, concept_spec = next(iter(self.inputs.items()))
            pipe_group.renderables.append(
                Text.from_markup(f"\nInput: [cyan]{escape(input_name)}[/cyan] ([bold green]{escape(concept_spec)}[/bold green])")
            )
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
                inputs_table.add_row(escape(input_name), escape(concept_spec))
            pipe_group.renderables.append(inputs_table)

        pipe_group.renderables.append(Text.from_markup(f"\nOutput concept: [bold green]{escape(self.output)}[/bold green]"))
        if self.signature_for is not None:
            pipe_group.renderables.append(Text.from_markup(f"\nSignature for: [bold yellow]{escape(self.signature_for)}[/bold yellow]"))

        return pipe_group
