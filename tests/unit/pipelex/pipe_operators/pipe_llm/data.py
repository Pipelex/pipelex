from typing import ClassVar

from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class PipeLLMInputTestCases:
    """Test cases for PipeLLM input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_TEXT_INPUT: ClassVar[tuple[str, PipeLLMBlueprint]] = (
        "valid_text_input",
        PipeLLMBlueprint(
            description="Test case: valid_text_input",
            inputs={"user_text": "native.Text"},
            output="native.Text",
            prompt="Process this text: $user_text",
        ),
    )

    VALID_IMAGE_INPUT: ClassVar[tuple[str, PipeLLMBlueprint]] = (
        "valid_image_input",
        PipeLLMBlueprint(
            description="Test case: valid_image_input",
            inputs={"user_image": "native.Image"},
            output="native.Text",
            prompt="Describe this image: $user_image",
        ),
    )

    VALID_TWO_INPUTS: ClassVar[tuple[str, PipeLLMBlueprint]] = (
        "valid_two_inputs",
        PipeLLMBlueprint(
            description="Test case: valid_two_inputs",
            inputs={"text_input": "native.Text", "another_text": "native.Text"},
            output="native.Text",
            prompt="Compare $text_input with $another_text",
        ),
    )

    VALID_TEXT_AND_IMAGE: ClassVar[tuple[str, PipeLLMBlueprint]] = (
        "valid_text_and_image",
        PipeLLMBlueprint(
            description="Test case: valid_text_and_image",
            inputs={"user_text": "native.Text", "user_image": "native.Image"},
            output="native.Text",
            prompt="Analyze this text: $user_text with the image: $user_image",
        ),
    )

    VALID_IMAGE_MENTIONED_IN_PROMPT: ClassVar[tuple[str, PipeLLMBlueprint]] = (
        "image_mentioned_in_prompt",
        PipeLLMBlueprint(
            description="Test case: image_mentioned_in_prompt",
            inputs={"user_image": "native.Image"},
            output="native.Text",
            prompt="Describe $user_image",
        ),
    )

    VALID_TEXT_AND_IMAGE_BOTH_IN_PROMPT: ClassVar[tuple[str, PipeLLMBlueprint]] = (
        "text_and_image_both_in_prompt",
        PipeLLMBlueprint(
            description="Test case: text_and_image_both_in_prompt",
            inputs={"user_text": "native.Text", "user_image": "native.Image"},
            output="native.Text",
            prompt="Analyze $user_text and describe $user_image",
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeLLMBlueprint]]] = [
        VALID_TEXT_INPUT,
        VALID_IMAGE_INPUT,
        VALID_TWO_INPUTS,
        VALID_TEXT_AND_IMAGE,
        VALID_IMAGE_MENTIONED_IN_PROMPT,
        VALID_TEXT_AND_IMAGE_BOTH_IN_PROMPT,
    ]
