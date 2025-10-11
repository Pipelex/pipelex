from typing import Literal

from pydantic import Field, field_validator
from pydantic.json_schema import SkipJsonSchema
from typing_extensions import override

from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle, TagStyle, TextFormat
from pipelex.types import StrEnum


class TargetFormat(StrEnum):
    PLAIN = "plain"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    SPREADSHEET = "spreadsheet"
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
            case TargetFormat.SPREADSHEET:
                return TagStyle.NO_TAG
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
            case TargetFormat.SPREADSHEET:
                return TextFormat.SPREADSHEET
            case TargetFormat.MERMAID:
                return TextFormat.PLAIN

    @property
    def prompting_style(self) -> PromptingStyle:
        return PromptingStyle(tag_style=self.tag_style, text_format=self.text_format)

    @property
    def template_category(self) -> Jinja2TemplateCategory:
        match self:
            case TargetFormat.PLAIN:
                return Jinja2TemplateCategory.MARKDOWN
            case TargetFormat.MARKDOWN:
                return Jinja2TemplateCategory.MARKDOWN
            case TargetFormat.HTML:
                return Jinja2TemplateCategory.HTML
            case TargetFormat.JSON:
                return Jinja2TemplateCategory.HTML
            case TargetFormat.SPREADSHEET:
                return Jinja2TemplateCategory.HTML
            case TargetFormat.MERMAID:
                return Jinja2TemplateCategory.MERMAID


class PipeComposeSpec(PipeSpec):
    """PipeComposeSpec defines a templating operation based on a Jinja2 template."""

    type: SkipJsonSchema[Literal["PipeCompose"]] = "PipeCompose"
    category: SkipJsonSchema[Literal["PipeOperator"]] = "PipeOperator"
    jinja2: str | None = Field(default=None, description="Jinja2 template string")
    target_format: TargetFormat | str = Field(description="Target format for the output")

    @field_validator("target_format", mode="before")
    @classmethod
    def validate_target_format(cls, target_format_value: str) -> TargetFormat:
        return TargetFormat(target_format_value)

    @override
    def to_blueprint(self) -> PipeComposeBlueprint:
        base_blueprint = super().to_blueprint()

        target_format = TargetFormat(self.target_format)
        prompting_style = target_format.prompting_style
        template_category = target_format.template_category

        return PipeComposeBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            jinja2_name=None,
            jinja2=self.jinja2,
            prompting_style=prompting_style,
            template_category=template_category,
            extra_context=None,
        )
