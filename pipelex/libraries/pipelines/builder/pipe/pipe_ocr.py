from typing import Literal, Optional

from pydantic import Field
from typing_extensions import override

from pipelex.libraries.pipelines.builder.pipe.pipe import PipeBlueprint
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint as PipeOcrBlueprintCore


class PipeOcrBlueprint(PipeBlueprint):
    """Blueprint for OCR (Optical Character Recognition) pipe operations in the Pipelex framework.

    PipeOcr enables text extraction from images and documents using OCR technology.
    Supports various OCR platforms and output configurations including image detection,
    caption generation, and page rendering.

    VERY IMPORTANT: THE INPUT OF THE PIPEOCR MUST BE NAMED "ocr_input" and it must be either an image or a pdf or a concept which refines one of them.

    Attributes:
        type: Fixed to "PipeOcr" for this pipe type.
        ocr_model: Needs to be "mistral-ocr".
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
        1. OCR model must be "mistral-ocr".
        2. Boolean flags (page_images, page_image_captions, page_views) are optional.
        3. page_views_dpi should be a positive integer when specified.

    Raises:
        ValidationError: When invalid OCR platform or DPI values are provided.
    """

    type: Literal["PipeOcr"] = "PipeOcr"
    category: Literal["PipeOperator"] = "PipeOperator"
    ocr_model: str = "mistral-ocr"
    page_images: Optional[bool] = None
    page_image_captions: Optional[bool] = None
    page_views: Optional[bool] = None
    page_views_dpi: Optional[int] = None

    @override
    def to_core_blueprint(self, pipe_code: str, domain: str) -> PipeOcrBlueprintCore:
        """Convert this PipeOcrBlueprint to the core PipeOcrBlueprint."""
        base_blueprint = super().to_core_blueprint(pipe_code, domain)

        return PipeOcrBlueprintCore(
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            ocr_model=self.ocr_model,
        )


class PipeOcrSpecBlueprint(PipeOcrBlueprint):
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
