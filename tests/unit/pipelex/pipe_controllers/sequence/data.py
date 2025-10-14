from typing import Any, ClassVar

from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeSequenceInputTestCases:
    """Test cases for PipeSequence input validation."""

    # Valid test cases: (test_id, blueprint)
    VALID_SIMPLE_SEQUENCE: ClassVar[tuple[str, PipeSequenceBlueprint]] = (
        "valid_simple_sequence",
        PipeSequenceBlueprint(
            description="Test case: valid_simple_sequence",
            inputs={"text": "native.Text"},
            output="native.Text",
            steps=[
                SubPipeBlueprint(pipe="step_1", result="result_1"),
                SubPipeBlueprint(pipe="step_2", result="result_2"),
            ],
        ),
    )

    VALID_THREE_STEPS: ClassVar[tuple[str, PipeSequenceBlueprint]] = (
        "valid_three_steps",
        PipeSequenceBlueprint(
            description="Test case: valid_three_steps",
            inputs={"input_data": "native.Text"},
            output="native.Text",
            steps=[
                SubPipeBlueprint(pipe="process_step_1", result="processed_1"),
                SubPipeBlueprint(pipe="process_step_2", result="processed_2"),
                SubPipeBlueprint(pipe="process_step_3", result="final_output"),
            ],
        ),
    )

    VALID_SINGLE_STEP: ClassVar[tuple[str, PipeSequenceBlueprint]] = (
        "valid_single_step",
        PipeSequenceBlueprint(
            description="Test case: valid_single_step",
            inputs={"data": "native.Text"},
            output="native.Text",
            steps=[
                SubPipeBlueprint(pipe="single_process", result="output"),
            ],
        ),
    )

    VALID_MULTIPLE_INPUTS: ClassVar[tuple[str, PipeSequenceBlueprint]] = (
        "valid_multiple_inputs",
        PipeSequenceBlueprint(
            description="Test case: valid_multiple_inputs",
            inputs={"text_input": "native.Text", "image_input": "native.Image"},
            output="native.Text",
            steps=[
                SubPipeBlueprint(pipe="analyze_text", result="text_analysis"),
                SubPipeBlueprint(pipe="analyze_image", result="image_analysis"),
                SubPipeBlueprint(pipe="combine_results", result="final_result"),
            ],
        ),
    )

    VALID_WITH_BATCH: ClassVar[tuple[str, PipeSequenceBlueprint]] = (
        "valid_with_batch",
        PipeSequenceBlueprint(
            description="Test case: valid_with_batch",
            inputs={"items": "native.Text"},
            output="native.Text",
            steps=[
                SubPipeBlueprint(
                    pipe="process_item",
                    batch_over="items",
                    batch_as="item",
                    result="processed_items",
                ),
                SubPipeBlueprint(pipe="summarize_results", result="summary"),
            ],
        ),
    )

    VALID_CASES: ClassVar[list[tuple[str, PipeSequenceBlueprint]]] = [
        VALID_SIMPLE_SEQUENCE,
        VALID_THREE_STEPS,
        VALID_SINGLE_STEP,
        VALID_MULTIPLE_INPUTS,
        VALID_WITH_BATCH,
    ]

    # Error test cases: (test_id, blueprint_dict, expected_error_message_fragment)
    # Using dicts instead of blueprints to avoid validation errors during import
    ERROR_EMPTY_STEPS: ClassVar[tuple[str, dict[str, Any], str]] = (
        "empty_steps",
        {
            "description": "Test case: empty_steps",
            "inputs": {"text": "native.Text"},
            "output": "native.Text",
            "steps": [],
        },
        "must have at least 1 step",
    )

    ERROR_CASES: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        ERROR_EMPTY_STEPS,
    ]
