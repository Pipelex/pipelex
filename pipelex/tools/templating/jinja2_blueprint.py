from typing import Any, Dict, Optional, Set

from pydantic import BaseModel

from pipelex import log
from pipelex.hub import get_template, get_template_provider
from pipelex.tools.templating.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle


class Jinja2Blueprint(BaseModel):
    jinja2_name: Optional[str] = None
    jinja2: Optional[str] = None
    prompting_style: Optional[PromptingStyle] = None
    template_category: Jinja2TemplateCategory = Jinja2TemplateCategory.LLM_PROMPT
    extra_context: Optional[Dict[str, Any]] = None

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
