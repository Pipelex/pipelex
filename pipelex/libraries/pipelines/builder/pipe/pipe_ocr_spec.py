from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint


class PipeOcrSpec(PipeSpec):
    """Spec for OCR (Optical Character Recognition) pipe operations in the Pipelex framework.

    PipeOcr enables text extraction from images and documents using OCR technology.
    Supports various OCR platforms and output configurations including image detection,
    caption generation, and page rendering.

    VERY IMPORTANT: THE INPUT OF THE PIPEOCR MUST BE NAMED "ocr_input" and it must be either an image or a pdf or a concept which refines one of them.

    Attributes:
        the_pipe_code: Pipe code. Must be snake_case.
        type: Fixed to "PipeOcr" for this pipe type.
        ocr: Needs to be "base_ocr_mistral".
        page_images: Whether to include detected images in the OCR output. When enabled,
                    extracts and returns embedded images found in documents.
        page_image_captions: Whether to generate captions for detected images using AI.
                            Useful for understanding image content in documents.
        page_views: Whether to include rendered page views in the output. Provides
                   visual representation of document pages.
        page_views_dpi: DPI (dots per inch) resolution for rendered page views.
                       Higher values provide better quality but larger file sizes.
                       Defaults to configuration setting.

    Validation Rules:
        1. OCR model must be "base_ocr_mistral".
        2. Boolean flags (page_images, page_image_captions, page_views) are optional.
        3. page_views_dpi should be a positive integer when specified.

    """

    type: Literal["PipeOcr"] = "PipeOcr"
    category: Literal["PipeOperator"] = "PipeOperator"
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
    ocr: str = "base_ocr_mistral"
    page_images: bool | None = None
    page_image_captions: bool | None = None
    page_views: bool | None = None
    page_views_dpi: int | None = None

    @override
    def to_blueprint(self) -> PipeOcrBlueprint:
        base_blueprint = super().to_blueprint()

        return PipeOcrBlueprint(
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            ocr=self.ocr,
        )
