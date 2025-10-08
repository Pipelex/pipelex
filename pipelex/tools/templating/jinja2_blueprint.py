from typing import Any

from pydantic import BaseModel, Field, model_validator

from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle


class Jinja2Blueprint(BaseModel):
    jinja2: str = Field(description="Raw Jinja2 template string")
    prompting_style: PromptingStyle | None = Field(default=None, description="Style of prompting to use (typically for different LLMs)")
    template_category: Jinja2TemplateCategory = Field(
        default=Jinja2TemplateCategory.LLM_PROMPT,
        description="Category of the template (could also be HTML, MARKDOWN, MERMAID, etc.), influences Jinja2 rendering environment config",
    )
    extra_context: dict[str, Any] | None = Field(default=None, description="Additional context variables for template rendering")

    @model_validator(mode="after")
    def validate_template(self) -> "Jinja2Blueprint":
        check_jinja2_parsing(jinja2_template_source=self.jinja2, template_category=self.template_category)
        return self
