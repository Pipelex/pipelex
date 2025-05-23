# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, Optional

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex.cogt.ocr.ocr_engine_factory import OcrEngineFactory, OcrPlatform
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.core.pipe_blueprint import PipeBlueprint, PipeSpecificFactoryProtocol
from pipelex.exceptions import PipeDefinitionError
from pipelex.pipe_operators.pipe_ocr import PipeOcr
from pipelex.tools.utils.validation_utils import has_exactly_one_among_attributes_from_list


class PipeOcrBlueprint(PipeBlueprint):
    definition: Optional[str] = None
    image: Optional[str] = None
    pdf: Optional[str] = None
    ocr_platform: Optional[OcrPlatform] = None
    page_images: bool = False
    page_image_captions: bool = False
    page_views: bool = False
    page_views_dpi: int = 300

    @model_validator(mode="after")
    def validate_input_source(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["image", "pdf"]):
            raise PipeDefinitionError("Either 'image' or 'pdf' must be provided")
        return self


class PipeOcrFactory(PipeSpecificFactoryProtocol[PipeOcrBlueprint, PipeOcr]):
    @classmethod
    @override
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeOcrBlueprint,
    ) -> PipeOcr:
        ocr_platform = pipe_blueprint.ocr_platform or OcrPlatform.MISTRAL
        match ocr_platform:
            case OcrPlatform.MISTRAL:
                ocr_engine = OcrEngineFactory.make_ocr_engine(ocr_handle=OcrHandle.MISTRAL_OCR)

        return PipeOcr(
            domain=domain_code,
            code=pipe_code,
            definition=pipe_blueprint.definition,
            ocr_engine=ocr_engine,
            output_concept_code=pipe_blueprint.output,
            image_stuff_name=pipe_blueprint.image,
            pdf_stuff_name=pipe_blueprint.pdf,
            should_include_images=pipe_blueprint.page_images,
            should_caption_images=pipe_blueprint.page_image_captions,
            should_include_page_views=pipe_blueprint.page_views,
            page_views_dpi=pipe_blueprint.page_views_dpi,
        )

    @classmethod
    @override
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeOcr:
        pipe_blueprint = PipeOcrBlueprint.model_validate(details_dict)
        return cls.make_pipe_from_blueprint(
            domain_code=domain_code,
            pipe_code=pipe_code,
            pipe_blueprint=pipe_blueprint,
        )
