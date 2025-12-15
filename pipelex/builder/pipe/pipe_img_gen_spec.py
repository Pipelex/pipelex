from typing import TYPE_CHECKING, Literal

from pydantic import Field, field_validator
from rich.console import Group
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from pipelex.cogt.img_gen.img_gen_setting import ImgGenModelChoice


class ImgGenSkill(StrEnum):
    GEN_IMAGE_BASIC = "gen_image_basic"
    GEN_IMAGE_FAST = "gen_image_fast"
    GEN_IMAGE_HIGH_QUALITY = "gen_image_high_quality"


class PipeImgGenSpec(PipeSpec):
    """Specs for image generation pipe operations in the Pipelex framework.

    PipeImgGen enables AI-powered image generation using various models like DALL-E or
    diffusion models. Supports static and dynamic prompts with configurable generation
    parameters.

    Output Multiplicity:
        Specify using bracket notation in output field:
        - output = "Image" - single image (default)
        - output = "Image[3]" - exactly 3 images
    """

    type: Literal["PipeImgGen"] = "PipeImgGen"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    img_gen_skill: ImgGenSkill | str = Field(description="Select the most adequate image generation skill according to the task to be performed.")
    prompt: str = Field(description="A finalized image generation prompt or prompt template: use `$` prefix for inline variables (e.g., `$topic`).")

    @field_validator("img_gen_skill", mode="before")
    @classmethod
    def validate_img_gen_skill(cls, img_gen_skill_value: str | None) -> ImgGenSkill | None:
        if img_gen_skill_value is None:
            return None
        else:
            return ImgGenSkill(img_gen_skill_value)

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with img_gen-specific details
        img_gen_group = Group()
        img_gen_group.renderables.append(base_group)

        # Add image generation specific information
        img_gen_group.renderables.append(Text())  # Blank line
        img_gen_group.renderables.append(Text.from_markup(f"Image Generation Skill: [bold yellow]{self.img_gen_skill}[/bold yellow]"))

        return img_gen_group

    @override
    def to_blueprint(self) -> PipeImgGenBlueprint:
        """Convert this PipeImgGenBlueprint to the core PipeImgGenBlueprint."""
        base_blueprint = super().to_blueprint()

        img_gen_choice: ImgGenModelChoice = self.img_gen_skill

        return PipeImgGenBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            prompt=self.prompt,
            model=img_gen_choice,
            aspect_ratio=None,
            background=None,
            output_format=None,
            is_raw=None,
            seed=None,
        )
