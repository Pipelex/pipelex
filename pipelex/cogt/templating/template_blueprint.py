from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle


class TemplateBlueprint(BaseModel):
    """The rich form of a template: its Jinja2 source and category, plus an optional templating style and extra context."""

    # An authored surface (the `[pipe.name.template]` table): unknown keys are rejected, as on every blueprint.
    model_config = ConfigDict(extra="forbid")

    template: str = Field(description="Raw template source")
    templating_style: TemplatingStyle | None = Field(
        default=None,
        description="How the tag and format filters render in this template; omit it to take the runtime default templating style",
    )
    category: TemplateCategory = Field(
        description="Category of the template (could also be HTML, MARKDOWN, MERMAID, etc.), influences template rendering rules",
    )
    extra_context: dict[str, Any] | None = Field(default=None, description="Additional context variables for template rendering")

    @model_validator(mode="after")
    def validate_template(self) -> "TemplateBlueprint":
        preprocessed = preprocess_template(self.template)
        try:
            check_jinja2_parsing(template_source=preprocessed, template_category=self.category)
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Could not parse template for TemplateBlueprint: {exc}"
            raise ValueError(msg) from exc
        return self

    def required_variables(self) -> set[str]:
        template_source = preprocess_template(self.template)
        return detect_jinja2_required_variables(
            template_category=self.category,
            template_source=template_source,
        )
