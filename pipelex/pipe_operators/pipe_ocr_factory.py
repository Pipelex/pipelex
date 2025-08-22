from typing import Literal, Optional

from typing_extensions import override

from pipelex.cogt.ocr.ocr_engine_factory import OcrEngineFactory
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.config import get_config
from pipelex.core.concepts.concept import Concept, NativeConceptEnum
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.pipe_input_spec_factory import PipeInputSpecFactory
from pipelex.hub import get_concept_provider
from pipelex.pipe_operators.pipe_ocr import PipeOcr


class PipeOcrBlueprint(PipeBlueprint):
    type: Literal["PipeOcr"] = "PipeOcr"
    ocr_platform: Optional[OcrPlatform] = None
    page_images: Optional[bool] = None
    page_image_captions: Optional[bool] = None
    page_views: Optional[bool] = None
    page_views_dpi: Optional[int] = None


class PipeOcrFactory(PipeFactoryProtocol[PipeOcrBlueprint, PipeOcr]):
    @classmethod
    @override
    def make_from_blueprint(
        cls,
        domain: str,
        pipe_code: str,
        pipe_blueprint: PipeOcrBlueprint,
    ) -> PipeOcr:
        ocr_platform = pipe_blueprint.ocr_platform or OcrPlatform.MISTRAL
        match ocr_platform:
            case OcrPlatform.MISTRAL:
                ocr_engine = OcrEngineFactory.make_ocr_engine(ocr_handle=OcrHandle.MISTRAL_OCR)

        output_concept_code = pipe_blueprint.output
        if "." not in output_concept_code:
            if Concept.is_native_concept_code(concept_code=output_concept_code):
                output = get_concept_provider().get_native_concept(native_concept=NativeConceptEnum(output_concept_code))
            else:
                output = get_concept_provider().get_required_concept(
                    concept_string=Concept.construct_concept_string_with_domain(domain=domain, concept_code=output_concept_code)
                )
        else:
            output = get_concept_provider().get_required_concept(concept_string=output_concept_code)

        return PipeOcr(
            domain=domain,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            ocr_engine=ocr_engine,
            output=output,
            inputs=PipeInputSpecFactory.make_from_blueprint(domain=domain, blueprint=pipe_blueprint.inputs or {}),
            should_include_images=pipe_blueprint.page_images or False,
            should_caption_images=pipe_blueprint.page_image_captions or False,
            should_include_page_views=pipe_blueprint.page_views or False,
            page_views_dpi=pipe_blueprint.page_views_dpi or get_config().cogt.ocr_config.default_page_views_dpi,
        )
