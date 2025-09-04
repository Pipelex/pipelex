from typing import Any, Dict, Literal, Optional

from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.libraries.pipelines.builder.pipe.pipe import PipeBlueprint
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import TagStyle, TextFormat


class PromptingStyle(StructuredContent):
    tag_style: TagStyle = Field(strict=False)
    text_format: TextFormat = Field(TextFormat.PLAIN, strict=False)


class Jinja2Blueprint(StructuredContent):
    jinja2_name: Optional[str] = Field(default=None, description="Name of the Jinja2 template to use")
    jinja2: Optional[str] = Field(default=None, description="Raw Jinja2 template string")
    prompting_style: Optional[PromptingStyle] = Field(default=None, description="Style of prompting to use (typically for different LLMs)")
    template_category: Jinja2TemplateCategory = Field(
        default=Jinja2TemplateCategory.LLM_PROMPT,
        description="Category of the template (could also be HTML, MARKDOWN, MERMAID, etc.), influences Jinja2 rendering environment config",
    )
    extra_context: Optional[Dict[str, Any]] = Field(default=None, description="Additional context variables for template rendering")


class PipeJinja2Blueprint(PipeBlueprint, Jinja2Blueprint):
    type: Literal["PipeJinja2"] = "PipeJinja2"


class PipeJinja2SpecBlueprint(PipeJinja2Blueprint):
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
