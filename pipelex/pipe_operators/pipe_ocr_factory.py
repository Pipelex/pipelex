from typing import List, Literal, Optional

from typing_extensions import override

from pipelex.cogt.ocr.ocr_engine_factory import OcrEngineFactory
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
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
        blueprint: PipeOcrBlueprint,
        concept_codes_from_the_same_domain: Optional[List[str]] = None,
    ) -> PipeOcr:
        ocr_platform = blueprint.ocr_platform or OcrPlatform.MISTRAL
        match ocr_platform:
            case OcrPlatform.MISTRAL:
                ocr_engine = OcrEngineFactory.make_ocr_engine(ocr_handle=OcrHandle.MISTRAL_OCR)

        output_concept_domain, output_concept_code = ConceptFactory.make_domain_and_concept_code_from_concept_string_or_concept_code(
            domain=domain,
            concept_string_or_concept_code=blueprint.output,
            concept_codes_from_the_same_domain=concept_codes_from_the_same_domain,
        )
        return PipeOcr(
            domain=domain,
            code=pipe_code,
            definition=blueprint.definition,
            ocr_engine=ocr_engine,
            output=get_concept_provider().get_required_concept(
                concept_string=ConceptFactory.construct_concept_string_with_domain(domain=output_concept_domain, concept_code=output_concept_code)
            ),
            inputs=PipeInputSpecFactory.make_from_blueprint(
                domain=domain, blueprint=blueprint.inputs or {}, concept_codes_from_the_same_domain=concept_codes_from_the_same_domain
            ),
            should_include_images=blueprint.page_images or False,
            should_caption_images=blueprint.page_image_captions or False,
            should_include_page_views=blueprint.page_views or False,
            page_views_dpi=blueprint.page_views_dpi or get_config().cogt.ocr_config.default_page_views_dpi,
        )
