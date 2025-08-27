from typing import List, Optional

from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_concept_provider
from pipelex.pipe_operators.jinja2.pipe_jinja2 import PipeJinja2
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint
from pipelex.tools.templating.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.templating.jinja2_template_category import Jinja2TemplateCategory
from pipelex.tools.templating.template_preprocessor import preprocess_template


class PipeJinja2Factory(PipeFactoryProtocol[PipeJinja2Blueprint, PipeJinja2]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeJinja2Blueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeJinja2:
        preprocessed_template: Optional[str] = None
        if blueprint.jinja2:
            preprocessed_template = preprocess_template(blueprint.jinja2)
            check_jinja2_parsing(
                jinja2_template_source=preprocessed_template,
                template_category=blueprint.template_category,
            )
        else:
            preprocessed_template = None

        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=blueprint.output_concept_string_or_concept_code,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeJinja2(
            domain=domain,
            code=pipe_code,
            definition=blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(
                    domain=output_domain_and_code.domain, concept_code=output_domain_and_code.concept_code
                )
            ),
            jinja2_name=blueprint.jinja2_name,
            jinja2=preprocessed_template,
            prompting_style=blueprint.prompting_style,
            template_category=blueprint.template_category,
            extra_context=blueprint.extra_context,
        )

    @classmethod
    def make_pipe_jinja2_from_template_str(
        cls,
        domain: str,
        inputs: Optional[PipeInputSpec] = None,
        template_str: Optional[str] = None,
        template_name: Optional[str] = None,
    ) -> PipeJinja2:
        if template_str:
            preprocessed_template = preprocess_template(template_str)
            check_jinja2_parsing(
                jinja2_template_source=preprocessed_template,
                template_category=Jinja2TemplateCategory.LLM_PROMPT,
            )
            return PipeJinja2(
                domain=domain,
                code="adhoc_pipe_jinja2_from_template_str",
                jinja2=preprocessed_template,
                inputs=inputs or PipeInputSpecFactory.make_empty(),
            )
        elif template_name:
            return PipeJinja2(
                domain=domain,
                code="adhoc_pipe_jinja2_from_template_name",
                jinja2_name=template_name,
                inputs=inputs or PipeInputSpecFactory.make_empty(),
            )
        else:
            raise PipeDefinitionError("Either template_str or template_name must be provided to make_pipe_jinja2_from_template_str")
