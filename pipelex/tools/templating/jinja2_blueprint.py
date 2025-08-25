from typing import Any, Dict, Optional, Set

from pydantic import BaseModel, Field

from pipelex import log
from pipelex.hub import get_template, get_template_provider
from pipelex.tools.templating.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle


class Jinja2Blueprint(BaseModel):
    jinja2_name: Optional[str] = Field(default=None, description="Name of the Jinja2 template to use")
    jinja2: Optional[str] = Field(default=None, description="Raw Jinja2 template string")
    prompting_style: Optional[PromptingStyle] = Field(default=None, description="Style of prompting to use (typically for different LLMs)")
    template_category: Jinja2TemplateCategory = Field(
        default=Jinja2TemplateCategory.LLM_PROMPT,
        description="Category of the template (could also be HTML, MARKDOWN, MERMAID, etc.), influences Jinja2 rendering environment config",
    )
    extra_context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context variables for template rendering")

    def required_variables(self) -> Set[str]:
        required_variables = detect_jinja2_required_variables(
            template_category=self.template_category,
            template_provider=get_template_provider(),
            jinja2_name=self.jinja2_name,
            jinja2=self.jinja2,
        )
        return {
            variable_name
            for variable_name in required_variables
            if not variable_name.startswith("_") and variable_name != "preliminary_text" and variable_name != "place_holder"
        }

    def validate_with_libraries(self):
        if self.jinja2_name:
            the_template = get_template(template_name=self.jinja2_name)
            log.debug(f"Validated jinja2 template '{self.jinja2_name}':\n{the_template}")
