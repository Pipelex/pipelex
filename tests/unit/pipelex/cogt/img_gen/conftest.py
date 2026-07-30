"""Shared builders for img_gen unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import (
    AspectRatio,
    Background,
    ImgGenJobConfig,
    ImgGenJobParams,
    ImgGenJobReport,
    InputFidelity,
    Quality,
)
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.misc.image_utils import ImageFormat

if TYPE_CHECKING:
    from pipelex.cogt.image.image_size import ImageSize
    from pipelex.cogt.image.prompt_image import PromptImage


def make_img_gen_job(
    *,
    positive_text: str = "A test prompt",
    negative_text: str | None = None,
    input_images: list[PromptImage] | None = None,
    aspect_ratio: AspectRatio = AspectRatio.SQUARE,
    size: ImageSize | None = None,
    background: Background = Background.OPAQUE,
    quality: Quality | None = None,
    input_fidelity: InputFidelity | None = None,
    nb_steps: int | None = None,
    guidance_scale: float | None = None,
    is_moderated: bool | None = None,
    safety_tolerance: int | None = None,
    is_raw: bool | None = None,
    output_format: ImageFormat | None = ImageFormat.PNG,
) -> ImgGenJob:
    """Create a test ImgGenJob with configurable prompt and job parameters."""
    return ImgGenJob(
        img_gen_prompt=ImgGenPrompt(
            positive_text=positive_text,
            negative_text=negative_text,
            input_images=input_images,
        ),
        job_params=ImgGenJobParams(
            aspect_ratio=aspect_ratio,
            size=size,
            background=background,
            quality=quality,
            input_fidelity=input_fidelity,
            nb_steps=nb_steps,
            guidance_scale=guidance_scale,
            is_moderated=is_moderated,
            safety_tolerance=safety_tolerance,
            is_raw=is_raw,
            output_format=output_format,
        ),
        job_config=ImgGenJobConfig(is_sync_mode=False),
        job_report=ImgGenJobReport(),
        job_metadata=JobMetadata(user_id="test-user", pipeline_run_id="test-run"),
    )
