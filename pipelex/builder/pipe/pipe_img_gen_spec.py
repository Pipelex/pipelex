from typing import Literal

from pydantic import Field, field_validator
from rich.console import Group
from rich.markup import escape
from rich.text import Text
from typing_extensions import override

from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.tools.misc.pretty import PrettyPrintable


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
    model: str | None = Field(
        default=None,
        description="Model preset, alias, waterfall, or direct model handle. Use presets from 'pipelex-agent models'.",
    )
    prompt: str = Field(description="A finalized image generation prompt or prompt template: use `$` prefix for inline variables (e.g., `$topic`).")

    @field_validator("model", mode="before")
    @classmethod
    def reject_empty_model(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            msg = "Model cannot be an empty string; omit the field to use defaults"
            raise ValueError(msg)
        return value

    @override
    def rendered_pretty(self, title: str | None = None, depth: int = 0) -> PrettyPrintable:
        # Get base pipe information from parent
        base_group = super().rendered_pretty(title=title, depth=depth)

        # Create a group combining base info with img_gen-specific details
        img_gen_group = Group()
        img_gen_group.renderables.append(base_group)

        # Add image generation specific information
        img_gen_group.renderables.append(Text())  # Blank line
        img_gen_group.renderables.append(Text.from_markup(f"Model: [bold yellow]{escape(self.model or '(default)')}[/bold yellow]"))

        return img_gen_group

    @override
    def to_blueprint(self) -> PipeImgGenBlueprint:
        """Convert this PipeImgGenSpec to the core PipeImgGenBlueprint."""
        base_blueprint = super().to_blueprint()

        return PipeImgGenBlueprint(
            description=base_blueprint.description,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            prompt=self.prompt,
            model=self.model,
            aspect_ratio=None,
            background=None,
            output_format=None,
            is_raw=None,
            seed=None,
        )
