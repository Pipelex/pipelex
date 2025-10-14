from typing import Literal

from pydantic import Field, field_validator
from typing_extensions import override

from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.types import StrEnum


class AvailableImgGen(StrEnum):
    BASE_IMG_GEN = "base_img_gen"
    FAST_IMG_GEN = "fast_img_gen"
    HIGH_QUALITY_IMG_GEN = "high_quality_img_gen"


class ImgGenSkill(StrEnum):
    GEN_IMAGE = "gen_image"
    GEN_IMAGE_FAST = "gen_image_fast"
    GEN_IMAGE_HIGH_QUALITY = "gen_image_high_quality"

    @property
    def model_recommendation(self) -> AvailableImgGen:
        match self:
            case ImgGenSkill.GEN_IMAGE:
                return AvailableImgGen.BASE_IMG_GEN
            case ImgGenSkill.GEN_IMAGE_FAST:
                return AvailableImgGen.FAST_IMG_GEN
            case ImgGenSkill.GEN_IMAGE_HIGH_QUALITY:
                return AvailableImgGen.HIGH_QUALITY_IMG_GEN


class PipeImgGenSpec(PipeSpec):
    """Specs for image generation pipe operations in the Pipelex framework.

    PipeImgGen enables AI-powered image generation using various models like DALL-E or
    diffusion models. Supports static and dynamic prompts with configurable generation
    parameters.
    """

    type: Literal["PipeImgGen"] = "PipeImgGen"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    img_gen_skill: ImgGenSkill | None = None
    nb_output: int | None = Field(default=None, ge=1)

    @field_validator("img_gen_skill", mode="before")
    @classmethod
    def validate_img_gen_skill(cls, img_gen_skill_value: str | None) -> ImgGenSkill | None:
        if img_gen_skill_value is None:
            return None
        else:
            return ImgGenSkill(img_gen_skill_value)

    @override
    def to_blueprint(self) -> PipeImgGenBlueprint:
        """Convert this PipeImgGenBlueprint to the core PipeImgGenBlueprint."""
        base_blueprint = super().to_blueprint()
        return PipeImgGenBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            pipe_category=self.pipe_category,
            img_gen_prompt=None,
            img_gen_prompt_var_name=None,
            model=self.img_gen_skill.model_recommendation if self.img_gen_skill else None,
            aspect_ratio=None,
            background=None,
            output_format=None,
            is_raw=None,
            seed=None,
            nb_output=self.nb_output,
        )
