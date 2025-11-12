from typing_extensions import override

from pipelex.config.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import get_concept_library, get_native_concept, get_required_concept
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
        # Parse output to strip multiplicity brackets
        output_parse_result = parse_concept_with_multiplicity(blueprint.output)

        output_domain_and_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_code(
            domain=domain,
            concept_string_or_code=output_parse_result.concept,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )

        image_stuff_name = None
        pdf_stuff_name = None
        concept_library = get_concept_library()
        if blueprint.inputs is None:
            raise PipeDefinitionError(
                message="For PipeExtract you must provide either a pdf or an image or a concept that refines one of them",
                domain_code=domain,
                pipe_code=pipe_code,
                description=blueprint.description,
            )
        inputs = InputRequirementsFactory.make_from_blueprint(
            domain=domain,
            blueprint=blueprint.inputs or {},
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        # Already validated above that we have exactly one input
        input_name = blueprint.input_names[0]
        input_requirement = inputs.get_required_input_requirement(input_name)

        if concept_library.is_compatible(
            tested_concept=input_requirement.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.IMAGE),
            strict=True,
        ):
            image_stuff_name = input_name
        elif concept_library.is_compatible(
            tested_concept=input_requirement.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.PDF),
            strict=True,
        ):
            pdf_stuff_name = input_name
        else:
            msg = (
                f"The input concept {input_requirement.concept.concept_string} is not compatible "
                f"with the required concept {get_native_concept(native_concept=NativeConceptCode.IMAGE).concept_string} or "
                f"{get_native_concept(native_concept=NativeConceptCode.PDF).concept_string}"
            )
            raise PipeDefinitionError(
                message=msg,
                domain_code=domain,
                pipe_code=pipe_code,
                description=blueprint.description,
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
            inputs=inputs,
            extract_choice=blueprint.model,
            image_stuff_name=image_stuff_name,
            pdf_stuff_name=pdf_stuff_name,
            should_include_images=blueprint.page_images or False,
            should_caption_images=blueprint.page_image_captions or False,
            should_include_page_views=blueprint.page_views or False,
            page_views_dpi=blueprint.page_views_dpi or get_config().cogt.extract_config.default_page_views_dpi,
        )
