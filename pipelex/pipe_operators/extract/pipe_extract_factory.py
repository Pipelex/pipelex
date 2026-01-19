from typing import Any

from typing_extensions import override

from pipelex.config import get_config
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.hub import get_concept_library, get_native_concept
from pipelex.pipe_operators.extract.exceptions import PipeExtractFactoryError
from pipelex.pipe_operators.extract.pipe_extract import PipeExtract
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint


class PipeExtractFactory(PipeFactoryProtocol[PipeExtractBlueprint, PipeExtract]):
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
        blueprint: PipeExtractBlueprint,
    ) -> PipeExtract:
        concept_library = get_concept_library()
        image_stuff_name = None
        document_stuff_name = None

        # Already validated above that we have exactly one input
        input_name = blueprint.input_names[0]
        input_requirement = inputs.get_required_stuff_spec(input_name)

        if concept_library.is_compatible(
            tested_concept=input_requirement.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.IMAGE),
            strict=True,
        ):
            image_stuff_name = input_name
        elif concept_library.is_compatible(
            tested_concept=input_requirement.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.DOCUMENT),
            strict=True,
        ):
            document_stuff_name = input_name
        else:
            msg = (
                f"The input concept {input_requirement.concept.concept_ref} is not compatible "
                f"with the required concept {get_native_concept(native_concept=NativeConceptCode.IMAGE).concept_ref} or "
                f"{get_native_concept(native_concept=NativeConceptCode.DOCUMENT).concept_ref}"
            )
            raise PipeExtractFactoryError(msg)

        page_views_dpi = blueprint.page_views_dpi or get_config().cogt.extract_config.default_page_views_dpi

        return PipeExtract(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            output=output,
            inputs=inputs,
            extract_choice=blueprint.model,
            image_stuff_name=image_stuff_name,
            document_stuff_name=document_stuff_name,
            max_page_images=blueprint.max_page_images,
            should_caption_images=blueprint.page_image_captions or False,
            should_include_page_views=blueprint.page_views or False,
            page_views_dpi=page_views_dpi,
        )
