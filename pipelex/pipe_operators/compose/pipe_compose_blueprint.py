from typing import Any, Literal

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeComposeBlueprint(PipeBlueprint):
    type: Literal["PipeCompose"] = "PipeCompose"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    template: str | TemplateBlueprint

    @property
    def template_source(self) -> str:
        if isinstance(self.template, TemplateBlueprint):
            return self.template.template
        return self.template

    @property
    def template_category(self) -> TemplateCategory:
        if isinstance(self.template, TemplateBlueprint):
            return self.template.category
        else:
            return TemplateCategory.BASIC

    @property
    def templating_style(self) -> TemplatingStyle | None:
        if isinstance(self.template, TemplateBlueprint):
            return self.template.templating_style
        else:
            return None

    @property
    def extra_context(self) -> dict[str, Any] | None:
        if isinstance(self.template, TemplateBlueprint):
            return self.template.extra_context
        else:
            return None
