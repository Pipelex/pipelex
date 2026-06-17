from typing import Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.markup import escape
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable


class PipeStructureSpec(PipeSpec):
    """Spec for the PipeStructure operator.

    PipeStructure converts a Text-compatible input into a structured concept using an LLM call.
    Use it when you already have text (e.g., extracted from a PDF, fetched from a search, or
    produced by an earlier pipe) and want to turn it into typed data.

    Validation Rules:
        - inputs dict must have exactly one entry, and its concept must be Text-compatible.
        - output must NOT be Text-compatible.
    """

    type: SkipJsonSchema[Literal["PipeStructure"]] = "PipeStructure"
    pipe_category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"
    model: str | None = Field(
        default=None,
        description="Model preset, alias, waterfall, or direct model handle. Use presets from 'pipelex-agent models'.",
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
        base_group = super().rendered_pretty(title=title, depth=depth)

        structure_group = Group()
        structure_group.renderables.append(base_group)

        structure_group.renderables.append(Text())  # Blank line
        structure_group.renderables.append(Text.from_markup(f"Model: [bold yellow]{escape(self.model or '(default)')}[/bold yellow]"))

        return structure_group

    @override
    def to_blueprint(self) -> PipeStructureBlueprint:
        base_blueprint = super().to_blueprint()

        return PipeStructureBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            model=self.model,
        )
