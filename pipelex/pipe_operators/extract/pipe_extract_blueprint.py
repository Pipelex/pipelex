from typing import Literal

from pipelex.cogt.extract.extract_setting import ExtractChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeExtractBlueprint(PipeBlueprint):
    type: Literal["PipeExtract"] = "PipeExtract"
    category: Literal["PipeOperator"] = "PipeOperator"
    ocr: ExtractChoice | None = None
    page_images: bool | None = None
    page_image_captions: bool | None = None
    page_views: bool | None = None
    page_views_dpi: int | None = None
