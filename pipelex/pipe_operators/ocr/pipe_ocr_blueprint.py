from typing import Literal, Optional

from pydantic import Field

from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeOcrBlueprint(PipeBlueprint):
    """PipeOcr is used to extract text from images with OCR technology."""

    type: Literal["PipeOcr"] = "PipeOcr"
    ocr_platform: Optional[OcrPlatform] = Field(default=None, description="OCR platform to use for text extraction. Defaults to Mistral")
    page_images: Optional[bool] = Field(default=None, description="Include detected images in the OCR output")
    page_image_captions: Optional[bool] = Field(default=None, description="Generate captions for detected images")
    page_views: Optional[bool] = Field(default=None, description="Include rendered page views in the output")
    page_views_dpi: Optional[int] = Field(default=None, description="DPI resolution for page views. Defaults to configuration setting")
