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
            type="PipeSequence",
            pipe_category="PipeController",
            steps=[
                SubPipeBlueprint(pipe="step1", result="result1"),
                SubPipeBlueprint(pipe="step2", result="result2"),
                SubPipeBlueprint(pipe="step3", result="final_result"),
            ],
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeSequenceSpec, PipeSequenceBlueprint]]] = [
        SIMPLE_SEQUENCE,
    ]
