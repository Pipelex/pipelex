from typing import ClassVar

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.tools.misc.image_utils import ImageFormat


class PipeImgGenInputTestCases:
    """Test cases for PipeImgGen input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_TEXT_INPUT: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_text_input",
        PipeImgGenBlueprint(
            description="VALID_TEXT_INPUT: Test case: valid_text_input",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            prompt="@prompt",
        ),
    )

    VALID_WITH_INLINE_PROMPT: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_inline_prompt",
        PipeImgGenBlueprint(
            description="VALID_WITH_INLINE_PROMPT: Test case: valid_with_inline_prompt",
            inputs={},
            output="native.Image",
            prompt="A beautiful sunset over the ocean",
        ),
    )

    VALID_WITH_ASPECT_RATIO: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_aspect_ratio",
        PipeImgGenBlueprint(
            description="VALID_WITH_ASPECT_RATIO: Test case: valid_with_aspect_ratio",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            prompt="@prompt",
            aspect_ratio=AspectRatio.LANDSCAPE_16_9,
        ),
    )

    VALID_WITH_NB_OUTPUT: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_nb_output",
        PipeImgGenBlueprint(
            description="VALID_WITH_NB_OUTPUT: Test case: valid_with_nb_output",
            inputs={"prompt": "native.Text"},
            output="native.Image[3]",
            prompt="@prompt",
        ),
    )

    VALID_WITH_SEED: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_seed",
        PipeImgGenBlueprint(
            description="VALID_WITH_SEED: Test case: valid_with_seed",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            prompt="@prompt",
            seed=42,
        ),
    )

    VALID_WITH_SEED_AUTO: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_seed_auto",
        PipeImgGenBlueprint(
            description="VALID_WITH_SEED_AUTO: Test case: valid_with_seed_auto",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            prompt="@prompt",
            seed="auto",
        ),
    )

    VALID_WITH_BACKGROUND: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_background",
        PipeImgGenBlueprint(
            description="VALID_WITH_BACKGROUND: Test case: valid_with_background",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            prompt="@prompt",
            background=Background.TRANSPARENT,
        ),
    )

    VALID_WITH_OUTPUT_FORMAT: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_output_format",
        PipeImgGenBlueprint(
            description="VALID_WITH_OUTPUT_FORMAT: Test case: valid_with_output_format",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            prompt="@prompt",
            output_format=ImageFormat.PNG,
        ),
    )

    VALID_WITH_IS_RAW: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_is_raw",
        PipeImgGenBlueprint(
            description="VALID_WITH_IS_RAW: Test case: valid_with_is_raw",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            prompt="@prompt",
            is_raw=True,
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeImgGenBlueprint]]] = [
        VALID_TEXT_INPUT,
        VALID_WITH_INLINE_PROMPT,
        VALID_WITH_ASPECT_RATIO,
        VALID_WITH_NB_OUTPUT,
        VALID_WITH_SEED,
        VALID_WITH_SEED_AUTO,
        VALID_WITH_BACKGROUND,
        VALID_WITH_OUTPUT_FORMAT,
        VALID_WITH_IS_RAW,
    ]
