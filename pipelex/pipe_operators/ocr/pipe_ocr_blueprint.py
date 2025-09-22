from typing import Literal, Optional

from pipelex.cogt.ocr.ocr_setting import OcrChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeOcrBlueprint(PipeBlueprint):
    type: Literal["PipeOcr"] = "PipeOcr"
    category: Literal["PipeOperator"] = "PipeOperator"
    ocr: Optional[OcrChoice] = None
    page_images: Optional[bool] = None
    page_image_captions: Optional[bool] = None
    page_views: Optional[bool] = None
    page_views_dpi: Optional[int] = None
