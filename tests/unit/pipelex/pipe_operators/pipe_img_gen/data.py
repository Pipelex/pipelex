from typing import ClassVar

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, OutputFormat
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class PipeImgGenInputTestCases:
    """Test cases for PipeImgGen input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_TEXT_INPUT: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_text_input",
        PipeImgGenBlueprint(
            description="Test case: valid_text_input",
            inputs={"prompt": "native.Text"},
            output="native.Image",
        ),
    )

    VALID_WITH_INLINE_PROMPT: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_inline_prompt",
        PipeImgGenBlueprint(
            description="Test case: valid_with_inline_prompt",
            inputs={},
            output="native.Image",
            img_gen_prompt="A beautiful sunset over the ocean",
        ),
    )

    VALID_WITH_ASPECT_RATIO: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_aspect_ratio",
        PipeImgGenBlueprint(
            description="Test case: valid_with_aspect_ratio",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            aspect_ratio=AspectRatio.LANDSCAPE_16_9,
        ),
    )

    VALID_WITH_NB_OUTPUT: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_nb_output",
        PipeImgGenBlueprint(
            description="Test case: valid_with_nb_output",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            nb_output=3,
        ),
    )

    VALID_WITH_SEED: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_seed",
        PipeImgGenBlueprint(
            description="Test case: valid_with_seed",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            seed=42,
        ),
    )

    VALID_WITH_SEED_AUTO: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_seed_auto",
        PipeImgGenBlueprint(
            description="Test case: valid_with_seed_auto",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            seed="auto",
        ),
    )

    VALID_WITH_BACKGROUND: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_background",
        PipeImgGenBlueprint(
            description="Test case: valid_with_background",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            background=Background.TRANSPARENT,
        ),
    )

    VALID_WITH_OUTPUT_FORMAT: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_output_format",
        PipeImgGenBlueprint(
            description="Test case: valid_with_output_format",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            output_format=OutputFormat.PNG,
        ),
    )

    VALID_WITH_IS_RAW: ClassVar[tuple[str, PipeImgGenBlueprint]] = (
        "valid_with_is_raw",
        PipeImgGenBlueprint(
            description="Test case: valid_with_is_raw",
            inputs={"prompt": "native.Text"},
            output="native.Image",
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

    # Error test cases: (test_id, blueprint, expected_error_message_fragment)
    ERROR_NO_INPUT_NO_PROMPT: ClassVar[tuple[str, PipeImgGenBlueprint, str]] = (
        "no_input_no_prompt",
        PipeImgGenBlueprint(
            description="Test case: no_input_no_prompt",
            inputs={},
            output="native.Image",
        ),
        "missing_input_variable",
    )

    ERROR_MULTIPLE_INPUTS: ClassVar[tuple[str, PipeImgGenBlueprint, str]] = (
        "multiple_inputs",
        PipeImgGenBlueprint(
            description="Test case: multiple_inputs",
            inputs={"prompt1": "native.Text", "prompt2": "native.Text"},
            output="native.Image",
        ),
        "too_many_candidate_inputs",
    )

    ERROR_WRONG_INPUT_TYPE: ClassVar[tuple[str, PipeImgGenBlueprint, str]] = (
        "wrong_input_type",
        PipeImgGenBlueprint(
            description="Test case: wrong_input_type",
            inputs={"image": "native.Image"},
            output="native.Image",
        ),
        "inadequate_input_concept",
    )

    ERROR_BOTH_PROMPT_AND_INPUT: ClassVar[tuple[str, PipeImgGenBlueprint, str]] = (
        "both_prompt_and_input",
        PipeImgGenBlueprint(
            description="Test case: both_prompt_and_input",
            inputs={"prompt": "native.Text"},
            output="native.Image",
            img_gen_prompt="A beautiful sunset",
        ),
        "There must be no inputs if img_gen_prompt is provided",
    )

    ERROR_CASES: ClassVar[list[tuple[str, PipeImgGenBlueprint, str]]] = [
        ERROR_NO_INPUT_NO_PROMPT,
        ERROR_MULTIPLE_INPUTS,
        ERROR_WRONG_INPUT_TYPE,
        ERROR_BOTH_PROMPT_AND_INPUT,
    ]
