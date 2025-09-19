from typing import Literal, Optional, Union

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import AspectRatio, Quality
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists


class PipeImgGenBlueprint(PipeBlueprint):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    category: Literal["PipeOperator"] = "PipeOperator"
    img_gen_prompt: Optional[str] = None
    imgg_handle: Optional[ImggHandle] = None
    aspect_ratio: Optional[AspectRatio] = Field(default=None, strict=False)
    quality: Optional[Quality] = Field(default=None, strict=False)
    nb_steps: Optional[int] = Field(default=None, gt=0)
    guidance_scale: Optional[float] = Field(default=None, gt=0)
    is_moderated: Optional[bool] = None
    safety_tolerance: Optional[int] = Field(default=None, ge=1, le=6)
    is_raw: Optional[bool] = None
    seed: Optional[Union[int, Literal["auto"]]] = None
    nb_output: Optional[int] = Field(default=None, ge=1)
    img_gen_prompt_var_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_imgg_prompt_and_imgg_prompt_stuff_name(self) -> Self:
        if excess_attributes_list := has_more_than_one_among_attributes_from_lists(
            self,
            [
                ["quality", "nb_steps"],
            ],
        ):
            raise PipeDefinitionError(f"PipeImgGenBlueprint should have no more than one of {excess_attributes_list} among them")
        return self

    @field_validator("img_gen_prompt_var_name")
    @classmethod
    def validate_input_var_name_not_provided_as_attribute(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            raise PipeDefinitionError("img_gen_prompt_var_name must be None before input validation")
        return value
