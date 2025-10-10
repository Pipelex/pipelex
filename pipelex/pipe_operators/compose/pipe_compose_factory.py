from typing_extensions import override

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.hub import get_required_concept
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
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
        check_jinja2_parsing(
            template_source=preprocessed_template,
            template_category=blueprint.template_category,
        )

        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
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

    @classmethod
    def make_pipe_compose_from_template_str(
        cls,
        domain: str,
        template_str: str,
        inputs: InputRequirements | None = None,
    ) -> PipeCompose:
        preprocessed_template = preprocess_template(template_str)
        check_jinja2_parsing(
            template_source=preprocessed_template,
            template_category=TemplateCategory.LLM_PROMPT,
        )
        return PipeCompose(
            domain=domain,
            code="adhoc_pipe_compose_from_template_str",
            template=preprocessed_template,
            inputs=inputs or InputRequirementsFactory.make_empty(),
        )
