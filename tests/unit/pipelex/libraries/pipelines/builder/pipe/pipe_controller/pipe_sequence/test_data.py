from typing import ClassVar

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.libraries.pipelines.builder.pipe.sub_pipe_spec import SubPipeSpec
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
            inputs={"input_data": InputRequirementBlueprint(concept="Text")},
            output="ProcessedData",
            type="PipeSequence",
            category="PipeController",
            steps=[
                SubPipeBlueprint(pipe="step1", result="result1"),
                SubPipeBlueprint(pipe="step2", result="result2"),
                SubPipeBlueprint(pipe="step3", result="final_result"),
            ],
        ),
    )

    SEQUENCE_WITH_BATCH = (
        "sequence_with_batch",
        PipeSequenceSpec(
            pipe_code="batch_sequence",
            description="Sequence with batch",
            inputs={"items": "ItemList"},
            output="ProcessedItems",
            steps=[
                SubPipeSpec(pipe_code="prepare", result="prepared_items"),
                SubPipeSpec(
                    pipe_code="process_item",
                    result="processed_items",
                    batch_over="prepared_items",
                    batch_as="current_item",
                ),
            ],
        ),
        PipeSequenceBlueprint(
            description="Sequence with batch",
            inputs={"items": InputRequirementBlueprint(concept="ItemList")},
            output="ProcessedItems",
            type="PipeSequence",
            category="PipeController",
            steps=[
                SubPipeBlueprint(pipe="prepare", result="prepared_items"),
                SubPipeBlueprint(
                    pipe="process_item",
                    result="processed_items",
                    batch_over="prepared_items",
                    batch_as="current_item",
                ),
            ],
        ),
    )

    TEST_CASES: ClassVar[list[tuple[str, PipeSequenceSpec, PipeSequenceBlueprint]]] = [
        SIMPLE_SEQUENCE,
        SEQUENCE_WITH_BATCH,
    ]
