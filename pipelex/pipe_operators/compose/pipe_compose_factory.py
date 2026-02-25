from typing import Any

from typing_extensions import override

from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
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
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeComposeBlueprint,
    ) -> PipeCompose:
        if blueprint.construct_blueprint is not None:
            return PipeCompose(
                domain_code=domain_code,
                code=pipe_code,
                description=description,
                inputs=inputs,
                output=output,
                construct_blueprint=blueprint.construct_blueprint,
            )
        else:
            return cls._make_template_mode(
                pipe_code=pipe_code,
                domain_code=domain_code,
                description=description,
                inputs=inputs,
                output=output,
                blueprint=blueprint,
            )

    @classmethod
    def _make_template_mode(
        cls,
        pipe_code: str,
        domain_code: str,
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeComposeBlueprint,
    ) -> PipeCompose:
        """Create PipeCompose in template mode (produces Text output)."""
        template_source = blueprint.template_source
        if template_source is None:
            msg = "Template source is required for template mode"
            raise PipeComposeFactoryError(msg)

        preprocessed_template = preprocess_template(template_source)
        try:
            check_jinja2_parsing(
                template_source=preprocessed_template,
                template_category=blueprint.template_category,
            )
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Error parsing Jinja2 template for PipeCompose: {exc}"
            raise PipeComposeFactoryError(msg) from exc

        return PipeCompose(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            template=preprocessed_template,
            templating_style=blueprint.templating_style,
            category=blueprint.template_category,
            extra_context=blueprint.extra_context,
        )
