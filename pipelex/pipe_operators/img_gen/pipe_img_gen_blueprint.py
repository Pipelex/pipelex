from typing import Literal, Optional, Union

from pydantic import Field

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, OutputFormat
from pipelex.cogt.img_gen.img_gen_setting import ImgGenChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint


class PipeImgGenBlueprint(PipeBlueprint):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    category: Literal["PipeOperator"] = "PipeOperator"
    img_gen_prompt: Optional[str] = None
    img_gen_prompt_var_name: Optional[str] = None

    # New ImgGenChoice pattern (like LLM)
    img_gen: Optional[ImgGenChoice] = None

    # One-time settings (not in ImgGenSetting)
    aspect_ratio: Optional[AspectRatio] = Field(default=None, strict=False)
    is_raw: Optional[bool] = None
    seed: Optional[Union[int, Literal["auto"]]] = None
    nb_output: Optional[int] = Field(default=None, ge=1)
    background: Optional[Background] = Field(default=None, strict=False)
    output_format: Optional[OutputFormat] = Field(default=None, strict=False)
