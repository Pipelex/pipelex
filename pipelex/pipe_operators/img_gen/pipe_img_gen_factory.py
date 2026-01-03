from typing import Any

from typing_extensions import override

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class PipeImgGenFactory(PipeFactoryProtocol[PipeImgGenBlueprint, PipeImgGen]):
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
        blueprint: PipeImgGenBlueprint,
    ) -> PipeImgGen:
        # Parse output for multiplicity (may have brackets like "Image[]" or "Image[3]")
        output_parse_result = parse_concept_with_multiplicity(blueprint.output)

        # Convert bracket notation to output_multiplicity (default to 1 if no brackets)
        final_multiplicity = output_parse_result.multiplicity if isinstance(output_parse_result.multiplicity, int) else 1

        prompt_blueprint = TemplateBlueprint(
            template=blueprint.prompt,
            category=TemplateCategory.IMG_GEN_PROMPT,
        )
        negative_prompt_blueprint = (
            TemplateBlueprint(
                template=blueprint.negative_prompt,
                category=TemplateCategory.IMG_GEN_PROMPT,
            )
            if blueprint.negative_prompt
            else None
        )
        return PipeImgGen(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            output_multiplicity=final_multiplicity,
            prompt_blueprint=prompt_blueprint,
            negative_prompt_blueprint=negative_prompt_blueprint,
            img_gen_choice=blueprint.model,
            aspect_ratio=blueprint.aspect_ratio,
            is_raw=blueprint.is_raw,
            seed=blueprint.seed,
            background=blueprint.background,
            output_format=blueprint.output_format,
        )
