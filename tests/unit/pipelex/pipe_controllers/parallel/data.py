from typing import Any, ClassVar

from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeParallelInputTestCases:
    """Test cases for PipeParallel input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_WITH_ADD_EACH_OUTPUT: ClassVar[tuple[str, PipeParallelBlueprint]] = (
        "valid_with_add_each_output",
        PipeParallelBlueprint(
            description="Test case: valid_with_add_each_output",
            inputs={"data": "native.Text"},
            output="native.Text",
            parallels=[
                SubPipeBlueprint(pipe="process_a", result="result_a"),
                SubPipeBlueprint(pipe="process_b", result="result_b"),
            ],
            add_each_output=True,
        ),
    )

    VALID_WITH_COMBINED_OUTPUT: ClassVar[tuple[str, PipeParallelBlueprint]] = (
        "valid_with_combined_output",
        PipeParallelBlueprint(
            description="Test case: valid_with_combined_output",
            inputs={"data": "native.Text"},
            output="native.Text",
            parallels=[
                SubPipeBlueprint(pipe="analyze_1", result="analysis_1"),
                SubPipeBlueprint(pipe="analyze_2", result="analysis_2"),
            ],
            combined_output="native.Text",
        ),
    )

    VALID_WITH_BOTH_OUTPUT_OPTIONS: ClassVar[tuple[str, PipeParallelBlueprint]] = (
        "valid_with_both_output_options",
        PipeParallelBlueprint(
            description="Test case: valid_with_both_output_options",
            inputs={"data": "native.Text"},
            output="native.Text",
            parallels=[
                SubPipeBlueprint(pipe="compute_x", result="x"),
                SubPipeBlueprint(pipe="compute_y", result="y"),
            ],
            add_each_output=True,
            combined_output="native.Text",
        ),
    )

    VALID_THREE_PARALLELS: ClassVar[tuple[str, PipeParallelBlueprint]] = (
        "valid_three_parallels",
        PipeParallelBlueprint(
            description="Test case: valid_three_parallels",
            inputs={"input_data": "native.Text"},
            output="native.Text",
            parallels=[
                SubPipeBlueprint(pipe="branch_1", result="result_1"),
                SubPipeBlueprint(pipe="branch_2", result="result_2"),
                SubPipeBlueprint(pipe="branch_3", result="result_3"),
            ],
            add_each_output=True,
        ),
    )

    VALID_MULTIPLE_INPUTS: ClassVar[tuple[str, PipeParallelBlueprint]] = (
        "valid_multiple_inputs",
        PipeParallelBlueprint(
            description="Test case: valid_multiple_inputs",
            inputs={"text_data": "native.Text", "image_data": "native.Image"},
            output="native.Text",
            parallels=[
                SubPipeBlueprint(pipe="process_text", result="text_result"),
                SubPipeBlueprint(pipe="process_image", result="image_result"),
            ],
            combined_output="native.Text",
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeParallelBlueprint]]] = [
        VALID_WITH_ADD_EACH_OUTPUT,
        VALID_WITH_COMBINED_OUTPUT,
        VALID_WITH_BOTH_OUTPUT_OPTIONS,
        VALID_THREE_PARALLELS,
        VALID_MULTIPLE_INPUTS,
    ]

    # Error test cases: (test_id, blueprint_dict, expected_error_message_fragment)
    # Using dicts instead of blueprints to avoid validation errors during import
    ERROR_NO_OUTPUT_OPTIONS: ClassVar[tuple[str, dict[str, Any], str]] = (
        "no_output_options",
        {
            "description": "Test case: no_output_options",
            "inputs": {"data": "native.Text"},
            "output": "native.Text",
            "parallels": [
                {"pipe": "process_a", "result": "result_a"},
                {"pipe": "process_b", "result": "result_b"},
            ],
            "add_each_output": False,
            "combined_output": None,
        },
        "requires either add_each_output to be True or combined_output to be set",
    )

    ERROR_CASES: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        ERROR_NO_OUTPUT_OPTIONS,
    ]
