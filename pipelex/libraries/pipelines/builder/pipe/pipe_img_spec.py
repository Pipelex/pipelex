from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, OutputFormat
from pipelex.cogt.img_gen.img_gen_setting import ImgGenChoice
from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class PipeImgGenSpec(PipeSpec):
    """Specs for image generation pipe operations in the Pipelex framework.

    PipeImgGen enables AI-powered image generation using various models like DALL-E or
    diffusion models. Supports static and dynamic prompts with configurable generation
    parameters.

    Attributes:
        the_pipe_code: Pipe code. Must be snake_case.
        type: Fixed to "PipeImgGen" for this pipe type.
        img_gen_prompt: Static text prompt for image generation. Use this or dynamic input.
        img_gen: Image generation choice (e.g., 'gpt-image-1'). Defaults to global config.
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
        img_gen_prompt_var_name: Variable name for dynamic prompt generation from inputs. Do not assign anything

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
    the_pipe_code: str = Field(description="Pipe code. Must be snake_case.")
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

    @override
    def to_blueprint(self) -> PipeImgGenBlueprint:
        """Convert this PipeImgGenBlueprint to the core PipeImgGenBlueprint."""
        base_blueprint = super().to_blueprint()
        return PipeImgGenBlueprint(
            definition=base_blueprint.definition,
            inputs=base_blueprint.inputs,
            output=base_blueprint.output,
            type=self.type,
            category=self.category,
            img_gen_prompt=self.img_gen_prompt,
            img_gen=self.img_gen,
            aspect_ratio=self.aspect_ratio,
            background=self.background,
            output_format=self.output_format,
            is_raw=self.is_raw,
            seed=self.seed,
            nb_output=self.nb_output,
            img_gen_prompt_var_name=None,  # Core expects None, builder uses "prompt" as default
        )
