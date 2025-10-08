from typing import Any, Literal

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.templating.template_blueprint import TemplateBlueprint
from pipelex.tools.templating.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle


class PipeComposeBlueprint(PipeBlueprint):
    type: Literal["PipeCompose"] = "PipeCompose"
    category: Literal["PipeOperator"] = "PipeOperator"
    template: str | TemplateBlueprint

    @property
    def template_source(self) -> str:
        if isinstance(self.template, TemplateBlueprint):
            return self.template.source
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
