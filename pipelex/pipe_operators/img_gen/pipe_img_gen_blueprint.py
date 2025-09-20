from typing import Literal, Optional, Union

from pydantic import Field, model_validator
from typing_extensions import Self

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, OutputFormat, Quality
from pipelex.cogt.img_gen.img_gen_setting import ImgGenChoice
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists


class PipeImgGenBlueprint(PipeBlueprint):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    img_gen_prompt: Optional[str] = None
    img_gen_prompt_var_name: Optional[str] = None

    # New ImgGenChoice pattern (like LLM)
    img_gen: Optional[ImgGenChoice] = None

    # Legacy individual settings (for backwards compatibility)
    imgg_handle: Optional[str] = None
    quality: Optional[Quality] = Field(default=None, strict=False)
    nb_steps: Optional[int] = Field(default=None, gt=0)
    guidance_scale: Optional[float] = Field(default=None, gt=0)
    is_moderated: Optional[bool] = None
    safety_tolerance: Optional[int] = Field(default=None, ge=1, le=6)

    # One-time settings (not in ImgGenSetting)
    aspect_ratio: Optional[AspectRatio] = Field(default=None, strict=False)
    is_raw: Optional[bool] = None
    seed: Optional[Union[int, Literal["auto"]]] = None
    nb_output: Optional[int] = Field(default=None, ge=1)
    background: Optional[Background] = Field(default=None, strict=False)
    output_format: Optional[OutputFormat] = Field(default=None, strict=False)

    @model_validator(mode="after")
    def validate_imgg_prompt_and_imgg_prompt_stuff_name(self) -> Self:
        # Check that img_gen and legacy settings are not mixed
        if self.img_gen is not None:
            legacy_settings = ["imgg_handle", "quality", "nb_steps", "guidance_scale", "is_moderated", "safety_tolerance"]
            for setting in legacy_settings:
                if getattr(self, setting) is not None:
                    raise PipeDefinitionError(
                        f"Cannot use both 'img_gen' and legacy setting '{setting}'. "
                        f"Use either the new img_gen pattern or the legacy individual settings."
                    )
        else:
            # Validate legacy settings
            if excess_attributes_list := has_more_than_one_among_attributes_from_lists(
                self,
                [
                    ["quality", "nb_steps"],
                ],
            ):
                raise PipeDefinitionError(f"PipeImgGenBlueprint should have no more than one of {excess_attributes_list} among them")
        return self
