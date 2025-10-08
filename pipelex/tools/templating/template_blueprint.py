from typing import Any

from pydantic import BaseModel, Field, model_validator

from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle


class TemplateBlueprint(BaseModel):
    source: str = Field(description="Raw template source")
    templating_style: TemplatingStyle | None = Field(default=None, description="Style of prompting to use (typically for different LLMs)")
    category: TemplateCategory = Field(
        description="Category of the template (could also be HTML, MARKDOWN, MERMAID, etc.), influences template rendering rules",
    )
    extra_context: dict[str, Any] | None = Field(default=None, description="Additional context variables for template rendering")

    @model_validator(mode="after")
    def validate_template(self) -> "TemplateBlueprint":
        check_jinja2_parsing(jinja2_template_source=self.source, template_category=self.category)
        return self
