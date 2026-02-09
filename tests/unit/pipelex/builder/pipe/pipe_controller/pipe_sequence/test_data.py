from typing import ClassVar

from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class PipeSequenceTestCases:
    SIMPLE_SEQUENCE = (
        "simple_sequence",
        PipeSequenceSpec(
            pipe_code="sequence_processor",
            description="A sequence of operations",
            inputs={"input_data": "Text"},
            output="ProcessedData",
            steps=[
                SubPipeSpec(pipe_code="step1", result="result1"),
                SubPipeSpec(pipe_code="step2", result="result2"),
                SubPipeSpec(pipe_code="step3", result="final_result"),
            ],
        ),
        PipeSequenceBlueprint(
            description="A sequence of operations",
            inputs={"input_data": "Text"},
            output="ProcessedData",
            steps=[
                SubPipeBlueprint(pipe="step1", result="result1"),
                SubPipeBlueprint(pipe="step2", result="result2"),
                SubPipeBlueprint(pipe="step3", result="final_result"),
            ],
        ),
    )

    SEQUENCE_WITH_BATCH_STEP = (
        "sequence_with_batch_step",
        PipeSequenceSpec(
            pipe_code="batch_sequence",
            description="A sequence with a batch step",
            inputs={"items": "Text[]"},
            output="Summary",
            steps=[
                SubPipeSpec(pipe_code="process_item", result="processed_items", batch_over="items", batch_as="item"),
                SubPipeSpec(pipe_code="summarize", result="summary"),
            ],
        ),
        PipeSequenceBlueprint(
            description="A sequence with a batch step",
            inputs={"items": "Text[]"},
            output="Summary",
            steps=[
                SubPipeBlueprint(pipe="process_item", result="processed_items", batch_over="items", batch_as="item"),
                SubPipeBlueprint(pipe="summarize", result="summary"),
            ],
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeSequenceSpec, PipeSequenceBlueprint]]] = [
        SIMPLE_SEQUENCE,
        SEQUENCE_WITH_BATCH_STEP,
    ]
