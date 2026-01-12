from typing import Literal

from pydantic import Field, field_validator
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
from pipelex.types import StrEnum


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
    """PipeComposeSpec defines a templating operation based on a Jinja2 template."""

    type: SkipJsonSchema[Literal["PipeCompose"]] = "PipeCompose"
    pipe_category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"
    template: str = Field(description="Jinja2 template string")
    target_format: TargetFormat | str = Field(description="Target format for the output")

    @field_validator("target_format", mode="before")
    @classmethod
    def validate_target_format(cls, target_format_value: str) -> TargetFormat:
        return TargetFormat(target_format_value)

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with compose-specific details
        compose_group = Group()
        compose_group.renderables.append(base_group)

        # Add target format
        compose_group.renderables.append(Text())  # Blank line
        compose_group.renderables.append(Text.from_markup(f"Target Format: [bold yellow]{self.target_format}[/bold yellow]"))

        # Add template in a panel
        compose_group.renderables.append(Text())  # Blank line
        template_panel = Panel(
            self.template,
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
