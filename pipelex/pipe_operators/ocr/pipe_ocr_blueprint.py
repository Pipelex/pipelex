from typing import Literal, Optional

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeOcrBlueprint(PipeBlueprint):
    type: Literal["PipeOcr"] = "PipeOcr"
    ocr_model: str
    page_images: Optional[bool] = None
    page_image_captions: Optional[bool] = None
    page_views: Optional[bool] = None
    page_views_dpi: Optional[int] = None
