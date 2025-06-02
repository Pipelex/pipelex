from typing import Any, Callable, Dict, Optional

from jinja2.runtime import Context

from pipelex.tools.templating.jinja2_filters import tag, text_format
from pipelex.tools.templating.jinja2_models import Jinja2FilterName
from pipelex.tools.templating.templating_models import TextFormat
from pipelex.types import StrEnum


class Jinja2TemplateCategory(StrEnum):
    HTML = "html"
    MARKDOWN = "markdown"
    MERMAID = "mermaid"
    LLM_PROMPT = "llm_prompt"

    @property
    def filters(self) -> Dict[Jinja2FilterName, Callable[[Context, Any, Optional[TextFormat]], Any]]:
        match self:
            case Jinja2TemplateCategory.HTML | Jinja2TemplateCategory.MARKDOWN | Jinja2TemplateCategory.MERMAID:
                return {}
            case Jinja2TemplateCategory.LLM_PROMPT:
                return {
                    Jinja2FilterName.FORMAT: text_format,
                    Jinja2FilterName.TAG: tag,
                }
