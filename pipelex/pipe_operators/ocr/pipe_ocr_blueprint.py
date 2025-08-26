from typing import Literal, Optional

from pipelex.cogt.ocr.ocr_platform import OcrPlatform
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeOcrBlueprint(PipeBlueprint):
    type: Literal["PipeOcr"] = "PipeOcr"
    ocr_platform: Optional[OcrPlatform] = None
    page_images: Optional[bool] = None
    page_image_captions: Optional[bool] = None
    page_views: Optional[bool] = None
    page_views_dpi: Optional[int] = None
