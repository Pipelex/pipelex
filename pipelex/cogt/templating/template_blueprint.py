from typing import Any

from pydantic import BaseModel, Field, model_validator

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables


class TemplateBlueprint(BaseModel):
    template: str = Field(description="Raw template source")
    templating_style: TemplatingStyle | None = Field(default=None, description="Style of prompting to use (typically for different LLMs)")
    category: TemplateCategory = Field(
        description="Category of the template (could also be HTML, MARKDOWN, MERMAID, etc.), influences template rendering rules",
    )
    extra_context: dict[str, Any] | None = Field(default=None, description="Additional context variables for template rendering")

    @model_validator(mode="after")
    def validate_template(self) -> "TemplateBlueprint":
        try:
            check_jinja2_parsing(template_source=self.template, template_category=self.category)
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
