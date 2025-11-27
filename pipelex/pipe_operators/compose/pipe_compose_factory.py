from typing import Any

from typing_extensions import override

from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.pipe_operators.compose.exceptions import PipeComposeFactoryError
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing


class PipeComposeFactory(PipeFactoryProtocol[PipeComposeBlueprint, PipeCompose]):
    @classmethod
    @override
    def make(
        cls,
        pipe_category: Any,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str | None,
        inputs: InputRequirements,
        output: Concept,
        blueprint: PipeComposeBlueprint,
    ) -> PipeCompose:
        preprocessed_template = preprocess_template(blueprint.template_source)
        try:
            check_jinja2_parsing(
                template_source=preprocessed_template,
                template_category=blueprint.template_category,
            )
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Error parsing Jinja2 template for PipeCompose: {exc}"
            raise PipeComposeFactoryError(msg) from exc

        return PipeCompose(
            domain=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            template=preprocessed_template,
            templating_style=blueprint.templating_style,
            category=blueprint.template_category,
            extra_context=blueprint.extra_context,
        )
