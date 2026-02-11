from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.cogt.templating.text_format import TextFormat
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.types import Self, StrEnum


class TargetFormat(StrEnum):
    PLAIN = "plain"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    MERMAID = "mermaid"

    @property
    def tag_style(self) -> TagStyle:
        match self:
            case TargetFormat.PLAIN:
                return TagStyle.NO_TAG
            case TargetFormat.MARKDOWN:
                return TagStyle.TICKS
            case TargetFormat.HTML:
                return TagStyle.XML
            case TargetFormat.JSON:
                return TagStyle.SQUARE_BRACKETS
            case TargetFormat.MERMAID:
                return TagStyle.NO_TAG

    @property
    def text_format(self) -> TextFormat:
        match self:
            case TargetFormat.PLAIN:
                return TextFormat.PLAIN
            case TargetFormat.MARKDOWN:
                return TextFormat.MARKDOWN
            case TargetFormat.HTML:
                return TextFormat.HTML
            case TargetFormat.JSON:
                return TextFormat.JSON
            case TargetFormat.MERMAID:
                return TextFormat.PLAIN

    @property
    def templating_style(self) -> TemplatingStyle:
        return TemplatingStyle(tag_style=self.tag_style, text_format=self.text_format)

    @property
    def category(self) -> TemplateCategory:
        match self:
            case TargetFormat.PLAIN:
                return TemplateCategory.MARKDOWN
            case TargetFormat.MARKDOWN:
                return TemplateCategory.MARKDOWN
            case TargetFormat.HTML:
                return TemplateCategory.HTML
            case TargetFormat.JSON:
                return TemplateCategory.HTML
            case TargetFormat.MERMAID:
                return TemplateCategory.MERMAID


class PipeComposeSpec(PipeSpec):
    """PipeComposeSpec defines a composition operation.

    Two modes are supported:

    **Template mode** (for Text/Html output):
    - Renders a template to produce formatted text
    - Use Pipelex pre-processor syntax:
      - `@variable` renders an entire object with all attributes auto-formatted
      - `$variable.field` for inline field access (e.g., "Order #$order.id")
      - Only use `{{ variable.field }}` for isolated single-field access
    - NEVER manually list all attributes - use `@variable` instead

    **Construct mode** (for StructuredContent output):
    - Assembles a structured object from working memory variables
    - PREFER `{ from = "variable" }` for direct object/value assignment
    - Use `{ template = "..." }` ONLY for string composition (e.g., "INV-$order.id")
    - NEVER use templates to manually replicate object attributes
    """

    type: SkipJsonSchema[Literal["PipeCompose"]] = "PipeCompose"
    pipe_category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"

    # Template mode fields
    template: str | None = Field(
        default=None,
        description=(
            "Template string using Pipelex pre-processor syntax: "
            "use @variable to render entire objects with auto-formatting, "
            "$variable.field for inline access. "
            "NEVER manually list all attributes of an object - use @variable instead."
        ),
    )
    target_format: TargetFormat | str | None = Field(
        default=None, description="Target format for the output (template mode)", examples=list(TargetFormat)
    )

    # Construct mode field
    # Note: Named 'construct_spec' to avoid conflict with Pydantic's BaseModel.construct() method
    # Accepts both 'construct' and 'construct_spec' as input names (see normalize_construct_field validator)
    # mock_format: "ignore" ensures dry run factory only generates template mode (to avoid mutual exclusivity conflict)
    construct_spec: dict[str, Any] | None = Field(
        default=None,
        validation_alias="construct",
        description=(
            "Field composition spec mapping field names to values. "
            "PREFER { from = 'variable' } for direct object assignment. "
            "Use { template = '...' } ONLY for string composition like 'INV-$order.id'. "
            "NEVER use templates to manually replicate object attributes."
        ),
        json_schema_extra={"mock_format": "ignore"},
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_construct_field(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Accept both 'construct_spec' and 'construct' as input field names.

        The LLM may generate either name, so we normalize 'construct_spec' to 'construct'
        which is the validation_alias that Pydantic expects.
        """
        if "construct_spec" in values and "construct" not in values:
            values["construct"] = values.pop("construct_spec")
        return values

    @field_validator("target_format", mode="before")
    @classmethod
    def validate_target_format(cls, target_format_value: str | None) -> TargetFormat | None:
        if target_format_value is None:
            return None
        return TargetFormat(target_format_value)

    @model_validator(mode="after")
    def validate_mode_exclusivity(self) -> Self:
        """Validate that exactly one mode is used."""
        has_template = self.template is not None
        has_construct = self.construct_spec is not None

        if not has_template and not has_construct:
            msg = "PipeComposeSpec requires either 'template' or 'construct' to be provided"
            raise ValueError(msg)
        if has_template and has_construct:
            msg = "PipeComposeSpec cannot have both 'template' and 'construct' - use one or the other"
            raise ValueError(msg)
        if has_template and self.target_format is None:
            msg = "Template mode requires 'target_format' to be specified"
            raise ValueError(msg)
        return self

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with compose-specific details
        compose_group = Group()
        compose_group.renderables.append(base_group)

        if self.construct_spec is not None:
            # Construct mode
            compose_group.renderables.append(Text())  # Blank line
            compose_group.renderables.append(Text.from_markup("[bold cyan]Mode:[/bold cyan] Construct"))
            construct_panel = Panel(
                str(self.construct_spec),
                title="Construct",
                title_align="left",
                border_style="cyan",
                padding=(0, 1),
            )
            compose_group.renderables.append(construct_panel)
        else:
            # Template mode
            compose_group.renderables.append(Text())  # Blank line
            compose_group.renderables.append(Text.from_markup(f"Target Format: [bold yellow]{self.target_format}[/bold yellow]"))

            # Add template in a panel
            compose_group.renderables.append(Text())  # Blank line
            template_panel = Panel(
                self.template or "",
                title="Template",
                title_align="left",
                border_style="green",
                padding=(0, 1),
            )
            compose_group.renderables.append(template_panel)

        return compose_group

    @override
    def to_blueprint(self) -> PipeComposeBlueprint:
        base_blueprint = super().to_blueprint()

        if self.construct_spec is not None:
            # Construct mode: pass the raw construct dict via model_validate
            # The PipeComposeBlueprint's model_validator expects 'construct' key in raw dict
            return PipeComposeBlueprint.model_validate(
                {
                    "description": base_blueprint.description,
                    "inputs": base_blueprint.inputs,
                    "output": base_blueprint.output,
                    "construct": self.construct_spec,
                }
            )
        elif self.template is not None:
            # Template mode - target_format is guaranteed non-None by model validator
            assert self.target_format is not None
            target_format = TargetFormat(self.target_format)
            templating_style = target_format.templating_style
            category = target_format.category

            template_blueprint = TemplateBlueprint(
                template=self.template,
                templating_style=templating_style,
                category=category,
                extra_context=None,
            )

            return PipeComposeBlueprint(
                description=base_blueprint.description,
                inputs=base_blueprint.inputs,
                output=base_blueprint.output,
                template=template_blueprint,
            )
        else:
            msg = "PipeComposeSpec must have either 'template' or 'construct' to be provided"
            raise ValueError(msg)
