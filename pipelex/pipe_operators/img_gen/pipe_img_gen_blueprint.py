from typing import Literal, Optional, Union

from pydantic import Field, model_validator
from typing_extensions import Self

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import AspectRatio, Quality
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists


class PipeImgGenBlueprint(PipeBlueprint):
    """PipeImgGen is used to generate images."""

    type: Literal["PipeImgGen"] = "PipeImgGen"
    img_gen_prompt: Optional[str] = Field(default=None, description="A static text prompt for image generation. Use this or input")
    imgg_handle: Optional[ImggHandle] = Field(
        default=None,
        description="The handle for the image generation model to use (e.g., 'dall-e-3'). Defaults to the model specified in the global config",
    )
    aspect_ratio: Optional[AspectRatio] = Field(default=None, strict=False, description="The desired aspect ratio of the image (e.g., '16:9', '1:1')")
    quality: Optional[Quality] = Field(default=None, strict=False, description="The quality of the generated image (e.g., 'standard', 'hd')")
    nb_steps: Optional[int] = Field(
        default=None,
        gt=0,
        description="For diffusion models, the number of steps to run. More steps can increase detail but take longer. Must be > 0",
    )
    guidance_scale: Optional[float] = Field(
        default=None, gt=0, description="How strictly the model should adhere to the prompt. Higher values mean closer adherence. Must be > 0"
    )
    is_moderated: Optional[bool] = Field(default=None, description="Whether content moderation should be applied")
    safety_tolerance: Optional[int] = Field(
        default=None, ge=1, le=6, description="Safety tolerance level for content moderation. Must be between 1 and 6"
    )
    is_raw: Optional[bool] = Field(default=None, description="Whether to return raw image data")
    seed: Optional[Union[int, Literal["auto"]]] = Field(
        default=None, description="A seed for the random number generator to ensure reproducibility. 'auto' uses a random seed"
    )
    nb_output: Optional[int] = Field(
        default=None, ge=1, description="The number of images to generate. If omitted, a single image is generated. Must be >= 1"
    )
    img_gen_prompt_var_name: Optional[str] = Field(default=None, description="Variable name for dynamic prompt generation")

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
