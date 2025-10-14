from typing import Literal

from pipelex.cogt.extract.extract_setting import ExtractModelChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeExtractBlueprint(PipeBlueprint):
    type: Literal["PipeExtract"] = "PipeExtract"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    model: ExtractModelChoice | None = None
    page_images: bool | None = None
    page_image_captions: bool | None = None
    page_views: bool | None = None
    page_views_dpi: int | None = None
