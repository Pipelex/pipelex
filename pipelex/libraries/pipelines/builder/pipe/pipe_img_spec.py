from typing import Literal

from pydantic import Field, field_validator
from typing_extensions import override

from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.types import StrEnum


class RecommendedImgGen(StrEnum):
    BASE_IMG_GEN = "base_img_gen"
    FAST_IMG_GEN = "fast_img_gen"
    HIGH_QUALITY_IMG_GEN = "high_quality_img_gen"


class PipeImgGenSpec(PipeSpec):
    """Specs for image generation pipe operations in the Pipelex framework.

    PipeImgGen enables AI-powered image generation using various models like DALL-E or
    diffusion models. Supports static and dynamic prompts with configurable generation
    parameters.
    """

    type: Literal["PipeImgGen"] = "PipeImgGen"
    category: Literal["PipeOperator"] = "PipeOperator"
    img_gen: RecommendedImgGen | None = None
    nb_output: int | None = Field(default=None, ge=1)

    @field_validator("img_gen", mode="before")
    @classmethod
    def validate_img_gen(cls, img_gen_value: str | None) -> RecommendedImgGen | None:
        if img_gen_value is None:
            return None
        else:
            return RecommendedImgGen(img_gen_value)

    @override
    def to_blueprint(self) -> PipeImgGenBlueprint:
        """Convert this PipeImgGenBlueprint to the core PipeImgGenBlueprint."""
        base_blueprint = super().to_blueprint()
        return PipeImgGenBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            img_gen_prompt=None,
            img_gen_prompt_var_name=None,
            img_gen=self.img_gen,
            aspect_ratio=None,
            background=None,
            output_format=None,
            is_raw=None,
            seed=None,
            nb_output=self.nb_output,
        )
