from typing import Literal, Optional, Union

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.cogt.imgg.imgg_handle import ImggHandle
from pipelex.cogt.imgg.imgg_job_components import AspectRatio, Quality
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.exceptions import PipeDefinitionError
from pipelex.tools.typing.validation_utils import has_more_than_one_among_attributes_from_lists


class PipeImgGenBlueprint(PipeBlueprint):
    """Blueprint for image generation pipe operations in the Pipelex framework.

    PipeImgGen enables AI-powered image generation using various models like DALL-E or
    diffusion models. Supports static and dynamic prompts with configurable generation
    parameters.

    Attributes:
        type: Fixed to "PipeImgGen" for this pipe type.
        img_gen_prompt: Static text prompt for image generation. Use this or dynamic input.
        imgg_handle: Image generation model handle (e.g., 'dall-e-3'). Defaults to global config.
        aspect_ratio: Desired image aspect ratio (e.g., '16:9', '1:1').
        quality: Generated image quality setting (e.g., 'standard', 'hd').
        nb_steps: Number of diffusion steps for diffusion models. More steps increase detail
                 but take longer. Must be > 0.
        guidance_scale: Prompt adherence strength. Higher values mean closer adherence to prompt.
                       Must be > 0.
        is_moderated: Whether to apply content moderation to generated images.
        safety_tolerance: Content moderation tolerance level. Must be between 1 and 6.
        is_raw: Whether to return raw image data instead of processed format.
        seed: Random seed for reproducibility. Use integer value or 'auto' for random seed.
        nb_output: Number of images to generate. Defaults to single image. Must be >= 1.
        img_gen_prompt_var_name: Variable name for dynamic prompt generation from inputs. Will default to "prompt"

    Validation Rules:
        1. Quality and nb_steps are mutually exclusive (cannot specify both).
        2. nb_steps must be greater than 0 when specified.
        3. guidance_scale must be greater than 0 when specified.
        4. safety_tolerance must be between 1 and 6 inclusive.
        5. nb_output must be at least 1 when specified.

    Raises:
        PipeDefinitionError: When validation rules are violated or mutually exclusive
                            fields are set simultaneously.
    """

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
