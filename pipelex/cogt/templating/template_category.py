from collections.abc import Callable
from typing import Any

from jinja2.runtime import Context

from pipelex.cogt.templating.templating_style import TextFormat
from pipelex.tools.jinja2.jinja2_filters import tag, text_format
from pipelex.tools.jinja2.jinja2_models import Jinja2FilterName
from pipelex.types import StrEnum


class TemplateCategory(StrEnum):
    BASIC = "basic"
    EXPRESSION = "expression"
    HTML = "html"
    MARKDOWN = "markdown"
    MERMAID = "mermaid"
    LLM_PROMPT = "llm_prompt"

    @property
    def filters(self) -> dict[Jinja2FilterName, Callable[[Context, Any, TextFormat | None], Any]]:
        match self:
            case TemplateCategory.BASIC:
                return {
                    Jinja2FilterName.FORMAT: text_format,
                    Jinja2FilterName.TAG: tag,
                }
            case TemplateCategory.EXPRESSION:
                return {}
            case TemplateCategory.HTML | TemplateCategory.MARKDOWN:
                return {
                    Jinja2FilterName.FORMAT: text_format,
                    Jinja2FilterName.TAG: tag,
                }
            case TemplateCategory.LLM_PROMPT:
                return {
                    Jinja2FilterName.FORMAT: text_format,
                    Jinja2FilterName.TAG: tag,
                }
            case TemplateCategory.MERMAID:
                return {}
