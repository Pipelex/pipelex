from typing_extensions import override

from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.exceptions import ConceptFactoryError
from pipelex.core.pipes.exceptions import PipeVariableMultiplicityError
from pipelex.core.pipes.inputs.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import get_required_concept
from pipelex.pipe_operators.compose.exceptions import PipeComposeFactoryError
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.jinja2.jinja2_errors import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing


class PipeComposeFactory(PipeFactoryProtocol[PipeComposeBlueprint, PipeCompose]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeComposeBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
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

        # Parse output to strip multiplicity brackets
        try:
            output_parse_result = parse_concept_with_multiplicity(blueprint.output)
        except PipeVariableMultiplicityError as exc:
            msg = f"Error parsing concept with multiplicity for PipeCompose: {exc}"
            raise PipeComposeFactoryError(msg) from exc
        try:
            output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
                domain=domain,
                concept_string_or_code=output_parse_result.concept,
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            )
        except ConceptFactoryError as exc:
            msg = f"Error making domain and concept code for PipeCompose: {exc}"
            raise PipeComposeFactoryError(msg) from exc
        return PipeCompose(
            domain=domain,
            code=pipe_code,
            description=blueprint.description,
            inputs=InputRequirementsFactory.make_from_blueprint(
                domain=domain,
                blueprint=blueprint.inputs or {},
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            ),
            output=get_required_concept(
                concept_string=ConceptFactory.make_concept_string_with_domain(
                    domain=output_domain_and_code.domain,
                    concept_code=output_domain_and_code.concept_code,
                ),
            ),
            template=preprocessed_template,
            templating_style=blueprint.templating_style,
            category=blueprint.template_category,
            extra_context=blueprint.extra_context,
        )
