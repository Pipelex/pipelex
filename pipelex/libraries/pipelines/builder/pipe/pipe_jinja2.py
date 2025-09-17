from typing import Any, Dict, Literal, Optional

from pydantic import Field
from typing_extensions import override

from pipelex.core.stuffs.stuff_content import StructuredContent
from pipelex.libraries.pipelines.builder.pipe.pipe import PipeBlueprint
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint as PipeJinja2BlueprintCore
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.templating_models import PromptingStyle as PromptingStyleCore
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
    category: Literal["PipeOperator"] = "PipeOperator"

    @override
    def to_core_blueprint(self, pipe_code: str, domain: str) -> PipeJinja2BlueprintCore:
        """Convert this PipeJinja2Blueprint to the core PipeJinja2Blueprint."""
        base_blueprint = super().to_core_blueprint(pipe_code, domain)

        if self.prompting_style:
            prompting_style = (
                self.prompting_style
                if isinstance(self.prompting_style, PromptingStyleCore)
                else PromptingStyleCore(tag_style=self.prompting_style.tag_style, text_format=self.prompting_style.text_format)
            )
        else:
            prompting_style = None

        return PipeJinja2BlueprintCore(
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            jinja2_name=self.jinja2_name,
            jinja2=self.jinja2,
            prompting_style=prompting_style,
            template_category=self.template_category,
            extra_context=self.extra_context,
        )


class PipeJinja2SpecBlueprint(PipeJinja2Blueprint):
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
