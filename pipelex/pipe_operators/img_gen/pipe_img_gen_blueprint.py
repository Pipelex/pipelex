from typing import Literal

from pydantic import Field

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, OutputFormat
from pipelex.cogt.img_gen.img_gen_setting import ImgGenChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeImgGenBlueprint(PipeBlueprint):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    category: Literal["PipeOperator"] = "PipeOperator"
    img_gen_prompt: str | None = None
    img_gen_prompt_var_name: str | None = None

    # New ImgGenChoice pattern (like LLM)
    img_gen: ImgGenChoice | None = None

    # One-time settings (not in ImgGenSetting)
    aspect_ratio: AspectRatio | None = Field(default=None, strict=False)
    is_raw: bool | None = None
    seed: int | Literal["auto"] | None = None
    nb_output: int | None = Field(default=None, ge=1)
    background: Background | None = Field(default=None, strict=False)
    output_format: OutputFormat | None = Field(default=None, strict=False)
