from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_factory import PipeInputSpecFactory
from pipelex.hub import get_concept_provider
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class PipeImgGenFactory(PipeFactoryProtocol[PipeImgGenBlueprint, PipeImgGen]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        blueprint: PipeImgGenBlueprint,
        concept_codes_from_the_same_domain: list[str] | None = None,
    ) -> PipeImgGen:
        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeImgGen(
            domain=domain,
            code=pipe_code,
            definition=blueprint.definition,
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain,
                blueprint=blueprint.inputs or {},
                concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
            ),
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(
                    domain=output_domain_and_code.domain,
                    concept_code=output_domain_and_code.concept_code,
                ),
            ),
            output_multiplicity=blueprint.nb_output or 1,
            img_gen_prompt=blueprint.img_gen_prompt,
            img_gen_prompt_var_name=blueprint.img_gen_prompt_var_name,
            img_gen=blueprint.img_gen,
            aspect_ratio=blueprint.aspect_ratio,
            is_raw=blueprint.is_raw,
            seed=blueprint.seed,
            background=blueprint.background,
            output_format=blueprint.output_format,
        )
