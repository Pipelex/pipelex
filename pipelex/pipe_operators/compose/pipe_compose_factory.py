from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input import PipeInputSpec
from pipelex.core.pipes.pipe_input_factory import PipeInputSpecFactory
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_concept_provider
from pipelex.pipe_operators.compose.pipe_compose import PipeCompose
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.template_preprocessor import preprocess_template


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
        preprocessed_template: str | None = None
        if blueprint.jinja2:
            preprocessed_template = preprocess_template(blueprint.jinja2)
            check_jinja2_parsing(
                jinja2_template_source=preprocessed_template,
                template_category=blueprint.template_category,
            )
        else:
            preprocessed_template = None

        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeCompose(
            domain=domain,
            code=pipe_code,
            description=blueprint.description,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain,
                blueprint=blueprint.inputs or {},
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.make_concept_string_with_domain(
                    domain=output_domain_and_code.domain,
                    concept_code=output_domain_and_code.concept_code,
                ),
            ),
            jinja2_name=blueprint.jinja2_name,
            jinja2=preprocessed_template,
            prompting_style=blueprint.prompting_style,
            template_category=blueprint.template_category,
            extra_context=blueprint.extra_context,
        )

    @classmethod
    def make_pipe_compose_from_template_str(
        cls,
        domain: str,
        inputs: PipeInputSpec | None = None,
        template_str: str | None = None,
        template_name: str | None = None,
    ) -> PipeCompose:
        if template_str:
            preprocessed_template = preprocess_template(template_str)
            check_jinja2_parsing(
                jinja2_template_source=preprocessed_template,
                template_category=Jinja2TemplateCategory.LLM_PROMPT,
            )
            return PipeCompose(
                domain=domain,
                code="adhoc_pipe_compose_from_template_str",
                jinja2=preprocessed_template,
                inputs=inputs or PipeInputSpecFactory.make_empty(),
            )
        elif template_name:
            return PipeCompose(
                domain=domain,
                code="adhoc_pipe_compose_from_template_name",
                jinja2_name=template_name,
                inputs=inputs or PipeInputSpecFactory.make_empty(),
            )
        else:
            msg = "Could not make a PipeCompose because neither template_str nor template_name were provided"
            raise PipeDefinitionError(msg)
