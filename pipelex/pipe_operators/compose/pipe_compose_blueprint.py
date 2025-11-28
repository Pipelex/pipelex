from typing import Any, Literal

from typing_extensions import override

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.cogt.templating.templating_style import TemplatingStyle
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables


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

    @override
    def validate_inputs(self):
        preprocessed_template = preprocess_template(self.template_source)
        try:
            check_jinja2_parsing(
                template_source=preprocessed_template,
                template_category=self.template_category,
            )
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Could not parse template for PipeCompose: {exc}"
            raise ValueError(msg) from exc
        required_variables = {
            variable_name
            for variable_name in detect_jinja2_required_variables(
                template_category=self.template_category,
                template_source=preprocessed_template,
            )
            if not variable_name.startswith("_") and variable_name not in {"preliminary_text", "place_holder"}
        }
        for required_variable_name in required_variables:
            if required_variable_name not in self.input_names:
                msg = f"Required variable '{required_variable_name}' is not in the inputs of PipeCompose."
                raise ValueError(msg)

    @override
    def validate_output(self):
        pass
