from typing import List, Optional

from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
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
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeImgGen:
        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=blueprint.output_concept_string_or_concept_code,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeImgGen(
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
            output_multiplicity=blueprint.nb_output or 1,
            imgg_prompt=blueprint.img_gen_prompt,
            imgg_handle=blueprint.imgg_handle,
            aspect_ratio=blueprint.aspect_ratio,
            nb_steps=blueprint.nb_steps,
            guidance_scale=blueprint.guidance_scale,
            is_moderated=blueprint.is_moderated,
            safety_tolerance=blueprint.safety_tolerance,
            is_raw=blueprint.is_raw,
            seed=blueprint.seed,
            img_gen_prompt_var_name=blueprint.img_gen_prompt_var_name,
        )
