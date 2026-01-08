from collections.abc import Callable
from typing import Any

from pipelex.tools.jinja2.jinja2_filters import escape_script_tag, tag, text_format
from pipelex.tools.jinja2.jinja2_models import Jinja2FilterName
from pipelex.types import StrEnum


class TemplateCategory(StrEnum):
    BASIC = "basic"
    EXPRESSION = "expression"
    HTML = "html"
    MARKDOWN = "markdown"
    MERMAID = "mermaid"
    LLM_PROMPT = "llm_prompt"
    IMG_GEN_PROMPT = "img_gen_prompt"

    @property
    def filters(self) -> dict[Jinja2FilterName, Callable[..., Any]]:
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
                    Jinja2FilterName.ESCAPE_SCRIPT_TAG: escape_script_tag,
                }
            case TemplateCategory.LLM_PROMPT:
                return {
                    Jinja2FilterName.FORMAT: text_format,
                    Jinja2FilterName.TAG: tag,
                }
            case TemplateCategory.IMG_GEN_PROMPT:
                return {
                    Jinja2FilterName.FORMAT: text_format,
                    Jinja2FilterName.TAG: tag,
                }
            case TemplateCategory.MERMAID:
                return {}
