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
            output="native.Composite",
            branches=[
                SubPipeBlueprint(pipe="process_a", result="result_a"),
                SubPipeBlueprint(pipe="process_b", result="result_b"),
            ],
            add_each_output=True,
        ),
    )

    VALID_WITHOUT_ADD_EACH_OUTPUT: ClassVar[tuple[str, PipeParallelBlueprint]] = (
        "valid_without_add_each_output",
        PipeParallelBlueprint(
            description="Test case: valid_without_add_each_output",
            inputs={"data": "native.Text"},
            output="native.Composite",
            branches=[
                SubPipeBlueprint(pipe="analyze_1", result="analysis_1"),
                SubPipeBlueprint(pipe="analyze_2", result="analysis_2"),
            ],
        ),
    )

    VALID_THREE_PARALLELS: ClassVar[tuple[str, PipeParallelBlueprint]] = (
        "valid_three_branches",
        PipeParallelBlueprint(
            description="Test case: valid_three_parallels",
            inputs={"input_data": "native.Text"},
            output="native.Composite",
            branches=[
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
            output="native.Composite",
            branches=[
                SubPipeBlueprint(pipe="process_text", result="text_result"),
                SubPipeBlueprint(pipe="process_image", result="image_result"),
            ],
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeParallelBlueprint]]] = [
        VALID_WITH_ADD_EACH_OUTPUT,
        VALID_WITHOUT_ADD_EACH_OUTPUT,
        VALID_THREE_PARALLELS,
        VALID_MULTIPLE_INPUTS,
    ]

    # Error test cases: (test_id, blueprint_dict, expected_error_message_fragment)
    # Using dicts instead of blueprints to avoid validation errors during import
    ERROR_NATIVE_NON_COMPOSITE_OUTPUT: ClassVar[tuple[str, dict[str, Any], str]] = (
        "native_non_composite_output",
        {
            "description": "Test case: native_non_composite_output",
            "inputs": {"data": "native.Text"},
            "output": "native.Text",
            "branches": [
                {"pipe": "process_a", "result": "result_a"},
                {"pipe": "process_b", "result": "result_b"},
            ],
            "add_each_output": True,
        },
        "must be 'Composite' or a structured concept",
    )

    ERROR_MULTIPLICITY_OUTPUT: ClassVar[tuple[str, dict[str, Any], str]] = (
        "multiplicity_output",
        {
            "description": "Test case: multiplicity_output",
            "inputs": {"data": "native.Text"},
            "output": "native.Composite[]",
            "branches": [
                {"pipe": "process_a", "result": "result_a"},
                {"pipe": "process_b", "result": "result_b"},
            ],
            "add_each_output": True,
        },
        "must not declare a multiplicity",
    )

    ERROR_CASES: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        ERROR_NATIVE_NON_COMPOSITE_OUTPUT,
        ERROR_MULTIPLICITY_OUTPUT,
    ]
