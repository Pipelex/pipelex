from typing import ClassVar

from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint


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

    # Note: PipeFunc has minimal validation since it's very flexible
    # The main validation is that function_name is required (enforced by Pydantic)
    # We don't have error cases for inputs since any input configuration is valid
    ERROR_CASES: ClassVar[list[tuple[str, PipeFuncBlueprint, str]]] = []
