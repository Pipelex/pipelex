from typing_extensions import override

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.exceptions import StaticValidationError, StaticValidationErrorType
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import get_concept_library, get_required_concept
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
        # Parse output for multiplicity (may have brackets like "Image[]" or "Image[3]")
        output_parse_result = parse_concept_with_multiplicity(blueprint.output)

        # Convert bracket notation to output_multiplicity (default to 1 if no brackets)
        final_multiplicity = output_parse_result.multiplicity if isinstance(output_parse_result.multiplicity, int) else 1

        # Use concept without brackets for output concept resolution
        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=output_parse_result.concept,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        inputs = InputRequirementsFactory.make_from_blueprint(
            domain=domain,
            blueprint=blueprint.inputs or {},
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        concept_library = get_concept_library()

        input_name = blueprint.input_names[0]
        input_requirement = inputs.get_required_input_requirement(input_name)

        img_gen_prompt_var_name = blueprint.img_gen_prompt_var_name

        if concept_library.is_compatible(
            tested_concept=input_requirement.concept,
            wanted_concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        ):
            img_gen_prompt_var_name = input_name
        else:
            inadequate_input_concept_error = StaticValidationError(
                error_type=StaticValidationErrorType.INADEQUATE_INPUT_CONCEPT,
                domain=domain,
                pipe_code=pipe_code,
                variable_names=[input_name],
                provided_concept_code=input_requirement.concept.code,
                explanation="For PipeImgGen you must provide a text input or a concept that refines text",
            )
            raise inadequate_input_concept_error

        return PipeImgGen(
            domain=domain,
            code=pipe_code,
            description=blueprint.description,
            inputs=inputs,
            output=get_required_concept(
                concept_string=ConceptFactory.make_concept_string_with_domain(
                    domain=output_domain_and_code.domain,
                    concept_code=output_domain_and_code.concept_code,
                ),
            ),
            output_multiplicity=final_multiplicity,
            img_gen_prompt=blueprint.img_gen_prompt,
            img_gen_prompt_var_name=img_gen_prompt_var_name,
            img_gen=blueprint.model,
            aspect_ratio=blueprint.aspect_ratio,
            is_raw=blueprint.is_raw,
            seed=blueprint.seed,
            background=blueprint.background,
            output_format=blueprint.output_format,
        )
