from typing import Any

from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
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
        description: str | None,
        inputs: InputRequirements,
        output: Concept,
        blueprint: PipeImgGenBlueprint,
    ) -> PipeImgGen:
        # Parse output for multiplicity (may have brackets like "Image[]" or "Image[3]")
        output_parse_result = parse_concept_with_multiplicity(blueprint.output)

        # Convert bracket notation to output_multiplicity (default to 1 if no brackets)
        final_multiplicity = output_parse_result.multiplicity if isinstance(output_parse_result.multiplicity, int) else 1

        img_gen_prompt = blueprint.img_gen_prompt
        img_gen_prompt_var_name = blueprint.img_gen_prompt_var_name

        # If we have inputs, that means that the prompt is in the inputs.
        # The blueprint already validated that there is only 1 input.
        if blueprint.inputs:
            img_gen_prompt_var_name = blueprint.input_names[0]
        else:
            img_gen_prompt = blueprint.img_gen_prompt

        return PipeImgGen(
            domain=domain_code,
            code=pipe_code,
            description=description,
            inputs=inputs,
            output=output,
            output_multiplicity=final_multiplicity,
            img_gen_prompt=img_gen_prompt,
            img_gen_prompt_var_name=img_gen_prompt_var_name,
            img_gen_choice=blueprint.model,
            aspect_ratio=blueprint.aspect_ratio,
            is_raw=blueprint.is_raw,
            seed=blueprint.seed,
            background=blueprint.background,
            output_format=blueprint.output_format,
        )
