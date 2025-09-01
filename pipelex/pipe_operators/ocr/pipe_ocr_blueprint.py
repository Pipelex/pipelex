from typing import Literal, Optional

from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeOcrBlueprint(PipeBlueprint):
    """Blueprint for OCR (Optical Character Recognition) pipe operations in the Pipelex framework.

    PipeOcr enables text extraction from images and documents using OCR technology.
    Supports various OCR platforms and output configurations including image detection,
    caption generation, and page rendering.

    Attributes:
        type: Fixed to "PipeOcr" for this pipe type.
        ocr_platform: OCR platform to use for text extraction (e.g., Mistral, Tesseract).
                     Defaults to Mistral or global configuration setting.
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
        1. OCR platform must be a valid OcrPlatform enum value when specified.
        2. Boolean flags (page_images, page_image_captions, page_views) are optional.
        3. page_views_dpi should be a positive integer when specified.

    Raises:
        ValidationError: When invalid OCR platform or DPI values are provided.
    """

    type: Literal["PipeOcr"] = "PipeOcr"
    ocr_platform: Optional[OcrPlatform] = None
    page_images: Optional[bool] = None
    page_image_captions: Optional[bool] = None
    page_views: Optional[bool] = None
    page_views_dpi: Optional[int] = None
