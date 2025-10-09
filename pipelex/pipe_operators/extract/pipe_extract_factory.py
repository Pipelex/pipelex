from typing_extensions import override

from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.hub import get_required_concept
from pipelex.pipe_operators.extract.pipe_extract import PipeExtract
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint


class PipeExtractFactory(PipeFactoryProtocol[PipeExtractBlueprint, PipeExtract]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeExtractBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> PipeExtract:
        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )

        return PipeExtract(
            domain=domain,
            code=pipe_code,
            description=blueprint.description,
            output=get_required_concept(
                concept_string=ConceptFactory.make_concept_string_with_domain(
                    domain=output_domain_and_code.domain,
                    concept_code=output_domain_and_code.concept_code,
                ),
            ),
            inputs=InputRequirementsFactory.make_from_blueprint(
                domain=domain,
                blueprint=blueprint.inputs or {},
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            ),
            extract_choice=blueprint.model,
            should_include_images=blueprint.page_images or False,
            should_caption_images=blueprint.page_image_captions or False,
            should_include_page_views=blueprint.page_views or False,
            page_views_dpi=blueprint.page_views_dpi or get_config().cogt.extract_config.default_page_views_dpi,
        )
