from typing import ClassVar

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.system.registries.func_registry import pipe_func


# Register test functions for validation tests
@pipe_func(name="my_function")
def my_function(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-function-argument]  # pyright: ignore[reportUnusedParameter]
    """Test function with no inputs."""
    return TextContent(text="test output")


@pipe_func(name="process_text")
def process_text(working_memory: WorkingMemory) -> TextContent:
    """Test function with single text input."""
    input_data = working_memory.get_stuff_as_str("input_data")
    return TextContent(text=f"processed: {input_data}")


@pipe_func(name="combine_data")
def combine_data(working_memory: WorkingMemory) -> TextContent:
    """Test function with multiple inputs."""
    text_input = working_memory.get_stuff_as_str("text_input")
    number_input = working_memory.get_stuff_as_number("number_input")
    return TextContent(text=f"combined: {text_input} and {number_input}")


@pipe_func(name="process_image")
def process_image(working_memory: WorkingMemory) -> TextContent:
    """Test function with image input."""
    image = working_memory.get_stuff_as_image("image")
    return TextContent(text=f"processed image: {image.url}")


@pipe_func(name="process_all")
def process_all(working_memory: WorkingMemory) -> TextContent:
    """Test function with mixed inputs."""
    text = working_memory.get_stuff_as_str("text")
    image = working_memory.get_stuff_as_image("image")
    number = working_memory.get_stuff_as_number("number")
    return TextContent(text=f"processed all: {text}, {image.url}, {number}")


class PipeFuncInputTestCases:
    """Test cases for PipeFunc input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_NO_INPUTS: ClassVar[tuple[str, PipeFuncBlueprint]] = (
        "valid_no_inputs",
        PipeFuncBlueprint(
            description="Test case: valid_no_inputs",
            inputs={},
            output="native.Text",
            function_name="my_function",
        ),
    )

    VALID_SINGLE_INPUT: ClassVar[tuple[str, PipeFuncBlueprint]] = (
        "valid_single_input",
        PipeFuncBlueprint(
            description="Test case: valid_single_input",
            inputs={"input_data": "native.Text"},
            output="native.Text",
            function_name="process_text",
        ),
    )

    VALID_MULTIPLE_INPUTS: ClassVar[tuple[str, PipeFuncBlueprint]] = (
        "valid_multiple_inputs",
        PipeFuncBlueprint(
            description="Test case: valid_multiple_inputs",
            inputs={"text_input": "native.Text", "number_input": "native.Number"},
            output="native.Text",
            function_name="combine_data",
        ),
    )

    VALID_IMAGE_INPUT: ClassVar[tuple[str, PipeFuncBlueprint]] = (
        "valid_image_input",
        PipeFuncBlueprint(
            description="Test case: valid_image_input",
            inputs={"image": "native.Image"},
            output="native.Text",
            function_name="process_image",
        ),
    )

    VALID_MIXED_INPUTS: ClassVar[tuple[str, PipeFuncBlueprint]] = (
        "valid_mixed_inputs",
        PipeFuncBlueprint(
            description="Test case: valid_mixed_inputs",
            inputs={"text": "native.Text", "image": "native.Image", "number": "native.Number"},
            output="native.Text",
            function_name="process_all",
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeFuncBlueprint]]] = [
        VALID_NO_INPUTS,
        VALID_SINGLE_INPUT,
        VALID_MULTIPLE_INPUTS,
        VALID_IMAGE_INPUT,
        VALID_MIXED_INPUTS,
    ]
